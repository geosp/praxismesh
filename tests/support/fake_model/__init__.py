"""Deterministic fake model endpoint (RFC Phase 1: Deterministic fake model).

An OpenAI-compatible `/v1/chat/completions` server. The reply is chosen from the
request's message history, not from server state: step N of the script answers a
request whose history holds N tool results. Any worker that resends the same
history therefore gets the same next step, which is what lets the recovery check
show that a conversation survived a lost worker.

Script steps (JSON): {"tool": name, "args": {...}}, {"tools": [{"tool": ..., "args":
...}, ...]} for several calls in one response, or {"text": "..."}; any step
may add "pause": true, which holds that response until `POST /control/release`.
A pause is one-shot: once released, or once the same step is requested again,
it is not applied again.

    from tests.support.fake_model import FakeModel
    with FakeModel(script) as fake: base_url = fake.base_url

    python -m tests.support.fake_model --script script.json --port 8765
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any

Step = dict[str, Any]


def tool_results(messages: list[dict[str, Any]]) -> int:
    """The number of model responses that called tools (several calls in one
    response count once), which is the script step to answer next."""
    return sum(1 for m in messages if m.get("role") == "assistant" and m.get("tool_calls"))


class FakeModelState:
    def __init__(self, script: list[Step]) -> None:
        self.script = script
        self.requests: list[dict[str, Any]] = []
        self.served: list[int] = []
        self.paused_step: int | None = None
        self.pauses_done: set[int] = set()
        self.release = threading.Event()
        self.lock = threading.Lock()

    def reply(self, body: dict[str, Any]) -> dict[str, Any]:
        messages = body.get("messages", [])
        index = min(tool_results(messages), len(self.script) - 1)
        step = self.script[index]
        with self.lock:
            self.requests.append(body)
            self.served.append(index)
            pause = bool(step.get("pause")) and index not in self.pauses_done
            if pause:
                self.pauses_done.add(index)
                self.paused_step = index
                self.release.clear()
        if pause:
            self.release.wait(timeout=600)
            with self.lock:
                self.paused_step = None
        calls = step.get("tools") or ([step] if "tool" in step else [])
        if calls:
            message: dict[str, Any] = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{index}_{n}_{len(self.requests)}",
                        "type": "function",
                        "function": {"name": c["tool"], "arguments": json.dumps(c["args"])},
                    }
                    for n, c in enumerate(calls)
                ],
            }
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": step.get("text", "done")}
            finish = "stop"
        return {
            "id": f"fake-{len(self.requests)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "fake"),
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        }


def _handler(state: FakeModelState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # quiet
            pass

        def _send(self, payload: Any, status: int = 200) -> None:
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/v1/models":
                self._send({"object": "list", "data": [{"id": "fake", "object": "model"}]})
            elif self.path == "/control/state":
                with state.lock:
                    self._send(
                        {
                            "served": state.served,
                            "paused_step": state.paused_step,
                            "requests": len(state.requests),
                        }
                    )
            else:
                self._send({"error": "not found"}, 404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/v1/chat/completions":
                # The caller may have gone away while the response was held.
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self._send(state.reply(body))
            elif self.path == "/control/release":
                state.release.set()
                self._send({"released": True})
            else:
                self._send({"error": "not found"}, 404)

    return Handler


class FakeModel:
    """Run the fake model in a background thread."""

    def __init__(self, script: list[Step], host: str = "127.0.0.1", port: int = 0) -> None:
        self.state = FakeModelState(script)
        self.server = ThreadingHTTPServer((host, port), _handler(self.state))
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host!s}:{port}"

    def __enter__(self) -> FakeModel:
        self.thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.state.release.set()
        self.server.shutdown()
        self.server.server_close()

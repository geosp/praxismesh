"""Independent model and tool observations for the interruption experiments."""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
from pathlib import Path

from model_gateway import Boundary
from recovery_store import Authority, Superseded

TOOL_NAMES = {"mcp__recovery__" + name for name in ("write_note", "read_note", "effect_once")}


def tool_call(name: str, step: int) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"recovery-call-{step}",
                "type": "function",
                "function": {"name": "mcp__recovery__" + name, "arguments": "{}"},
            }
        ],
    }


class RecoveryModel(Boundary):
    def __init__(self, path: Path, stage: str, marker: str):
        self.stage = stage
        self.marker = marker
        self.barrier = threading.Event()
        self.release = threading.Event()
        self.conversation_restored = False
        super().__init__(path, "recovery", allowed_tools=TOOL_NAMES)

    def answer(self, request: dict) -> dict:
        if self.stage == "checkpoint":
            if self.calls == 1:
                return tool_call("write_note", self.calls)
            self.conversation_restored = self.marker in json.dumps(request["messages"])
            self.barrier.set()
            self.release.wait(60)
            return {"role": "assistant", "content": "checkpoint observer released"}
        if self.calls == 1:
            self.conversation_restored = self.marker in json.dumps(request["messages"])
            return tool_call("read_note", self.calls)
        if self.calls == 2:
            return tool_call("effect_once", self.calls)
        return {"role": "assistant", "content": "recovery fixture complete"}

    def close(self):
        self.release.set()
        super().close()


class ToolExecutor:
    def __init__(
        self,
        state: Path,
        authority: Authority,
        attempt: int,
        marker: str,
        *,
        hold_effect: bool = False,
    ):
        self.entries: list[dict] = []
        self.effect_committed = threading.Event()
        self.release = threading.Event()
        self.threads: set[threading.Thread] = set()
        self.lock = threading.Lock()
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/tool":
                    self.send_error(403)
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size < 4096:
                    self.send_error(400)
                    return
                params = json.loads(self.rfile.read(size))
                name = params.get("name")
                admitted = name in {"write_note", "read_note", "effect_once"} and not params.get(
                    "arguments"
                )
                entry = {
                    "sequence": len(owner.entries) + 1,
                    "attempt": attempt,
                    "tool": name,
                    "admitted": admitted,
                }
                owner.entries.append(entry)
                status = 200
                try:
                    if not admitted:
                        raise ValueError("refused tool")
                    # Check ownership even for workspace operations. The endpoint
                    # binds attempt identity; caller cannot choose a newer attempt.
                    with authority.connect() as db:
                        authority.require_owner(db, attempt)
                    note = state / "workspace/recovery-note.txt"
                    if name == "write_note":
                        note.write_text(marker)
                        body = {"note": marker}
                    elif name == "read_note":
                        body = {"note": note.read_text()}
                        entry["restored_note_matches"] = body["note"] == marker
                    else:
                        body = authority.effect(attempt, "recovery-effect-1")
                        owner.effect_committed.set()
                        if hold_effect:
                            owner.release.wait(60)
                        # A tool that finishes after supersession must not return
                        # an authoritative success to the stale bridge.
                        with authority.connect() as db:
                            authority.require_owner(db, attempt)
                    entry["outcome"] = "success"
                except (Superseded, ValueError, OSError) as error:
                    status = 409
                    entry["outcome"] = type(error).__name__
                    body = {"error": type(error).__name__}
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(body).encode())
                    entry["result_delivery"] = "sent"
                except (BrokenPipeError, ConnectionResetError):
                    entry["result_delivery"] = "worker disconnected"

            def log_message(self, *args):
                pass

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

            def process_request(self, request, client_address):
                thread = threading.Thread(
                    target=self.process_request_thread, args=(request, client_address), daemon=True
                )
                with owner.lock:
                    owner.threads.add(thread)
                thread.start()

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    with owner.lock:
                        owner.threads.discard(threading.current_thread())

        path = state / "ipc/tools.sock"
        self.server = Server(str(path), Handler)
        path.chmod(0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def owned_work_alive(self):
        with self.lock:
            return self.thread.is_alive() or bool(self.threads)

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        with self.lock:
            threads = list(self.threads)
        for thread in threads:
            thread.join(timeout=2)
        if self.thread.is_alive() or any(t.is_alive() for t in threads):
            raise RuntimeError("fixture executor survived teardown")

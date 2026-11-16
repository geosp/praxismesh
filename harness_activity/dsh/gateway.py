"""Worker-side model gateway for one DSH attempt (DSH migration plan D2, D6, R11, R14, R16).

The DSH process has no network and no credentials. Its model provider reaches
only this gateway, through a Unix socket in the attempt tree. For every request
the gateway:

- checks the per-attempt key, the model and the exact granted tool catalog (R14);
- runs the barrier before every request after the first one (D6);
- admits the request through the usage ledger, which writes a durable row before
  dispatch and settles it on the response (R11, D9);
- forwards it to the template's model endpoint with the worker's credentials;
- emits a `token` event with the response's counts, never its text (R16).

DSH sees its tools as `mcp__praxis__<name>`; the model sees the bare names, as it
does with `openai_agents`. The gateway asks the endpoint for a complete response
and replays it to DSH as a stream, so usage is always part of what it settles.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from common.observability.metrics import TOOL_ERRORS
from harness_activity.dsh.composition import TOOL_PREFIX
from harness_activity.dsh.ledger import Dispatch, UsageLedger
from harness_activity.events import AttemptEvents
from harness_activity.runner import StopRun, Superseded, Usage

log = logging.getLogger("praxis.harness")
MAX_BODY = 8 * 1024 * 1024
UPSTREAM_TIMEOUT_S = 600.0

Reply = tuple[int, str, bytes]
Route = Callable[[dict[str, str], bytes], Awaitable[Reply]]


def json_reply(status: int, body: dict[str, Any]) -> Reply:
    return status, "application/json", json.dumps(body).encode()


def error_reply(status: int, message: str) -> Reply:
    return json_reply(status, {"error": {"message": message, "type": "praxis_gateway"}})


class SocketServer:
    """A minimal HTTP/1.1 server on a Unix socket: one request per connection."""

    def __init__(self, path: Path, routes: dict[tuple[str, str], Route]) -> None:
        self.path, self.routes = path, routes
        self.server: asyncio.Server | None = None
        self.tasks: set[asyncio.Task[None]] = set()

    async def start(self, gid: int | None = None) -> None:
        self.path.unlink(missing_ok=True)
        self.server = await asyncio.start_unix_server(self._serve, str(self.path), limit=2**20)
        if gid is not None:
            os.chown(self.path, -1, gid)
        os.chmod(self.path, 0o660)

    async def close(self) -> None:
        if self.server is not None:
            self.server.close()
        for task in list(self.tasks):
            task.cancel()
        for task in list(self.tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self.path.unlink(missing_ok=True)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self.tasks.add(task)
        try:
            reply = await self._handle(reader)
            status, content_type, body = reply
            head = (
                f"HTTP/1.1 {status} {'OK' if status == 200 else 'Error'}\r\n"
                f"Content-Type: {content_type}\r\nContent-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write(head.encode() + body)
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass  # the caller went away
        finally:
            self.tasks.discard(task)
            writer.close()

    async def _handle(self, reader: asyncio.StreamReader) -> Reply:
        head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
        parts = head[0].split(" ")
        if len(parts) < 2:
            return error_reply(400, "bad request")
        headers = {
            name.strip().lower(): value.strip()
            for name, _, value in (line.partition(":") for line in head[1:] if line)
        }
        try:
            size = int(headers.get("content-length", "0"))
        except ValueError:
            return error_reply(400, "bad request")
        if not 0 <= size <= MAX_BODY:
            return error_reply(413, "request too large")
        body = await reader.readexactly(size)
        route = self.routes.get((parts[0], parts[1]))
        if route is None:
            return error_reply(403, "path not allowed")
        return await route(headers, body)


def to_model(request: dict[str, Any]) -> dict[str, Any]:
    """The request the endpoint gets: bare tool names, one complete response."""
    out = copy.deepcopy(request)
    out["stream"] = False
    out.pop("stream_options", None)

    def strip(function: Any) -> None:
        if isinstance(function, dict) and str(function.get("name", "")).startswith(TOOL_PREFIX):
            function["name"] = function["name"][len(TOOL_PREFIX) :]

    for tool in out.get("tools", []):
        strip(tool.get("function"))
    for message in out.get("messages", []):
        if isinstance(message, dict):
            for call in message.get("tool_calls") or []:
                strip(call.get("function"))
    choice = out.get("tool_choice")
    if isinstance(choice, dict):
        strip(choice.get("function"))
    return out


def as_stream(response: dict[str, Any]) -> bytes:
    """Replay a complete chat completion as the chunks DSH's provider expects."""
    choice = (response.get("choices") or [{}])[0]
    message = dict(choice.get("message") or {"role": "assistant", "content": ""})
    if message.get("tool_calls"):
        message["tool_calls"] = [dict(c, index=i) for i, c in enumerate(message["tool_calls"])]
    base = {
        "id": response.get("id", "chatcmpl-praxis"),
        "object": "chat.completion.chunk",
        "created": response.get("created", 0),
        "model": response.get("model", ""),
    }
    chunks: list[dict[str, Any]] = [
        {"choices": [{"index": 0, "delta": message, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": choice.get("finish_reason")}]},
        {"choices": [], "usage": response.get("usage")},
    ]
    lines = [b"data: " + json.dumps({**base, **chunk}).encode() + b"\n\n" for chunk in chunks]
    return b"".join(lines) + b"data: [DONE]\n\n"


class Gateway:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        attempt_key: str,
        granted: set[str],
        ledger: UsageLedger,
        usage: Usage,
        template_ref: str,
        finished: Callable[[], bool],
        on_response: Callable[[], None],
        refused: list[str],
        barrier: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        events: AttemptEvents | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model, self.base_url, self.api_key = model, base_url, api_key
        self.attempt_key, self.granted, self.ledger, self.usage = (
            attempt_key,
            granted,
            ledger,
            usage,
        )
        self.template_ref, self.finished, self.on_response = template_ref, finished, on_response
        self.refused, self.barrier, self.events = refused, barrier, events
        self.client = client or httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_S)
        self.offered = {TOOL_PREFIX + name for name in granted}
        self.logical: dict[str, int] = {}
        self.dispatched = 0
        # What the runner classifies when the run ends (policy.classify).
        self.fault: str | None = None
        self.error_type: str | None = None
        self.blocked = False
        self.stop_summary: str | None = None
        # Set when the attempt must be stopped now instead of ending by itself.
        self.abort = asyncio.Event()

    def routes(self) -> dict[tuple[str, str], Route]:
        return {
            ("POST", "/v1/chat/completions"): self.completions,
            ("GET", "/v1/models"): self.models,
        }

    def _authorized(self, headers: dict[str, str]) -> bool:
        return headers.get("authorization", "") == f"Bearer {self.attempt_key}"

    async def models(self, headers: dict[str, str], body: bytes) -> Reply:
        if not self._authorized(headers):
            return error_reply(403, "not this attempt")
        return json_reply(200, {"object": "list", "data": [{"id": self.model, "object": "model"}]})

    async def completions(self, headers: dict[str, str], body: bytes) -> Reply:
        if not self._authorized(headers):
            return error_reply(403, "not this attempt")
        try:
            request = json.loads(body)
            names = {t["function"]["name"] for t in request.get("tools", [])}
        except (ValueError, KeyError, TypeError):
            return error_reply(400, "bad request")
        if names != self.offered or request.get("model") != self.model:
            # The runtime offers something the template did not grant (R14).
            self.blocked = True
            self.abort.set()
            log.error("DSH model or tool grants changed; request refused")
            return error_reply(403, "effective model or tool grants changed")
        step = self.logical.setdefault(hashlib.sha256(body).hexdigest(), len(self.logical) + 1)
        deny = "explicit completion" if self.finished() else None
        if deny is None and self.dispatched and self.barrier is not None:
            deny = await self._barrier(request)
        record = await self.ledger.admit("main", step, deny=deny)
        if not record.dispatched:
            return error_reply(429, f"request not admitted: {record.denial}")
        self.dispatched += 1
        self.usage.inner_turns = self.ledger.settled()["logical_steps"]
        return await self._forward(request, record)

    async def _barrier(self, request: dict[str, Any]) -> str | None:
        assert self.barrier is not None
        try:
            await self.barrier(request)
        except StopRun as stop:
            self.stop_summary = str(stop)
            return "token budget"
        except Superseded:
            self.error_type = "Superseded"
            self.abort.set()
            return "superseded"
        except Exception as error:
            log.warning(
                "checkpoint barrier failed",
                extra={"fields": {"error": type(error).__name__, "detail": str(error)[:200]}},
            )
            self.fault = "checkpoint barrier failed"
            return self.fault
        return None

    async def _forward(self, request: dict[str, Any], record: Dispatch) -> Reply:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions", json=to_model(request), headers=headers
            )
        except httpx.HTTPError as error:
            # Whether the endpoint generated anything is unknown: the row stays
            # unsettled and the next attempt charges it conservatively (D9).
            self.fault = "provider transport failure"
            log.warning("model endpoint failed", extra={"fields": {"error": type(error).__name__}})
            return error_reply(502, "model endpoint transport failure")
        if 400 <= response.status_code < 500:
            # Rejected before generation: nothing was used.
            await self.ledger.settle(record, None, known_zero=True)
            self.fault = (
                "provider rejected input" if response.status_code == 400 else "provider failure"
            )
            return error_reply(response.status_code, "the model endpoint rejected the request")
        if response.status_code != 200:
            self.fault = "provider failure"
            return error_reply(502, "the model endpoint failed")
        try:
            completion = response.json()
            usage = completion.get("usage")
            await self.ledger.settle(record, usage)
            message = completion["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            self.fault = "provider protocol failure"
            return error_reply(502, "the model endpoint returned an invalid response")
        if not record.settled:
            self.fault = "provider returned no usage"
            return error_reply(502, "the model endpoint returned no usage")
        self.usage.tokens_in += record.input_tokens or 0
        self.usage.tokens_out += record.output_tokens or 0
        if self.events is not None:
            self.events.emit(
                "token",
                request_id=record.request_id,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
            )
        self.on_response()
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            name = str(function.get("name"))
            if name in self.granted:
                function["name"] = TOOL_PREFIX + name
            else:
                # DSH has no such tool and returns the error to the model.
                self.refused.append(name)
                TOOL_ERRORS.labels(template=self.template_ref, tool=name).inc()
                log.warning("refused tool call", extra={"fields": {"tool": name}})
        if request.get("stream"):
            return 200, "text/event-stream", as_stream(completion)
        return json_reply(200, completion)

    async def close(self) -> None:
        await self.client.aclose()

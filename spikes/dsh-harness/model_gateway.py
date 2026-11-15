"""Trusted host-side model boundary and container-local loopback relay.

The candidate has no IP network. Its relay can reach only this Unix socket;
this server accepts fixed model paths and never accepts a caller-selected URL.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.client
import http.server
import json
import socket
import socketserver
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

MAX_BODY = 2 * 1024 * 1024
MODEL_PATHS = {"/v1/chat/completions", "/v1/models"}
ALLOWED_TOOLS = {"skill", "mcp__sample-shop__lookup_price", "mcp__sample-shop__lookup_stock"}


def serve_relay(socket_path: str) -> http.server.ThreadingHTTPServer:
    class Relay(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.forward()

        def do_GET(self) -> None:
            self.forward()

        def forward(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            if self.path not in MODEL_PATHS or not 0 <= size <= MAX_BODY:
                self.send_error(403)
                return
            connection = http.client.HTTPConnection("fixture", timeout=110)
            connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.sock.settimeout(110)
            connection.sock.connect(socket_path)
            try:
                connection.request(
                    self.command,
                    self.path,
                    self.rfile.read(size),
                    {"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                self.send_response(response.status)
                self.send_header(
                    "Content-Type", response.getheader("Content-Type", "application/json")
                )
                self.end_headers()
                while data := response.read(8192):
                    self.wfile.write(data)
                    self.wfile.flush()
            finally:
                connection.close()

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 8080), Relay)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Boundary:
    def __init__(
        self,
        path: Path,
        case: str,
        upstream: str | None = None,
        api_key: str = "",
        *,
        allowed_tools: set[str] | None = None,
    ):
        self.case = case
        self.upstream = upstream
        self.api_key = api_key
        self.allowed_tools = ALLOWED_TOOLS if allowed_tools is None else frozenset(allowed_tools)
        self.requests: list[dict] = []
        self.calls = 0
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.handlers: set[threading.Thread] = set()
        self.sockets: set[socket.socket] = set()
        self.connections: set[http.client.HTTPConnection] = set()
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path != "/v1/models":
                    self.send_error(403)
                    return
                self.reply({"object": "list", "data": [{"id": "spark", "object": "model"}]})

            def do_POST(self) -> None:
                size = int(self.headers.get("Content-Length", "0"))
                if self.path != "/v1/chat/completions" or not 0 < size <= MAX_BODY:
                    self.send_error(403)
                    return
                body = self.rfile.read(size)
                request = json.loads(body)
                names = [t["function"]["name"] for t in request.get("tools", [])]
                with owner.lock:
                    owner.calls += 1
                    record = {
                        "sequence": owner.calls,
                        "path": self.path,
                        "request_hash": hashlib.sha256(body).hexdigest(),
                        "tools": names,
                        "model": request.get("model"),
                        "poison_visible": b"poison-spike-skill" in body,
                        "native_input_visible": b"/permission danger-full-access" in body,
                        "skill_body_seen": b"# Order desk" in body,
                        "denial_seen": any(
                            any(
                                term in str(m.get("content", "")).lower()
                                for term in (
                                    "unknown_tool",
                                    "unknown tool",
                                    "not registered",
                                    "refused",
                                )
                            )
                            for m in request.get("messages", [])
                            if m.get("role") == "tool"
                        ),
                    }
                    owner.requests.append(record)
                if set(names) != owner.allowed_tools or request.get("model") != "spark":
                    self.send_error(403, "effective model/tool grants changed")
                    return
                if len(owner.requests) > 8:
                    self.send_error(429, "probe request allowance exhausted")
                    return
                if not owner.admit(request, record):
                    self.send_error(429, "trusted probe admission refused")
                    return
                if owner.upstream is not None:
                    if request.get("model") != "spark":
                        self.send_error(403)
                        return
                    owner.forward(self, body, record)
                    return
                message = owner.answer(request)
                if owner.stopping.is_set():
                    return
                usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
                if request.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    delta = dict(message)
                    if "tool_calls" in delta:
                        delta["tool_calls"] = [
                            dict(t, index=i) for i, t in enumerate(delta["tool_calls"])
                        ]
                    chunks = [
                        {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                        {
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "tool_calls"
                                    if "tool_calls" in message
                                    else "stop",
                                }
                            ]
                        },
                        {"choices": [], "usage": usage},
                    ]
                    for chunk in chunks:
                        chunk.update(
                            id="chatcmpl-spike",
                            object="chat.completion.chunk",
                            created=0,
                            model="spark",
                        )
                        self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                    self.wfile.write(b"data: [DONE]\n\n")
                else:
                    self.reply(
                        {
                            "id": "chatcmpl-spike",
                            "object": "chat.completion",
                            "created": 0,
                            "model": "spark",
                            "choices": [
                                {
                                    "index": 0,
                                    "message": message,
                                    "finish_reason": "tool_calls"
                                    if "tool_calls" in message
                                    else "stop",
                                }
                            ],
                            "usage": usage,
                        }
                    )

            def reply(self, body: dict) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def log_message(self, *args: object) -> None:
                pass

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

            def process_request(self, request, client_address):
                thread = threading.Thread(
                    target=self.process_request_thread, args=(request, client_address), daemon=True
                )
                with owner.lock:
                    owner.sockets.add(request)
                    owner.handlers.add(thread)
                thread.start()

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    with owner.lock:
                        owner.sockets.discard(request)
                        owner.handlers.discard(threading.current_thread())

        self.server = Server(str(path), Handler)
        path.chmod(0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        deadline = time.monotonic() + 2
        while True:
            with self.lock:
                sockets = list(self.sockets) + [c.sock for c in self.connections if c.sock]
                handlers = list(self.handlers)
            for stream in sockets:
                with contextlib.suppress(OSError):
                    stream.shutdown(socket.SHUT_RDWR)
                stream.close()
            if not handlers or time.monotonic() >= deadline:
                break
            for thread in handlers:
                thread.join(timeout=0.02)

    def owned_work_alive(self) -> bool:
        with self.lock:
            return self.thread.is_alive() or bool(self.handlers or self.connections or self.sockets)

    def admit(self, request: dict, record: dict) -> bool:
        return True

    def forward(
        self, handler: http.server.BaseHTTPRequestHandler, body: bytes, record: dict
    ) -> None:
        target = urlsplit(self.upstream)
        prefix = target.path.rstrip("/")
        if not prefix.endswith("/v1"):
            prefix += "/v1"
        cls = (
            http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
        )
        connection = cls(target.hostname, target.port, timeout=1)
        with self.lock:
            self.connections.add(connection)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        try:
            if self.stopping.is_set():
                return
            connection.connect()
            if self.stopping.is_set():
                return
            connection.sock.settimeout(100)
            connection.request("POST", prefix + "/chat/completions", body, headers)
            response = connection.getresponse()
            record["provider_status"] = response.status
            if response.status != 200:
                handler.send_error(502, "configured local provider rejected request")
                return
            handler.send_response(200)
            handler.send_header(
                "Content-Type", response.getheader("Content-Type", "application/json")
            )
            handler.end_headers()
            observed = bytearray()
            while chunk := response.read(8192):
                observed.extend(chunk)
                if len(observed) > MAX_BODY:
                    raise ValueError("provider response exceeded probe limit")
                handler.wfile.write(chunk)
                handler.wfile.flush()
            usage = None
            for line in observed.decode(errors="replace").splitlines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    item = json.loads(line[6:])
                    if item.get("usage"):
                        usage = item["usage"]
            record["provider_usage"] = usage
        except Exception as error:
            record["provider_error_type"] = type(error).__name__
            # No remote exception body, URL or credential enters experiment output.
            if not self.stopping.is_set():
                with contextlib.suppress(OSError):
                    handler.send_error(502, "local provider transport failed")
        finally:
            connection.close()
            with self.lock:
                self.connections.discard(connection)

    def answer(self, request: dict) -> dict:
        names = {t["function"]["name"]: t["function"] for t in request.get("tools", [])}
        step = self.calls
        tool = None
        arguments = {}
        if self.case in ("capability", "poison"):
            if step == 1:
                tool = "skill"
                props = names[tool]["parameters"]["properties"]
                key = next(k for k in props if k in ("name", "skill", "skill_name"))
                arguments = {key: "order-desk"}
            elif step == 2:
                tool = "mcp__sample-shop__lookup_price"
                arguments = {"sku": "SKU-1"}
            elif step == 3:
                tool = "mcp__sample-shop__lookup_stock"
                arguments = {"sku": "SKU-1"}
            elif step == 4 and self.case == "poison":
                tool = "poison_plugin_tool"
        elif self.case in ("denied-tool", "native-text") and step == 1:
            tool = "mcp__sample-shop__admin_reset"
        if tool:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{step}",
                        "type": "function",
                        "function": {"name": tool, "arguments": json.dumps(arguments)},
                    }
                ],
            }
        return {"role": "assistant", "content": json.dumps({"unit_price": 12.5, "stock": 3})}

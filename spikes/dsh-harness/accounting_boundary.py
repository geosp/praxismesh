"""Host accounting gateway and independently counted deterministic HTTP provider."""

from __future__ import annotations

import hashlib
import http.client
import http.server
import json
import threading

from model_gateway import MAX_BODY, Boundary
from recovery_boundary import TOOL_NAMES, tool_call
from usage_ledger import UsageLedger


class FixtureProvider:
    def __init__(self, case: str, responder=None):
        self.case = case
        self.stage = "setup" if case == "auxiliary" else "main"
        self.dispatches: list[dict] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.responder = responder
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                size = int(self.headers.get("Content-Length", "0"))
                if self.path != "/v1/chat/completions" or not 0 < size <= MAX_BODY:
                    self.send_error(403)
                    return
                request = json.loads(self.rfile.read(size))
                number = len(owner.dispatches) + 1
                record = {
                    "sequence": number,
                    "stage": owner.stage,
                    "request_hash": hashlib.sha256(
                        json.dumps(request, sort_keys=True).encode()
                    ).hexdigest(),
                }
                owner.dispatches.append(record)
                if owner.case in ("stall-model", "cancel-model"):
                    record.update(
                        disposition="known stalled before generation",
                        input_tokens=0,
                        output_tokens=0,
                    )
                    owner.entered.set()
                    owner.release.wait(60)
                    record["disposition"] = "known interrupted before generation"
                    return
                owner.entered.set()
                scripted = owner.responder(request, number) if owner.responder is not None else None
                if scripted is not None and scripted.get("fault"):
                    fault = scripted["fault"]
                    record.update(disposition=fault, input_tokens=0, output_tokens=0)
                    if fault == "fixture disconnect before generation":
                        return
                    status = {
                        "fixture rejected input": 400,
                        "fixture unavailable before generation": 503,
                        "fixture malformed stream before generation": 200,
                    }[fault]
                    self.send_response(status)
                    self.send_header(
                        "Content-Type", "text/event-stream" if status == 200 else "application/json"
                    )
                    self.end_headers()
                    self.wfile.write(
                        b"data: malformed-fixture-json\n\n"
                        if status == 200
                        else b'{"error":{"message":"controlled fixture failure"}}'
                    )
                    return
                if owner.case == "retry" and number == 1:
                    record.update(
                        disposition="known pre-generation failure", input_tokens=0, output_tokens=0
                    )
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        b'{"error":{"message":"fixture pre-generation failure",'
                        b'"type":"server_error"}}'
                    )
                    return
                usage = {
                    "prompt_tokens": 4 if owner.stage == "compaction" else 7,
                    "completion_tokens": 6 if owner.stage == "compaction" else 3,
                }
                if scripted is not None:
                    message = scripted["message"]
                elif owner.stage == "setup":
                    message = {
                        "role": "assistant",
                        "content": "fixture historical sentence. " * 1000,
                    }
                elif owner.stage == "compaction":
                    message = {"role": "assistant", "content": "Fixture history summary."}
                elif owner.case == "tools":
                    sequence = ("read_note", "write_note", "read_note", "effect_once", "forbidden")
                    message = (
                        tool_call(sequence[number - 1], number)
                        if number <= len(sequence)
                        else {"role": "assistant", "content": "Fixture tool checks complete."}
                    )
                elif owner.case in ("stall-tool", "cancel-tool"):
                    message = tool_call("effect_once", number)
                else:
                    message = tool_call("write_note", number)
                record.update(
                    disposition="success",
                    input_tokens=usage["prompt_tokens"],
                    output_tokens=usage["completion_tokens"],
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                delta = dict(message)
                if "tool_calls" in delta:
                    delta["tool_calls"] = [
                        dict(t, index=i) for i, t in enumerate(delta["tool_calls"])
                    ]
                for item in (
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
                ):
                    item.update(
                        id=f"fixture-{number}",
                        object="chat.completion.chunk",
                        created=0,
                        model="spark",
                    )
                    self.wfile.write(b"data: " + json.dumps(item).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n")

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.release.set()
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.server_close()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)

    def owned_work_alive(self):
        return self.thread.is_alive()


class AccountingBoundary(Boundary):
    def __init__(self, path, run: str, provider: FixtureProvider, budget: int, steps: int = 8):
        self.provider = provider
        self.ledger = UsageLedger(run, "controls", 1, budget, steps)
        self.setup_ledger = None
        self.logical: dict[str, int] = {}
        self.denied = threading.Event()
        super().__init__(path, "accounting", upstream="fixture-only", allowed_tools=TOOL_NAMES)

    def begin_auxiliary(self, run: str):
        # Controller-only once, between completed setup turns and native /compact.
        if self.setup_ledger is not None or self.ledger.totals()["unknown_usage"]:
            raise ValueError("auxiliary stage not at settled setup boundary")
        self.setup_ledger = self.ledger
        self.ledger = UsageLedger(run, "controls", 1, 10)
        self.logical = {}
        self.provider.stage = "compaction"

    def close(self):
        try:
            super().close()
        finally:
            self.provider.close()

    def owned_work_alive(self):
        return super().owned_work_alive() or self.provider.owned_work_alive()

    def admit(self, request: dict, record: dict) -> bool:
        digest = record["request_hash"]
        step = self.logical.setdefault(digest, len(self.logical) + 1)
        purpose = self.provider.stage
        if (
            self.ledger.records
            and self.ledger.records[-1]["disposition"] == "pre-generation failure"
        ):
            purpose = "retry"
        observation = self.ledger.ingress(purpose, step)
        record["accounting"] = observation
        if not observation["dispatched"]:
            self.denied.set()
        return observation["dispatched"]

    def forward(self, handler, body: bytes, record: dict):
        # Buffer a bounded provider response to settle usage before releasing it
        # to DSH. This avoids an admission race at the next model step.
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.provider.server.server_port, timeout=5
        )
        with self.lock:
            self.connections.add(connection)
        try:
            connection.request(
                "POST", "/v1/chat/completions", body, {"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            encoded = response.read(MAX_BODY + 1)
            if len(encoded) > MAX_BODY:
                raise ValueError("provider fixture exceeded response bound")
            record["provider_status"] = response.status
            if response.status == 503:
                # This capability applies ONLY to this controller-owned provider,
                # whose independent dispatch record proves pre-generation failure.
                last = self.provider.dispatches[-1]
                if last["disposition"] != "known pre-generation failure":
                    raise ValueError("unproven zero-usage failure")
                self.ledger.settle(record["accounting"], None, known_pre_generation=True)
            elif response.status == 200:
                usage = None
                for line in encoded.splitlines():
                    if line.startswith(b"data: ") and line[6:] != b"[DONE]":
                        item = json.loads(line[6:])
                        if item.get("usage") is not None:
                            usage = item["usage"]
                self.ledger.settle(record["accounting"], usage)
                record["provider_usage"] = usage
            handler.send_response(response.status)
            handler.send_header("Content-Type", response.getheader("Content-Type"))
            handler.end_headers()
            handler.wfile.write(encoded)
        except (OSError, http.client.HTTPException) as error:
            record["provider_error_type"] = type(error).__name__
            # Only this independent fixture can prove that it never generated.
            # Other disconnected providers retain unknown usage.
            if self.provider.dispatches and self.provider.dispatches[-1].get("disposition") in (
                "known stalled before generation",
                "known interrupted before generation",
            ):
                self.ledger.settle(
                    record["accounting"], None, known_pre_generation=True, cancelled=True
                )
            if not self.stopping.is_set():
                handler.send_error(502, "fixture provider interrupted")
        finally:
            connection.close()
            with self.lock:
                self.connections.discard(connection)

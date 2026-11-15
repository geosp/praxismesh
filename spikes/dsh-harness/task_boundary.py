"""Trusted budget gateway for isolated task Activities and their fixture providers."""

from __future__ import annotations

import http.client
import json
from urllib.parse import urlsplit

from model_gateway import MAX_BODY, Boundary
from usage_ledger import UsageLedger

FIXTURE_FAULTS = {
    "fixture disconnect before generation",
    "fixture rejected input",
    "fixture unavailable before generation",
    "fixture malformed stream before generation",
}


class TaskBoundary(Boundary):
    # The usage ledger owns the model-step limit so its denial is recorded and
    # inner-step exhaustion maps to continuation, not a retryable failure.
    request_cap = None

    def __init__(
        self,
        path,
        run: str,
        attempt: int,
        tools: set[str],
        completion,
        *,
        budget: int,
        steps: int,
        fixture=None,
        upstream=None,
        api_key="",
        checkpoint=None,
    ):
        self.completion = completion
        self.fixture = fixture
        self.ledger = UsageLedger(run, "task", attempt, budget, steps)
        self.logical = {}
        self.fault = None
        self.checkpoint = checkpoint
        target = (
            upstream if fixture is None else f"http://127.0.0.1:{fixture.server.server_port}/v1"
        )
        if not target:
            raise ValueError("trusted provider target required")
        super().__init__(path, "task", upstream=target, api_key=api_key, allowed_tools=tools)

    def admit(self, request: dict, record: dict) -> bool:
        step = self.logical.setdefault(record["request_hash"], len(self.logical) + 1)
        deny = "explicit completion" if self.completion.finished.is_set() else None
        if deny is None and self.checkpoint is not None:
            try:
                self.checkpoint()
                record["checkpoint_acknowledged"] = True
            except Exception as error:
                record["checkpoint_error_type"] = type(error).__name__
                self.fault = "checkpoint barrier failed"
                deny = "checkpoint barrier failed"
        observation = self.ledger.ingress("main", step, deny=deny)
        record["accounting"] = observation
        return observation["dispatched"]

    def forward(self, handler, body: bytes, record: dict):
        target = urlsplit(self.upstream)
        prefix = target.path.rstrip("/")
        if not prefix.endswith("/v1"):
            prefix += "/v1"
        cls = (
            http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
        )
        connection = cls(target.hostname, target.port, timeout=2)
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
            encoded = response.read(MAX_BODY + 1)
            if len(encoded) > MAX_BODY:
                raise ValueError("provider response exceeded bound")
            record["provider_status"] = response.status
            fixture_record = self.fixture.dispatches[-1] if self.fixture is not None else {}
            known_fault = fixture_record.get("disposition") in FIXTURE_FAULTS
            if known_fault:
                self.fault = fixture_record["disposition"]
                self.ledger.settle(record["accounting"], None, known_pre_generation=True)
            elif response.status == 200:
                usage = None
                if response.getheader("Content-Type", "").startswith("application/json"):
                    usage = json.loads(encoded).get("usage")
                else:
                    for line in encoded.splitlines():
                        if line.startswith(b"data: ") and line[6:] != b"[DONE]":
                            item = json.loads(line[6:])
                            if item.get("usage") is not None:
                                usage = item["usage"]
                self.ledger.settle(record["accounting"], usage)
                record["provider_usage"] = usage
            if response.status >= 400 and not known_fault:
                self.fault = (
                    "provider rejected input"
                    if response.status == 400
                    else "provider transport failure"
                )
            handler.send_response(response.status)
            handler.send_header(
                "Content-Type", response.getheader("Content-Type", "application/json")
            )
            handler.end_headers()
            handler.wfile.write(encoded)
        except (OSError, http.client.HTTPException, ValueError) as error:
            record["provider_error_type"] = type(error).__name__
            self.fault = "provider transport or protocol failure"
            last = (
                self.fixture.dispatches[-1]
                if self.fixture is not None and self.fixture.dispatches
                else {}
            )
            if last.get("disposition") == "fixture disconnect before generation":
                self.fault = last["disposition"]
                self.ledger.settle(record["accounting"], None, known_pre_generation=True)
            if not self.stopping.is_set():
                handler.send_error(502, "trusted provider transport/protocol failure")
        finally:
            connection.close()
            with self.lock:
                self.connections.discard(connection)

    def close(self):
        try:
            super().close()
        finally:
            if self.fixture is not None:
                self.fixture.close()

    def owned_work_alive(self):
        return super().owned_work_alive() or (
            self.fixture is not None and self.fixture.owned_work_alive()
        )

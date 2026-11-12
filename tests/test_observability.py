"""Observability baseline (spec observability/baseline)."""

from __future__ import annotations

import json
import logging
import socket

import httpx
import pytest

from common.observability import configure_logging, disable_sdk_tracing, log_context
from common.observability.metrics import TOKENS, serve_metrics


def test_log_context_ids(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    with log_context(task_id="task-abc12345", workflow_id="task-abc12345", turn=2, attempt=1):
        logging.getLogger("praxis.test").info("tool called", extra={"fields": {"tool": "x"}})
    logging.getLogger("praxis.test").info("outside")
    first, second = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert first["task_id"] == "task-abc12345" and first["turn"] == 2 and first["tool"] == "x"
    assert first["workflow_id"] == "task-abc12345" and first["attempt"] == 1
    assert "task_id" not in second


def test_no_sdk_trace_export() -> None:
    from agents.tracing import get_trace_provider

    disable_sdk_tracing()
    provider = get_trace_provider()
    assert provider._multi_processor._processors == ()  # type: ignore[attr-defined]


def test_metrics_endpoint() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    serve_metrics(port)
    TOKENS.labels(template="local-default@1", direction="in").inc(42)
    body = httpx.get(f"http://127.0.0.1:{port}/metrics", timeout=5).text
    assert 'praxis_tokens_total{direction="in",template="local-default@1"}' in body

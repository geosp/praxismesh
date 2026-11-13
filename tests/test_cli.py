"""CLI logging at the client-to-platform boundary (observability baseline)."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from common.blob_store.s3 import S3BlobStore
from common.schemas import BlobRef, TaskStart
from orchestrator import cli


class _Engine:
    async def dispose(self) -> None:
        return None


class _S3:
    async def ensure_bucket(self) -> None:
        return None


class _Handle:
    async def result(self) -> Any:
        raise AssertionError("--wait was not requested")


class _Tracer:
    def start_as_current_span(self, name: str, attributes: dict[str, str]) -> Any:
        return contextlib.nullcontext()


class _Provider:
    def get_tracer(self, name: str) -> _Tracer:
        return _Tracer()

    def shutdown(self) -> None:
        return None


def test_submit_writes_contextual_json_log_to_stderr(monkeypatch: Any, capsys: Any) -> None:
    ref = BlobRef(
        id="blob:" + "0" * 64,
        key="sha256/" + "0" * 64,
        checksum="sha256:" + "0" * 64,
        content_type="text/plain",
        bytes=1,
        retention_class="task",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    start = TaskStart(
        task_id="task-cli-00000001",
        request_id="req-cli-00000001",
        profile="default",
        template="local-default",
        instructions_ref=ref,
    )

    async def prepare(*args: Any, **kwargs: Any) -> TaskStart:
        return start

    async def connect() -> object:
        return object()

    async def start_task(*args: Any, **kwargs: Any) -> _Handle:
        return _Handle()

    monkeypatch.setattr(cli, "PROVIDER", _Provider())
    monkeypatch.setattr(cli, "make_engine", _Engine)
    monkeypatch.setattr(S3BlobStore, "from_env", lambda: _S3())
    monkeypatch.setattr(cli, "prepare_task", prepare)
    monkeypatch.setattr(cli, "connect", connect)
    monkeypatch.setattr(cli, "start_task", start_task)

    assert cli.main(["task", "submit", "--instructions", "hello"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "task_id": "task-cli-00000001",
        "request_id": "req-cli-00000001",
    }
    line = json.loads(captured.err)
    assert line["msg"] == "task submitted"
    assert line["task_id"] == "task-cli-00000001"
    assert line["request_id"] == "req-cli-00000001"

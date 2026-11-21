"""CLI logging at the client-to-platform boundary (observability baseline)."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

import pytest

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
        profile="openai",
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
    assert line["workflow_id"] == "task-cli-00000001"


# `agentctl tail` and `events prune` (Phase 2 events plan tasks 3.1, 3.2).


def _events(n: int, start: int = 0) -> list[Any]:
    from common.schemas.events import AgentEvent

    return [
        AgentEvent(
            seq=start + i,
            timestamp=datetime.now(UTC),
            workflow_id="wf",
            task_id="wf",
            attempt_id="wf:1:1",
            type="token",
            payload={"input_tokens": start + i},
        )
        for i in range(n)
    ]


async def _published(n: int) -> Any:
    from common.events import MemoryTransport, Writer

    t = MemoryTransport()
    await t.publish("wf", Writer("wf", 1, 1), "b0", _events(n))
    return t


async def _never_closed() -> bool:
    return False


async def test_tail_resumes_after_an_offset() -> None:
    t, lines = await _published(30), list[str]()
    last = await cli.print_events(
        t, "wf", 20, follow=False, closed=_never_closed, write=lines.append
    )
    assert [int(line.split("\t")[0]) for line in lines] == list(range(21, 31))
    assert last == 30
    assert lines[0].split("\t")[1:3] == ["wf:1:1", "token"]


async def test_tail_reports_pruned_events_first() -> None:
    t, lines = await _published(20), list[str]()
    assert await t.prune("wf", below=15) == 15
    await cli.print_events(t, "wf", 5, follow=False, closed=_never_closed, write=lines.append)
    assert lines[0] == "expired: events before 15 were pruned"
    assert [int(line.split("\t")[0]) for line in lines[1:]] == list(range(15, 21))


async def test_tail_follows_until_the_workflow_closes_then_reads_to_the_end(
    monkeypatch: Any,
) -> None:
    import asyncio

    from common.events import Writer

    t, lines, state = await _published(2), list[str](), {"closed": False}

    async def closed() -> bool:
        return state["closed"]

    monkeypatch.setattr(cli, "POLL_CLOSED_S", 0.05)
    following = asyncio.create_task(
        cli.print_events(t, "wf", 0, follow=True, closed=closed, write=lines.append)
    )
    await asyncio.sleep(0.1)
    await t.publish("wf", Writer("wf", 1, 1), "b1", _events(3, 2))
    state["closed"] = True  # the last batch may land as the Workflow closes
    await t.publish("wf", Writer("wf", 1, 1), "b2", _events(1, 5))
    assert await asyncio.wait_for(following, 5) == 6
    assert [int(line.split("\t")[0]) for line in lines] == list(range(1, 7))


def test_durations_parse() -> None:
    from datetime import timedelta

    import pytest

    assert cli.parse_duration("7d") == timedelta(days=7)
    assert cli.parse_duration("30m") == timedelta(minutes=30)
    with pytest.raises(Exception, match="duration"):
        cli.parse_duration("7 days")


def test_tail_and_prune_parse() -> None:
    args = cli.parser().parse_args(["tail", "task-1", "--after", "4", "--no-follow"])
    assert (args.group, args.task_id, args.after, args.follow) == ("tail", "task-1", 4, False)
    args = cli.parser().parse_args(["events", "prune", "--task", "task-1", "--below", "15"])
    assert (args.command, args.task, args.below, args.older_than) == ("prune", "task-1", 15, None)


def test_join_refuses_an_unknown_request(monkeypatch: Any, capsys: Any) -> None:
    """Phase 2 messaging D5: --join checks the request has a task before submitting."""
    from common.persistence.repositories import TaskRepository

    async def nothing(self: Any, request_id: str) -> bool:
        return False

    async def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("nothing is submitted for an unknown request")

    monkeypatch.setattr(cli, "PROVIDER", _Provider())
    monkeypatch.setattr(cli, "make_engine", _Engine)
    monkeypatch.setattr(TaskRepository, "request_exists", nothing)
    monkeypatch.setattr(cli, "prepare_task", never)
    assert cli.main(["task", "submit", "--instructions", "hi", "--join", "req-nope"]) == 2
    assert "request req-nope has no task to join" in capsys.readouterr().err
    args = cli.parser().parse_args(["task", "submit", "--instructions", "x", "--join", "req-1"])
    assert args.join == "req-1" and args.request is None


def test_gc_dry_run_reaches_gc_and_prints_its_plan(monkeypatch: Any, capsys: Any) -> None:
    """`agentctl gc --dry-run` (Phase 3A persistence plan phase 02 task 2.1)."""
    from common.persistence.removal import BatchResult
    from orchestrator.lifecycle import Totals

    seen: dict[str, Any] = {}

    async def gc(engine: Any, bucket: Any, status_of: Any, *, dry_run: bool) -> Totals:
        seen["dry_run"] = dry_run
        totals = Totals("gc:test")
        totals.add(BatchResult(2, 3, 1, (), 1), "checkpoints expired")
        return totals

    async def connect() -> object:
        return object()

    monkeypatch.setattr(cli, "PROVIDER", _Provider())
    monkeypatch.setattr(cli, "make_engine", _Engine)
    monkeypatch.setattr(S3BlobStore, "from_env", lambda: _S3())
    monkeypatch.setattr(cli, "connect", connect)
    monkeypatch.setattr(cli, "gc", gc)
    assert cli.main(["gc", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert seen == {"dry_run": True}
    assert report["dry_run"] is True and report["by_reason"]["checkpoints expired"]["rows"] == 2


def test_request_delete_passes_force_and_dry_run(monkeypatch: Any, capsys: Any) -> None:
    """`agentctl request delete REQ --force --dry-run` (phase 02 task 3.2)."""
    from orchestrator.lifecycle import Totals

    seen: dict[str, Any] = {}

    async def delete_request(
        engine: Any, bucket: Any, status_of: Any, request_id: str, *, force: bool, dry_run: bool
    ) -> Totals:
        seen.update(request_id=request_id, force=force, dry_run=dry_run)
        return Totals("delete:test")

    async def connect() -> object:
        return object()

    monkeypatch.setattr(cli, "PROVIDER", _Provider())
    monkeypatch.setattr(cli, "make_engine", _Engine)
    monkeypatch.setattr(S3BlobStore, "from_env", lambda: _S3())
    monkeypatch.setattr(cli, "connect", connect)
    monkeypatch.setattr(cli, "delete_request", delete_request)
    assert cli.main(["request", "delete", "req-1", "--force", "--dry-run"]) == 0
    assert seen == {"request_id": "req-1", "force": True, "dry_run": True}
    assert json.loads(capsys.readouterr().out)["request_id"] == "req-1"


@pytest.mark.parametrize("clean", [True, False])
def test_reconcile_exits_1_when_anything_is_listed(
    monkeypatch: Any, capsys: Any, clean: bool
) -> None:
    """`agentctl reconcile [--reindex]` (Phase 3A persistence plan phase 03 task 1.1, R17)."""
    from orchestrator.reconcile import Report

    seen: dict[str, Any] = {}

    async def reconcile(engine: Any, bucket: Any, status_of: Any, *, reindex: bool) -> Report:
        seen["reindex"] = reindex
        return Report() if clean else Report(never_ended={"task-1": "closed"})

    async def connect() -> object:
        return object()

    monkeypatch.setattr(cli, "PROVIDER", _Provider())
    monkeypatch.setattr(cli, "make_engine", _Engine)
    monkeypatch.setattr(S3BlobStore, "from_env", lambda: _S3())
    monkeypatch.setattr(cli, "connect", connect)
    monkeypatch.setattr(cli, "reconcile", reconcile)
    assert cli.main(["reconcile", "--reindex"]) == (0 if clean else 1)
    report = json.loads(capsys.readouterr().out)
    assert seen == {"reindex": True}
    assert report["clean"] is clean
    if not clean:
        assert report["never_ended"] == [{"task_id": "task-1", "workflow": "closed"}]

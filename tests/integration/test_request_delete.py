"""`agentctl request delete`: a fixed task list, redaction, fencing and the blobs
no other holder keeps (Phase 3A persistence plan phase 02 task 3.2; R3, R10, R11,
R12, R13, R21, R24, R25, D12; notes.md#redact).

Each test runs on a scratch database migrated to head, with an in-memory bucket.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import MemoryBlobStore
from common.blob_store.s3 import S3BlobStore
from common.errors import InvalidTaskInput
from common.persistence.fence import REQUEST_LOCK, TASK_LOCK, FenceRejected
from common.persistence.removal import Batch, RemovalEngine
from common.persistence.repositories import (
    AttemptRepository,
    Checkpoint,
    CheckpointRepository,
    RecordingBlobStore,
)
from common.schemas import BlobRef
from orchestrator import cli
from orchestrator.lifecycle import DeleteRefused, delete_request, marker
from tests.support.lifecycle import (
    FakeTemporal,
    StoredTask,
    content_rows,
    end_task,
    expired,
    new_task_id,
    one,
    publish_events,
    record_task,
    tombstones,
)
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    async with scratch_database("head") as (_, eng):
        yield eng


async def finished(
    engine: AsyncEngine, store: RecordingBlobStore, request: str, *, shared: bytes = b""
) -> StoredTask:
    """A task of `request` with an input, a checkpoint, an artifact, events, and
    content rows in every table notes.md#redact lists."""
    task = new_task_id("task-del")
    inputs = {"in.txt": shared or f"input {task}".encode()}
    stored = await record_task(engine, store, task_id=task, request_id=request, inputs=inputs)
    await AttemptRepository(engine).start(task, 1, 1, "worker-a")
    ws = await store.put(f"workspace {task}".encode(), retention="checkpoint", task_id=task)
    await CheckpointRepository(engine).insert_fenced(
        Checkpoint(f"{task}:1:1:0", task, 1, 1, 0, task, 0, ws, None)
    )
    await publish_events(engine, task, 3)
    await content_rows(engine, task, request)
    return await end_task(
        engine,
        store,
        stored,
        artifacts={"report.md": f"report {task}".encode()},
        questions=["What next?"],
    )


async def test_a_finished_request_is_removed_redacted_and_recorded(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    a = await finished(engine, store, request)
    b = await finished(engine, store, request)
    totals = await delete_request(engine, inner, FakeTemporal(), request)

    for t in (a, b):  # R10: nothing of theirs can be read
        for ref in (t.instructions, *t.inputs.values(), *t.artifacts.values()):
            assert await expired(store, ref)
        assert (
            await one(engine, "SELECT count(*) FROM checkpoints WHERE task_id = :t", t=t.task_id)
            == 0
        )
        assert (
            await one(engine, "SELECT count(*) FROM agent_events WHERE task_id = :t", t=t.task_id)
            == 0
        )
        for table in ("sample_orders", "task_inbox"):
            assert (
                await one(engine, f"SELECT count(*) FROM {table} WHERE task_id = :t", t=t.task_id)
                == 0
            )
        # R11: content holds the marker; IDs, statuses and usage remain.
        mark = marker(datetime.now(UTC))
        raw = await one(engine, "SELECT result FROM tasks WHERE task_id = :t", t=t.task_id)
        result = raw if isinstance(raw, dict) else json.loads(raw)
        assert result["summary"] == mark and result["questions"] == [mark]
        assert result["artifacts"] == [] and result["task_id"] == t.task_id
        assert result["status"] == "succeeded" and result["tokens_in"] == 10
        assert (
            await one(engine, "SELECT status FROM tasks WHERE task_id = :t", t=t.task_id)
            == "succeeded"
        )
        assert (
            await one(engine, "SELECT body FROM task_messages WHERE sender_task = :t", t=t.task_id)
            == mark
        )
        assert (
            json.loads(
                await one(
                    engine,
                    "SELECT message_data FROM agent_messages WHERE session_id = :t",
                    t=t.task_id,
                )
            )
            == mark
        )
        assert await one(
            engine,
            "SELECT CAST(result AS text) FROM idempotency_keys WHERE task_id = :t",
            t=t.task_id,
        ) == json.dumps(mark)
        assert (
            await one(
                engine, "SELECT retained_base FROM event_logs WHERE workflow_id = :t", t=t.task_id
            )
            == 4
        )  # pruned to the end: tail reports expired
        assert (
            await one(
                engine,
                "SELECT outcome FROM task_attempts WHERE task_id = :t AND turn = 2",
                t=t.task_id,
            )
            == "deleted"
        )
    # R13: tombstones name the request; counts sum to what was removed; no content.
    stones = await tombstones(engine, totals.operation)
    assert {s.action for s in stones} == {"request.delete"} and {s.subject for s in stones} == {
        f"request:{request}"
    }
    assert len(stones) == totals.batches  # F135: only committed batches count
    assert stones[0].details["tasks"] == sorted([a.task_id, b.task_id])
    for key in ("rows", "references", "blobs"):
        assert sum(s.details[key] for s in stones) == getattr(totals, key)
    assert "secret" not in json.dumps([s.details for s in stones])


async def test_task_output_of_a_redacted_task_reports_no_output(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    a = await finished(engine, store, request)
    await delete_request(engine, inner, FakeTemporal(), request)
    monkeypatch.setattr(cli, "make_engine", lambda: _Borrowed(engine))
    monkeypatch.setattr(S3BlobStore, "from_env", lambda: inner)
    with pytest.raises(InvalidTaskInput, match=r"has no output 'report.md' \(outputs: none\)"):
        await cli.output(argparse.Namespace(task_id=a.task_id, path="report.md", to=None))


class _Borrowed:
    """The test's engine, which the CLI must not dispose."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)

    async def dispose(self) -> None:
        return None


async def test_a_request_with_a_running_task_is_refused(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    done = await finished(engine, store, request)
    running = await record_task(engine, store, request_id=request)
    with pytest.raises(DeleteRefused, match=running.task_id):  # R12
        await delete_request(engine, inner, FakeTemporal(), request)
    assert not await expired(store, done.artifacts["report.md"])
    assert (
        await one(
            engine, "SELECT count(*) FROM audit_log WHERE subject = :s", s=f"request:{request}"
        )
        == 0
    )


async def test_force_deletes_only_a_closed_workflow(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    left = await record_task(engine, store, request_id=request)  # terminated, never ended
    with pytest.raises(DeleteRefused, match="--force"):
        await delete_request(engine, inner, FakeTemporal({left.task_id: "closed"}), request)
    with pytest.raises(DeleteRefused, match="still running"):  # R21
        await delete_request(
            engine, inner, FakeTemporal({left.task_id: "running"}), request, force=True
        )
    assert not await expired(store, left.instructions)
    await delete_request(engine, inner, FakeTemporal({left.task_id: "closed"}), request, force=True)
    assert await expired(store, left.instructions)
    assert (
        await one(engine, "SELECT status FROM tasks WHERE task_id = :t", t=left.task_id) == "failed"
    )
    assert await one(
        engine, "SELECT ended_at IS NOT NULL FROM tasks WHERE task_id = :t", t=left.task_id
    )


async def test_a_blob_shared_with_another_request_survives(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    shared = f"shared orders {uuid.uuid4()}".encode()
    gone = await finished(engine, store, f"req-del-{uuid.uuid4().hex[:8]}", shared=shared)
    other = await finished(engine, store, f"req-keep-{uuid.uuid4().hex[:8]}", shared=shared)
    await delete_request(engine, inner, FakeTemporal(), gone.request_id)
    assert await store.get(other.inputs["in.txt"]) == shared  # R3
    assert not await expired(store, other.artifacts["report.md"])


async def test_a_late_attempt_of_a_deleted_task_writes_nothing(engine: AsyncEngine) -> None:
    """R25: a --force delete while the Activity still runs."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    task = await record_task(engine, store, request_id=request)
    await AttemptRepository(engine).start(task.task_id, 1, 1, "worker-a")
    await delete_request(engine, inner, FakeTemporal({task.task_id: "closed"}), request, force=True)

    late_ws = f"late workspace {task.task_id}".encode()
    ref = await store.put(late_ws, retention="checkpoint", task_id=task.task_id)
    with pytest.raises(FenceRejected):
        await CheckpointRepository(engine).insert_fenced(
            Checkpoint(f"{task.task_id}:1:1:9", task.task_id, 1, 1, 9, task.task_id, 0, ref, None)
        )
    with pytest.raises(FenceRejected):
        await publish_events(engine, task.task_id, 1, turn=1)
    assert ref.key not in inner.objects  # bytes with no live holder were not uploaded
    assert (
        await one(
            engine,
            "SELECT count(*) FROM blob_refs WHERE task_id = :t AND removed_at IS NULL",
            t=task.task_id,
        )
        == 0
    )
    assert (
        await one(engine, "SELECT count(*) FROM checkpoints WHERE task_id = :t", t=task.task_id)
        == 0
    )


async def test_a_task_joining_mid_delete_is_untouched(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R24: the delete changes only the tasks the request had when it began."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    first = await finished(engine, store, request)
    paused, resume = asyncio.Event(), asyncio.Event()
    real_run = RemovalEngine.run
    runs = 0

    async def pausing_run(self: RemovalEngine, batch: Batch) -> Any:
        nonlocal runs
        runs += 1
        if runs == 2:  # after the first batch fixed the task list
            paused.set()
            await resume.wait()
        return await real_run(self, batch)

    monkeypatch.setattr(RemovalEngine, "run", pausing_run)
    deleting = asyncio.create_task(delete_request(engine, inner, FakeTemporal(), request))
    await asyncio.wait_for(paused.wait(), 30)
    joiner = new_task_id("task-join")
    joining = asyncio.create_task(  # uploads now; its row waits for the request lock
        record_task(
            engine,
            store,
            task_id=joiner,
            request_id=request,
            inputs={"j": b"join " + joiner.encode()},
        )
    )
    await asyncio.sleep(0.5)
    assert not joining.done()  # record_task waits for the delete
    resume.set()
    await deleting
    joined = await joining
    assert await expired(store, first.artifacts["report.md"])
    assert await store.get(joined.inputs["j"]) == b"join " + joiner.encode()
    assert await one(engine, "SELECT status FROM tasks WHERE task_id = :t", t=joiner) == "running"
    assert (
        await one(
            engine,
            "SELECT count(*) FROM blob_refs WHERE task_id = :t AND removed_at IS NOT NULL",
            t=joiner,
        )
        == 0
    )


async def test_a_dry_run_reports_the_plan_and_changes_nothing(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    a = await finished(engine, store, request)
    dry = await delete_request(engine, inner, FakeTemporal(), request, dry_run=True)
    assert not await expired(store, a.artifacts["report.md"])
    assert await tombstones(engine, dry.operation) == []
    real = await delete_request(engine, inner, FakeTemporal(), request)
    assert (dry.rows, dry.references, dry.blobs, dry.by_reason) == (
        real.rows,
        real.references,
        real.blobs,
        real.by_reason,
    )


async def test_a_delete_waits_out_an_attempt_holding_its_task_lock(engine: AsyncEngine) -> None:
    """An attempt's message write takes its task lock, then the request lock
    (messages._enter): the delete releases the request lock and tries again."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    a = await finished(engine, store, request)
    held, write_done = asyncio.Event(), asyncio.Event()

    async def message_write() -> None:
        async with engine.begin() as conn:
            await conn.execute(TASK_LOCK, {"t": a.task_id})
            held.set()
            await asyncio.sleep(0.3)  # the delete starts and takes the request lock
            await conn.execute(REQUEST_LOCK, {"r": request})
        write_done.set()

    writer = asyncio.create_task(message_write())
    await held.wait()
    totals = await asyncio.wait_for(delete_request(engine, inner, FakeTemporal(), request), 60)
    await writer
    assert write_done.is_set() and totals.blobs >= 1
    assert await expired(store, a.artifacts["report.md"])


async def test_a_put_during_the_delete_already_revives_nothing(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first batch marks the uploads under each task's lock (review F81), so
    an upload racing the rest of the delete finds the mark (R25)."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    a = await finished(engine, store, request)
    paused, resume = asyncio.Event(), asyncio.Event()
    real_run = RemovalEngine.run
    runs = 0

    async def pausing_run(self: RemovalEngine, batch: Batch) -> Any:
        nonlocal runs
        runs += 1
        if runs == 2:
            paused.set()
            await resume.wait()
        return await real_run(self, batch)

    monkeypatch.setattr(RemovalEngine, "run", pausing_run)
    deleting = asyncio.create_task(delete_request(engine, inner, FakeTemporal(), request))
    await asyncio.wait_for(paused.wait(), 30)
    late = await store.put(b"late " + a.task_id.encode(), retention="checkpoint", task_id=a.task_id)
    live = await one(
        engine,
        "SELECT count(*) FROM blob_refs WHERE task_id = :t AND holder_table = 'upload' "
        "AND removed_at IS NULL",
        t=a.task_id,
    )
    resume.set()
    await deleting
    assert live == 0 and late.key not in inner.objects


async def test_an_attempt_of_a_later_turn_is_fenced_too(engine: AsyncEngine) -> None:
    """F118 (R25): the fencing row's own turn, or any later one, passes no write."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    task = await record_task(engine, store, request_id=request)
    await AttemptRepository(engine).start(task.task_id, 1, 1, "worker-a")
    await delete_request(engine, inner, FakeTemporal({task.task_id: "closed"}), request, force=True)
    for turn, attempt in ((2, 1), (2, 2), (9, 1)):
        with pytest.raises(FenceRejected):
            await AttemptRepository(engine).start(task.task_id, turn, attempt, "worker-late")
        ws = await store.put(f"ws {turn}".encode(), retention="checkpoint", task_id=task.task_id)
        with pytest.raises(FenceRejected):
            await CheckpointRepository(engine).insert_fenced(
                Checkpoint(
                    f"{task.task_id}:{turn}:{attempt}:0",
                    task.task_id,
                    turn,
                    attempt,
                    0,
                    task.task_id,
                    0,
                    ws,
                    None,
                )
            )
        with pytest.raises(FenceRejected):
            await publish_events(engine, task.task_id, 1, turn=turn)
    assert (
        await one(
            engine,
            "SELECT worker_identity FROM task_attempts WHERE task_id = :t AND outcome = 'deleted'",
            t=task.task_id,
        )
        == "cli:request-delete"
    )


async def test_a_deleted_task_with_no_upload_left_still_revives_nothing(
    engine: AsyncEngine,
) -> None:
    """F125 (R25, D10): a task counts as deleted by its `deleted` attempt row,
    even when the delete marked none of its references."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    task = await record_task(engine, store, request_id=request)
    async with engine.begin() as conn:  # as if a pre-0007 task: no upload references
        await conn.execute(text("DELETE FROM blob_refs WHERE task_id = :t"), {"t": task.task_id})
    await delete_request(engine, inner, FakeTemporal({task.task_id: "closed"}), request, force=True)
    late = await store.put(
        b"late " + task.task_id.encode(), retention="checkpoint", task_id=task.task_id
    )
    assert late.key not in inner.objects
    assert (
        await one(
            engine,
            "SELECT count(*) FROM blob_refs WHERE task_id = :t AND removed_at IS NULL",
            t=task.task_id,
        )
        == 0
    )


async def test_a_deleted_tasks_conversation_and_tool_writes_are_refused(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F117 (R25, R11): the openai session store and the sample MCP server write
    nothing for a task once its request is deleted."""
    from harness_activity.session_store import SQLAlchemySessionStore
    from sample_mcp import server

    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    task = await record_task(engine, store, request_id=request)
    session = SQLAlchemySessionStore(task.task_id, engine).session
    await session.add_items([{"role": "user", "content": "before the delete"}])
    await delete_request(engine, inner, FakeTemporal({task.task_id: "closed"}), request, force=True)

    with pytest.raises(FenceRejected):
        await session.add_items([{"role": "user", "content": "late secret"}])
    monkeypatch.setenv("PRAXIS_TASK_ID", task.task_id)
    monkeypatch.setattr(server, "_engine", engine)
    with pytest.raises(FenceRejected):
        await server.record_order("SKU-1", 3)
    for table, column in (("agent_messages", "session_id"), ("sample_orders", "task_id"),
                          ("idempotency_keys", "task_id")):  # fmt: skip
        rows = await one(
            engine, f"SELECT count(*) FROM {table} WHERE {column} = :t", t=task.task_id
        )
        assert rows == (1 if table == "agent_messages" else 0), table


class _SlowBucket(MemoryBlobStore):
    """An inner store whose uploads wait until released."""

    def __init__(self) -> None:
        super().__init__()
        self.uploading, self.release = asyncio.Event(), asyncio.Event()
        self.hold = False

    async def put(self, data: Any, **kwargs: Any) -> BlobRef:
        if self.hold:
            self.uploading.set()
            await self.release.wait()
        return await super().put(data, **kwargs)


async def test_an_upload_in_flight_during_a_delete_leaves_no_object_behind(
    engine: AsyncEngine,
) -> None:
    """F124 (R10, D10): the upload happens under the blob's row lock, so a removal
    that marks the blob deletes the object after it lands, never before."""
    inner = _SlowBucket()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    task = await record_task(engine, store, request_id=request)
    inner.hold = True
    data = b"workspace in flight " + task.task_id.encode()
    uploading = asyncio.create_task(store.put(data, retention="checkpoint", task_id=task.task_id))
    await asyncio.wait_for(inner.uploading.wait(), 10)
    deleting = asyncio.create_task(
        delete_request(engine, inner, FakeTemporal({task.task_id: "closed"}), request, force=True)
    )
    await asyncio.sleep(0.5)
    inner.release.set()
    ref = await uploading
    await asyncio.wait_for(deleting, 60)
    assert ref.key not in inner.objects  # removed with the rest of the task
    assert await expired(store, ref)


async def test_content_that_only_looks_redacted_is_redacted(engine: AsyncEngine) -> None:
    """F123 (R11): only the exact marker counts as redacted; model output that
    starts with "[deleted " is redacted like any other content."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    a = await finished(engine, store, request)
    fake = "[deleted draft] the key is 1234"
    async with engine.begin() as conn:
        raw = await conn.scalar(
            text("SELECT result FROM tasks WHERE task_id = :t"), {"t": a.task_id}
        )
        result = raw if isinstance(raw, dict) else json.loads(raw)
        result["summary"] = fake
        await conn.execute(
            text("UPDATE tasks SET result = CAST(:r AS json) WHERE task_id = :t"),
            {"r": json.dumps(result), "t": a.task_id},
        )
        await conn.execute(
            text("UPDATE task_messages SET body = :b WHERE sender_task = :t"),
            {"b": fake, "t": a.task_id},
        )
        await conn.execute(
            text("UPDATE agent_messages SET message_data = :m WHERE session_id = :t"),
            {"m": json.dumps(fake), "t": a.task_id},
        )
        await conn.execute(
            text("UPDATE idempotency_keys SET result = CAST(:r AS json) WHERE task_id = :t"),
            {"r": json.dumps(fake), "t": a.task_id},
        )
    await delete_request(engine, inner, FakeTemporal(), request)
    mark = marker(datetime.now(UTC))
    raw = await one(engine, "SELECT result FROM tasks WHERE task_id = :t", t=a.task_id)
    result = raw if isinstance(raw, dict) else json.loads(raw)
    assert result["summary"] == mark and result["questions"] == [mark] and result["artifacts"] == []
    assert (
        await one(engine, "SELECT body FROM task_messages WHERE sender_task = :t", t=a.task_id)
        == mark
    )
    assert (
        json.loads(
            await one(
                engine, "SELECT message_data FROM agent_messages WHERE session_id = :t", t=a.task_id
            )
        )
        == mark
    )
    assert await one(
        engine, "SELECT CAST(result AS text) FROM idempotency_keys WHERE task_id = :t", t=a.task_id
    ) == json.dumps(mark)


async def test_a_rerun_finishes_the_killed_deletes_own_task_list(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F122 (R24, R15): a rerun resumes the task list of the delete it finishes,
    so a task that joined after the killed run is neither deleted nor blocking."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    first = await finished(engine, store, request)
    real_run = RemovalEngine.run
    runs = 0

    class Killed(Exception):
        pass

    async def killing_run(self: RemovalEngine, batch: Batch) -> Any:
        nonlocal runs
        runs += 1
        if runs == 2:  # after the first batch fixed the task list
            raise Killed
        return await real_run(self, batch)

    monkeypatch.setattr(RemovalEngine, "run", killing_run)
    with pytest.raises(Killed):
        await delete_request(engine, inner, FakeTemporal(), request)
    monkeypatch.undo()
    joiner = await record_task(engine, store, request_id=request, inputs={"j": b"joined later"})

    totals = await delete_request(engine, inner, FakeTemporal(), request)  # joiner is running
    assert await expired(store, first.artifacts["report.md"])
    assert await store.get(joiner.inputs["j"]) == b"joined later"
    stones = await tombstones(engine, totals.operation)
    assert stones[0].details["tasks"] == [first.task_id] and stones[0].details["resumed"]
    assert stones[-1].details["reason"] == "request delete complete"
    with pytest.raises(DeleteRefused, match=joiner.task_id):  # a fresh delete sees it
        await delete_request(engine, inner, FakeTemporal(), request)


async def test_force_says_why_each_task_counted_as_ended(engine: AsyncEngine) -> None:
    """F143 (R21, engineer decision): the plan, the report and the first
    tombstone name each forced task with Temporal's answer."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-del-{uuid.uuid4().hex[:8]}"
    closed = await record_task(engine, store, request_id=request)
    gone = await record_task(engine, store, request_id=request)
    temporal = FakeTemporal({closed.task_id: "closed"})  # `gone` is unknown: missing
    expected = {closed.task_id: "closed", gone.task_id: "missing"}
    dry = await delete_request(engine, inner, temporal, request, force=True, dry_run=True)
    assert dry.forced == expected and dry.report()["forced"] == expected
    totals = await delete_request(engine, inner, temporal, request, force=True)
    assert totals.forced == expected
    assert (await tombstones(engine, totals.operation))[0].details["forced"] == expected

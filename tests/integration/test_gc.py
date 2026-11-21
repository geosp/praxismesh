"""`agentctl gc` removes what has expired and nothing else (Phase 3A persistence
plan phase 02 task 2.1; R6, R7, R8, D4, D5; notes.md#d2, notes.md#d3).

Each test runs on a scratch database migrated to head, with an in-memory
bucket: `gc` acts on a whole database, so it never runs on the stack's own.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import BlobExpired, MemoryBlobStore
from common.events import TableTransport, Writer
from common.persistence.removal import RemovalBusy, run_lock
from common.persistence.repositories import Checkpoint, CheckpointRepository, RecordingBlobStore
from common.schemas.events import AgentEvent
from orchestrator.lifecycle import GcRefused, WorkflowStatus, gc
from tests.support.lifecycle import StoredTask, end_task, new_task_id, record_task
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    async with scratch_database("head") as (_, eng):
        yield eng


class Temporal:
    """Fake Workflow statuses, by task ID; unknown IDs are missing."""

    def __init__(self, **status: WorkflowStatus) -> None:
        self.status = status
        self.asked: list[str] = []

    async def __call__(self, task_id: str) -> WorkflowStatus:
        self.asked.append(task_id)
        return self.status.get(task_id, "missing")


async def ended(
    engine: AsyncEngine, store: RecordingBlobStore, days_ago: float, **inputs: bytes
) -> StoredTask:
    stored = await record_task(engine, store, inputs=inputs)
    await checkpoint(engine, store, stored)
    return await end_task(
        engine,
        store,
        stored,
        artifacts={"out.md": f"artifact {stored.task_id}".encode()},
        ended_at=NOW - timedelta(days=days_ago),
    )


async def checkpoint(engine: AsyncEngine, store: RecordingBlobStore, stored: StoredTask) -> None:
    ws = await store.put(
        f"workspace {stored.task_id}".encode(), retention="checkpoint", task_id=stored.task_id
    )
    await CheckpointRepository(engine).insert(
        Checkpoint(f"{stored.task_id}:1:1:0", stored.task_id, 1, 1, 0, stored.task_id, 0, ws, None)
    )


async def count(engine: AsyncEngine, sql: str, **params: object) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(sql), params)).scalar_one())


async def set_last_put(engine: AsyncEngine, key: str, at: datetime) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE blob_objects SET last_put_at = :at WHERE key = :k"), {"at": at, "k": key}
        )


async def readable(store: RecordingBlobStore, stored: StoredTask, which: str) -> bool:
    ref = {"instructions": stored.instructions, **stored.inputs, **stored.artifacts}[which]
    try:
        await store.get(ref)
    except BlobExpired:
        return False
    return True


async def test_gc_removes_what_expired_and_keeps_the_rest(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    old = await ended(engine, store, 8, **{"in.txt": f"input {uuid.uuid4()}".encode()})
    late = await store.put(  # a stale attempt's workspace, uploaded after the end (#74)
        f"late workspace {old.task_id}".encode(), retention="checkpoint", task_id=old.task_id
    )
    recent = await ended(engine, store, 6)
    running = await record_task(engine, store)
    await checkpoint(engine, store, running)
    ancient = await ended(engine, store, 400)
    audit = await store.put(b"audit record", retention="audit", task_id=ancient.task_id)

    totals = await gc(engine, inner, Temporal())

    # R6: the 8-day-old task's checkpoints, their references, the late upload
    # and the blobs left without a live reference are gone.
    assert (
        await count(engine, "SELECT count(*) FROM checkpoints WHERE task_id = :t", t=old.task_id)
        == 0
    )
    assert late.key not in inner.objects
    assert f"workspace {old.task_id}".encode() not in {o.data for o in inner.objects.values()}
    # Its inputs (transcript, 30 days) and artifact (90 days) are kept.
    assert await readable(store, old, "in.txt") and await readable(store, old, "out.md")
    # R7: a task ended 6 days ago, and a running one, keep their checkpoints.
    for kept in (recent, running):
        assert (
            await count(
                engine, "SELECT count(*) FROM checkpoints WHERE task_id = :t", t=kept.task_id
            )
            == 1
        )
    assert await readable(store, recent, "instructions")
    # A 400-day-old task loses its artifact, but `audit` of any age is kept,
    # and so are the task rows themselves (class audit).
    assert not await readable(store, ancient, "out.md")
    assert await store.get(audit) == b"audit record"
    assert (
        await count(engine, "SELECT count(*) FROM tasks WHERE task_id = :t", t=ancient.task_id) == 1
    )
    assert totals.blobs >= 3 and totals.batches >= 3
    reasons = set(totals.by_reason)
    assert {"checkpoints expired", "references expired"} <= reasons


async def test_every_batch_has_a_tombstone_and_the_counts_add_up(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    for _ in range(3):
        await ended(engine, store, 100)
    totals = await gc(engine, inner, Temporal())
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT action, details FROM audit_log WHERE operation_id = :o"),
            {"o": totals.operation},
        )
        stones = [(r[0], r[1] if isinstance(r[1], dict) else json.loads(r[1])) for r in rows]
    assert len(stones) == totals.batches and {a for a, _ in stones} == {"gc"}
    for key in ("rows", "references", "blobs"):
        assert sum(d[key] for _, d in stones) == getattr(totals, key)


async def test_a_dry_run_reports_the_same_plan_and_changes_nothing(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    old = await ended(engine, store, 100)
    objects = dict(inner.objects)
    dry = await gc(engine, inner, Temporal(), dry_run=True)
    assert inner.objects == objects and await readable(store, old, "out.md")
    assert (
        await count(
            engine, "SELECT count(*) FROM audit_log WHERE operation_id = :o", o=dry.operation
        )
        == 0
    )
    real = await gc(engine, inner, Temporal())
    assert (dry.rows, dry.references, dry.blobs, dry.by_reason) == (
        real.rows,
        real.references,
        real.blobs,
        real.by_reason,
    )


async def test_wake_and_batch_rows_expire_with_their_task(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    old = await ended(engine, store, 2)  # ephemeral (1 day) past; transcript (30) not
    waiting = await record_task(engine, store)  # still running
    await TableTransport(engine).publish(
        old.task_id,
        Writer(old.task_id, 1, 1),
        f"{old.task_id}:1:1:0",
        [
            AgentEvent(
                seq=0,
                timestamp=NOW,
                workflow_id=old.task_id,
                task_id=old.task_id,
                attempt_id=f"{old.task_id}:1:1",
                type="token",
                payload={},
            )
        ],
    )
    async with engine.begin() as conn:
        for workflow, created in ((old.task_id, NOW), (waiting.task_id, NOW - timedelta(days=9))):
            await conn.execute(
                text("INSERT INTO message_wakes (recipient_workflow, created_at) VALUES (:w, :c)"),
                {"w": workflow, "c": created},
            )
    await gc(engine, inner, Temporal())
    assert (
        await count(
            engine, "SELECT count(*) FROM event_batches WHERE workflow_id = :w", w=old.task_id
        )
        == 0
    )
    assert (
        await count(
            engine, "SELECT count(*) FROM agent_events WHERE workflow_id = :w", w=old.task_id
        )
        == 1
    )
    assert (
        await count(
            engine,
            "SELECT count(*) FROM message_wakes WHERE recipient_workflow = :w",
            w=old.task_id,
        )
        == 0
    )
    # An undelivered wake for a task still running is kept, however old (ADR-0010).
    assert (
        await count(
            engine,
            "SELECT count(*) FROM message_wakes WHERE recipient_workflow = :w",
            w=waiting.task_id,
        )
        == 1
    )


async def test_orphans_wait_for_the_safety_window(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    old = await store.put(f"orphan old {uuid.uuid4()}".encode(), retention="ephemeral")
    new = await store.put(f"orphan new {uuid.uuid4()}".encode(), retention="ephemeral")
    await set_last_put(engine, old.key, NOW - timedelta(hours=25))
    await set_last_put(engine, new.key, NOW - timedelta(hours=1))
    stray = f"sha256/{uuid.uuid4().hex * 2}"  # in the bucket with no row at all
    inner.objects[stray] = replace(inner.objects[old.key], created_at=NOW - timedelta(hours=30))
    totals = await gc(engine, inner, Temporal())
    assert old.key not in inner.objects and stray not in inner.objects  # R8
    assert new.key in inner.objects
    assert totals.by_reason["orphans"]["blobs"] == 2


async def test_rowless_uploads_go_only_when_the_workflow_is_not_running(
    engine: AsyncEngine,
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    closed, queued = new_task_id(), new_task_id()
    gone = await store.put(f"input {closed}".encode(), retention="transcript", task_id=closed)
    kept = await store.put(f"input {queued}".encode(), retention="transcript", task_id=queued)
    for ref in (gone, kept):
        await set_last_put(engine, ref.key, NOW - timedelta(hours=30))
    statuses: dict[str, WorkflowStatus] = {closed: "closed", queued: "running"}
    temporal = Temporal(**statuses)
    await gc(engine, inner, temporal)
    assert gone.key not in inner.objects  # D5: no row, Workflow closed
    assert kept.key in inner.objects  # R7: queued for a worker, kept
    assert set(temporal.asked) == {closed, queued}


async def test_gc_refuses_while_a_reference_is_unindexed(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    old = await ended(engine, store, 100)
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM blob_refs WHERE holder_table = 'tasks'"))
    with pytest.raises(GcRefused, match="reconcile --reindex"):
        await gc(engine, inner, Temporal())
    assert await readable(store, old, "out.md")  # nothing removed


async def test_gc_fails_at_once_while_another_run_holds_the_lock(engine: AsyncEngine) -> None:
    async with run_lock(engine):
        with pytest.raises(RemovalBusy):
            await gc(engine, MemoryBlobStore(), Temporal())

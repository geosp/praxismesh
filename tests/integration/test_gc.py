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
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import BlobExpired, MemoryBlobStore
from common.blob_store.base import content_key
from common.events import TableTransport
from common.persistence.removal import RemovalBusy, run_lock
from common.persistence.repositories import Checkpoint, CheckpointRepository, RecordingBlobStore
from orchestrator.lifecycle import GcRefused, gc
from orchestrator.workflow_status import WorkflowStatus
from tests.support.lifecycle import (
    FakeTemporal,
    StoredTask,
    content_rows,
    end_task,
    new_task_id,
    one,
    publish_events,
    record_task,
)
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    async with scratch_database("head") as (_, eng):
        yield eng


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
    audit_rows = await one(engine, "SELECT count(*) FROM audit_log")

    totals = await gc(engine, inner, FakeTemporal())
    # F132 (R7): audit rows of any age are kept; gc only appends its tombstones.
    assert await one(engine, "SELECT count(*) FROM audit_log") == audit_rows + totals.batches

    # R6: the 8-day-old task's checkpoints, their references, the late upload
    # and the blobs left without a live reference are gone.
    assert (
        await one(engine, "SELECT count(*) FROM checkpoints WHERE task_id = :t", t=old.task_id) == 0
    )
    assert late.key not in inner.objects
    assert f"workspace {old.task_id}".encode() not in {o.data for o in inner.objects.values()}
    # Its inputs (transcript, 30 days) and artifact (90 days) are kept.
    assert await readable(store, old, "in.txt") and await readable(store, old, "out.md")
    # R7: a task ended 6 days ago, and a running one, keep their checkpoints.
    for kept in (recent, running):
        assert (
            await one(engine, "SELECT count(*) FROM checkpoints WHERE task_id = :t", t=kept.task_id)
            == 1
        )
    assert await readable(store, recent, "instructions")
    for kept in (recent, running):  # F132: their workspaces still read
        workspace = content_key(f"workspace {kept.task_id}".encode())[0]
        assert workspace in inner.objects
        assert not await one(
            engine, "SELECT removed_at IS NOT NULL FROM blob_objects WHERE key = :k", k=workspace
        )
    # F132: the expired references are marked, by this run.
    assert (
        await one(
            engine,
            "SELECT count(*) FROM blob_refs WHERE task_id = :t AND holder_table = 'checkpoints' "
            "AND removed_by = :o",
            t=old.task_id,
            o=totals.operation,
        )
        == 1
    )
    # A 400-day-old task loses its artifact, but `audit` of any age is kept,
    # and so are the task rows themselves (class audit).
    assert not await readable(store, ancient, "out.md")
    assert await store.get(audit) == b"audit record"
    assert (
        await one(engine, "SELECT count(*) FROM tasks WHERE task_id = :t", t=ancient.task_id) == 1
    )
    assert totals.blobs >= 3 and totals.batches >= 3
    reasons = set(totals.by_reason)
    assert {"checkpoints expired", "references expired"} <= reasons


async def test_every_batch_has_a_tombstone_and_the_counts_add_up(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    for _ in range(3):
        await ended(engine, store, 100)
    totals = await gc(engine, inner, FakeTemporal())
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
    dry = await gc(engine, inner, FakeTemporal(), dry_run=True)
    assert inner.objects == objects and await readable(store, old, "out.md")
    assert (
        await one(engine, "SELECT count(*) FROM audit_log WHERE operation_id = :o", o=dry.operation)
        == 0
    )
    real = await gc(engine, inner, FakeTemporal())
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
    await publish_events(engine, old.task_id, 1)
    async with engine.begin() as conn:
        for workflow, created in ((old.task_id, NOW), (waiting.task_id, NOW - timedelta(days=9))):
            await conn.execute(
                text("INSERT INTO message_wakes (recipient_workflow, created_at) VALUES (:w, :c)"),
                {"w": workflow, "c": created},
            )
    await gc(engine, inner, FakeTemporal())
    assert (
        await one(
            engine, "SELECT count(*) FROM event_batches WHERE workflow_id = :w", w=old.task_id
        )
        == 0
    )
    assert (
        await one(engine, "SELECT count(*) FROM agent_events WHERE workflow_id = :w", w=old.task_id)
        == 1
    )
    assert (
        await one(
            engine,
            "SELECT count(*) FROM message_wakes WHERE recipient_workflow = :w",
            w=old.task_id,
        )
        == 0
    )
    # An undelivered wake for a task still running is kept, however old (ADR-0010).
    assert (
        await one(
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
    totals = await gc(engine, inner, FakeTemporal())
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
    temporal = FakeTemporal(statuses)
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
        await gc(engine, inner, FakeTemporal())
    assert await readable(store, old, "out.md")  # nothing removed


async def test_gc_fails_at_once_while_another_run_holds_the_lock(engine: AsyncEngine) -> None:
    async with run_lock(engine):
        with pytest.raises(RemovalBusy):
            await gc(engine, MemoryBlobStore(), FakeTemporal())


async def test_an_object_that_is_not_a_content_key_is_reported_not_removed(
    engine: AsyncEngine,
) -> None:
    """F119 (R8, R15): gc never records a key it cannot address; it reports it,
    and every later run still works."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    real = await store.put(f"orphan {uuid.uuid4()}".encode(), retention="ephemeral")
    await set_last_put(engine, real.key, NOW - timedelta(hours=25))
    inner.objects["notes/readme.txt"] = replace(
        inner.objects[real.key], created_at=NOW - timedelta(days=3)
    )
    first = await gc(engine, inner, FakeTemporal())
    second = await gc(engine, inner, FakeTemporal())
    assert "notes/readme.txt" in inner.objects and real.key not in inner.objects
    assert first.unrecognised == ["notes/readme.txt"] == second.unrecognised
    assert (
        await one(engine, "SELECT count(*) FROM blob_objects WHERE key = 'notes/readme.txt'") == 0
    )


async def test_an_orphan_uploaded_after_the_listing_is_kept_and_not_counted(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8, review F135: the orphan batch marks nothing, commits nothing, and the
    report counts no batch for it."""
    from common.persistence import refs

    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    ref = await store.put(f"orphan {uuid.uuid4()}".encode(), retention="ephemeral")
    real_orphaned = refs.orphaned

    async def stale_listing(conn: Any, bucket: Any) -> list[refs.Orphan]:
        # As if the listing ran 30 hours ago, before this object's last upload.
        found = await real_orphaned(conn, bucket)
        return [replace(o, last_put_at=NOW - timedelta(hours=30)) for o in found]

    monkeypatch.setattr(refs, "orphaned", stale_listing)
    totals = await gc(engine, inner, FakeTemporal())
    assert ref.key in inner.objects
    assert "orphans" not in totals.by_reason and totals.batches == 0
    assert (
        await one(
            engine, "SELECT count(*) FROM audit_log WHERE operation_id = :o", o=totals.operation
        )
        == 0
    )


async def test_every_row_rule_and_the_event_prune_expire_with_their_task(
    engine: AsyncEngine,
) -> None:
    """F120 (R6, R7): each of gc's row rules and its event prune, on a task that
    ended 400 days ago; a message to a task still running is kept."""
    from orchestrator import cli

    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    old = await ended(engine, store, 400)
    running = await record_task(engine, store)
    await content_rows(engine, old.task_id, old.request_id)
    await publish_events(engine, old.task_id, 5)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO task_messages (message_id, request_id, sender_task, recipient_task, "
                "kind, status, body, idempotency_key) VALUES (:m, :r, :s, :t, 'send', 'pending', "
                "'to a running task', :m)"
            ),
            {
                "m": f"{old.task_id}:open",
                "r": old.request_id,
                "s": old.task_id,
                "t": running.task_id,
            },
        )
        await conn.execute(
            text("UPDATE tasks SET ended_at = :at WHERE task_id = :t"),
            {"at": NOW - timedelta(days=400), "t": old.task_id},
        )
    totals = await gc(engine, inner, FakeTemporal())

    t = old.task_id
    for table, column in (
        ("checkpoints", "task_id"),
        ("agent_sessions", "session_id"),
        ("agent_messages", "session_id"),
        ("task_inbox", "task_id"),
        ("idempotency_keys", "task_id"),
        ("sample_orders", "task_id"),
        ("event_batches", "workflow_id"),
        ("agent_events", "workflow_id"),
    ):
        assert await one(engine, f"SELECT count(*) FROM {table} WHERE {column} = :t", t=t) == 0, (
            table
        )
    # The message to itself went; the one to a running task is kept.
    assert await one(engine, "SELECT count(*) FROM task_messages WHERE sender_task = :t", t=t) == 1
    assert (
        await one(engine, "SELECT retained_base FROM event_logs WHERE workflow_id = :t", t=t) == 6
    )
    lines: list[str] = []

    async def closed() -> bool:
        return True

    await cli.print_events(
        TableTransport(engine), t, 0, follow=False, closed=closed, write=lines.append
    )
    assert lines == ["expired: events before 6 were pruned"]
    assert {"events expired", "agent_sessions expired", "task_messages expired"} <= set(
        totals.by_reason
    )


async def test_a_second_gc_or_a_delete_fails_at_once_while_gc_runs(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4 across several batches (review F141): while one gc is between batches,
    another gc and a request delete fail at once; the first then completes."""
    import asyncio

    from common.persistence.removal import Batch, RemovalEngine
    from orchestrator.lifecycle import delete_request

    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    for _ in range(3):
        await ended(engine, store, 100)
    other = await ended(engine, store, 1)
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
    first = asyncio.create_task(gc(engine, inner, FakeTemporal()))
    await asyncio.wait_for(paused.wait(), 30)
    with pytest.raises(RemovalBusy):
        await asyncio.wait_for(gc(engine, inner, FakeTemporal(), dry_run=True), 5)
    with pytest.raises(RemovalBusy):
        await asyncio.wait_for(delete_request(engine, inner, FakeTemporal(), other.request_id), 5)
    resume.set()
    totals = await first
    assert totals.batches > 2
    monkeypatch.undo()
    await delete_request(engine, inner, FakeTemporal(), other.request_id)  # free again


async def test_bytes_back_under_a_removed_row_are_removed_again(engine: AsyncEngine) -> None:
    """F145 (R6, R15): a re-upload whose transaction never committed leaves the
    bytes in the bucket under a row still marked and bucket-deleted; gc removes
    them again, while bytes a committed put revived stay."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    content = f"input {uuid.uuid4()}".encode()
    old = await ended(engine, store, 100, **{"in.txt": content})
    removed = old.inputs["in.txt"]
    await gc(engine, inner, FakeTemporal())
    assert removed.key not in inner.objects
    # The upload of a put whose commit then failed: bytes in, row rolled back.
    await inner.put(content, retention="transcript")
    assert removed.key in inner.objects
    totals = await gc(engine, inner, FakeTemporal())
    assert removed.key not in inner.objects
    assert totals.finished >= 1

"""Events leave only through `TableTransport.prune`, run in removal batches with
their tombstones and references marked (Phase 3A persistence plan phase 02 task
1.4; D6, D11)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.blob_store import MemoryBlobStore
from common.events import Expired, TableTransport, Writer
from common.persistence.removal import (
    BATCH_LIMIT,
    Batch,
    RemovalBusy,
    RemovalEngine,
    operation_id,
)
from common.persistence.repositories import RecordingBlobStore
from common.schemas import BlobRef
from common.schemas.events import AgentEvent
from orchestrator import cli
from orchestrator.lifecycle import event_batch, prune_events
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration


class Crash(Exception):
    pass


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # A scratch database: a removal run finishes every marked blob it finds.
    async with scratch_database("head") as (_, eng):
        yield eng


def new_workflow() -> str:
    return f"wf-prune-{uuid.uuid4().hex[:12]}"


async def publish(engine: AsyncEngine, wf: str, n: int, attachment: BlobRef | None = None) -> None:
    """`n` events in batches of 64; the first carries `attachment`."""
    transport = TableTransport(engine)
    for start in range(0, n, 64):
        events = [
            AgentEvent(
                seq=i,
                timestamp=datetime.now(UTC),
                workflow_id=wf,
                task_id=wf,
                attempt_id=f"{wf}:1:1",
                type="tool_result" if i == 0 and attachment else "token",
                payload={"i": i},
                blob_ref=attachment if i == 0 else None,
            )
            for i in range(start, min(start + 64, n))
        ]
        await transport.publish(wf, Writer(wf, 1, 1), f"{wf}:1:1:{start}", events)


async def tombstones(engine: AsyncEngine, op: str) -> list[dict[str, int]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT details FROM audit_log WHERE operation_id = :o ORDER BY id"), {"o": op}
        )
        return [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]


async def event_count(engine: AsyncEngine, wf: str) -> int:
    async with engine.connect() as conn:
        found = await conn.execute(
            text("SELECT count(*) FROM agent_events WHERE workflow_id = :w"), {"w": wf}
        )
        return int(found.scalar_one())


async def test_a_gc_prune_reads_as_expired_not_as_a_gap(engine: AsyncEngine) -> None:
    wf = new_workflow()
    await publish(engine, wf, 30)
    totals, base = await prune_events(engine, MemoryBlobStore(), wf, below=31)
    assert (totals.rows, base) == (30, 31)
    lines: list[str] = []

    async def closed() -> bool:
        return True

    await cli.print_events(
        TableTransport(engine), wf, 0, follow=False, closed=closed, write=lines.append
    )
    assert lines == ["expired: events before 31 were pruned"]
    items = [item async for item in TableTransport(engine).read(wf, 0, follow=False)]
    assert items == [Expired(31)]


async def test_an_attached_blob_is_marked_and_removed_with_its_event(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    wf = new_workflow()
    attachment = await store.put(f"attachment {wf}".encode(), retention="transcript")
    # Stored with no task, so only the event will hold it.
    await publish(engine, wf, 3, attachment)
    totals, _ = await prune_events(engine, inner, wf, below=4)
    assert (totals.rows, totals.references, totals.blobs) == (3, 1, 1)
    assert attachment.key not in inner.objects
    [stone] = await tombstones(engine, totals.operation)
    assert stone["rows"] == 3 and stone["references"] == 1 and stone["blobs"] == 1


async def test_a_long_log_is_pruned_in_batches_of_at_most_500(engine: AsyncEngine) -> None:
    wf = new_workflow()
    await publish(engine, wf, 1200)
    dry, _ = await prune_events(engine, MemoryBlobStore(), wf, below=1201, dry_run=True)
    assert dry.rows == 1200 and await event_count(engine, wf) == 1200  # nothing changed
    assert await tombstones(engine, dry.operation) == []

    totals, base = await prune_events(engine, MemoryBlobStore(), wf, below=1201)
    assert base == 1201 and await event_count(engine, wf) == 0
    stones = await tombstones(engine, totals.operation)
    assert [s["rows"] for s in stones] == [BATCH_LIMIT, BATCH_LIMIT, 200]
    assert sum(s["rows"] for s in stones) == totals.rows == 1200


async def test_a_prune_and_its_tombstone_commit_together(engine: AsyncEngine) -> None:
    """A run killed during a batch leaves neither; one killed after it, both."""
    wf = new_workflow()
    await publish(engine, wf, 10)
    op = operation_id("gc")
    transport = TableTransport(engine)
    batch, _ = event_batch(transport, wf, below=6, older_than=None, limit=BATCH_LIMIT, operation=op)
    pruned = batch.rows
    assert pruned is not None

    async def prune_then_crash(conn: AsyncConnection) -> int:
        await pruned(conn)
        raise Crash

    batch.rows = prune_then_crash
    with pytest.raises(Crash):
        await RemovalEngine(engine, MemoryBlobStore(), op).run(batch)
    assert await event_count(engine, wf) == 10 and await tombstones(engine, op) == []

    removal = RemovalEngine(engine, MemoryBlobStore(), op)

    async def crash(keys: object) -> int:
        raise Crash

    removal.finish = crash  # type: ignore[method-assign]
    batch, _ = event_batch(transport, wf, below=6, older_than=None, limit=BATCH_LIMIT, operation=op)
    with pytest.raises(Crash):
        await removal.run(batch)
    assert await event_count(engine, wf) == 5
    [stone] = await tombstones(engine, op)
    assert stone["rows"] == 5


async def test_prune_marks_the_pruned_events_references(engine: AsyncEngine) -> None:
    store = RecordingBlobStore(MemoryBlobStore(), engine)
    wf = new_workflow()
    attachment = await store.put(f"attachment {wf}".encode(), retention="transcript")
    await publish(engine, wf, 2, attachment)
    async with engine.begin() as conn:
        base = await TableTransport(engine).prune(
            wf, below=2, conn=conn, limit=BATCH_LIMIT, removed_by="prune:direct"
        )
        marks = await conn.execute(
            text("SELECT removed_by FROM blob_refs WHERE holder_key = :k"), {"k": f"{wf}/1"}
        )
        assert base == 2 and [m[0] for m in marks] == ["prune:direct"]
    async with engine.begin() as conn:  # the limit caps the events deleted
        assert await TableTransport(engine).prune(wf, below=3, conn=conn, limit=0) == 2


async def test_a_second_run_fails_at_once_while_the_first_holds_the_lock(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D4: one removal run at a time, across all of its batches."""
    wf, other = new_workflow(), new_workflow()
    await publish(engine, wf, 1200)  # three batches
    await publish(engine, other, 5)
    between_batches = asyncio.Event()
    resume = asyncio.Event()
    real_run = RemovalEngine.run
    runs = 0

    async def pausing_run(self: RemovalEngine, batch: Batch) -> Any:
        nonlocal runs
        runs += 1
        if runs == 2:  # after the first batch committed
            between_batches.set()
            await resume.wait()
        return await real_run(self, batch)

    monkeypatch.setattr(RemovalEngine, "run", pausing_run)
    first = asyncio.create_task(prune_events(engine, MemoryBlobStore(), wf, below=1201))
    await asyncio.wait_for(between_batches.wait(), 30)
    with pytest.raises(RemovalBusy):  # at once, not after the first run
        await asyncio.wait_for(
            prune_events(engine, MemoryBlobStore(), other, below=6, dry_run=True), 5
        )
    resume.set()
    totals, base = await first
    assert (totals.batches, totals.rows, base) == (3, 1200, 1201)
    monkeypatch.undo()
    totals, base = await prune_events(engine, MemoryBlobStore(), other, below=6)  # free again
    assert (totals.rows, base) == (5, 6)

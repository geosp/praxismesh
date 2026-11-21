"""The removal engine: rows, references, blob marks and the tombstone in one
transaction, then the bucket, and a rerun that finishes what a crash left
(Phase 3A persistence plan phase 02 task 1.2; R3, R13, R15, D6)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.blob_store import BlobExpired, MemoryBlobStore
from common.persistence.removal import Batch, RemovalEngine, live_references, operation_id
from common.persistence.repositories import RecordingBlobStore
from tests.support.lifecycle import StoredTask, end_task, record_task
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration


class Crash(Exception):
    pass


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # A scratch database: a removal run finishes every marked blob it finds.
    async with scratch_database("head") as (_, eng):
        yield eng


async def task_batch(engine: AsyncEngine, stored: StoredTask, op: str) -> Batch:
    async with engine.connect() as conn:
        held = await live_references(conn, [stored.task_id])
    return Batch("test.remove", f"task:{stored.task_id}", held, details={"reason": op})


async def tombstones(engine: AsyncEngine, op: str) -> list[dict[str, object]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT action, subject, details FROM audit_log WHERE operation_id = :o"),
            {"o": op},
        )
        return [
            {
                "action": r[0],
                "subject": r[1],
                **(r[2] if isinstance(r[2], dict) else json.loads(r[2])),
            }
            for r in rows
        ]


async def blob_state(engine: AsyncEngine, key: str) -> tuple[bool, bool]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT removed_at IS NOT NULL, bucket_deleted_at IS NOT NULL "
                    "FROM blob_objects WHERE key = :k"
                ),
                {"k": key},
            )
        ).one()
        return bool(row[0]), bool(row[1])


async def test_a_shared_blob_survives_while_another_task_holds_it(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    shared = f"shared bytes {uuid.uuid4()}".encode()
    a = await end_task(engine, store, await record_task(engine, store, inputs={"x": shared}))
    b = await end_task(engine, store, await record_task(engine, store, inputs={"x": shared}))
    op = operation_id("test")
    batch = await task_batch(engine, a, op)
    result = await RemovalEngine(engine, inner, op).run(batch)

    # a's instructions and input, each held by its row and by a's upload reference
    assert result.references == len(batch.references) == 4
    assert a.inputs["x"].key not in result.marked  # b still holds it (R3)
    assert await store.get(b.inputs["x"]) == shared
    assert result.marked == (a.instructions.key,)
    with pytest.raises(BlobExpired):
        await store.get(a.instructions)
    assert a.instructions.key not in inner.objects  # the bucket step ran
    assert await blob_state(engine, a.instructions.key) == (True, True)
    [stone] = await tombstones(engine, op)
    assert stone["rows"] == 0 and stone["references"] == result.references
    assert stone["blobs"] == 1 and stone["subject"] == f"task:{a.task_id}"


async def test_a_dry_run_changes_nothing_and_reports_the_same_counts(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    a = await end_task(engine, store, await record_task(engine, store))
    op = operation_id("test")
    batch = await task_batch(engine, a, op)
    dry_removal = RemovalEngine(engine, inner, op, dry_run=True)
    async with dry_removal.session():
        dry = await dry_removal.run(batch)
    assert dry.tombstone is None and await tombstones(engine, op) == []
    assert await store.get(a.instructions) and a.instructions.key in inner.objects
    real = await RemovalEngine(engine, inner, op).run(batch)
    assert (dry.rows, dry.references, dry.blobs) == (real.rows, real.references, real.blobs)


async def test_a_crash_inside_the_batch_leaves_nothing(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    a = await end_task(engine, store, await record_task(engine, store))
    op = operation_id("test")
    batch = await task_batch(engine, a, op)

    async def rows(conn: AsyncConnection) -> int:
        await conn.execute(text("DELETE FROM task_inbox WHERE task_id = :t"), {"t": a.task_id})
        raise Crash

    batch.rows = rows
    with pytest.raises(Crash):
        await RemovalEngine(engine, inner, op).run(batch)
    assert await tombstones(engine, op) == []
    assert await store.get(a.instructions)
    async with engine.connect() as conn:
        assert len(await live_references(conn, [a.task_id])) == len(batch.references)


async def test_a_crash_before_the_bucket_step_is_finished_by_the_next_run(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    a = await end_task(engine, store, await record_task(engine, store))
    op = operation_id("test")
    removal = RemovalEngine(engine, inner, op)

    async def crash(keys: object) -> int:
        raise Crash

    monkeypatch.setattr(removal, "finish", crash)
    with pytest.raises(Crash):
        await removal.run(await task_batch(engine, a, op))
    monkeypatch.undo()
    assert len(await tombstones(engine, op)) == 1  # committed with its tombstone (R13)
    assert await blob_state(engine, a.instructions.key) == (True, False)
    assert a.instructions.key in inner.objects
    with pytest.raises(BlobExpired):  # marked: reads as expired already
        await store.get(a.instructions)

    rerun = RemovalEngine(engine, inner, operation_id("test"))
    assert a.instructions.key in await rerun.pending()
    await rerun.finish_pending()
    assert a.instructions.key not in inner.objects
    assert await blob_state(engine, a.instructions.key) == (True, True)
    assert len(await tombstones(engine, op)) == 1  # nothing counted twice (R15)


async def test_a_crash_after_the_bucket_delete_is_finished_by_the_next_run(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    a = await end_task(engine, store, await record_task(engine, store))
    op = operation_id("test")
    removal = RemovalEngine(engine, inner, op)

    async def crash(key: str) -> None:
        raise Crash

    monkeypatch.setattr(removal, "after_bucket_delete", crash)
    with pytest.raises(Crash):
        await removal.run(await task_batch(engine, a, op))
    assert a.instructions.key not in inner.objects  # deleted, not recorded
    assert await blob_state(engine, a.instructions.key) == (True, False)

    rerun = RemovalEngine(engine, inner, operation_id("test"))
    assert await rerun.finish_pending() >= 1  # the missing object is not an error
    assert await blob_state(engine, a.instructions.key) == (True, True)


async def test_a_put_between_the_batch_and_the_bucket_step_keeps_the_object(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    a = await end_task(engine, store, await record_task(engine, store))
    op = operation_id("test")
    removal = RemovalEngine(engine, inner, op)
    real_finish = removal.finish

    async def put_first(keys: tuple[str, ...]) -> int:
        await store.put(f"instructions {a.task_id}".encode(), retention="transcript")
        return await real_finish(keys)

    monkeypatch.setattr(removal, "finish", put_first)
    await removal.run(await task_batch(engine, a, op))
    assert a.instructions.key in inner.objects  # the mark was cleared: kept
    assert await blob_state(engine, a.instructions.key) == (False, False)
    assert await store.get(a.instructions)

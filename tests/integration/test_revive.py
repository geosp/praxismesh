"""Uploading removed bytes again makes them live; a delete's own marks stay
(Phase 3A persistence plan phase 02 task 1.3; R22, D10; notes.md#revive,
notes.md#d2)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import MemoryBlobStore
from common.persistence import refs
from common.persistence.removal import Batch, RemovalEngine, live_references, operation_id
from common.persistence.repositories import RecordingBlobStore
from orchestrator.lifecycle import delete_request, gc
from tests.support.lifecycle import FakeTemporal, StoredTask, end_task, record_task
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # A scratch database: a removal run finishes every marked blob it finds.
    async with scratch_database("head") as (_, eng):
        yield eng


async def remove_task(
    engine: AsyncEngine, inner: MemoryBlobStore, stored: StoredTask, kind: str
) -> RemovalEngine:
    """Mark every reference the task holds, as a GC or delete batch does, and
    return the engine (bucket step done)."""
    async with engine.connect() as conn:
        held = await live_references(conn, [stored.task_id])
    removal = RemovalEngine(engine, inner, operation_id(kind))
    await removal.run(Batch(f"test.{kind}", f"task:{stored.task_id}", held))
    return removal


async def ref_marks(engine: AsyncEngine, task_id: str, key: str) -> set[str | None]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT removed_by FROM blob_refs WHERE task_id = :t AND blob_key = :k"),
            {"t": task_id, "k": key},
        )
        return {r[0] for r in rows}


async def blob_row(engine: AsyncEngine, key: str) -> tuple[bool, bool, datetime]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT removed_at IS NOT NULL, bucket_deleted_at IS NOT NULL, last_put_at "
                    "FROM blob_objects WHERE key = :k"
                ),
                {"k": key},
            )
        ).one()
        return bool(row[0]), bool(row[1]), row[2]


async def test_a_file_resubmitted_after_a_delete_is_live_again(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    data = f"orders.csv {uuid.uuid4()}".encode()
    old = await end_task(engine, store, await record_task(engine, store, inputs={"in": data}))
    await remove_task(engine, inner, old, "delete")
    key = old.inputs["in"].key
    assert key not in inner.objects and (await blob_row(engine, key))[0]

    new = await record_task(engine, store, inputs={"in": data})  # the same file again
    assert await store.get(new.inputs["in"]) == data  # uploaded again, readable (R22)
    assert (await blob_row(engine, key))[:2] == (False, False)
    assert await ref_marks(engine, new.task_id, key) == {None}  # live for the new task
    # The deleted task's references keep the delete's mark (D10).
    [mark] = await ref_marks(engine, old.task_id, key)
    assert mark is not None and mark.startswith(refs.DELETE_OPERATION)


async def test_a_put_between_the_mark_and_the_bucket_delete_keeps_the_object(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    data = f"report {uuid.uuid4()}".encode()
    old = await end_task(engine, store, await record_task(engine, store, inputs={"in": data}))
    key = old.inputs["in"].key
    async with engine.connect() as conn:
        held = await live_references(conn, [old.task_id])
    removal = RemovalEngine(engine, inner, operation_id("gc"))
    real_finish = removal.finish
    other = f"task-revive-{uuid.uuid4().hex[:12]}"

    async def put_then_finish(keys: tuple[str, ...]) -> int:
        await store.put(data, retention="transcript", task_id=other)
        return await real_finish(keys)

    monkeypatch.setattr(removal, "finish", put_then_finish)
    result = await removal.run(Batch("test.gc", f"task:{old.task_id}", held))
    assert key in result.marked  # the batch marked it
    assert key in inner.objects  # the bucket step saw the cleared mark (R22)
    assert (await blob_row(engine, key))[:2] == (False, False)
    assert await ref_marks(engine, other, key) == {None}


async def test_a_put_after_the_bucket_delete_uploads_the_bytes_again(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    data = f"log {uuid.uuid4()}".encode()
    old = await end_task(engine, store, await record_task(engine, store, inputs={"in": data}))
    await remove_task(engine, inner, old, "gc")
    key = old.inputs["in"].key
    assert key not in inner.objects

    other = f"task-revive-{uuid.uuid4().hex[:12]}"
    ref = await store.put(data, retention="transcript", task_id=other)
    assert inner.objects[key].data == data and await store.get(ref) == data
    assert (await blob_row(engine, key))[:2] == (False, False)


async def test_an_old_orphan_uploaded_again_restarts_its_window(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    data = f"orphan {uuid.uuid4()}".encode()
    ref = await store.put(data, retention="ephemeral")  # no task: an orphan
    old_put = datetime.now(UTC) - timedelta(days=3)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE blob_objects SET last_put_at = :at WHERE key = :k"),
            {"at": old_put, "k": ref.key},
        )
        orphans = {o.key: o for o in await refs.orphaned(conn, await inner.list_objects())}
    assert orphans[ref.key].last_put_at == old_put  # past the 24-hour window

    task = f"task-revive-{uuid.uuid4().hex[:12]}"
    await store.put(data, retention="transcript", task_id=task)
    assert (await blob_row(engine, ref.key))[2] > old_put  # the window restarts (D5)
    async with engine.connect() as conn:
        later = {o.key for o in await refs.orphaned(conn, await inner.list_objects())}
    assert ref.key not in later  # the upload reference keeps it live
    assert await ref_marks(engine, task, ref.key) == {None}


async def test_a_file_resubmitted_after_a_request_delete_survives_the_next_gc(
    engine: AsyncEngine,
) -> None:
    """R22 scenario 1 end to end (review F132): delete a request, submit the same
    file again, run gc: the new task still reads it."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    data = f"orders.csv {uuid.uuid4()}".encode()
    old = await end_task(engine, store, await record_task(engine, store, inputs={"in": data}))
    await delete_request(engine, inner, FakeTemporal(), old.request_id)
    new = await record_task(engine, store, inputs={"in": data})
    await gc(engine, inner, FakeTemporal())
    assert await store.get(new.inputs["in"]) == data

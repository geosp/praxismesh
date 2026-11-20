"""`RecordingBlobStore.put` records each upload for its task, in one transaction
with its `blob_objects` row (Phase 3A persistence plan phase 01 task 2.2; R1, D2,
D10; notes.md#revive steps 1-2)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import BlobNotFound, MemoryBlobStore
from common.persistence.refs import DELETE_OPERATION
from common.persistence.repositories import RecordingBlobStore, TaskRepository, make_engine
from orchestrator.submit import prepare_task
from registry.loader import load_registry

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


async def test_submit_uploads_are_held_by_their_task_before_record_task(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    unique = uuid.uuid4().hex
    (tmp_path / "notes.txt").write_text(f"SKU-1 x3 {unique}")
    (tmp_path / "more.txt").write_text(f"SKU-2 x1 {unique}")  # R1: two input files
    (tmp_path / "copy.txt").write_text(f"SKU-1 x3 {unique}")  # same bytes: one reference
    store = RecordingBlobStore(MemoryBlobStore(), engine)
    start = await prepare_task(
        {
            "profile": "openai",
            "instructions": f"Order it. {unique}",
            "input_files": ["notes.txt", "more.txt", "copy.txt"],
        },
        load_registry(),
        store,
        base_dir=tmp_path,
    )
    assert await TaskRepository(engine).get(start.task_id) is None  # no row yet
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT holder_table, holder_key, holder_column, blob_key, request_id, "
                "removed_at FROM blob_refs WHERE task_id = :t"
            ),
            {"t": start.task_id},
        )
        held = {tuple(r) for r in rows}
        put = await conn.execute(
            text("SELECT key, last_put_at FROM blob_objects WHERE key = ANY(:k)"),
            {
                "k": [
                    start.instructions_ref.key,
                    start.input_refs["notes.txt"].key,
                    start.input_refs["more.txt"].key,
                ]
            },
        )
        recorded = list(put)
        assert len(recorded) == 3 and all(r.last_put_at is not None for r in recorded)
    assert held == {
        ("upload", start.task_id, "", start.instructions_ref.key, None, None),
        ("upload", start.task_id, "", start.input_refs["notes.txt"].key, None, None),
        ("upload", start.task_id, "", start.input_refs["more.txt"].key, None, None),
    }
    assert start.input_refs["copy.txt"].key == start.input_refs["notes.txt"].key


async def test_repeat_put_clears_a_removal_and_keeps_the_stronger_class(
    engine: AsyncEngine,
) -> None:
    store = RecordingBlobStore(MemoryBlobStore(), engine)
    task = f"task-test-{uuid.uuid4().hex[:12]}"
    data = f"bytes for {task}".encode()
    ref = await store.put(data, retention="artifact", task_id=task)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE blob_objects SET removed_at = now(), removed_by = 'gc:op', "
                "bucket_deleted_at = now(), last_put_at = now() - interval '2 days' "
                "WHERE key = :k"
            ),
            {"k": ref.key},
        )
    await store.put(data, retention="checkpoint")  # no task: no upload reference
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT retention_class, removed_at, removed_by, bucket_deleted_at, "
                    "last_put_at > now() - interval '1 minute' AS recent "
                    "FROM blob_objects WHERE key = :k"
                ),
                {"k": ref.key},
            )
        ).one()
        holders = await conn.execute(
            text("SELECT holder_key, retention_class FROM blob_refs WHERE blob_key = :k"),
            {"k": ref.key},
        )
        assert [tuple(h) for h in holders] == [(task, "artifact")]
    assert row.retention_class == "artifact"
    assert (row.removed_at, row.removed_by, row.bucket_deleted_at) == (None, None, None)
    assert row.recent


async def _delete_task(engine: AsyncEngine, task: str, keys: list[str]) -> None:
    """What a phase 02 delete leaves: the task's references and blobs marked by a
    delete, the bucket step done."""
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE blob_refs SET removed_at = now(), removed_by = :by WHERE task_id = :t"),
            {"t": task, "by": f"{DELETE_OPERATION}op-{task}"},
        )
        await conn.execute(
            text(
                "UPDATE blob_objects SET removed_at = now(), removed_by = :by, "
                "bucket_deleted_at = now() WHERE key = ANY(:k)"
            ),
            {"k": keys, "by": f"{DELETE_OPERATION}op-{task}"},
        )


async def test_a_deleted_tasks_late_upload_of_the_same_bytes_revives_nothing(
    engine: AsyncEngine,
) -> None:
    """Review F80 (R25, R10, D10): the blob stays marked and the bytes stay gone."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    task = f"task-test-{uuid.uuid4().hex[:12]}"
    data = f"workspace of {task}".encode()
    ref = await store.put(data, retention="checkpoint", task_id=task)
    await inner.delete(ref)  # the bucket step
    await _delete_task(engine, task, [ref.key])
    late = await store.put(data, retention="checkpoint", task_id=task)
    assert late.key == ref.key
    with pytest.raises(BlobNotFound):
        await inner.get(late)
    async with engine.connect() as conn:
        blob = (
            await conn.execute(
                text("SELECT removed_by, bucket_deleted_at FROM blob_objects WHERE key = :k"),
                {"k": ref.key},
            )
        ).one()
        live = await conn.execute(
            text("SELECT count(*) FROM blob_refs WHERE task_id = :t AND removed_at IS NULL"),
            {"t": task},
        )
        assert live.scalar_one() == 0
    assert blob.removed_by == f"{DELETE_OPERATION}op-{task}" and blob.bucket_deleted_at


async def test_a_deleted_tasks_late_upload_of_new_bytes_leaves_no_live_reference(
    engine: AsyncEngine,
) -> None:
    """Review F81 (R25, D2): new bytes from a deleted task's stale attempt."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    task = f"task-test-{uuid.uuid4().hex[:12]}"
    ref = await store.put(f"first {task}".encode(), retention="checkpoint", task_id=task)
    await _delete_task(engine, task, [ref.key])
    late = await store.put(f"later {task}".encode(), retention="checkpoint", task_id=task)
    with pytest.raises(BlobNotFound):
        await inner.get(late)  # never uploaded
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT blob_key, removed_by FROM blob_refs WHERE task_id = :t"),
            {"t": task},
        )
        marks = {r.blob_key: r.removed_by for r in rows}
        blob = (
            await conn.execute(
                text("SELECT removed_by, bucket_deleted_at FROM blob_objects WHERE key = :k"),
                {"k": late.key},
            )
        ).one()
    assert marks == {k: f"{DELETE_OPERATION}op-{task}" for k in (ref.key, late.key)}
    assert blob.removed_by == f"{DELETE_OPERATION}op-{task}" and blob.bucket_deleted_at

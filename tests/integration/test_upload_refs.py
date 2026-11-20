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

from common.blob_store import MemoryBlobStore
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
    store = RecordingBlobStore(MemoryBlobStore(), engine)
    start = await prepare_task(
        {"profile": "openai", "instructions": f"Order it. {unique}", "input_files": ["notes.txt"]},
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
            {"k": [start.instructions_ref.key, start.input_refs["notes.txt"].key]},
        )
        recorded = list(put)
        assert len(recorded) == 2 and all(r.last_put_at is not None for r in recorded)
    assert held == {
        ("upload", start.task_id, "", start.instructions_ref.key, None, None),
        ("upload", start.task_id, "", start.input_refs["notes.txt"].key, None, None),
    }


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

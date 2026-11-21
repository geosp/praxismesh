"""A blob whose removal is recorded reads as expired, naming the date (Phase 3A
persistence plan phase 02 task 1.1; R9, D6)."""

from __future__ import annotations

import argparse
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import BlobExpired, MemoryBlobStore
from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore, make_engine
from orchestrator import cli
from tests.support.lifecycle import end_task, record_task

pytestmark = pytest.mark.integration

REMOVED = datetime(2026, 11, 2, 3, 4, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


async def mark_removed(engine: AsyncEngine, key: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE blob_objects SET removed_at = :at, removed_by = 'gc:test' WHERE key = :k"),
            {"at": REMOVED, "k": key},
        )


async def test_get_stream_and_stat_raise_expired_with_the_date(engine: AsyncEngine) -> None:
    store = RecordingBlobStore(MemoryBlobStore(), engine)
    ref = await store.put(f"expiring {uuid.uuid4()}".encode(), retention="artifact")
    assert await store.get(ref)  # live: reads
    await mark_removed(engine, ref.key)
    with pytest.raises(BlobExpired, match="expired: removed on 2026-11-02 03:04 UTC") as error:
        await store.get(ref)
    assert error.value.removed_at == REMOVED
    with pytest.raises(BlobExpired):
        await store.stat(ref)
    with pytest.raises(BlobExpired):
        [chunk async for chunk in store.stream(ref)]


async def test_task_output_reports_an_expired_artifact(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    stored = await record_task(engine, store)
    await end_task(
        engine, store, stored, artifacts={"report.md": f"report {uuid.uuid4()}".encode()}
    )
    monkeypatch.setattr(S3BlobStore, "from_env", lambda: inner)
    args = argparse.Namespace(task_id=stored.task_id, path="report.md", to=None)

    await mark_removed(engine, stored.artifacts["report.md"].key)
    with pytest.raises(BlobExpired, match="expired: removed on 2026-11-02") as error:
        await cli.output(args)
    assert "not found" not in str(error.value)

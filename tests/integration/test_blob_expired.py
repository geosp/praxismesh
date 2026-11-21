"""A blob whose removal is recorded reads as expired, naming the date (Phase 3A
persistence plan phase 02 task 1.1; R9, D6)."""

from __future__ import annotations

import argparse
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import BlobExpired, MemoryBlobStore
from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore
from orchestrator import cli
from orchestrator.lifecycle import gc
from tests.support.lifecycle import Borrowed, FakeTemporal, end_task, record_task
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration

REMOVED = datetime(2026, 11, 2, 3, 4, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # A scratch database: the marks these tests set never reach the stack's (F133).
    async with scratch_database("head") as (_, eng):
        yield eng


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


async def test_task_output_reports_an_artifact_gc_removed(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R9 end to end (review F132): gc removes the artifact of a task that ended
    100 days ago; `task output` reports it expired, with the date, not missing."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    stored = await record_task(engine, store)
    await end_task(
        engine,
        store,
        stored,
        artifacts={"report.md": f"report {uuid.uuid4()}".encode()},
        ended_at=datetime.now(UTC) - timedelta(days=100),
    )
    await gc(engine, inner, FakeTemporal())
    monkeypatch.setattr(cli, "make_engine", lambda: Borrowed(engine))
    monkeypatch.setattr(S3BlobStore, "from_env", lambda: inner)
    args = argparse.Namespace(task_id=stored.task_id, path="report.md", to=None)
    today = f"{datetime.now(UTC):%Y-%m-%d}"
    with pytest.raises(BlobExpired, match=f"expired: removed on {today}") as error:
        await cli.output(args)
    assert "not found" not in str(error.value)

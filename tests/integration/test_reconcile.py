"""`agentctl reconcile [--reindex]` lists what is inconsistent and changes nothing
without `--reindex` (Phase 3A persistence plan phase 03 task 1.1; R17, D4).

Each test seeds one case on a scratch database migrated to head, with an
in-memory bucket.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import MemoryBlobStore
from common.persistence.removal import RemovalBusy, run_lock
from common.persistence.repositories import RecordingBlobStore
from orchestrator.reconcile import reconcile
from tests.support.lifecycle import FakeTemporal, end_task, one, record_task
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    async with scratch_database("head") as (_, eng):
        yield eng


async def snapshot(engine: AsyncEngine) -> tuple[object, ...]:
    """Counts that a read-only reconcile must leave as they were."""
    return tuple(
        [
            await one(engine, f"SELECT count(*) FROM {t}")
            for t in ("blob_refs", "blob_objects", "audit_log", "tasks")
        ]
    )


async def test_a_consistent_store_is_clean(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    stored = await record_task(engine, store, inputs={"a.csv": b"a"})
    await end_task(engine, store, stored, artifacts={"out.md": b"out"})
    report = await reconcile(engine, inner, FakeTemporal())
    assert report.clean, report.as_json()


async def test_a_missing_blob_is_listed_as_dangling(engine: AsyncEngine) -> None:
    """A restored backup whose bucket copy missed one blob (R17)."""
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    stored = await record_task(engine, store, inputs={"a.csv": b"lost bytes"})
    await end_task(engine, store, stored)
    await inner.delete(stored.inputs["a.csv"])
    before = await snapshot(engine)
    report = await reconcile(engine, inner, FakeTemporal())
    assert [(r.blob_key, r.holder_table, r.holder_column) for r in report.dangling] == [
        (stored.inputs["a.csv"].key, "tasks", "input_refs"),
        (stored.inputs["a.csv"].key, "upload", ""),
    ]
    assert not report.clean
    assert await snapshot(engine) == before


async def test_an_orphan_is_listed_with_its_age(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    ref = await inner.put(b"nobody holds me", retention="ephemeral")
    now = datetime.now(UTC) + timedelta(hours=30)
    report = await reconcile(engine, inner, FakeTemporal(), now=now)
    orphans: Any = report.as_json()["orphaned"]
    (orphan,) = orphans
    assert orphan["key"] == ref.key and orphan["content_key"] is True
    assert 29.9 <= orphan["age_hours"] <= 30.1
    assert await one(engine, "SELECT count(*) FROM blob_objects") == 0  # read-only


async def test_unindexed_references_are_listed_then_reindexed(engine: AsyncEngine) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    stored = await record_task(engine, store)
    await end_task(engine, store, stored, artifacts={"out.md": b"out"})
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM blob_refs WHERE holder_table = 'tasks'"))
    before = await snapshot(engine)
    listed = await reconcile(engine, inner, FakeTemporal())
    assert {r.holder_column for r in listed.unindexed} == {"instructions_ref", "result"}
    assert listed.reindexed is None and await snapshot(engine) == before

    repaired = await reconcile(engine, inner, FakeTemporal(), reindex=True)
    assert repaired.reindexed is not None and repaired.reindexed.references == 2
    assert repaired.clean, repaired.as_json()
    again = await reconcile(engine, inner, FakeTemporal(), reindex=True)
    assert again.reindexed is not None and again.reindexed.references == 0


async def test_a_task_whose_workflow_closed_is_listed_as_never_ended(
    engine: AsyncEngine,
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    closed = await record_task(engine, store)
    gone = await record_task(engine, store)
    running = await record_task(engine, store)
    done = await end_task(engine, store, await record_task(engine, store))
    temporal = FakeTemporal({closed.task_id: "closed", running.task_id: "running"})
    report = await reconcile(engine, inner, temporal)
    assert report.never_ended == {closed.task_id: "closed", gone.task_id: "missing"}
    assert done.task_id not in temporal.asked  # only unended tasks are asked


async def test_reindex_waits_for_no_one_and_fails_on_the_run_lock(engine: AsyncEngine) -> None:
    """`--reindex` writes, so it takes D4's lock; a read-only run does not."""
    inner = MemoryBlobStore()
    async with run_lock(engine):
        assert (await reconcile(engine, inner, FakeTemporal())).clean
        with pytest.raises(RemovalBusy):
            await reconcile(engine, inner, FakeTemporal(), reindex=True)

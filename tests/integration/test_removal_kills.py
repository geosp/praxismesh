"""A delete and a GC killed partway, then run again (Phase 3A persistence plan
phase 02 task 3.3; R13, R15): every committed batch has its tombstone, the
counts sum once, and the dangling check finds nothing.

Each test runs on a scratch database migrated to head, with an in-memory bucket.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.blob_store import MemoryBlobStore
from common.blob_store.s3 import S3BlobStore
from common.persistence import refs
from common.persistence.removal import Batch, BatchResult, RemovalEngine, run_lock
from common.persistence.repositories import (
    AttemptRepository,
    Checkpoint,
    CheckpointRepository,
    RecordingBlobStore,
)
from orchestrator.lifecycle import delete_request, gc
from tests.support.lifecycle import FakeTemporal, StoredTask, end_task, new_task_id, record_task
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration


class Killed(Exception):
    pass


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    async with scratch_database("head") as (_, eng):
        yield eng


async def stored_task(
    engine: AsyncEngine, store: RecordingBlobStore, request: str, ended_days_ago: float
) -> StoredTask:
    task = new_task_id("task-kill")
    stored = await record_task(
        engine, store, task_id=task, request_id=request, inputs={"in": f"in {task}".encode()}
    )
    await AttemptRepository(engine).start(task, 1, 1, "worker-a")
    for seq in range(3):
        ws = await store.put(f"ws {task} {seq}".encode(), retention="checkpoint", task_id=task)
        await CheckpointRepository(engine).insert_fenced(
            Checkpoint(f"{task}:1:1:{seq}", task, 1, 1, seq, task, 0, ws, None)
        )
    return await end_task(
        engine,
        store,
        stored,
        artifacts={"out": f"out {task}".encode()},
        ended_at=datetime.now(UTC) - timedelta(days=ended_days_ago),
    )


def kill_at(monkeypatch: pytest.MonkeyPatch, where: str, at: int) -> None:
    """Kill the run `inside` its `at`-th batch (before it commits), or `after`
    its `at`-th committed batch (with its tombstone, before its bucket step)."""
    real_batch = RemovalEngine._batch
    real_finish = RemovalEngine.finish
    calls = {"batch": 0, "finish": 0}

    async def batch(
        self: RemovalEngine, conn: AsyncConnection, b: Batch, *, dry_run: bool
    ) -> BatchResult:
        calls["batch"] += 1
        result = await real_batch(self, conn, b, dry_run=dry_run)
        if where == "inside" and calls["batch"] == at:
            raise Killed  # the transaction rolls back: no tombstone
        return result

    async def finish(self: RemovalEngine, keys: Any) -> int:
        # A committed batch's bucket step gets its marked keys as a tuple;
        # finish_pending, at the start of a run, gets a list and is not counted,
        # nor is a batch that marked no blob (its bucket step does nothing).
        calls["finish"] += isinstance(keys, tuple) and bool(keys)
        if where == "after" and calls["finish"] == at:
            raise Killed  # committed with its tombstone; the bucket step never ran
        return await real_finish(self, keys)

    monkeypatch.setattr(RemovalEngine, "_batch", batch)
    monkeypatch.setattr(RemovalEngine, "finish", finish)


async def tombstone_counts(engine: AsyncEngine, ops: list[str]) -> dict[str, int]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT details FROM audit_log WHERE operation_id = ANY(:o)"), {"o": ops}
        )
        details = [r[0] if isinstance(r[0], dict) else json.loads(r[0]) for r in rows]
    return {k: sum(d[k] for d in details) for k in ("rows", "references", "blobs")} | {
        "tombstones": len(details)
    }


async def marked_by(engine: AsyncEngine, ops: list[str]) -> dict[str, int]:
    async with engine.connect() as conn:
        refs_marked = await conn.scalar(
            text("SELECT count(*) FROM blob_refs WHERE removed_by = ANY(:o)"), {"o": ops}
        )
        blobs_marked = await conn.scalar(
            text("SELECT count(*) FROM blob_objects WHERE removed_by = ANY(:o)"), {"o": ops}
        )
        unfinished = await conn.scalar(
            text(
                "SELECT count(*) FROM blob_objects WHERE removed_at IS NOT NULL "
                "AND bucket_deleted_at IS NULL"
            )
        )
    return {
        "references": int(refs_marked),
        "blobs": int(blobs_marked),
        "unfinished": int(unfinished),
    }


async def operations(engine: AsyncEngine, action: str) -> list[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT DISTINCT operation_id FROM audit_log WHERE action = :a"), {"a": action}
        )
        return [r[0] for r in rows]


async def check_consistent(engine: AsyncEngine, inner: MemoryBlobStore, action: str) -> None:
    ops = await operations(engine, action)
    stones, marks = await tombstone_counts(engine, ops), await marked_by(engine, ops)
    # The counts sum once: every marked reference and blob is counted by exactly
    # one tombstone, across the killed run and its rerun.
    assert stones["references"] == marks["references"] > 0
    assert stones["blobs"] == marks["blobs"] > 0
    assert marks["unfinished"] == 0  # the rerun finished the bucket steps
    async with engine.connect() as conn:
        assert await refs.dangling(conn, await inner.list_objects()) == []
        removed = await conn.execute(
            text("SELECT key FROM blob_objects WHERE removed_at IS NOT NULL")
        )
        assert not {r[0] for r in removed} & set(inner.objects)


@pytest.mark.parametrize("where", ["inside", "after"])
async def test_a_killed_delete_finishes_when_run_again(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    request = f"req-kill-{uuid.uuid4().hex[:8]}"
    for _ in range(2):
        await stored_task(engine, store, request, 0)
    kill_at(monkeypatch, where, 2)  # two tasks: two batches mark blobs
    with pytest.raises(Killed):
        await delete_request(engine, inner, FakeTemporal(), request)
    killed_ops = await operations(engine, "request.delete")
    assert (await tombstone_counts(engine, killed_ops))["tombstones"] >= 1  # R13
    # Killed after a commit: its blobs are marked, the bucket step not done.
    assert ((await marked_by(engine, killed_ops))["unfinished"] > 0) == (where == "after")

    monkeypatch.undo()
    rerun = await delete_request(
        engine, inner, FakeTemporal(), request
    )  # R15: runs again, completes
    assert (rerun.finished > 0) == (where == "after")  # F135: reported
    await check_consistent(engine, inner, "request.delete")
    async with engine.connect() as conn:
        live = await conn.scalar(
            # By task: upload references carry no request (F132).
            text(
                "SELECT count(*) FROM blob_refs WHERE removed_at IS NULL AND task_id IN "
                "(SELECT task_id FROM tasks WHERE request_id = :r)"
            ),
            {"r": request},
        )
    assert live == 0


@pytest.mark.parametrize("where", ["inside", "after"])
async def test_a_killed_gc_finishes_when_run_again(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    inner = MemoryBlobStore()
    store = RecordingBlobStore(inner, engine)
    for _ in range(3):
        await stored_task(engine, store, f"req-kill-{uuid.uuid4().hex[:8]}", 100)
    kill_at(monkeypatch, where, 2)
    with pytest.raises(Killed):
        await gc(engine, inner, FakeTemporal())
    killed_ops = await operations(engine, "gc")
    assert (await tombstone_counts(engine, killed_ops))["tombstones"] >= 1  # R13
    assert ((await marked_by(engine, killed_ops))["unfinished"] > 0) == (where == "after")

    monkeypatch.undo()
    rerun = await gc(engine, inner, FakeTemporal())
    assert (rerun.finished > 0) == (where == "after")  # F135: reported
    await check_consistent(engine, inner, "gc")
    again = await gc(engine, inner, FakeTemporal())  # nothing left: nothing counted twice
    assert (again.rows, again.references, again.blobs) == (0, 0, 0)


async def test_a_delete_whose_process_is_killed_finishes_when_run_again() -> None:
    """A real process death (SIGKILL) after a committed batch, on SeaweedFS
    (impl-review F131, F164): the dead connection releases D4's run lock and the
    request lock, the batch's tombstone is there, and a rerun deletes the
    remaining objects from the bucket."""
    os.environ.setdefault("S3_BUCKET", "praxismesh")
    s3 = S3BlobStore.from_env()
    s3.bucket = f"kill-{uuid.uuid4().hex[:10]}"
    await s3.ensure_bucket()
    request = f"req-kill-{uuid.uuid4().hex[:8]}"
    try:
        async with scratch_database("head") as (name, engine):
            store = RecordingBlobStore(s3, engine)
            for _ in range(2):
                await stored_task(engine, store, request, 0)
            child = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "tests.support.removal_child", name, s3.bucket, request, "1"
            )
            assert await child.wait() == -signal.SIGKILL

            killed_ops = await operations(engine, "request.delete")
            assert (await tombstone_counts(engine, killed_ops))["tombstones"] >= 1  # R13
            assert (await marked_by(engine, killed_ops))["unfinished"] > 0
            async with run_lock(engine):
                pass  # released by the dead session
            rerun = await delete_request(engine, s3, FakeTemporal(), request)  # R15
            assert rerun.finished > 0
            ops = await operations(engine, "request.delete")
            marks = await marked_by(engine, ops)
            assert (await tombstone_counts(engine, ops))["blobs"] == marks["blobs"] > 0
            assert marks["unfinished"] == 0
            listing = await s3.list_objects()
            async with engine.connect() as conn:
                assert await refs.dangling(conn, listing) == []
                removed = await conn.execute(
                    text("SELECT key FROM blob_objects WHERE removed_at IS NOT NULL")
                )
                assert not {r[0] for r in removed} & set(listing)
            assert listing == {}  # every object belonged to the request
    finally:
        for obj in s3.client.list_objects_v2(Bucket=s3.bucket).get("Contents", []):
            s3.client.delete_object(Bucket=s3.bucket, Key=obj["Key"])
        s3.client.delete_bucket(Bucket=s3.bucket)

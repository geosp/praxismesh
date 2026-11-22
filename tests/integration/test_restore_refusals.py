"""Restore refuses a stack that holds data (Phase 3A persistence plan phase 03
task 2.2; R23, D8): a task row, a Workflow in the app's namespace with no task
row, or a bucket object. Each case runs `check_empty`, the step infra/restore.sh
runs before it changes anything, on a scratch database and a bucket of its own.
The drill (`make drill`) runs the whole script on a stack."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import WorkflowExecutionStatus

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore
from common.persistence.retention import APP_TABLES
from orchestrator import backup as backup_module
from orchestrator.backup import RestoreRefused, check_empty, workflow_count
from tests.support.lifecycle import record_task
from tests.support.scratch_db import scratch_database
from tests.support.stack import run_id, scratch_bucket, temporal_client

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    async with scratch_database("head") as (_, eng):
        yield eng


@pytest.fixture
async def bucket() -> AsyncIterator[S3BlobStore]:
    async with scratch_bucket("restore", create=False) as s3:  # created by the first put
        yield s3


async def test_an_empty_stack_is_accepted(engine: AsyncEngine, bucket: S3BlobStore) -> None:
    await check_empty(engine, bucket, workflows=0)


async def test_a_database_without_tables_is_accepted(bucket: S3BlobStore) -> None:
    async with scratch_database(None) as (_, bare):
        await check_empty(bare, bucket, workflows=0)


async def snapshot(engine: AsyncEngine, bucket: S3BlobStore) -> tuple[dict[str, int], set[str]]:
    async with engine.connect() as conn:
        rows = {
            t: int(await conn.scalar(text(f"SELECT count(*) FROM {t}")) or 0) for t in APP_TABLES
        }
    return rows, set(await bucket.list_objects())


async def test_a_task_row_is_refused(engine: AsyncEngine, bucket: S3BlobStore) -> None:
    await bucket.ensure_bucket()
    await record_task(engine, RecordingBlobStore(bucket, engine))
    before = await snapshot(engine, bucket)
    with pytest.raises(RestoreRefused, match=r"tasks 1\b.*bucket .* holds objects"):
        await check_empty(engine, bucket, workflows=0)
    assert await snapshot(engine, bucket) == before  # check_empty changed nothing (F170)


async def test_rows_without_a_task_are_refused(engine: AsyncEngine, bucket: S3BlobStore) -> None:
    """Any application row counts, not only a task's (impl-review F171): an
    upload's object row whose object is gone from the bucket."""
    await bucket.ensure_bucket()
    ref = await RecordingBlobStore(bucket, engine).put(b"an upload", retention="ephemeral")
    bucket.client.delete_object(Bucket=bucket.bucket, Key=ref.key)
    with pytest.raises(RestoreRefused, match=r"rows: .*blob_objects 1") as refused:
        await check_empty(engine, bucket, workflows=0)
    assert "holds objects" not in str(refused.value)


async def test_a_workflow_without_a_task_row_is_refused(
    engine: AsyncEngine, bucket: S3BlobStore
) -> None:
    with pytest.raises(RestoreRefused, match=r"Temporal lists 1 Workflow"):
        await check_empty(engine, bucket, workflows=1)


async def test_a_bucket_object_is_refused(engine: AsyncEngine, bucket: S3BlobStore) -> None:
    await bucket.ensure_bucket()
    await bucket.put(b"left behind", retention="ephemeral")
    with pytest.raises(RestoreRefused, match="holds objects"):
        await check_empty(engine, bucket, workflows=0)


async def test_workflow_count_asks_the_app_namespace() -> None:
    """Through Temporal's API, with the CLI's client settings (ADR-0002)."""
    client = await temporal_client()
    handle = await client.start_workflow(
        "NoSuchWorkflow", id=f"count-{run_id()}", task_queue=f"no-worker-{run_id()}"
    )
    try:
        assert await workflow_count() >= 1
    finally:
        await handle.terminate("test")


async def test_restore_refuses_a_workflow_with_no_task_row(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """restore.sh's `check-empty` step as it runs (impl-review F168): an empty
    database and bucket, and a Workflow in the app's namespace counted through
    Temporal's API. The step refuses, and the Workflow is still there."""
    client = await temporal_client()
    handle = await client.start_workflow(
        "NoSuchWorkflow", id=f"restore-{run_id()}", task_queue=f"no-worker-{run_id()}"
    )
    monkeypatch.setattr(backup_module, "make_engine", lambda: engine)
    monkeypatch.setenv("S3_BUCKET", f"restore-absent-{run_id()}")
    try:
        with pytest.raises(RestoreRefused, match=r"Temporal lists \d+ Workflow") as refused:
            await backup_module._main(["check-empty"])
        assert "rows" not in str(refused.value) and "holds objects" not in str(refused.value)
        assert (await handle.describe()).status == WorkflowExecutionStatus.RUNNING
    finally:
        await handle.terminate("test")

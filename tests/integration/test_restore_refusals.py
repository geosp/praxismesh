"""Restore refuses a stack that holds data (Phase 3A persistence plan phase 03
task 2.2; R23, D8): a task row, a Workflow in the app's namespace with no task
row, or a bucket object. Each case runs `check_empty`, the step infra/restore.sh
runs before it changes anything, on a scratch database and a bucket of its own.
The drill (`make drill`) runs the whole script on a stack."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore
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


async def test_a_task_row_is_refused(engine: AsyncEngine, bucket: S3BlobStore) -> None:
    await bucket.ensure_bucket()
    stored = await record_task(engine, RecordingBlobStore(bucket, engine))
    with pytest.raises(RestoreRefused, match=r"1 task\(s\).*bucket .* holds objects"):
        await check_empty(engine, bucket, workflows=0)
    assert stored.task_id  # nothing was changed: check_empty only reads


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

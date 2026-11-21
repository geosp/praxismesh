"""Helpers for tests against the local stack. Settings come from the environment,
which `make smoke` and `make restart-check` load from infra/.env."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from temporalio.client import Client
from temporalio.worker import Worker

from common.blob_store.s3 import S3BlobStore
from tests.support.hello import HelloWorkflow, say_hello

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


WORKER_IDENTITY = "phase0-smoke-worker"


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise RuntimeError(f"{name} is not set; run through make, which loads infra/.env")
    return value


def run_id() -> str:
    return uuid.uuid4().hex[:12]


@asynccontextmanager
async def scratch_bucket(prefix: str, *, create: bool = True) -> AsyncIterator[S3BlobStore]:
    """An S3 store on a bucket of the test's own (`<prefix>-<run id>`) on the
    stack's SeaweedFS, emptied and deleted afterwards. With `create=False` the
    bucket is left to its first put, as the stack's own bucket is."""
    os.environ.setdefault("S3_BUCKET", "praxismesh")
    s3 = S3BlobStore.from_env()
    s3.bucket = f"{prefix}-{run_id()}"
    if create:
        await s3.ensure_bucket()
    try:
        yield s3
    finally:
        for key in await s3.list_objects():
            s3.client.delete_object(Bucket=s3.bucket, Key=key)
        with suppress(s3.client.exceptions.NoSuchBucket):
            s3.client.delete_bucket(Bucket=s3.bucket)


async def temporal_client() -> Client:
    address = f"127.0.0.1:{env('TEMPORAL_PORT', '7233')}"
    try:
        return await Client.connect(
            address, namespace=env("TEMPORAL_NAMESPACE", "default"), identity=WORKER_IDENTITY
        )
    except Exception as e:
        raise RuntimeError(f"Temporal at {address} is unreachable: {e}") from e


async def run_hello(client: Client, workflow_id: str, name: str) -> str:
    """Run HelloWorkflow once with an in-process worker on a unique task queue."""
    task_queue = f"phase0-smoke-{run_id()}"
    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[HelloWorkflow],
        activities=[say_hello],
        # Fixed, so recorded histories carry no workstation hostname.
        identity=WORKER_IDENTITY,
    ):
        # Bounded, so a run killed midway leaves no Workflow running forever.
        return await client.execute_workflow(
            HelloWorkflow.run,
            name,
            id=workflow_id,
            task_queue=task_queue,
            # Longer than 3 Activity attempts of 10 s plus backoff (hello.py).
            execution_timeout=timedelta(seconds=60),
        )


async def wait_until_listed(client: Client, workflow_id: str, timeout_s: float = 10.0) -> bool:
    """Poll the visibility API, which lags behind the Workflow's completion."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    while True:
        async for _ in client.list_workflows(f"WorkflowId = '{workflow_id}'"):
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.5)


def retention_seconds(value: str) -> int:
    """Parse TEMPORAL_RETENTION (<number><s|m|h|d>, as check-prereqs.sh enforces)."""
    return int(value[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[value[-1]]


def s3_client(secret_key: str | None = None) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{env('S3_PORT', '8333')}",
        aws_access_key_id=env("S3_ACCESS_KEY"),
        aws_secret_access_key=secret_key or env("S3_SECRET_KEY"),
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 2}),
    )

"""Helpers for tests against the local stack. Settings come from the environment,
which `make smoke` and `make restart-check` load from infra/.env."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from temporalio.client import Client
from temporalio.worker import Worker

from tests.support.hello import HelloWorkflow, say_hello

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise RuntimeError(f"{name} is not set; run through make, which loads infra/.env")
    return value


def run_id() -> str:
    return uuid.uuid4().hex[:12]


async def temporal_client() -> Client:
    address = f"127.0.0.1:{env('TEMPORAL_PORT', '7233')}"
    try:
        return await Client.connect(address, namespace=env("TEMPORAL_NAMESPACE", "default"))
    except Exception as e:
        raise RuntimeError(f"Temporal at {address} is unreachable: {e}") from e


async def run_hello(client: Client, workflow_id: str, name: str) -> str:
    """Run HelloWorkflow once with an in-process worker on a unique task queue."""
    task_queue = f"phase0-smoke-{run_id()}"
    async with Worker(
        client, task_queue=task_queue, workflows=[HelloWorkflow], activities=[say_hello]
    ):
        return await client.execute_workflow(
            HelloWorkflow.run, name, id=workflow_id, task_queue=task_queue
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


def s3_client() -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{env('S3_PORT', '8333')}",
        aws_access_key_id=env("S3_ACCESS_KEY"),
        aws_secret_access_key=env("S3_SECRET_KEY"),
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 2}),
    )

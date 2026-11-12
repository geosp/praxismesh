"""Run the orchestrator and template workers in-process for integration tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from temporalio.client import Client

from common.observability import disable_sdk_tracing
from workers.main import build_worker, connect


@asynccontextmanager
async def running_workers(scratch: Path, template: str = "local-default") -> AsyncIterator[Client]:
    os.environ["PRAXIS_SCRATCH"] = str(scratch)
    # Unique queues, so running worker containers never take the test's tasks.
    os.environ["PRAXIS_QUEUE_PREFIX"] = f"test-{uuid.uuid4().hex[:8]}."
    disable_sdk_tracing()
    client = await connect("praxis-test")
    orchestrator = await build_worker(client, "orchestrator", None)
    harness = await build_worker(client, "template", template)
    async with orchestrator, harness:
        yield client

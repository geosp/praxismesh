"""`workflow_status` against the stack's Temporal, not a fake (Phase 3A
persistence plan R17, R21, D5; impl-review F130): a Workflow waiting for a
worker is `running`, a terminated one `closed`, an unknown ID `missing`."""

from __future__ import annotations

import pytest

from orchestrator.workflow_status import status_of, workflow_status
from tests.support.stack import run_id, temporal_client

pytestmark = pytest.mark.integration


async def test_running_closed_and_missing() -> None:
    client = await temporal_client()
    workflow_id = f"status-{run_id()}"
    # No worker polls this queue, so the Workflow stays running.
    handle = await client.start_workflow(
        "NoSuchWorkflow", id=workflow_id, task_queue=f"no-worker-{run_id()}"
    )
    try:
        assert await workflow_status(client, workflow_id) == "running"
    finally:
        await handle.terminate("test")
    assert await workflow_status(client, workflow_id) == "closed"
    assert await status_of(client)(f"never-started-{run_id()}") == "missing"

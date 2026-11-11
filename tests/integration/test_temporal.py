"""Temporal smoke test: hello Workflow on the local stack (local-stack spec)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.support.stack import run_hello, run_id, temporal_client, wait_until_listed

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "hello_history.json"


async def test_hello_workflow() -> None:
    client = await temporal_client()
    workflow_id = f"phase0-hello-{run_id()}"

    assert await run_hello(client, workflow_id, "PraxisMesh") == "Hello, PraxisMesh!"
    assert await wait_until_listed(client, workflow_id), "Workflow not listed by visibility"

    # Re-record the replay fixture: RECORD_HELLO_HISTORY=1 make smoke
    if os.environ.get("RECORD_HELLO_HISTORY") == "1":
        history = await client.get_workflow_handle(workflow_id).fetch_history()
        FIXTURE.write_text(history.to_json())

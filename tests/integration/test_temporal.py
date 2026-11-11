"""Temporal smoke tests on the local stack (local-stack spec)."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest

from tests.support.stack import (
    env,
    retention_seconds,
    run_hello,
    run_id,
    temporal_client,
    wait_until_listed,
)

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


async def test_namespace_retention() -> None:
    """The namespace the smoke test runs in has the configured retention (§4.13)."""
    client = await temporal_client()
    namespace = env("TEMPORAL_NAMESPACE", "default")
    response = await client.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=namespace)
    )
    ttl = response.config.workflow_execution_retention_ttl.ToSeconds()
    assert ttl == retention_seconds(env("TEMPORAL_RETENTION", "72h"))


def test_ui_reachable() -> None:
    """The UI answers on its documented host port, not only inside its container."""
    url = f"http://127.0.0.1:{env('TEMPORAL_UI_PORT', '8080')}/"
    assert httpx.get(url, timeout=10).status_code == 200

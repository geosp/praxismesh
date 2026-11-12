"""A scripted task end to end through TaskWorkflow and run_harness_turn, against the
local stack with the deterministic fake model (specs execution/*; RFC Testing)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from temporalio.api.common.v1 import WorkflowExecution
from temporalio.api.workflowservice.v1 import DeleteWorkflowExecutionRequest
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError, WorkflowAlreadyStartedError

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import RecordingBlobStore, make_engine
from common.schemas import TaskResult
from orchestrator.submit import prepare_task, start_task
from registry.loader import load_registry
from tests.support.fake_model import FakeModel
from tests.support.stack import env, run_id
from tests.support.workers import running_workers
from workers.main import build_worker, connect

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[1] / "support" / "fake_model" / "order_script.json"


def order_script() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = json.loads(SCRIPT.read_text())
    return steps


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeModel]:
    with FakeModel(order_script()) as model:
        monkeypatch.setenv("VLLM_BASE_URL", model.base_url)
        yield model


async def submit(client: Client, task_id: str | None = None) -> tuple[str, Any]:
    engine = make_engine()
    s3 = S3BlobStore.from_env()
    await s3.ensure_bucket()
    data: dict[str, Any] = {
        "profile": "default",
        "instructions": "Order 3 units of SKU-1 and write order-summary.md.",
        "outputs": ["order-summary.md"],
    }
    if task_id:
        data["task_id"] = task_id
    start = await prepare_task(
        data, load_registry(), RecordingBlobStore(s3, engine), base_dir=Path.cwd()
    )
    await engine.dispose()
    return start.task_id, await start_task(client, start)


async def test_scripted_task_end_to_end(tmp_path: Path, fake: FakeModel) -> None:
    async with running_workers(tmp_path) as client:
        task_id, handle = await submit(client)
        result = TaskResult.model_validate(await handle.result())
    assert result.status == "succeeded", result.failure_reason
    assert result.summary == "Ordered 3 x SKU-1." and result.turns == 1
    assert result.tokens_in == 400 and result.template == "local-default"
    s3 = S3BlobStore.from_env()
    (artifact,) = result.artifacts
    assert artifact.path == "order-summary.md"
    assert (await s3.get(artifact.ref)).decode().endswith("| SKU-1 | 3 | 12.50 | 37.50 |\n")
    assert artifact.ref.retention_class == "audit"

    engine = make_engine()
    async with engine.connect() as conn:
        orders = (
            await conn.execute(
                text("SELECT count(*) FROM sample_orders WHERE task_id = :t"), {"t": task_id}
            )
        ).scalar_one()
        checkpoints = (
            await conn.execute(
                text("SELECT count(*), max(finish::text) FROM checkpoints WHERE task_id = :t"),
                {"t": task_id},
            )
        ).one()
        task = (
            await conn.execute(
                text("SELECT status, result FROM tasks WHERE task_id = :t"), {"t": task_id}
            )
        ).one()
        attempt = (
            await conn.execute(
                text("SELECT outcome, tool_calls FROM task_attempts WHERE task_id = :t"),
                {"t": task_id},
            )
        ).one()
    await engine.dispose()
    assert orders == 1
    # seq 0 before the first model call, one per later call, and a final one.
    assert checkpoints[0] == 5 and json.loads(checkpoints[1])["status"] == "done"
    assert task[0] == "succeeded" and task[1]["status"] == "succeeded"
    assert attempt == ("done", 4)
    # The fake model saw only the template's tools and the skill in the instructions.
    first = fake.state.requests[0]
    assert ".skills/order-desk/SKILL.md" in first["messages"][0]["content"]


async def test_duplicate_task_id_rejected(tmp_path: Path, fake: FakeModel) -> None:
    task_id = f"task-dup-{run_id()}"
    async with running_workers(tmp_path) as client:
        _, handle = await submit(client, task_id)
        await handle.result()
        # While Temporal remembers the run, it rejects the start itself.
        with pytest.raises(WorkflowAlreadyStartedError):
            await submit(client, task_id)
        # After retention (simulated by deleting the closed run), the tasks table
        # rejects it before any harness turn runs.
        description = await handle.describe()
        await client.workflow_service.delete_workflow_execution(
            DeleteWorkflowExecutionRequest(
                namespace=env("TEMPORAL_NAMESPACE", "default"),
                workflow_execution=WorkflowExecution(
                    workflow_id=task_id, run_id=description.run_id
                ),
            )
        )
        second = None
        for _ in range(120):  # the deletion is asynchronous; allow up to 60 s
            try:
                _, second = await submit(client, task_id)
                break
            except WorkflowAlreadyStartedError:
                await asyncio.sleep(0.5)
        assert second is not None, "Temporal did not delete the closed run within 60 s"

        with pytest.raises(WorkflowFailureError) as failure:
            await second.result()
    activity_error = failure.value.cause
    assert isinstance(activity_error, ActivityError)
    assert isinstance(activity_error.cause, ApplicationError)
    assert activity_error.cause.type == "TaskAlreadyExists"
    engine = make_engine()
    async with engine.connect() as conn:
        harness_turns = (
            await conn.execute(
                text("SELECT count(*) FROM task_attempts WHERE task_id = :t"), {"t": task_id}
            )
        ).scalar_one()
    await engine.dispose()
    assert harness_turns == 1  # only the first run's turn; the rejected run ran none


async def test_worker_concurrency_from_template(fake: FakeModel) -> None:
    """A template worker runs at most `concurrency_per_pod` harness turns at once."""
    client = await connect("praxis-test")
    worker = await build_worker(client, "template", "local-default")
    expected = load_registry().templates["local-default"].template.concurrency_per_pod
    assert worker.config()["max_concurrent_activities"] == expected

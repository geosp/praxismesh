"""TaskWorkflow with mocked Activities in Temporal's time-skipping test server, and a
replay of a committed history (spec execution/task-workflow; plan §8).

Re-record the replay fixture after a deliberate Workflow change:
    RECORD_TASK_HISTORY=1 uv run pytest tests/test_task_workflow.py
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from temporalio import activity
from temporalio.client import Client, WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from common.errors import CapabilityError
from common.schemas import (
    BlobRef,
    CompleteTaskInput,
    RecordTaskInput,
    ResolvedTask,
    TaskResult,
    TaskStart,
    TurnInput,
    TurnOutcome,
)
from orchestrator.workflow import TaskWorkflow

FIXTURE = Path(__file__).parent / "fixtures" / "task_workflow_history.json"
QUEUE = "orchestration-test"
REF = BlobRef(
    id="blob:" + "0" * 64,
    key="sha256/" + "0" * 64,
    checksum="sha256:" + "0" * 64,
    content_type="text/plain",
    bytes=1,
    retention_class="task",
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
)
RESOLVED = ResolvedTask(
    template="local-default",
    template_version=1,
    template_hash="sha256:x",
    task_queue="tpl.local-default",
    tier="local",
    max_turns=3,
    max_tokens=1000,
    max_wall_time=timedelta(minutes=30),
    turn_timeout=timedelta(minutes=10),
    heartbeat_timeout=timedelta(seconds=30),
)

TurnBehavior = Callable[[TurnInput, int], TurnOutcome]


def start(task_id: str = "task-wf-00000001") -> TaskStart:
    return TaskStart(
        task_id=task_id,
        request_id="req-1",
        profile="default",
        template="local-default",
        instructions_ref=REF,
    )


def activities(behavior: TurnBehavior) -> list[Callable[..., Any]]:
    @activity.defn(name="resolve_capabilities")
    async def resolve_capabilities(s: TaskStart) -> ResolvedTask:
        return RESOLVED

    @activity.defn(name="record_task")
    async def record_task(payload: RecordTaskInput) -> None:
        return None

    @activity.defn(name="run_harness_turn")
    async def run_harness_turn(turn: TurnInput) -> TurnOutcome:
        return behavior(turn, activity.info().attempt)

    @activity.defn(name="complete_task")
    async def complete_task(p: CompleteTaskInput) -> TaskResult:
        return TaskResult(
            task_id=p.task_id,
            status=p.status,
            summary=p.summary,
            artifacts=p.artifacts,
            questions=p.questions,
            failure_reason=p.failure_reason,
            tier_used="local",
            template="local-default",
            template_version=1,
            template_hash="sha256:x",
            turns=p.turns,
            attempts=p.attempts,
            tokens_in=p.tokens_in,
            tokens_out=p.tokens_out,
        )

    return [resolve_capabilities, record_task, run_harness_turn, complete_task]


async def run_task(behavior: TurnBehavior, task_id: str | None = None) -> tuple[TaskResult, str]:
    task_id = task_id or f"task-wf-{uuid.uuid4()}"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        acts = activities(behavior)
        # A client with a fixed identity, so recorded histories carry no hostname;
        # results are read through env.client, which keeps time-skipping.
        client = await Client.connect(
            env.client.service_client.config.target_host,
            namespace=env.client.namespace,
            data_converter=pydantic_data_converter,
            identity="test-client",
        )
        # Fixed identities, so recorded histories carry no hostname.
        async with (
            Worker(
                client,
                task_queue=QUEUE,
                workflows=[TaskWorkflow],
                activities=acts,
                identity="test-orchestrator",
            ),
            Worker(
                client,
                task_queue="tpl.local-default",
                activities=acts,
                identity="test-harness",
            ),
        ):
            handle = await client.start_workflow(
                TaskWorkflow.run, start(task_id), id=task_id, task_queue=QUEUE
            )
            skipping = env.client.get_workflow_handle(task_id, result_type=TaskResult)
            result = await skipping.result()
            history = (await handle.fetch_history()).to_json()
    return result, history


def outcome(status: str, attempt: int = 1, tokens: int = 100) -> TurnOutcome:
    return TurnOutcome(status=status, tokens_in=tokens, attempts=attempt)  # type: ignore[arg-type]


async def test_done_in_one_turn() -> None:
    result, history = await run_task(lambda t, a: outcome("done"))
    assert (result.status, result.turns, result.tokens_in) == ("succeeded", 1, 100)
    if os.environ.get("RECORD_TASK_HISTORY") == "1":
        FIXTURE.write_text(history)


async def test_turn_budget_exhausted() -> None:
    result, _ = await run_task(lambda t, a: outcome("continue"))
    assert result.status == "failed" and result.failure_reason == "turn budget exhausted"
    assert result.turns == 3


async def test_token_budget_exhausted() -> None:
    result, _ = await run_task(lambda t, a: outcome("continue", tokens=600))
    assert result.failure_reason == "token budget exhausted" and result.turns == 2


async def test_needs_input_is_terminal() -> None:
    def behavior(t: TurnInput, a: int) -> TurnOutcome:
        return TurnOutcome(status="needs_input", questions=["Which SKU?"])

    result, _ = await run_task(behavior)
    assert result.status == "needs_input" and result.questions == ["Which SKU?"]


async def test_retries_are_not_turns() -> None:
    def behavior(t: TurnInput, attempt: int) -> TurnOutcome:
        if attempt < 3:
            raise RuntimeError("worker lost")
        return outcome("done", attempt=attempt)

    result, _ = await run_task(behavior)
    assert (result.status, result.turns, result.attempts) == ("succeeded", 1, 3)


async def test_capability_error_is_final() -> None:
    calls: list[int] = []

    def behavior(t: TurnInput, attempt: int) -> TurnOutcome:
        calls.append(attempt)
        raise CapabilityError("not allowed")

    result, _ = await run_task(behavior)
    assert result.status == "failed" and "CapabilityError" in (result.failure_reason or "")
    assert calls == [1]


async def test_remaining_tokens_passed_to_turns() -> None:
    seen: list[int] = []

    def behavior(t: TurnInput, a: int) -> TurnOutcome:
        seen.append(t.remaining_tokens)
        return outcome("continue", tokens=300)

    await run_task(behavior)
    assert seen == [1000, 700, 400]


async def test_task_workflow_replay() -> None:
    history = WorkflowHistory.from_json("task-wf-replay", FIXTURE.read_text())
    replayer = Replayer(workflows=[TaskWorkflow], data_converter=pydantic_data_converter)
    result = await replayer.replay_workflow(history)
    assert result.replay_failure is None

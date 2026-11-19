"""TaskWorkflow's waiting loop in Temporal's time-skipping server (Phase 2 messaging
task 4.3; D7, D11, D14, D17; R14-R17, R20-R22, R24, R31, R33).

The Activities are fakes: `run_harness_turn` follows a script of statuses, and
`claim_inbox` answers from a queue of claims, so each test drives one path.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import activity
from temporalio.client import WorkflowHandle
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from common.schemas import (
    ClaimInboxInput,
    CompleteTaskInput,
    InboxClaim,
    RecordTaskInput,
    ResolvedTask,
    TaskResult,
    TaskStart,
    TurnInput,
    TurnOutcome,
)
from orchestrator.workflow import TaskWorkflow
from tests.test_task_workflow import REF, RESOLVED

QUEUE = "orchestration-wait-test"
Claimer = Callable[[ClaimInboxInput, int], InboxClaim]


class Fakes:
    def __init__(self, turns: list[str], claim: Claimer, resolved: ResolvedTask) -> None:
        self.turns, self.claim, self.resolved = list(turns), claim, resolved
        self.turn_inputs: list[TurnInput] = []
        self.claims: list[ClaimInboxInput] = []
        self.completed: list[CompleteTaskInput] = []

    def activities(self) -> list[Callable[..., Any]]:
        @activity.defn(name="resolve_capabilities")
        async def resolve_capabilities(s: TaskStart) -> ResolvedTask:
            return self.resolved

        @activity.defn(name="record_task")
        async def record_task(payload: RecordTaskInput) -> None:
            return None

        @activity.defn(name="run_harness_turn")
        async def run_harness_turn(turn: TurnInput) -> TurnOutcome:
            self.turn_inputs.append(turn)
            status = self.turns.pop(0) if self.turns else "done"
            return TurnOutcome(status=status, tokens_in=1, summary=f"turn {turn.turn}")  # type: ignore[arg-type]

        @activity.defn(name="claim_inbox")
        async def claim_inbox(payload: ClaimInboxInput) -> InboxClaim:
            self.claims.append(payload)
            return self.claim(payload, activity.info().attempt)

        @activity.defn(name="complete_task")
        async def complete_task(p: CompleteTaskInput) -> TaskResult:
            self.completed.append(p)
            return TaskResult(
                task_id=p.task_id, status=p.status, summary=p.summary,
                failure_reason=p.failure_reason, tier_used="local", template="local-default",
                template_version=1,
                template_hash="sha256:x", turns=p.turns, attempts=p.attempts,
                tokens_in=p.tokens_in, tokens_out=p.tokens_out,
            )  # fmt: skip

        return [resolve_capabilities, record_task, run_harness_turn, claim_inbox, complete_task]


def resolved(**kw: Any) -> ResolvedTask:
    return RESOLVED.model_copy(
        update={"max_wakes": 50, "idle_timeout": timedelta(minutes=10), **kw}
    )


def start(task_id: str) -> TaskStart:
    return TaskStart(task_id=task_id, request_id="req-1", profile="openai",
                     template="local-default", instructions_ref=REF)  # fmt: skip


async def run(
    fakes: Fakes,
    during: Callable[[WorkflowHandle[Any, Any], WorkflowEnvironment], Any] | None = None,
) -> tuple[TaskResult | BaseException, list[int]]:
    """Run a task; `during` may signal or cancel it. Returns the result (or the
    error) and the history length of each run."""
    task_id = f"task-wait-{uuid.uuid4()}"
    executor = ThreadPoolExecutor(max_workers=8)
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        acts = fakes.activities()
        async with (
            Worker(env.client, task_queue=QUEUE, workflows=[TaskWorkflow], activities=acts,
                   activity_executor=executor),
            Worker(env.client, task_queue="tpl.local-default", activities=acts,
                   activity_executor=executor),
        ):  # fmt: skip
            handle = await env.client.start_workflow(
                TaskWorkflow.run, start(task_id), id=task_id, task_queue=QUEUE
            )
            if during is not None:
                await during(handle, env)
            outcome: TaskResult | BaseException
            try:
                outcome = await handle.result()
            except Exception as e:
                outcome = e
            # Follow the Continue-As-New chain from the first run.
            lengths, run_id = [], handle.first_execution_run_id
            while run_id:
                history = await env.client.get_workflow_handle(
                    task_id, run_id=run_id
                ).fetch_history()
                lengths.append(len(history.events))
                last = history.events[-1]
                attrs = last.workflow_execution_continued_as_new_event_attributes
                run_id = (
                    attrs.new_execution_run_id
                    if last.HasField("workflow_execution_continued_as_new_event_attributes")
                    else ""
                )
    return outcome, lengths


def rows(n: int, deadline: datetime | None = None) -> InboxClaim:
    return InboxClaim(message_ids=[f"m{i}" for i in range(n)], next_deadline=deadline)


async def test_a_claim_with_rows_starts_a_woken_turn() -> None:
    """R14: after a waiting turn, a claim with rows runs the next turn at once."""
    fakes = Fakes(["waiting", "done"], lambda c, a: rows(1), resolved())
    result, _ = await run(fakes)
    assert isinstance(result, TaskResult) and result.status == "succeeded"
    assert [t.turn for t in fakes.turn_inputs] == [1, 2] and [c.turn for c in fakes.claims] == [2]
    assert fakes.turn_inputs[1].max_ask_wait == timedelta(minutes=10)


async def test_an_idle_task_succeeds_after_its_idle_timeout() -> None:
    """R20: nothing pending and no open question: success after the idle timeout."""
    fakes = Fakes(["waiting"], lambda c, a: rows(0), resolved(idle_timeout=timedelta(seconds=60)))
    result, _ = await run(fakes)
    assert isinstance(result, TaskResult) and result.status == "succeeded"
    assert len(fakes.turn_inputs) == 1 and fakes.completed[-1].summary == "turn 1"


async def test_a_question_deadline_wakes_the_asker_to_claim_its_expiry() -> None:
    """R17: the sleep ends at the open question's deadline; the next claim brings the
    expiry and starts a woken turn."""
    deadline = datetime.now(UTC) + timedelta(minutes=2)

    def claim(c: ClaimInboxInput, attempt: int) -> InboxClaim:
        return rows(0, deadline) if c.now < deadline else rows(1)

    fakes = Fakes(["waiting", "done"], claim, resolved())
    result, _ = await run(fakes)
    assert isinstance(result, TaskResult) and result.status == "succeeded"
    assert len(fakes.claims) >= 2 and fakes.claims[-1].now >= deadline


async def test_a_signal_ends_the_sleep() -> None:
    """R14, D6: an `inbox` Signal wakes a sleeping task, which claims again."""
    state = {"signalled": False}

    def claim(c: ClaimInboxInput, attempt: int) -> InboxClaim:
        return rows(1) if state["signalled"] else rows(0)

    async def signal(handle: WorkflowHandle[Any, Any], env: WorkflowEnvironment) -> None:
        while not fakes.claims:
            await asyncio.sleep(0.05)
        state["signalled"] = True
        await handle.signal(TaskWorkflow.inbox)

    fakes = Fakes(["waiting", "done"], claim, resolved(idle_timeout=timedelta(hours=1)))
    result, _ = await run(fakes, signal)
    assert isinstance(result, TaskResult) and result.status == "succeeded"
    assert len(fakes.turn_inputs) == 2


async def test_out_of_wall_time_ends_by_open_questions() -> None:
    """R21, R31: with no open question the task succeeds; with one it fails."""
    far = datetime.now(UTC) + timedelta(days=2)
    short = resolved(max_wall_time=timedelta(minutes=5), idle_timeout=timedelta(hours=1))
    ok, _ = await run(Fakes(["waiting"], lambda c, a: rows(0), short))
    open_question, _ = await run(Fakes(["waiting"], lambda c, a: rows(0, far), short))
    assert isinstance(ok, TaskResult) and ok.status == "succeeded"
    assert isinstance(open_question, TaskResult) and open_question.status == "failed"
    assert open_question.failure_reason == "wall-time budget exhausted"


async def test_woken_turns_have_their_own_budget() -> None:
    """R22: woken turns never spend max_turns; max_wakes ends the task."""
    fakes = Fakes(["waiting"] * 10, lambda c, a: rows(1), resolved(max_turns=1, max_wakes=4))
    result, _ = await run(fakes)
    assert isinstance(result, TaskResult) and result.failure_reason == "wake budget exhausted"
    assert len(fakes.turn_inputs) == 5  # one working turn, four woken turns


async def test_a_cancel_during_the_wait_still_completes_the_task() -> None:
    """R24, D17: a cancellation while sleeping runs complete_task, which closes the
    task's messages."""

    async def cancel(handle: WorkflowHandle[Any, Any], env: WorkflowEnvironment) -> None:
        while not fakes.claims:
            await asyncio.sleep(0.05)
        await handle.cancel()

    fakes = Fakes(["waiting"], lambda c, a: rows(0), resolved(idle_timeout=timedelta(hours=1)))
    await run(fakes, cancel)
    assert [(c.status, c.failure_reason) for c in fakes.completed] == [("failed", "cancelled")]


async def test_a_claim_that_keeps_failing_ends_the_task_through_complete_task() -> None:
    """D7, R24: the claim retries until the wall-time deadline, then the task ends."""

    def claim(c: ClaimInboxInput, attempt: int) -> InboxClaim:
        raise RuntimeError("database unavailable")

    fakes = Fakes(["waiting"], claim, resolved(max_wall_time=timedelta(minutes=3)))
    result, _ = await run(fakes)
    assert isinstance(result, TaskResult) and result.status == "failed"
    assert (result.failure_reason or "").startswith("inbox unavailable")
    assert len(fakes.completed) == 1


async def test_back_to_back_wakes_continue_as_new_and_stay_bounded() -> None:
    """R33, D11: 100 back-to-back wakes keep every run under 2,000 history events,
    and the task still finishes after new runs started."""
    fakes = Fakes(["waiting"] * 100 + ["done"], lambda c, a: rows(1),
                  resolved(max_wakes=200))  # fmt: skip
    result, lengths = await run(fakes)
    assert isinstance(result, TaskResult) and result.status == "succeeded"
    assert len(fakes.turn_inputs) == 101 and result.turns == 101
    assert len(lengths) >= 2 and max(lengths) < 2000, lengths

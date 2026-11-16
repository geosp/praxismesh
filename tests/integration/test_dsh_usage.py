"""Unknown usage when no later attempt runs (DSH migration plan D7, D9, R12, R13;
phase 02 impl-review F59, F68).

`run_harness_turn` with the real database and a stub runner that plays a DSH
attempt: it dispatches ledger rows like the gateway and then fails as `DshRunner`
classifies it. No DSH container is needed.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from common.blob_store import MemoryBlobStore
from common.persistence.repositories import (
    AttemptRepository,
    TaskRepository,
    UsageLedgerRepository,
    make_engine,
)
from common.schemas import CompleteTaskInput, TaskStart, TurnInput
from harness_activity.activity import HarnessActivities
from harness_activity.dsh.composition import DEFAULT_CONTEXT_WINDOW
from harness_activity.dsh.ledger import DSH_MAX_OUTPUT_TOKENS
from harness_activity.runner import AttemptContext, RunnerFailure, RunResult, Usage
from registry.loader import load_registry
from tests.support.session_stores import MemorySessionStore
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
WINDOW = load_registry().templates["local-dsh"].template.context_window or 0


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


@dataclasses.dataclass
class Scope:
    workspace: Path
    store: MemorySessionStore

    async def close(self) -> None:
        return None


class StubRunner:
    """Settles `settled` requests, leaves `unsettled` in flight, then fails."""

    def __init__(
        self, ledger: UsageLedgerRepository, failure: RunnerFailure, settled: int, unsettled: int
    ) -> None:
        self.ledger, self.failure = ledger, failure
        self.settled, self.unsettled = settled, unsettled
        self.context: AttemptContext | None = None

    async def open_attempt(self, context: AttemptContext, tmp: Path) -> Scope:
        self.context = context
        workspace = tmp / f"{context.attempt}"
        workspace.mkdir(parents=True, exist_ok=True)
        return Scope(workspace, MemorySessionStore(context.task_id))

    async def run(self, config: Any, workspace: Path, session: Any, text_: str, before: Any,
                  usage: Usage) -> RunResult:  # fmt: skip
        assert self.context is not None
        c = self.context
        for n in range(self.settled + self.unsettled):
            request = f"req-{n + 1:04d}"
            await self.ledger.dispatch(c.task_id, c.turn, c.attempt, request, "main")
            if n < self.settled:
                await self.ledger.settle(c.task_id, c.turn, c.attempt, request, 100, 10)
                usage.tokens_in, usage.tokens_out = usage.tokens_in + 100, usage.tokens_out + 10
                usage.inner_turns += 1
        raise self.failure


async def setup(engine: AsyncEngine, tmp_path: Path, runner: StubRunner) -> tuple[
    HarnessActivities, TurnInput
]:  # fmt: skip
    blobs = MemoryBlobStore()
    task_id = f"task-usage-{run_id()}"
    start = TaskStart(
        task_id=task_id,
        request_id="req-1",
        profile="dsh",
        template="local-dsh",
        instructions_ref=await blobs.put(b"go", retention="task"),
    )
    await TaskRepository(engine).record_task(
        start, workflow_id=task_id, run_id="run-1", template_version=1, template_hash="x"
    )
    registry = load_registry()
    acts = HarnessActivities(
        registry,
        engine,
        blobs,
        runner,
        tmp_path,
        "test-usage-worker",
        open_attempt=lambda context: runner.open_attempt(context, tmp_path),
    )
    turn = TurnInput(
        task_id=task_id,
        turn=1,
        template="local-dsh",
        template_version=1,
        template_hash=registry.templates["local-dsh"].hash,
        remaining_tokens=10_000_000,
        remaining_wall_time=timedelta(minutes=10),
        request_id="req-usage",
    )
    return acts, turn


def env(attempt: int, task_id: str) -> ActivityEnvironment:
    environment = ActivityEnvironment()
    environment.info = dataclasses.replace(
        environment.info,
        attempt=attempt,
        heartbeat_details=[],
        heartbeat_timeout=timedelta(seconds=3),
        start_to_close_timeout=timedelta(minutes=5),
        workflow_id=task_id,
    )
    return environment


async def attempt_row(engine: AsyncEngine, task_id: str, attempt: int) -> tuple[Any, ...]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT outcome, failure_category, tokens_in, tokens_out, usage_known "
                    "FROM task_attempts WHERE task_id = :t AND attempt = :a"
                ),
                {"t": task_id, "a": attempt},
            )
        ).one()
    return tuple(row)


async def test_non_retryable_failure_charges_its_own_unknown_request(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """F59: a forced stop with a request in flight has no later attempt to charge it.
    The failure details carry the D9 charge and `usage_known = false`; the attempt
    row stores NULL tokens, never 0."""
    runner = StubRunner(UsageLedgerRepository(engine), RunnerFailure("DshForcedStop", False), 1, 1)
    acts, turn = await setup(engine, tmp_path, runner)
    with pytest.raises(ApplicationError) as raised:
        await env(1, turn.task_id).run(acts.run_harness_turn, turn)
    assert raised.value.non_retryable and raised.value.type == "DshForcedStop"
    details = raised.value.details[0]
    assert details["tokens_in"] == 100 + WINDOW
    assert details["tokens_out"] == 10 + DSH_MAX_OUTPUT_TOKENS
    assert details["usage_known"] is False and details["inner_turns"] == 2
    assert await attempt_row(engine, turn.task_id, 1) == (
        "failed", "DshForcedStop", None, None, False
    )  # fmt: skip


async def test_cancelled_attempt_charges_its_own_unknown_request(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """F59, R18 `cancel`: the cancelled attempt's row says its usage is unknown."""
    runner = StubRunner(
        UsageLedgerRepository(engine),
        RunnerFailure("DshCancelled", False, cancelled=True),
        0,
        1,
    )
    acts, turn = await setup(engine, tmp_path, runner)
    with pytest.raises(asyncio.CancelledError):
        await env(1, turn.task_id).run(acts.run_harness_turn, turn)
    assert await attempt_row(engine, turn.task_id, 1) == (
        "cancelled", "DshCancelled", None, None, False
    )  # fmt: skip


async def test_retryable_failure_is_charged_once_across_attempts(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """D9: charging at the failure and again when the next attempt opens counts the
    unknown request once, over three attempts (review F75)."""
    ledger = UsageLedgerRepository(engine)
    runner = StubRunner(ledger, RunnerFailure("DshUsageUnknown", True), 1, 1)
    acts, turn = await setup(engine, tmp_path, runner)
    heartbeats: list[dict[str, Any]] = []
    for attempt in (1, 2):
        environment = env(attempt, turn.task_id)
        if heartbeats:
            environment.info = dataclasses.replace(
                environment.info, heartbeat_details=[heartbeats[-1]]
            )
        environment.on_heartbeat = lambda *d: heartbeats.append(d[0])
        with pytest.raises(ApplicationError) as raised:
            await environment.run(acts.run_harness_turn, turn)
        heartbeats.append(raised.value.details[0])
    details = raised.value.details[0]
    # Two attempts, each with one settled and one unknown request.
    assert details["tokens_in"] == 2 * (100 + WINDOW)
    assert details["tokens_out"] == 2 * (10 + DSH_MAX_OUTPUT_TOKENS)
    assert details["usage_known"] is False and details["unknown_requests"] == 2
    runner.failure, runner.settled, runner.unsettled = RunnerFailure("DshUsageUnknown", True), 1, 0
    environment = env(3, turn.task_id)
    environment.info = dataclasses.replace(environment.info, heartbeat_details=[heartbeats[-1]])
    with pytest.raises(ApplicationError) as raised:
        await environment.run(acts.run_harness_turn, turn)
    assert raised.value.details[0]["tokens_in"] == 3 * 100 + 2 * WINDOW


async def test_exhausted_turn_charges_the_last_attempts_unknown_request(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """F59: the sixth Temporal attempt raises AttemptsExhausted without running. The
    fifth real attempt's request in flight is still charged."""
    ledger = UsageLedgerRepository(engine)
    runner = StubRunner(ledger, RunnerFailure("DshUsageUnknown", True), 0, 0)
    acts, turn = await setup(engine, tmp_path, runner)
    attempts = AttemptRepository(engine)
    await attempts.start(turn.task_id, 1, 5, "lost-worker")
    await ledger.dispatch(turn.task_id, 1, 5, "req-0001", "main")  # the worker dies here
    with pytest.raises(ApplicationError) as raised:
        await env(6, turn.task_id).run(acts.run_harness_turn, turn)
    assert raised.value.type == "AttemptsExhausted"
    details = raised.value.details[0]
    assert (details["tokens_in"], details["usage_known"]) == (WINDOW, False)
    assert await attempt_row(engine, turn.task_id, 5) == (
        "lost", "lost_or_timed_out", None, None, False
    )  # fmt: skip


async def test_lost_attempt_with_settled_requests_records_them(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """F68: an attempt lost between requests reads the usage the ledger observed,
    not the 0 it was created with."""
    ledger = UsageLedgerRepository(engine)
    runner = StubRunner(ledger, RunnerFailure("DshUsageUnknown", True), 0, 0)
    _, turn = await setup(engine, tmp_path, runner)
    attempts = AttemptRepository(engine)
    await attempts.start(turn.task_id, 1, 1, "lost-worker")
    for request in ("req-0001", "req-0002"):
        await ledger.dispatch(turn.task_id, 1, 1, request, "main")
        await ledger.settle(turn.task_id, 1, 1, request, 100, 10)
    await attempts.start(turn.task_id, 1, 2, "next-worker")
    assert await ledger.close_unknown(turn.task_id, 1, 2) == (0, 200, 20, 2)
    assert await attempt_row(engine, turn.task_id, 1) == (
        "lost", "lost_or_timed_out", 200, 20, True
    )  # fmt: skip


async def test_stale_attempt_cannot_dispatch(engine: AsyncEngine, tmp_path: Path) -> None:
    """D10, R11 (review F61): once a newer attempt started, the stale attempt's
    dispatch writes no ledger row, so nothing is spent outside the turn's totals."""
    ledger = UsageLedgerRepository(engine)
    runner = StubRunner(ledger, RunnerFailure("DshUsageUnknown", True), 0, 0)
    _, turn = await setup(engine, tmp_path, runner)
    attempts = AttemptRepository(engine)
    await attempts.start(turn.task_id, 1, 1, "worker-a")
    assert await ledger.dispatch(turn.task_id, 1, 1, "req-0001", "main") is True
    await attempts.start(turn.task_id, 1, 2, "worker-b")
    assert await ledger.dispatch(turn.task_id, 1, 1, "req-0002", "main") is False
    assert await ledger.dispatch(turn.task_id, 1, 2, "req-0001", "main") is True
    async with engine.connect() as conn:
        found = await conn.execute(
            text("SELECT attempt, request_id FROM usage_ledger WHERE task_id = :t ORDER BY 1, 2"),
            {"t": turn.task_id},
        )
        assert [tuple(r) for r in found] == [(1, "req-0001"), (2, "req-0001")]


@pytest.mark.parametrize("closer", ["failed for good", "task completed"])
async def test_rows_closed_without_a_finish_hold_the_ledger_usage(
    closer: str, engine: AsyncEngine, tmp_path: Path
) -> None:
    """D7, R12 (review F101): a row closed without a finish (the turn failed for
    good, or the task completed) holds the ledger's usage through it, or NULL when
    a request up to it was never observed; never the 0 it was created with."""
    ledger = UsageLedgerRepository(engine)
    runner = StubRunner(ledger, RunnerFailure("DshUsageUnknown", True), 0, 0)
    _, turn = await setup(engine, tmp_path, runner)
    attempts = AttemptRepository(engine)
    await attempts.start(turn.task_id, 1, 1, "worker-a")
    await ledger.dispatch(turn.task_id, 1, 1, "req-0001", "main")
    await ledger.settle(turn.task_id, 1, 1, "req-0001", 100, 10)
    await attempts.start(turn.task_id, 2, 1, "worker-a")  # a second turn, unobserved
    await ledger.dispatch(turn.task_id, 2, 1, "req-0001", "main")
    if closer == "failed for good":
        await attempts.close_unfinished(turn.task_id, 2, "HarnessInputError", through_attempt=1)
    else:
        await attempts.close_unfinished(turn.task_id, None, "task_completed")
    async with engine.connect() as conn:
        found = await conn.execute(
            text(
                "SELECT turn, tokens_in, tokens_out, usage_known FROM task_attempts "
                "WHERE task_id = :t ORDER BY turn"
            ),
            {"t": turn.task_id},
        )
        rows = [tuple(r) for r in found]
    turn_two = (2, None, None, False)  # its request was never observed
    if closer == "failed for good":
        assert rows == [(1, 0, 0, True), turn_two]  # turn 1 is still open, untouched
    else:
        assert rows == [(1, 100, 10, True), turn_two]


async def test_complete_task_charges_what_the_ledger_left_unobserved(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """R11-R13, D9 (review F98): the turn ended with no Activity code running (the
    worker died with a request in flight, then schedule_to_close expired, or the
    task was cancelled). The Workflow only had the last heartbeat; complete_task
    takes the usage from the ledger: settled tokens plus the D9 charge, unknown."""
    from orchestrator.activities import OrchestratorActivities

    ledger = UsageLedgerRepository(engine)
    runner = StubRunner(ledger, RunnerFailure("DshUsageUnknown", True), 0, 0)
    acts, turn = await setup(engine, tmp_path, runner)
    await AttemptRepository(engine).start(turn.task_id, 1, 1, "dead-worker")
    await ledger.dispatch(turn.task_id, 1, 1, "req-0001", "main")
    await ledger.settle(turn.task_id, 1, 1, "req-0001", 100, 10)
    await ledger.dispatch(turn.task_id, 1, 1, "req-0002", "main")  # the worker died
    orchestrator = OrchestratorActivities(acts.registry, TaskRepository(engine))
    resolved = await ActivityEnvironment().run(
        orchestrator.resolve_capabilities,
        TaskStart(
            task_id=turn.task_id,
            request_id="req-1",
            profile="dsh",
            template="local-dsh",
            instructions_ref=await acts.blobs.put(b"x", retention="task"),
        ),
    )
    result = await ActivityEnvironment().run(
        orchestrator.complete_task,
        CompleteTaskInput(
            task_id=turn.task_id,
            status="failed",
            failure_reason="harness turn 1 failed: CancelledError",
            resolved=resolved,
            turns=1,
            attempts=1,
            tokens_in=100,  # the last heartbeat saw the settled request only
            tokens_out=10,
            inner_turns=1,
        ),
    )
    assert (result.tokens_in, result.tokens_out) == (100 + WINDOW, 10 + DSH_MAX_OUTPUT_TOKENS)
    assert result.usage_known is False
    assert result.inner_turns == 2  # D11 (F136): both requests, from the ledger
    assert await attempt_row(engine, turn.task_id, 1) == (
        "failed", "task_completed", None, None, False
    )  # fmt: skip


async def test_lost_rows_hold_the_ledger_usage_when_the_task_completes(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """D7, R12 (review F134): attempt 1 dies with a request in flight, attempt 2 is
    refused (which marks attempt 1 lost), and no real attempt follows. When the task
    completes, attempt 1's row reads unknown, not the 0 it was created with."""
    ledger = UsageLedgerRepository(engine)
    runner = StubRunner(ledger, RunnerFailure("DshUsageUnknown", True), 0, 0)
    _, turn = await setup(engine, tmp_path, runner)
    attempts = AttemptRepository(engine)
    await attempts.start(turn.task_id, 1, 1, "dead-worker")
    await ledger.dispatch(turn.task_id, 1, 1, "req-0001", "main")
    await attempts.record_refusal(turn.task_id, 1, 2, "refusing-worker", "dsh_unserviceable")
    assert (await attempt_row(engine, turn.task_id, 1))[0] == "lost"
    await attempts.close_unfinished(turn.task_id, None, "task_completed")
    assert await attempt_row(engine, turn.task_id, 1) == (
        "lost", "lost_or_timed_out", None, None, False
    )  # fmt: skip


async def test_complete_task_survives_a_template_the_orchestrator_no_longer_has(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """R11, D9 (review F137): the task's template version is gone from the
    orchestrator's registry. complete_task still completes, charging the default
    context window, instead of failing on the lookup."""
    from orchestrator.activities import OrchestratorActivities

    ledger = UsageLedgerRepository(engine)
    runner = StubRunner(ledger, RunnerFailure("DshUsageUnknown", True), 0, 0)
    acts, turn = await setup(engine, tmp_path, runner)
    await AttemptRepository(engine).start(turn.task_id, 1, 1, "dead-worker")
    await ledger.dispatch(turn.task_id, 1, 1, "req-0001", "main")
    orchestrator = OrchestratorActivities(acts.registry, TaskRepository(engine))
    resolved = await ActivityEnvironment().run(
        orchestrator.resolve_capabilities,
        TaskStart(
            task_id=turn.task_id,
            request_id="req-1",
            profile="dsh",
            template="local-dsh",
            instructions_ref=await acts.blobs.put(b"x", retention="task"),
        ),
    )
    gone = resolved.model_copy(update={"template_hash": "sha256:" + "f" * 64})
    result = await ActivityEnvironment().run(
        orchestrator.complete_task,
        CompleteTaskInput(
            task_id=turn.task_id, status="failed", failure_reason="x", resolved=gone, turns=1,
            attempts=1, tokens_in=0, tokens_out=0, inner_turns=0,
        ),
    )  # fmt: skip
    assert result.tokens_in == DEFAULT_CONTEXT_WINDOW and result.usage_known is False

"""`TaskWorkflow`: one durable task on the orchestration queue (RFC Phase 1).

Drives harness turns on `tpl.{template}`, accounts turns, tokens and wall time,
and retries infrastructure failures only. Inputs and outputs are IDs and
`BlobRef`s; all I/O happens in Activities (plan §2).
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, CancelledError

with workflow.unsafe.imports_passed_through():
    from common.schemas import (
        Artifact,
        ClaimInboxInput,
        CompleteTaskInput,
        InboxClaim,
        RecordTaskInput,
        ResolvedTask,
        TaskResult,
        TaskStart,
        TaskState,
        TurnInput,
        TurnOutcome,
    )

NON_RETRYABLE = [
    "AttemptsExhausted",
    "HarnessInputError",
    "CapabilityError",
    "BudgetExceeded",
    "InvalidTaskInput",
    "TaskAlreadyExists",
    "NonRetryableError",
]
SHORT = timedelta(seconds=30)
SHORT_RETRY = RetryPolicy(maximum_attempts=5, non_retryable_error_types=NON_RETRYABLE)
# Unlimited Temporal attempts per turn, bounded by schedule_to_close: the Activity
# itself stops after 5 real attempts, so template-version refusals (which a worker
# of the right version will take later) do not use them up (review F7).
TURN_ATTEMPTS = 0
WAIT_PATCH = "phase2-wait"
COMPLETE_RETRY = RetryPolicy(maximum_attempts=0, non_retryable_error_types=NON_RETRYABLE)
# Continue as new before a run's history grows past this many events (D11, R33).
HISTORY_LIMIT = 1000


def failed_turn_usage(cause: BaseException | None) -> tuple[int, int, int, int, bool]:
    """What a turn that failed for good used: tokens in and out, inner turns,
    attempts, and whether that usage is exact. A timeout carries the last heartbeat;
    a failure the Activity raised carries its usage in the error's details (review
    F10, gate F1). Usage that includes a conservative charge is not known (D7, F58)."""
    details: Any = getattr(cause, "last_heartbeat_details", None) or getattr(cause, "details", None)
    if details and isinstance(details[0], dict):
        d = details[0]
        return (
            int(d.get("tokens_in", 0)),
            int(d.get("tokens_out", 0)),
            int(d.get("inner_turns", 0)),
            int(d.get("attempts", 1)),
            bool(d.get("usage_known", True)),
        )
    return 0, 0, 0, 1, True


def failure_category(error: ActivityError) -> str:
    cause = error.cause
    if isinstance(cause, ApplicationError) and cause.type:
        return cause.type
    return type(cause).__name__ if cause is not None else "ActivityError"


@workflow.defn(name="TaskWorkflow")
class TaskWorkflow:
    def __init__(self) -> None:
        self.woken = False

    @workflow.signal(name="inbox")
    def inbox(self) -> None:
        """A hint that the inbox changed (Phase 2 messaging D6); the claim reads it."""
        self.woken = True

    @workflow.run
    async def run(self, start: TaskStart) -> TaskResult:
        # Phase 1 histories never took the waiting path; they replay the old loop
        # command for command (Phase 2 messaging D12, R29). A continued run is new.
        if start.carried is None and not workflow.patched(WAIT_PATCH):
            return await self._run_v1(start)
        return await self._run_v2(start.model_copy(update={"carried": None}), start.carried)

    async def _run_v1(self, start: TaskStart) -> TaskResult:
        resolved: ResolvedTask = await workflow.execute_activity(
            "resolve_capabilities",
            start,
            result_type=ResolvedTask,
            start_to_close_timeout=SHORT,
            retry_policy=SHORT_RETRY,
        )
        # Rejects a reused task ID for good, beyond Temporal's retention; a run
        # stopped here ends without complete_task, leaving the old row untouched.
        await workflow.execute_activity(
            "record_task",
            RecordTaskInput(start=start, resolved=resolved),
            start_to_close_timeout=SHORT,
            retry_policy=SHORT_RETRY,
        )
        deadline = workflow.now() + resolved.max_wall_time
        turns = attempts = tokens_in = tokens_out = inner_turns = 0
        usage_known = True
        status = "failed"
        summary, reason = "", None
        questions: list[str] = []
        artifacts: list[Artifact] = []
        while True:
            if turns >= resolved.max_turns:
                reason = "turn budget exhausted"
                break
            used = tokens_in + tokens_out
            if used >= resolved.max_tokens:
                reason = "token budget exhausted"
                break
            remaining_time = deadline - workflow.now()
            if remaining_time <= timedelta(0):
                reason = "wall-time budget exhausted"
                break
            turns += 1
            try:
                outcome: TurnOutcome = await workflow.execute_activity(
                    "run_harness_turn",
                    TurnInput(
                        task_id=start.task_id,
                        turn=turns,
                        template=resolved.template,
                        template_version=resolved.template_version,
                        template_hash=resolved.template_hash,
                        remaining_tokens=resolved.max_tokens - used,
                        remaining_wall_time=remaining_time,
                        request_id=start.request_id,
                    ),
                    result_type=TurnOutcome,
                    task_queue=resolved.task_queue,
                    start_to_close_timeout=resolved.turn_timeout,
                    heartbeat_timeout=resolved.heartbeat_timeout,
                    schedule_to_close_timeout=resolved.turn_timeout * 6,
                    # A cancelled turn records its attempt (cancelled, its unknown
                    # usage) before the task completes and closes open rows (R18).
                    cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
                    retry_policy=RetryPolicy(
                        maximum_attempts=TURN_ATTEMPTS,
                        non_retryable_error_types=NON_RETRYABLE,
                    ),
                )
            except ActivityError as e:
                # Count what the lost attempts heartbeated before the turn failed
                # for good (informal review F10).
                lost_in, lost_out, lost_inner, lost_attempts, lost_known = failed_turn_usage(
                    e.cause
                )
                usage_known = usage_known and lost_known
                tokens_in += lost_in
                tokens_out += lost_out
                inner_turns += lost_inner
                attempts += lost_attempts
                reason = f"harness turn {turns} failed: {failure_category(e)}"
                break
            attempts += outcome.attempts
            inner_turns += outcome.inner_turns
            tokens_in += outcome.tokens_in
            tokens_out += outcome.tokens_out
            usage_known = usage_known and outcome.usage_known
            if outcome.status in ("done", "needs_input"):
                status = "succeeded" if outcome.status == "done" else "needs_input"
                summary, questions, artifacts = outcome.summary, outcome.questions, outcome.outputs
                break
        result: TaskResult = await workflow.execute_activity(
            "complete_task",
            CompleteTaskInput(
                task_id=start.task_id,
                status=status,  # type: ignore[arg-type]
                summary=summary,
                artifacts=artifacts,
                questions=questions,
                failure_reason=reason,
                resolved=resolved,
                turns=turns,
                attempts=attempts,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                inner_turns=inner_turns,
                usage_known=usage_known,
            ),
            result_type=TaskResult,
            start_to_close_timeout=SHORT,
            retry_policy=SHORT_RETRY,
        )
        return result

    async def _run_v2(self, start: TaskStart, carried: TaskState | None) -> TaskResult:
        """The Phase 2 loop: a turn may end `waiting`; the Workflow then claims its
        inbox, sleeps only if nothing came, and wakes on a Signal, a question deadline,
        its idle timeout or its wall-time budget (D7). Turns started by a claim count
        against `max_wakes`, others against `max_turns` (D14). Every ending runs
        `complete_task`, which closes the task's messages (D17)."""
        if carried is None:
            resolved: ResolvedTask = await workflow.execute_activity(
                "resolve_capabilities",
                start,
                result_type=ResolvedTask,
                start_to_close_timeout=SHORT,
                retry_policy=SHORT_RETRY,
            )
            await workflow.execute_activity(
                "record_task",
                RecordTaskInput(start=start, resolved=resolved),
                start_to_close_timeout=SHORT,
                retry_policy=SHORT_RETRY,
            )
            run = _Run(resolved=resolved, deadline=workflow.now() + resolved.max_wall_time)
            waiting = False
        else:
            run = _Run.from_state(carried)
            waiting = True  # a continued run was waiting: it claims first
        resolved = run.resolved
        status, reason, questions = "failed", None, list[str]()
        woken_turn = False
        try:
            while True:
                if waiting:
                    ending = await self._wait(start, run)
                    if ending is not None:
                        status, reason = ending
                        break
                    waiting, woken_turn = False, True
                if woken_turn and run.wakes >= resolved.max_wakes:
                    reason = "wake budget exhausted"
                    break
                if not woken_turn and run.work_turns >= resolved.max_turns:
                    reason = "turn budget exhausted"
                    break
                used = run.tokens_in + run.tokens_out
                if used >= resolved.max_tokens:
                    reason = "token budget exhausted"
                    break
                remaining_time = run.deadline - workflow.now()
                if remaining_time <= timedelta(0):
                    if woken_turn:  # still waiting: end by open questions (R21, R31)
                        status, reason = await self._ending_at_wall_time(start, run)
                    else:
                        reason = "wall-time budget exhausted"
                    break
                run.turn += 1
                if woken_turn:
                    run.wakes += 1
                else:
                    run.work_turns += 1
                woken_turn = False
                try:
                    outcome: TurnOutcome = await self._turn(start, run, used, remaining_time)
                except ActivityError as e:
                    if isinstance(e.cause, CancelledError):
                        raise asyncio.CancelledError() from e
                    lost_in, lost_out, lost_inner, lost_attempts, lost_known = failed_turn_usage(
                        e.cause
                    )
                    run.usage_known = run.usage_known and lost_known
                    run.tokens_in += lost_in
                    run.tokens_out += lost_out
                    run.inner_turns += lost_inner
                    run.attempts += lost_attempts
                    reason = f"harness turn {run.turn} failed: {failure_category(e)}"
                    break
                run.attempts += outcome.attempts
                run.inner_turns += outcome.inner_turns
                run.tokens_in += outcome.tokens_in
                run.tokens_out += outcome.tokens_out
                run.usage_known = run.usage_known and outcome.usage_known
                if outcome.status in ("done", "needs_input"):
                    status = "succeeded" if outcome.status == "done" else "needs_input"
                    run.summary, run.outputs = outcome.summary, outcome.outputs
                    questions = outcome.questions
                    break
                if outcome.status == "waiting":  # its outputs stand until a later turn (D18)
                    run.summary, run.outputs = outcome.summary, outcome.outputs
                    waiting = True
        except asyncio.CancelledError:
            status, reason = "failed", "cancelled"
        return await self._complete(start, run, status, reason, questions)

    async def _turn(
        self, start: TaskStart, run: _Run, used: int, remaining_time: timedelta
    ) -> TurnOutcome:
        resolved = run.resolved
        result: TurnOutcome = await workflow.execute_activity(
            "run_harness_turn",
            TurnInput(
                task_id=start.task_id,
                turn=run.turn,
                template=resolved.template,
                template_version=resolved.template_version,
                template_hash=resolved.template_hash,
                remaining_tokens=resolved.max_tokens - used,
                remaining_wall_time=remaining_time,
                request_id=start.request_id,
                max_ask_wait=resolved.max_ask_wait,
            ),
            result_type=TurnOutcome,
            task_queue=resolved.task_queue,
            start_to_close_timeout=resolved.turn_timeout,
            heartbeat_timeout=resolved.heartbeat_timeout,
            schedule_to_close_timeout=resolved.turn_timeout * 6,
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            retry_policy=RetryPolicy(
                maximum_attempts=TURN_ATTEMPTS, non_retryable_error_types=NON_RETRYABLE
            ),
        )
        return result

    async def _wait(self, start: TaskStart, run: _Run) -> tuple[str, str | None] | None:
        """After a `waiting` turn: continue as new if the history is long (D11), then
        claim; return None when a claim brought rows (run a woken turn), or the
        task's ending. Raises CancelledError on a cancel (the caller ends the task)."""
        resolved = run.resolved
        while True:
            info = workflow.info()
            if (
                info.is_continue_as_new_suggested()
                or info.get_current_history_length() > HISTORY_LIMIT
            ):
                workflow.continue_as_new(start.model_copy(update={"carried": run.to_state()}))
            remaining = run.deadline - workflow.now()
            if remaining <= timedelta(0):
                return await self._ending_at_wall_time(start, run)
            self.woken = False  # a Signal from here on ends the sleep below
            try:
                claim: InboxClaim = await workflow.execute_activity(
                    "claim_inbox",
                    ClaimInboxInput(task_id=start.task_id, turn=run.turn + 1, now=workflow.now()),
                    result_type=InboxClaim,
                    start_to_close_timeout=SHORT,
                    schedule_to_close_timeout=remaining,
                    # Idempotent: retried until the wall-time deadline (D7).
                    retry_policy=RetryPolicy(maximum_attempts=0),
                )
            except ActivityError as e:
                if isinstance(e.cause, CancelledError):
                    raise asyncio.CancelledError() from e
                unavailable = f"inbox unavailable: {failure_category(e)}"
                if isinstance(e.cause, ApplicationError) and e.cause.non_retryable:
                    return "failed", unavailable
                # Retries stop only when the next one would pass the wall-time deadline:
                # wait for it, then end by open questions like any waiting task (R21).
                left = run.deadline - workflow.now()
                if left > timedelta(0):
                    await workflow.sleep(left)
                return await self._ending_at_wall_time(start, run, unavailable)
            if claim.count:
                return None
            deadline = claim.next_deadline
            now = workflow.now()
            limits = [run.deadline - now]
            if deadline is not None:
                limits.append(deadline - now)
            else:  # the idle timeout applies only with no open question (R20)
                limits.append(resolved.idle_timeout)
            timeout = max(min(limits), timedelta(0))
            try:
                await workflow.wait_condition(lambda: self.woken, timeout=timeout)
            except TimeoutError:
                now = workflow.now()
                if now >= run.deadline:
                    return await self._ending_at_wall_time(start, run)
                if deadline is None:
                    return "succeeded", None  # idle timeout (R20)
                # a question's deadline passed: claim again, which expires it (R17)

    async def _ending_at_wall_time(
        self, start: TaskStart, run: _Run, unavailable: str = "wall-time budget exhausted"
    ) -> tuple[str, str | None]:
        """R21, R31: a waiting task out of wall time succeeded with no open question
        and failed with one. One last claim learns which, whatever path reached the
        deadline; if even that fails, the task failed (with `unavailable`)."""
        try:
            claim: InboxClaim = await workflow.execute_activity(
                "claim_inbox",
                ClaimInboxInput(task_id=start.task_id, turn=run.turn + 1, now=workflow.now()),
                result_type=InboxClaim,
                start_to_close_timeout=SHORT,
                schedule_to_close_timeout=SHORT * 2,
            )
        except ActivityError:
            return "failed", unavailable
        if claim.next_deadline is None:
            return "succeeded", None
        return "failed", "wall-time budget exhausted"

    async def _complete(
        self,
        start: TaskStart,
        run: _Run,
        status: str,
        reason: str | None,
        questions: list[str],
    ) -> TaskResult:
        payload = CompleteTaskInput(
            task_id=start.task_id,
            status=status,  # type: ignore[arg-type]
            summary=run.summary,
            artifacts=run.outputs,
            questions=questions,
            failure_reason=reason,
            resolved=run.resolved,
            turns=run.turn,
            attempts=run.attempts,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            inner_turns=run.inner_turns,
            usage_known=run.usage_known,
        )
        # Idempotent, so retried without limit: an ending during a database outage
        # still closes the task's messages once it returns (D17, R24). A cancel that
        # lands while it runs interrupts it only once.
        for _ in range(2):
            try:
                result: TaskResult = await workflow.execute_activity(
                    "complete_task",
                    payload,
                    result_type=TaskResult,
                    start_to_close_timeout=SHORT,
                    retry_policy=COMPLETE_RETRY,
                )
                return result
            except asyncio.CancelledError:
                continue
        raise asyncio.CancelledError()


@dataclasses.dataclass
class _Run:
    """The Phase 2 loop's working state; `TaskState` is its frozen, carried form."""

    resolved: ResolvedTask
    deadline: datetime
    turn: int = 0
    work_turns: int = 0
    wakes: int = 0
    attempts: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    inner_turns: int = 0
    usage_known: bool = True
    summary: str = ""
    outputs: list[Artifact] = dataclasses.field(default_factory=list)

    @classmethod
    def from_state(cls, state: TaskState) -> _Run:
        return cls(**{f.name: getattr(state, f.name) for f in dataclasses.fields(cls)})

    def to_state(self) -> TaskState:
        return TaskState(**{f.name: getattr(self, f.name) for f in dataclasses.fields(self)})

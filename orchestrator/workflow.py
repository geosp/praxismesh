"""`TaskWorkflow`: one durable task on the orchestration queue (RFC Phase 1).

Drives harness turns on `tpl.{template}`, accounts turns, tokens and wall time,
and retries infrastructure failures only. Inputs and outputs are IDs and
`BlobRef`s; all I/O happens in Activities (plan §2).
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from common.schemas import (
        Artifact,
        CompleteTaskInput,
        RecordTaskInput,
        ResolvedTask,
        TaskResult,
        TaskStart,
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


def failure_category(error: ActivityError) -> str:
    cause = error.cause
    if isinstance(cause, ApplicationError) and cause.type:
        return cause.type
    return type(cause).__name__ if cause is not None else "ActivityError"


@workflow.defn(name="TaskWorkflow")
class TaskWorkflow:
    @workflow.run
    async def run(self, start: TaskStart) -> TaskResult:
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
        turns = attempts = tokens_in = tokens_out = 0
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
                    ),
                    result_type=TurnOutcome,
                    task_queue=resolved.task_queue,
                    start_to_close_timeout=resolved.turn_timeout,
                    heartbeat_timeout=resolved.heartbeat_timeout,
                    schedule_to_close_timeout=resolved.turn_timeout * 6,
                    retry_policy=RetryPolicy(
                        maximum_attempts=TURN_ATTEMPTS,
                        non_retryable_error_types=NON_RETRYABLE,
                    ),
                )
            except ActivityError as e:
                reason = f"harness turn {turns} failed: {failure_category(e)}"
                break
            attempts += outcome.attempts
            tokens_in += outcome.tokens_in
            tokens_out += outcome.tokens_out
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
            ),
            result_type=TaskResult,
            start_to_close_timeout=SHORT,
            retry_policy=SHORT_RETRY,
        )
        return result

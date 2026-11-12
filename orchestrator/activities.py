"""Orchestrator Activities for `TaskWorkflow` (RFC Phase 1: TaskWorkflow)."""

from __future__ import annotations

import logging

from temporalio import activity

from common.observability import log_context
from common.persistence.repositories import AttemptRepository, TaskRepository
from common.schemas import (
    CompleteTaskInput,
    RecordTaskInput,
    ResolvedTask,
    TaskResult,
    TaskStart,
)
from orchestrator.constants import template_queue
from registry.loader import Registry

log = logging.getLogger("praxis.orchestrator")


def _ids(task_id: str, request_id: str | None = None) -> dict[str, str | None]:
    info = activity.info()
    return {"request_id": request_id, "task_id": task_id, "workflow_id": info.workflow_id}


class OrchestratorActivities:
    def __init__(self, registry: Registry, tasks: TaskRepository) -> None:
        self.registry = registry
        self.tasks = tasks
        self.attempts = AttemptRepository(tasks.engine)

    @activity.defn(name="resolve_capabilities")
    async def resolve_capabilities(self, start: TaskStart) -> ResolvedTask:
        """Choose the template and the effective budget: the smaller of the profile's
        value and the template's cap."""
        with log_context(**_ids(start.task_id, start.request_id)):
            profile, loaded = self.registry.resolve(start.profile, start.template)
            log.info("resolved", extra={"fields": {"template": loaded.template.ref}})
        t = loaded.template
        return ResolvedTask(
            template=t.name,
            template_version=t.version,
            template_hash=loaded.hash,
            task_queue=template_queue(t.name),
            tier=profile.tier,
            max_turns=min(profile.max_turns, t.max_turns_cap),
            max_tokens=min(profile.max_tokens, t.max_tokens_cap),
            max_wall_time=min(profile.max_wall_time, t.max_wall_time_cap),
            turn_timeout=t.turn_timeout,
            heartbeat_timeout=t.heartbeat_timeout,
        )

    @activity.defn(name="record_task")
    async def record_task(self, payload: RecordTaskInput) -> None:
        info = activity.info()
        if info.workflow_id is None or info.workflow_run_id is None:
            raise RuntimeError("record_task must run inside a Workflow")
        with log_context(**_ids(payload.start.task_id, payload.start.request_id)):
            log.info("recording task")
        await self.tasks.record_task(
            payload.start,
            workflow_id=info.workflow_id,
            run_id=info.workflow_run_id,
            template_version=payload.resolved.template_version,
            template_hash=payload.resolved.template_hash,
        )

    @activity.defn(name="complete_task")
    async def complete_task(self, payload: CompleteTaskInput) -> TaskResult:
        r = payload.resolved
        result = TaskResult(
            task_id=payload.task_id,
            status=payload.status,
            summary=payload.summary,
            artifacts=payload.artifacts,
            questions=payload.questions,
            failure_reason=payload.failure_reason,
            tier_used=r.tier,
            template=r.template,
            template_version=r.template_version,
            template_hash=r.template_hash,
            turns=payload.turns,
            attempts=payload.attempts,
            tokens_in=payload.tokens_in,
            tokens_out=payload.tokens_out,
            inner_turns=payload.inner_turns,
        )
        # Rows still open (for example after schedule_to_close expired, when no
        # Activity code ran) are closed with the task (gate F2).
        await self.attempts.close_unfinished(payload.task_id, None, "task_completed")
        await self.tasks.complete(payload.task_id, payload.status, result.model_dump(mode="json"))
        row = await self.tasks.get(payload.task_id)
        with log_context(**_ids(payload.task_id, (row or {}).get("request_id"))):
            log.info(
                "task completed",
                extra={"fields": {"status": payload.status, "reason": payload.failure_reason}},
            )
        return result

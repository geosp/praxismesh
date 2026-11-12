"""Orchestrator Activities for `TaskWorkflow` (RFC Phase 1: TaskWorkflow)."""

from __future__ import annotations

from temporalio import activity

from common.persistence.repositories import TaskRepository
from common.schemas import (
    CompleteTaskInput,
    RecordTaskInput,
    ResolvedTask,
    TaskResult,
    TaskStart,
)
from orchestrator.constants import template_queue
from registry.loader import Registry


class OrchestratorActivities:
    def __init__(self, registry: Registry, tasks: TaskRepository) -> None:
        self.registry = registry
        self.tasks = tasks

    @activity.defn(name="resolve_capabilities")
    async def resolve_capabilities(self, start: TaskStart) -> ResolvedTask:
        """Choose the template and the effective budget: the smaller of the profile's
        value and the template's cap."""
        profile, loaded = self.registry.resolve(start.profile, start.template)
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
        )
        await self.tasks.complete(payload.task_id, payload.status, result.model_dump(mode="json"))
        return result

"""Tasks with stored blobs, for the removal tests (Phase 3A persistence plan phase
02): a task recorded and ended through the real writers, with its uploads held by
it, so its references are the ones production writes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.persistence.messages import MessageRepository
from common.persistence.repositories import RecordingBlobStore, TaskRepository
from common.schemas import BlobRef, TaskResult, TaskStart


def new_task_id(prefix: str = "task-life") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class StoredTask:
    task_id: str
    request_id: str
    instructions: BlobRef
    inputs: dict[str, BlobRef] = field(default_factory=dict)
    artifacts: dict[str, BlobRef] = field(default_factory=dict)


async def record_task(
    engine: AsyncEngine,
    store: RecordingBlobStore,
    *,
    task_id: str | None = None,
    request_id: str | None = None,
    inputs: dict[str, bytes] | None = None,
) -> StoredTask:
    """Upload the instructions and inputs for a new task and record it, `running`."""
    task = task_id or new_task_id()
    instructions = await store.put(
        f"instructions {task}".encode(), retention="transcript", task_id=task
    )
    refs = {
        path: await store.put(data, retention="transcript", task_id=task)
        for path, data in (inputs or {}).items()
    }
    start = TaskStart(
        task_id=task,
        request_id=request_id or f"req-{task}",
        profile="openai",
        template="local-default",
        instructions_ref=instructions,
        input_refs=refs,
    )
    await TaskRepository(engine).record_task(
        start, workflow_id=task, run_id="run-1", template_version=1, template_hash="sha256:x"
    )
    return StoredTask(task, start.request_id, instructions, refs)


async def end_task(
    engine: AsyncEngine,
    store: RecordingBlobStore,
    stored: StoredTask,
    *,
    artifacts: dict[str, bytes] | None = None,
    status: str = "succeeded",
    ended_at: datetime | None = None,
    questions: list[str] | None = None,
) -> StoredTask:
    """Upload the artifacts and end the task through `end_task`; `ended_at`, if
    given, is then set as if the task had ended then."""
    for path, data in (artifacts or {}).items():
        stored.artifacts[path] = await store.put(data, retention="artifact", task_id=stored.task_id)
    result = TaskResult(
        task_id=stored.task_id,
        status=status,  # type: ignore[arg-type]
        summary=f"summary of {stored.task_id}",
        artifacts=[{"path": p, "ref": r} for p, r in stored.artifacts.items()],  # type: ignore[misc]
        questions=questions or [],
        failure_reason="it broke" if status == "failed" else None,
        tier_used="local",
        template="local-default",
        template_version=1,
        template_hash="sha256:x",
        turns=1,
        attempts=1,
        tokens_in=10,
        tokens_out=5,
    )
    await MessageRepository(engine).end_task(stored.task_id, status, result.model_dump(mode="json"))
    if ended_at is not None:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE tasks SET ended_at = :at WHERE task_id = :t"),
                {"at": ended_at, "t": stored.task_id},
            )
    return stored

"""Prepare and start a task (RFC Phase 1, TaskWorkflow: starting a task).

`prepare_task` validates the request, resolves the profile and template, mints the
task and request IDs, and uploads the instructions and input files as `task`
blobs, so the Workflow's input holds only IDs and blob references.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from common.blob_store import BlobStore
from common.errors import InvalidTaskInput
from common.schemas import TaskStart
from orchestrator.constants import TASK_WORKFLOW, orchestration_queue
from orchestrator.requests import parse_task_request
from registry.loader import Registry


def mint_task_id() -> str:
    return f"task-{uuid.uuid4()}"


async def prepare_task(
    data: dict[str, Any], registry: Registry, blobs: BlobStore, *, base_dir: Path
) -> TaskStart:
    request = parse_task_request(data)
    _, loaded = registry.resolve(request.profile, request.template)
    instructions_ref = await blobs.put(
        request.instructions.encode(), content_type="text/markdown", retention="task"
    )
    input_refs = {}
    for name in request.input_files:
        path = (base_dir / name).resolve()
        if not path.is_file():
            raise InvalidTaskInput(f"input file not found: {name}")
        input_refs[path.name] = await blobs.put(path.read_bytes(), retention="task")
    return TaskStart(
        task_id=request.task_id or mint_task_id(),
        request_id=f"req-{uuid.uuid4()}",
        profile=request.profile,
        template=loaded.template.name,
        instructions_ref=instructions_ref,
        input_refs=input_refs,
        outputs=request.outputs,
    )


async def start_task(client: Client, start: TaskStart) -> WorkflowHandle[Any, Any]:
    """Start `TaskWorkflow`. Temporal rejects a second start with the same ID while
    it remembers the first run; the `tasks` table rejects it after that."""
    return await client.start_workflow(
        TASK_WORKFLOW,
        start,
        id=start.task_id,
        task_queue=orchestration_queue(),
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
    )

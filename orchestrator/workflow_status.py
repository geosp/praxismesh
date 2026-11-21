"""What Temporal reports for a task's Workflow (its ID is the task ID), as `gc`,
`request delete` and `reconcile` ask it (Phase 3A persistence plan D5, R17,
R21)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

WorkflowStatus = Literal["running", "closed", "missing"]
# The status of a task's Workflow, by task ID.
StatusOf = Callable[[str], Awaitable[WorkflowStatus]]


async def workflow_status(client: Client, workflow_id: str) -> WorkflowStatus:
    """`running`, `closed` or `missing` (unknown, or beyond Temporal's retention);
    other Temporal errors propagate."""
    try:
        description = await client.get_workflow_handle(workflow_id).describe()
    except RPCError as e:
        if e.status == RPCStatusCode.NOT_FOUND:
            return "missing"
        raise
    return "running" if description.status == WorkflowExecutionStatus.RUNNING else "closed"


def status_of(client: Client) -> StatusOf:
    return lambda workflow_id: workflow_status(client, workflow_id)

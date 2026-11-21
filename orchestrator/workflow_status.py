"""What Temporal reports for a task's Workflow (its ID is the task ID), as `gc`,
`request delete` and `reconcile` ask it (Phase 3A persistence plan D5, R17,
R21)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from common.errors import PraxisError

WorkflowStatus = Literal["running", "closed", "missing"]
# The status of a task's Workflow, by task ID.
StatusOf = Callable[[str], Awaitable[WorkflowStatus]]


class WorkflowStatusUnavailable(PraxisError):
    """Temporal could not say (impl-review F186): the CLI prints an `error:` line
    and exits 2, so it is never read as `reconcile`'s findings (exit 1)."""


async def workflow_status(client: Client, workflow_id: str) -> WorkflowStatus:
    """`running`, `closed` or `missing` (unknown, or beyond Temporal's retention);
    any other Temporal error is a `WorkflowStatusUnavailable`."""
    try:
        description = await client.get_workflow_handle(workflow_id).describe()
    except RPCError as e:
        if e.status == RPCStatusCode.NOT_FOUND:
            return "missing"
        raise WorkflowStatusUnavailable(
            f"Temporal could not report Workflow {workflow_id}: {e.status.name}: {e.message}"
        ) from e
    return "running" if description.status == WorkflowExecutionStatus.RUNNING else "closed"


def status_of(client: Client) -> StatusOf:
    return lambda workflow_id: workflow_status(client, workflow_id)

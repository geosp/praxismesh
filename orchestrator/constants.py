"""Task queue names (RFC Phase 1, Components).

`PRAXIS_QUEUE_PREFIX` (default empty) namespaces every queue, so a test run's
in-process workers never share queues with running worker containers. Workflow
code never reads it: `resolve_capabilities` puts the template queue into
`ResolvedTask`.
"""

from __future__ import annotations

import os

TASK_WORKFLOW = "TaskWorkflow"


def _prefix() -> str:
    return os.environ.get("PRAXIS_QUEUE_PREFIX", "")


def orchestration_queue() -> str:
    return f"{_prefix()}orchestration"


def template_queue(template: str) -> str:
    """Workers for a template poll `tpl.{template}` (plan §4.2)."""
    return f"{_prefix()}tpl.{template}"

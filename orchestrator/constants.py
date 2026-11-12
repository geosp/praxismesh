"""Task queue names (RFC Phase 1, Components)."""

from __future__ import annotations

ORCHESTRATION_QUEUE = "orchestration"
TASK_WORKFLOW = "TaskWorkflow"


def template_queue(template: str) -> str:
    """Workers for a template poll `tpl.{template}` (plan §4.2)."""
    return f"tpl.{template}"

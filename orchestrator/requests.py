"""Validate task requests before any Workflow starts (plan §4.10; RFC Capability model).

A request may not name capabilities. Those come only from the template, so a
request field such as `skills` or `mcp_servers` is a capability error, reported
by name; any other unknown field is an input error.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from common.errors import CapabilityError, InvalidTaskInput
from common.schemas import TaskRequest

CAPABILITY_FIELDS = frozenset(
    {
        "mcp",
        "mcp_servers",
        "skills",
        "skills_bundle",
        "tools",
        "allowed_tools",
        "cli_tools",
        "model",
        "base_url",
        "harness",
    }
)


def parse_task_request(data: dict[str, Any]) -> TaskRequest:
    """Return the validated request, or raise naming the offending fields."""
    injected = sorted(CAPABILITY_FIELDS & set(data))
    if injected:
        raise CapabilityError(
            f"a task request may not set {', '.join(injected)}: "
            "capabilities come only from the worker template"
        )
    try:
        return TaskRequest.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'request'}: {err['msg']}"
            for err in e.errors()
        )
        raise InvalidTaskInput(f"invalid task request: {problems}") from e

"""A copy of the root `AgentEvent` schema (`common/schemas/events.py`).

The root project is not installable, so the spike keeps its own copy (plan D1).
`tests/test_models.py` checks that the field names still match the root schema.
`blob_ref` is a plain mapping here: the spike never sets it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "status",
    "token",
    "tool_call",
    "tool_result",
    "plan",
    "approval_request",
    "result",
    "error",
    "reset",
]


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int = Field(ge=0)
    timestamp: datetime
    workflow_id: str
    task_id: str
    attempt_id: str
    type: EventType
    payload: dict[str, Any] = {}
    blob_ref: dict[str, Any] | None = None

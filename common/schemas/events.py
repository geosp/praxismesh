"""`AgentEvent`: what a harness turn reports while it runs (docs/roadmap/schemas.md).

The DSH migration plan (D8) adds this minimal form so both runners emit events
before roadmap Phase 2 adds the transport, offsets and retention.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from common.schemas.base import Strict
from common.schemas.blob import BlobRef

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


class AgentEvent(Strict):
    seq: int = Field(ge=0)
    timestamp: datetime
    workflow_id: str
    task_id: str
    attempt_id: str = Field(description="task:turn:attempt; identifies the attempt that emitted it")
    type: EventType
    # Small, content-free payload: counts, tool names and statuses, never prompt
    # or model text. Larger data goes to a blob.
    payload: dict[str, Any] = {}
    blob_ref: BlobRef | None = None

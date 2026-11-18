"""Inbox schemas (Phase 2 messaging D6, D7; docs/roadmap/schemas.md).

`MessageEnvelope` mirrors a `task_messages` row. The body is inline text of at most
16 KB (D6), not the blob reference the roadmap first planned; the authorization
context is the request it belongs to (D9). `InboxClaim` is what `claim_inbox`
returns to the Workflow: IDs and a deadline, never a body (R28).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from common.schemas.base import Strict

MessageKind = Literal["send", "ask", "reply"]
MessageStatus = Literal[
    "pending", "claimed", "read", "answered", "expired", "cancelled", "undelivered", "rejected"
]


class MessageEnvelope(Strict):
    schema_version: Literal[1] = 1
    message_id: str
    request_id: str
    sender_task: str
    recipient_task: str
    kind: MessageKind
    correlation_id: str | None = None
    reply_to: str | None = None
    deadline: datetime | None = None
    status: MessageStatus
    reason: str | None = None
    body: str = Field(max_length=16_384)
    idempotency_key: str
    claimed_turn: int | None = None
    notice_turn: int | None = None
    created_at: datetime


class InboxClaim(Strict):
    schema_version: Literal[1] = 1
    message_ids: list[str] = []
    next_deadline: datetime | None = None

    @property
    def count(self) -> int:
        return len(self.message_ids)

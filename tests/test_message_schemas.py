"""Inbox schemas (Phase 2 messaging task 2.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from common.schemas import InboxClaim, MessageEnvelope


def envelope(**kw: object) -> MessageEnvelope:
    fields: dict[str, object] = {
        "message_id": "m1", "request_id": "req", "sender_task": "task-a",
        "recipient_task": "task-b", "kind": "ask", "correlation_id": "m1", "status": "pending", "body": "price?",
        "idempotency_key": "k", "created_at": datetime.now(UTC),
    } | kw  # fmt: skip
    return MessageEnvelope.model_validate(fields)


def test_an_envelope_round_trips() -> None:
    e = envelope()
    assert MessageEnvelope.model_validate_json(e.model_dump_json()) == e


def test_bodies_are_capped_and_kinds_and_statuses_are_checked() -> None:
    with pytest.raises(ValidationError):
        envelope(body="x" * 16_385)
    with pytest.raises(ValidationError):
        envelope(kind="broadcast")
    with pytest.raises(ValidationError):
        envelope(status="deleted")


def test_a_claim_carries_ids_and_a_deadline_only() -> None:
    claim = InboxClaim(message_ids=["m1", "m2"])
    assert claim.count == 2 and claim.next_deadline is None
    assert set(InboxClaim.model_fields) == {"schema_version", "message_ids", "next_deadline"}

"""The recorded DSH turn parses as `AgentEvent`s and holds no prompt text or
credentials (task 1.3, plan D3, R7)."""

from __future__ import annotations

from pathlib import Path

from event_transport.models import AgentEvent

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "dsh-turn-t01.jsonl"
ALLOWED = {"request_id", "input_tokens", "output_tokens", "tool", "call", "status"}


def recorded_turn() -> list[AgentEvent]:
    return [AgentEvent.model_validate_json(line) for line in FIXTURE.read_text().splitlines()]


def test_fixture_parses_and_is_one_attempt_in_order() -> None:
    events = recorded_turn()
    assert len(events) > 10
    assert [e.seq for e in events] == list(range(len(events)))
    assert len({e.attempt_id for e in events}) == 1


def test_payloads_hold_only_counts_names_and_statuses() -> None:
    for event in recorded_turn():
        assert set(event.payload) <= ALLOWED, event.payload
        for value in event.payload.values():
            assert not isinstance(value, str) or len(value) <= 40, value

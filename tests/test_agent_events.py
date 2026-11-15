"""DSH migration plan D8: the AgentEvent sink orders events and carries no text."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from common.schemas import AgentEvent
from harness_activity.events import AttemptEvents, MemorySink, NoOpSink


def test_events_are_ordered_and_carry_attempt_identity() -> None:
    sink = MemorySink()
    events = AttemptEvents(sink, "wf-1", "task-1", turn=2, attempt=3)
    events.emit("status", state="running")
    events.emit("tool_call", tool="read_file")
    events.emit("tool_result", tool="read_file", ok=True)
    events.emit("token", input_tokens=7, output_tokens=3)
    assert [e.seq for e in sink.events] == [0, 1, 2, 3]
    assert {e.attempt_id for e in sink.events} == {"task-1:2:3"}
    assert [e.type for e in sink.events] == ["status", "tool_call", "tool_result", "token"]


def test_unknown_event_type_and_fields_are_rejected() -> None:
    events = AttemptEvents(NoOpSink(), "wf-1", "task-1", turn=1, attempt=1)
    with pytest.raises(ValidationError):
        events.emit("prompt_text", text="secret")  # type: ignore[arg-type]
    good = events.emit("status", state="running")
    with pytest.raises(ValidationError):
        AgentEvent.model_validate({**good.model_dump(), "prompt": "text"})

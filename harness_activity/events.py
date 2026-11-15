"""Event sink for harness turns (DSH migration plan D8, R16).

Runners emit `AgentEvent`s through a sink. Roadmap Phase 2 replaces the no-op sink
with its streaming transport; tests use the in-memory sink.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Protocol

from common.schemas.events import AgentEvent, EventType


class EventSink(Protocol):
    def emit(self, event: AgentEvent) -> None: ...


class NoOpSink:
    def emit(self, event: AgentEvent) -> None:
        return None


class MemorySink:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


class AttemptEvents:
    """Numbers one attempt's events in emission order and stamps its identity."""

    def __init__(self, sink: EventSink, workflow_id: str, task_id: str, turn: int, attempt: int):
        self.sink, self.workflow_id, self.task_id = sink, workflow_id, task_id
        self.attempt_id = f"{task_id}:{turn}:{attempt}"
        self.seq = 0
        self.lock = threading.Lock()

    def emit(self, type: EventType, **payload: Any) -> AgentEvent:
        with self.lock:
            event = AgentEvent(
                seq=self.seq,
                timestamp=datetime.now(UTC),
                workflow_id=self.workflow_id,
                task_id=self.task_id,
                attempt_id=self.attempt_id,
                type=type,
                payload=payload,
            )
            self.seq += 1
        self.sink.emit(event)
        return event

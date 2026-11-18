"""An attempt's event stream for tests that call a runner directly."""

from __future__ import annotations

from harness_activity.events import AttemptEvents, MemorySink


def attempt_events(task: str = "task", turn: int = 1, attempt: int = 1) -> AttemptEvents:
    return AttemptEvents(MemorySink(), task, task, turn, attempt)

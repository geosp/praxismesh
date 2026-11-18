"""Event builders shared by the tests."""

from __future__ import annotations

from datetime import UTC, datetime

from event_transport.models import AgentEvent


def events(n: int, workflow_id: str = "wf-1", attempt: int = 1, start: int = 0) -> list[AgentEvent]:
    return [
        AgentEvent(
            seq=start + i,
            timestamp=datetime.now(UTC),
            workflow_id=workflow_id,
            task_id="task-1",
            attempt_id=f"task-1:1:{attempt}",
            type="token",
            payload={"i": start + i},
        )
        for i in range(n)
    ]

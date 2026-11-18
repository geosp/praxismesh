"""The event-transport interface (ADR-0009; Phase 2 events plan D1).

Offsets are per workflow, start at 1 and have no gaps. `read(after=N)` yields the
events with offsets above N. If any of them is no longer retained, it first yields
one `Expired` naming the retained base. Ported from the event-transport spike
(`spikes/event-transport/event_transport/transport.py`, issue #76).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from common.schemas.events import AgentEvent

# A re-sent batch ID is recognised for this long (the spike's re-send horizon).
RESEND_HORIZON_S = 600.0


@dataclass(frozen=True)
class Writer:
    """The attempt a batch comes from; the table transport fences on it (ADR-0007)."""

    task_id: str
    turn: int
    attempt: int


@dataclass(frozen=True)
class Expired:
    """Events after the requested offset were pruned; reading resumes at `retained_base`."""

    retained_base: int


Item = tuple[int, AgentEvent] | Expired


def expiry_for(after: int, retained_base: int | None) -> Expired | None:
    """The `Expired` a reader must yield first, if any: when some offset above
    `after` is below the retained base. Shared by every implementation."""
    if retained_base is not None and after < retained_base - 1:
        return Expired(retained_base)
    return None


async def guarded(after: int, items: AsyncIterator[Item]) -> AsyncGenerator[Item, None]:
    """The reader rule every implementation applies: an offset that jumps past the
    next one expected means events were pruned during the read, so an `Expired`
    naming it comes first; an offset that goes backwards or repeats is a bug and
    raises."""
    position = after
    async for item in items:
        if isinstance(item, Expired):
            yield item
            position = item.retained_base - 1
            continue
        offset = item[0]
        if offset <= position:
            raise RuntimeError(f"offset {offset} after {position}: repeated or out of order")
        if offset > position + 1:
            yield Expired(offset)
        yield item
        position = offset


class EventTransport(Protocol):
    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[AgentEvent]
    ) -> None:
        """Store a batch. Re-sending a batch ID within the re-send horizon stores
        nothing. Raises `FenceRejected` if a newer turn or attempt of the writer's
        task exists (the table transport; the in-memory reference does not fence)."""

    def read(
        self, workflow_id: str, after: int, *, follow: bool = False
    ) -> AsyncGenerator[Item, None]:
        """Yield `(offset, event)` above `after`, after an `Expired` if needed. With
        `follow`, wait for new events instead of stopping at the latest."""

    async def latest(self, workflow_id: str) -> int | None:
        """The highest offset stored, or None for an empty workflow."""

    async def prune(
        self, workflow_id: str, *, below: int | None = None, older_than: timedelta | None = None
    ) -> int | None:
        """Delete an offset prefix: below `below`, or the longest prefix whose events
        were all stored more than `older_than` ago. Returns the new retained base
        (the lowest remaining offset, or the next offset if none remain), or None
        for an empty workflow."""

    async def close(self) -> None:
        """Release connections."""

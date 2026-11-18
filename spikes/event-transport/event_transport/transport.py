"""The event-transport interface every option implements (plan D1, notes.md#d1).

Offsets are per workflow, start at 1 and have no gaps. `read(after=N)` yields the
events with offsets above N. If any of them is no longer retained, it first
yields one `Expired` naming the retained base (R2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from event_transport.models import AgentEvent


@dataclass(frozen=True)
class Expired:
    """Events after the requested offset were removed; reading resumes at `retained_base`."""

    retained_base: int


Item = tuple[int, AgentEvent] | Expired


def expiry_for(after: int, retained_base: int | None) -> Expired | None:
    """The `Expired` a reader must yield first, if any: when some offset above
    `after` is below the retained base. Shared by every implementation."""
    if retained_base is not None and after < retained_base - 1:
        return Expired(retained_base)
    return None


async def guarded(after: int, items: AsyncIterator[Item]) -> AsyncIterator[Item]:
    """The reader rule every implementation applies (impl review F31): an offset that
    jumps past the next one expected means events were removed during the read, so an
    `Expired` naming it comes first; an offset that goes backwards or repeats is a bug
    and raises, so the suite sees it."""
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
    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        """Store a batch. Re-sending a batch ID within the re-send horizon stores nothing (R3)."""

    def read(self, workflow_id: str, after: int, *, follow: bool = False) -> AsyncIterator[Item]:
        """Yield `(offset, event)` above `after`, after an `Expired` if needed. With
        `follow`, wait for new events instead of stopping at the latest."""

    async def latest(self, workflow_id: str) -> int | None:
        """The highest offset stored, or None for an empty workflow."""

    async def expire_below(self, workflow_id: str, offset: int) -> None:
        """Test hook: remove every event below `offset` using the option's retention (R2)."""

    async def roll_over(self, workflow_id: str) -> bool:
        """Test hook: Continue-As-New for options hosted in a Workflow, returning once
        the new run has started; returns False for options with no Workflow (R4)."""

    async def close(self) -> None:
        """Release connections."""

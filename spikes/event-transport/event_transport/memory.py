"""In-memory reference implementation, used to validate the shared suite (task 1.2)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from event_transport.models import AgentEvent
from event_transport.transport import Item, expiry_for, guarded


@dataclass
class _Log:
    events: dict[int, AgentEvent] = field(default_factory=dict)
    next_offset: int = 1
    base: int = 1
    batches: dict[str, float] = field(default_factory=dict)  # batch_id -> first seen
    changed: asyncio.Event = field(default_factory=asyncio.Event)


class MemoryTransport:
    def __init__(self, horizon_s: float = 600.0) -> None:
        self.horizon_s = horizon_s
        self.logs: dict[str, _Log] = {}

    def _log(self, workflow_id: str) -> _Log:
        return self.logs.setdefault(workflow_id, _Log())

    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        log = self._log(workflow_id)
        now = time.monotonic()
        log.batches = {b: t for b, t in log.batches.items() if now - t < self.horizon_s}
        if batch_id in log.batches:
            return
        log.batches[batch_id] = now
        for event in events:
            log.events[log.next_offset] = event
            log.next_offset += 1
        log.changed.set()

    def read(self, workflow_id: str, after: int, *, follow: bool = False) -> AsyncIterator[Item]:
        return guarded(after, self._read(workflow_id, after, follow))

    async def _read(self, workflow_id: str, after: int, follow: bool) -> AsyncIterator[Item]:
        log = self._log(workflow_id)
        expired = expiry_for(after, log.base) if log.next_offset > 1 else None
        if expired is not None:
            yield expired
            after = expired.retained_base - 1
        position = after
        while True:
            while position + 1 < log.next_offset:
                if position + 1 < log.base:
                    position = log.base - 1  # removed during the read: guarded() reports it
                    continue
                position += 1
                yield position, log.events[position]
            if not follow:
                return
            log.changed.clear()
            await log.changed.wait()

    async def latest(self, workflow_id: str) -> int | None:
        log = self._log(workflow_id)
        return log.next_offset - 1 if log.next_offset > 1 else None

    async def expire_below(self, workflow_id: str, offset: int) -> None:
        log = self._log(workflow_id)
        for o in range(log.base, min(offset, log.next_offset)):
            log.events.pop(o, None)
        log.base = max(log.base, min(offset, log.next_offset))

    async def roll_over(self, workflow_id: str) -> bool:
        return False

    async def close(self) -> None:
        return None

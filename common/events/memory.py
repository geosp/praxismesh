"""In-memory reference implementation of the event transport. It validates the
shared suite and backs unit tests; it does not fence (it has no attempt rows)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from common.events.transport import RESEND_HORIZON_S, Item, Writer, expiry_for, guarded
from common.schemas.events import AgentEvent


@dataclass
class _Log:
    events: dict[int, tuple[float, AgentEvent]] = field(default_factory=dict)  # stored at
    next_offset: int = 1
    base: int = 1
    batches: dict[str, float] = field(default_factory=dict)  # batch_id -> first seen
    changed: asyncio.Event = field(default_factory=asyncio.Event)


class MemoryTransport:
    def __init__(self, horizon_s: float = RESEND_HORIZON_S) -> None:
        self.horizon_s = horizon_s
        self.logs: dict[str, _Log] = {}

    def _log(self, workflow_id: str) -> _Log:
        return self.logs.setdefault(workflow_id, _Log())

    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[AgentEvent]
    ) -> None:
        log = self._log(workflow_id)
        now = time.monotonic()
        log.batches = {b: t for b, t in log.batches.items() if now - t < self.horizon_s}
        if batch_id in log.batches:
            return
        log.batches[batch_id] = now
        for event in events:
            log.events[log.next_offset] = (time.time(), event)
            log.next_offset += 1
        log.changed.set()

    def read(
        self, workflow_id: str, after: int, *, follow: bool = False
    ) -> AsyncGenerator[Item, None]:
        return guarded(after, self._read(workflow_id, after, follow))

    async def _read(self, workflow_id: str, after: int, follow: bool) -> AsyncIterator[Item]:
        log = self._log(workflow_id)
        expired = expiry_for(after, log.base) if log.next_offset > 1 else None
        if expired is not None:
            yield expired
            after = expired.retained_base - 1
        position = after
        while True:
            log.changed.clear()
            while position + 1 < log.next_offset:
                if position + 1 < log.base:
                    position = log.base - 1  # pruned during the read: guarded() reports it
                    continue
                position += 1
                yield position, log.events[position][1]
            if not follow:
                return
            await log.changed.wait()

    async def latest(self, workflow_id: str) -> int | None:
        log = self._log(workflow_id)
        return log.next_offset - 1 if log.next_offset > 1 else None

    async def prune(
        self,
        workflow_id: str,
        *,
        below: int | None = None,
        older_than: timedelta | None = None,
        conn: Any = None,
        limit: int | None = None,
        removed_by: str | None = None,
    ) -> int | None:
        log = self._log(workflow_id)
        if log.next_offset == 1:
            return None
        cutoff = _cutoff(log, below, older_than)
        if limit is not None:
            cutoff = min(cutoff, log.base + limit)
        for o in range(log.base, min(cutoff, log.next_offset)):
            log.events.pop(o, None)
        log.base = max(log.base, min(cutoff, log.next_offset))
        return log.base

    async def close(self) -> None:
        return None


def _cutoff(log: _Log, below: int | None, older_than: timedelta | None) -> int:
    if (below is None) == (older_than is None):
        raise ValueError("give exactly one of below and older_than")
    if below is not None:
        return below
    assert older_than is not None
    threshold = time.time() - older_than.total_seconds()
    newer = [o for o, (stored, _) in log.events.items() if stored >= threshold]
    return min(newer) if newer else log.next_offset

"""How the suite builds each transport, by name (`SPIKE_TRANSPORTS`).

`hosted` says whether the option keeps its log in a Temporal Workflow: R4 and R11
apply only then; for the others they are reported as N/A (plan D2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from event_transport.transport import EventTransport


@dataclass(frozen=True)
class Option:
    name: str
    hosted: bool
    build: Callable[[float], Awaitable[EventTransport]]  # horizon_s -> transport


async def _memory(horizon_s: float) -> EventTransport:
    from event_transport.memory import MemoryTransport

    return MemoryTransport(horizon_s)


OPTIONS: dict[str, Option] = {
    "memory": Option("memory", hosted=False, build=_memory),
}

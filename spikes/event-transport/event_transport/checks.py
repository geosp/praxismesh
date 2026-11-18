"""The requirement checks every transport runs (plan R1-R4, R7; task 1.4).

Each check is a plain async function that raises AssertionError when the transport
breaks the requirement, so the suite and its own validation share one definition.
Every check uses a fresh workflow ID, so transports with durable state can share a
stack between checks.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from event_transport.models import AgentEvent
from event_transport.transport import EventTransport, Expired, Item

BATCH = 64  # publish batch size (notes.md#d5)


def make_events(workflow_id: str, n: int, start: int = 0) -> list[AgentEvent]:
    return [
        AgentEvent(
            seq=start + i,
            timestamp=datetime.now(UTC),
            workflow_id=workflow_id,
            task_id=workflow_id,
            attempt_id=f"{workflow_id}:1:1",
            type="token",
            payload={"i": start + i},
        )
        for i in range(n)
    ]


def new_workflow() -> str:
    return f"wf-{uuid.uuid4().hex[:12]}"


async def collect(t: EventTransport, wf: str, after: int) -> list[Item]:
    return [item async for item in t.read(wf, after)]


def offsets(items: list[Item]) -> list[int]:
    return [i[0] for i in items if not isinstance(i, Expired)]


async def check_r1_resume(t: EventTransport) -> None:
    """R1: a reader killed after offset N resumes at N+1, in order, with no repeat."""
    wf = new_workflow()
    for b in range(3):
        await t.publish(wf, f"{wf}-b{b}", make_events(wf, 4, start=4 * b))
    got: list[int] = []

    async def tail() -> None:
        async for item in t.read(wf, 0, follow=True):
            assert not isinstance(item, Expired)
            got.append(item[0])
            if len(got) == 5:
                return

    await asyncio.wait_for(tail(), 30)
    assert got == [1, 2, 3, 4, 5], got
    await t.publish(wf, f"{wf}-b3", make_events(wf, 4, start=12))
    resumed = offsets(await collect(t, wf, got[-1]))
    assert resumed == list(range(6, 17)), resumed
    seqs = [e.seq for i in await collect(t, wf, 0) if not isinstance(i, Expired) for e in [i[1]]]
    assert seqs == list(range(16)), seqs


async def check_r2_expiry(t: EventTransport) -> None:
    """R2: asking below the retained base reports it first; asking at base-1 does not."""
    wf = new_workflow()
    await t.publish(wf, f"{wf}-b0", make_events(wf, 20))
    base = 15
    await t.expire_below(wf, base)
    items = await collect(t, wf, base - 10)
    assert items and items[0] == Expired(base), items[:2]
    assert offsets(items) == list(range(base, 21)), offsets(items)
    assert sum(isinstance(i, Expired) for i in items) == 1
    items = await collect(t, wf, base - 1)
    assert not any(isinstance(i, Expired) for i in items), items[:2]
    assert offsets(items) == list(range(base, 21))


async def check_r3_resend(t: EventTransport, horizon_s: float) -> None:
    """R3: a batch re-sent at once and just inside the horizon is stored once."""
    wf = new_workflow()
    batch = make_events(wf, 5)
    await t.publish(wf, f"{wf}-b0", batch)
    await t.publish(wf, f"{wf}-b0", batch)
    assert await t.latest(wf) == 5
    await asyncio.sleep(max(horizon_s - 5, 0.1))
    await t.publish(wf, f"{wf}-b0", batch)
    assert await t.latest(wf) == 5
    assert offsets(await collect(t, wf, 0)) == [1, 2, 3, 4, 5]


async def check_r4_roll_over(t: EventTransport) -> None:
    """R4: a reader at offset N during a roll-over gets N+1 onwards, no gap or repeat."""
    wf = new_workflow()
    await t.publish(wf, f"{wf}-b0", make_events(wf, 5))
    got: list[int] = []

    async def tail() -> None:
        async for item in t.read(wf, 3, follow=True):
            assert not isinstance(item, Expired)
            got.append(item[0])
            if len(got) == 7:
                return

    reader = asyncio.create_task(tail())
    await asyncio.sleep(0.5)
    await t.roll_over(wf)
    await t.publish(wf, f"{wf}-b1", make_events(wf, 5, start=5))
    await asyncio.wait_for(reader, 60)
    assert got == list(range(4, 11)), got
    assert offsets(await collect(t, wf, 0)) == list(range(1, 11))


async def check_r7_replay(t: EventTransport, recorded: list[AgentEvent]) -> None:
    """R7: the recorded turn, published in batches and read back, equals the recording."""
    wf = new_workflow()
    for b, start in enumerate(range(0, len(recorded), BATCH)):
        await t.publish(wf, f"{wf}-b{b}", recorded[start : start + BATCH])
    items = await collect(t, wf, 0)
    assert offsets(items) == list(range(1, len(recorded) + 1))
    assert [i[1] for i in items if not isinstance(i, Expired)] == recorded

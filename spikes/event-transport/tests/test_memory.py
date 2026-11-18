"""Unit tests of the in-memory reference implementation (task 1.2)."""

from __future__ import annotations

import asyncio

from event_transport.memory import MemoryTransport
from event_transport.transport import Expired

from tests.helpers import events


async def collect(t: MemoryTransport, after: int) -> list:
    return [item async for item in t.read("wf-1", after)]


async def test_offsets_start_at_one_and_have_no_gaps() -> None:
    t = MemoryTransport()
    await t.publish("wf-1", "b1", events(3))
    await t.publish("wf-1", "b2", events(2, start=3))
    assert [o for o, _ in await collect(t, 0)] == [1, 2, 3, 4, 5]
    assert await t.latest("wf-1") == 5
    assert await t.latest("other") is None


async def test_read_after_is_exclusive() -> None:
    t = MemoryTransport()
    await t.publish("wf-1", "b1", events(5))
    assert [o for o, _ in await collect(t, 3)] == [4, 5]


async def test_expiry_is_reported_once_then_events_from_the_base() -> None:
    t = MemoryTransport()
    await t.publish("wf-1", "b1", events(10))
    await t.expire_below("wf-1", 6)
    items = await collect(t, 2)
    assert items[0] == Expired(6) and [o for o, _ in items[1:]] == [6, 7, 8, 9, 10]
    assert all(not isinstance(i, Expired) for i in await collect(t, 5))


async def test_resent_batch_is_stored_once_within_the_horizon() -> None:
    t = MemoryTransport(horizon_s=0.2)
    await t.publish("wf-1", "b1", events(2))
    await t.publish("wf-1", "b1", events(2))
    assert await t.latest("wf-1") == 2
    await asyncio.sleep(0.25)
    await t.publish("wf-1", "b1", events(2))  # past the horizon: stored again
    assert await t.latest("wf-1") == 4


async def test_follow_waits_for_new_events() -> None:
    t = MemoryTransport()
    got: list[int] = []

    async def tail() -> None:
        async for item in t.read("wf-1", 0, follow=True):
            got.append(item[0])  # type: ignore[index]
            if len(got) == 3:
                return

    task = asyncio.create_task(tail())
    await asyncio.sleep(0.05)
    await t.publish("wf-1", "b1", events(3))
    await asyncio.wait_for(task, 1)
    assert got == [1, 2, 3]

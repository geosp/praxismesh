"""The requirement checks every transport runs (plan R1-R4, R7; task 1.4).

Each check is a plain async function that raises AssertionError when the transport
breaks the requirement, so the suite and its own validation share one definition.
Every check uses a fresh workflow ID, so transports with durable state can share a
stack between checks.
"""

from __future__ import annotations

import asyncio
import contextlib
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


async def check_r1_cancel(t: EventTransport) -> None:
    """R1: a following reader cancelled while it waits stops promptly, and a new
    reader resumes after its last offset (a tailer that cannot stop cannot resume)."""
    wf = new_workflow()
    await t.publish(wf, f"{wf}-b0", make_events(wf, 3))
    reader = t.read(wf, 0, follow=True).__aiter__()
    got = [await asyncio.wait_for(anext(reader), 30) for _ in range(3)]
    assert offsets(got) == [1, 2, 3]
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(anext(reader), 0.5)  # nothing new: times out, cancelled
    await asyncio.wait_for(reader.aclose(), 5)  # stops promptly
    await t.publish(wf, f"{wf}-b1", make_events(wf, 2, start=3))
    assert offsets(await collect(t, wf, 3)) == [4, 5]


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


async def check_r3_resend(t: EventTransport, horizon_s: float, hosted: bool = False) -> None:
    """R3: a batch re-sent at once, after a roll-over, and just inside the horizon is
    stored once."""
    wf = new_workflow()
    batch = make_events(wf, 5)
    await t.publish(wf, f"{wf}-b0", batch)
    await t.publish(wf, f"{wf}-b0", batch)
    assert await t.latest(wf) == 5
    rolled = await t.roll_over(wf)  # the batch-ID set must survive it
    assert rolled or not hosted, "roll_over did not start a new run"
    await t.publish(wf, f"{wf}-b0", batch)
    assert await t.latest(wf) == 5, "a re-send after a roll-over was stored again"
    await asyncio.sleep(max(horizon_s - 5, 0.1))
    await t.publish(wf, f"{wf}-b0", batch)
    assert await t.latest(wf) == 5
    assert offsets(await collect(t, wf, 0)) == [1, 2, 3, 4, 5]


async def check_r2_mid_read(t: EventTransport) -> None:
    """R2 during a read: a follower whose next events are removed while it reads gets
    an expiry report naming the new base, then the base onwards."""
    wf = new_workflow()
    await t.publish(wf, f"{wf}-b0", make_events(wf, 5))
    reader = t.read(wf, 0, follow=True).__aiter__()
    first = [await asyncio.wait_for(anext(reader), 30) for _ in range(5)]
    assert offsets(first) == [1, 2, 3, 4, 5]
    # Published after the reader's last page, then removed before it reads again.
    await t.publish(wf, f"{wf}-b1", make_events(wf, 95, start=5))
    await t.expire_below(wf, 50)
    await t.publish(wf, f"{wf}-b2", make_events(wf, 10, start=100))
    rest: list[Item] = []
    while not (offsets(rest) and offsets(rest)[-1] == 110):
        rest.append(await asyncio.wait_for(anext(reader), 30))
    await reader.aclose()
    # The reader was suspended after offset 5, so nothing later was buffered: the
    # report must name the real base, and every retained event must follow (R1, R2).
    expiries = [i for i in rest if isinstance(i, Expired)]
    assert expiries == [Expired(50)], rest[:3]
    assert offsets(rest[rest.index(expiries[0]) + 1 :]) == list(range(50, 111))


async def check_r4_roll_over(t: EventTransport, hosted: bool) -> None:
    """R4: a reader at offset N during a roll-over gets N+1 onwards, no gap or repeat.
    For a hosted option the roll-over must start a new run while the reader waits."""
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
    rolled = await t.roll_over(wf)
    if hosted:
        assert rolled, "roll_over did not start a new run"
        assert got == [4, 5], f"the reader moved before the post-roll publish: {got}"
    await t.publish(wf, f"{wf}-b1", make_events(wf, 5, start=5))
    await asyncio.wait_for(reader, 60)
    assert got == list(range(4, 11)), got
    assert offsets(await collect(t, wf, 0)) == list(range(1, 11))


async def check_r4_truncating_roll_over(t: EventTransport, keep: int = 500) -> None:
    """R4 with D5's retention: a roll-over keeps the last `keep` events; a stalled
    tailer then gets an expiry report naming the carried base and continues without
    a gap; reads after the base report nothing expired. Hosted options only."""
    wf = new_workflow()
    await t.publish(wf, f"{wf}-b0", make_events(wf, 5))
    tailer = t.read(wf, 3, follow=True).__aiter__()
    assert offsets([await asyncio.wait_for(anext(tailer), 30)]) == [4]
    for b in range(10):
        await t.publish(wf, f"{wf}-b{b + 1}", make_events(wf, 60, start=5 + 60 * b))
    assert await t.latest(wf) == 605
    assert await t.roll_over(wf), "roll_over did not start a new run"
    base = 605 - keep + 1
    await t.publish(wf, f"{wf}-b11", make_events(wf, 5, start=605))
    rest: list[Item] = []
    while not (offsets(rest) and offsets(rest)[-1] == 610):
        rest.append(await asyncio.wait_for(anext(tailer), 30))
    await tailer.aclose()
    expiries = [i for i in rest if isinstance(i, Expired)]
    assert expiries == [Expired(base)], rest[:3]
    assert offsets(rest[rest.index(expiries[0]) + 1 :]) == list(range(base, 611))
    assert (await collect(t, wf, 0))[0] == Expired(base)
    assert not any(isinstance(i, Expired) for i in await collect(t, wf, base - 1))


async def check_r7_replay(t: EventTransport, recorded: list[AgentEvent]) -> None:
    """R7: the recorded turn, published in batches and read back, equals the recording."""
    wf = new_workflow()
    for b, start in enumerate(range(0, len(recorded), BATCH)):
        await t.publish(wf, f"{wf}-b{b}", recorded[start : start + BATCH])
    items = await collect(t, wf, 0)
    assert offsets(items) == list(range(1, len(recorded) + 1))
    assert [i[1] for i in items if not isinstance(i, Expired)] == recorded

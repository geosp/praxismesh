"""`BatchingPublisher` (Phase 2 events plan task 2.1; R1, R7, R8, R9)."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from typing import Any

import pytest

from common.events import Expired, MemoryTransport, Writer
from common.persistence.fence import FenceRejected
from common.schemas.events import AgentEvent
from harness_activity.events import AttemptEvents, BatchingPublisher

WF = "task-1"
WRITER = Writer(WF, 1, 1)


class Recording(MemoryTransport):
    """The in-memory transport, recording each publish call (batch ID, size)."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, int]] = []

    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[AgentEvent]
    ) -> None:
        self.calls.append((batch_id, len(events)))
        await super().publish(workflow_id, writer, batch_id, events)


def event(seq: int, attempt_id: str = f"{WF}:1:1") -> AgentEvent:
    return AgentEvent(
        seq=seq,
        timestamp=datetime.now(UTC),
        workflow_id=WF,
        task_id=WF,
        attempt_id=attempt_id,
        type="token",
        payload={"input_tokens": seq},
    )


async def stored(t: MemoryTransport) -> list[int]:
    return [item[1].seq async for item in t.read(WF, 0) if not isinstance(item, Expired)]


def publisher(t: MemoryTransport, **kw: Any) -> BatchingPublisher:
    return BatchingPublisher(t, WRITER, WF, f"{WF}:1:1", **kw)


async def test_640_events_at_once_are_ten_batches() -> None:
    t = Recording()
    p = publisher(t)
    for i in range(640):
        p.emit(event(i))
    assert await p.close() is None
    assert [n for _, n in t.calls] == [64] * 10
    assert await stored(t) == list(range(640))


async def test_a_few_events_wait_for_the_delay_then_go_in_one_batch() -> None:
    t = Recording()
    p = publisher(t)
    for i in range(3):
        p.emit(event(i))
        await asyncio.sleep(0.015)
    await asyncio.sleep(0.1)
    assert t.calls == []  # under 200 ms since the oldest event
    await asyncio.sleep(0.2)
    assert [n for _, n in t.calls] == [3]
    assert await p.close() is None


async def test_close_flushes_the_last_event() -> None:
    t = Recording()
    p = publisher(t)
    p.emit(event(0))
    await asyncio.sleep(0.01)
    assert await p.close() is None
    assert await stored(t) == [0]


class LostReplies(Recording):
    """Each batch's first `fails` publishes commit and then raise, as a lost reply."""

    def __init__(self, fails: int, only: str = "") -> None:
        super().__init__()
        self.fails, self.only = fails, only
        self.seen: dict[str, int] = {}

    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[AgentEvent]
    ) -> None:
        await super().publish(workflow_id, writer, batch_id, events)
        self.seen[batch_id] = self.seen.get(batch_id, 0) + 1
        if batch_id.endswith(self.only) and self.seen[batch_id] <= self.fails:
            raise ConnectionError("reply lost")


async def test_a_lost_reply_is_resent_and_stored_once() -> None:
    t = LostReplies(fails=1)
    p = publisher(t, backoff_s=(0.01,))
    for i in range(5):
        p.emit(event(i))
    assert await p.close() is None
    assert await stored(t) == list(range(5))
    assert [b for b, _ in t.calls] == [f"{WF}:{WF}:1:1:0"] * 2


async def test_a_frozen_batch_survives_failed_tries_while_more_events_arrive() -> None:
    """Every try of batch 0 commits and loses its reply (backoff exhausted); more
    events arrive; then a re-send succeeds. Each event is stored exactly once."""
    t = LostReplies(fails=3, only=":0")
    p = publisher(t, backoff_s=(0.01, 0.01), delay_s=0.05)
    for i in range(10):
        p.emit(event(i))
    await asyncio.sleep(0.12)  # batch 0 is cut and fails all three tries
    for i in range(10, 20):
        p.emit(event(i))
    assert await p.close() is None
    assert await stored(t) == list(range(20))
    first = [b for b, _ in t.calls if b.endswith(":0")]
    assert len(first) >= 4 and {n for b, n in t.calls if b.endswith(":0")} == {10}


class Slow(Recording):
    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[AgentEvent]
    ) -> None:
        await asyncio.sleep(0.3)
        await super().publish(workflow_id, writer, batch_id, events)


async def test_a_slow_publish_keeps_batches_in_order() -> None:
    t = Slow()
    p = publisher(t)
    for i in range(70):  # one full batch, then 6 that wait behind it
        p.emit(event(i))
    await asyncio.sleep(0.25)
    for i in range(70, 80):
        p.emit(event(i))
    assert await p.close() is None
    assert await stored(t) == list(range(80))
    assert [b for b, _ in t.calls] == [f"{WF}:{WF}:1:1:{n}" for n in range(len(t.calls))]


class Refuses(Recording):
    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[AgentEvent]
    ) -> None:
        raise FenceRejected("a newer attempt owns this task")


async def test_a_refusal_stops_publishing_and_is_returned() -> None:
    t = Refuses()
    p = publisher(t)
    p.emit(event(0))
    await asyncio.sleep(0.3)
    p.emit(event(1))  # dropped: the attempt is superseded
    assert isinstance(await p.close(), FenceRejected)
    assert p.buffer == []


async def test_a_database_that_stays_down_is_returned_from_close() -> None:
    t = LostReplies(fails=1000)
    p = publisher(t, backoff_s=(0.01,))
    p.emit(event(0))
    assert isinstance(await p.close(), ConnectionError)


async def test_close_completes_when_its_caller_is_cancelled() -> None:
    t = Slow()
    p = publisher(t)
    p.emit(event(0))
    caller = asyncio.create_task(p.close())
    await asyncio.sleep(0.05)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    await asyncio.wait_for(p.task, 2)
    assert await stored(t) == [0]


async def test_batch_ids_name_the_attempt() -> None:
    t = Recording()
    one = BatchingPublisher(t, WRITER, WF, f"{WF}:1:1")
    two = BatchingPublisher(t, Writer(WF, 1, 2), WF, f"{WF}:1:2")
    one.emit(event(0))
    two.emit(event(0, f"{WF}:1:2"))
    await one.close()
    await two.close()
    assert sorted(b for b, _ in t.calls) == [f"{WF}:{WF}:1:1:0", f"{WF}:{WF}:1:2:0"]
    assert len(await stored(t)) == 2


async def test_attempt_events_from_threads_arrive_in_seq_order() -> None:
    t = Recording()
    p = publisher(t)
    events = AttemptEvents(p, WF, WF, 1, 1)
    threads = [
        threading.Thread(target=lambda: [events.emit("token") for _ in range(50)]) for _ in range(4)
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert await p.close() is None
    assert await stored(t) == list(range(200))

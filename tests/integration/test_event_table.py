"""The event table against the shared suite (Phase 2 events plan task 1.3; R1-R4).

The suite is the event-transport spike's (`spikes/event-transport/event_transport/
checks.py`, issue #76), ported to the production interface: every check runs on
the PostgreSQL table and on the in-memory reference, so a check that passes on
neither is caught. Table-only tests cover the fence, the lock order, the re-send
horizon, `older_than` pruning and a notification that lands during a fetch.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.events import EventTransport, Expired, Item, MemoryTransport, TableTransport, Writer
from common.events.table import POLL_S
from common.persistence.fence import FenceRejected
from common.persistence.repositories import (
    AttemptRepository,
    Checkpoint,
    CheckpointRepository,
    TaskRepository,
    make_engine,
)
from common.schemas import BlobRef, TaskStart
from common.schemas.events import AgentEvent
from tests.support.stack import run_id

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent-events-dsh-turn.jsonl"
BATCH = 64
HORIZON_S = 6.0  # the suite's re-send horizon (production uses 600 s)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


@pytest.fixture(params=["table", "memory"])
async def transport(request: pytest.FixtureRequest, engine: AsyncEngine) -> EventTransport:
    if request.param == "table":
        return TableTransport(engine, horizon_s=HORIZON_S)
    return MemoryTransport(horizon_s=HORIZON_S)


def new_workflow() -> str:
    return f"wf-test-{uuid.uuid4().hex[:12]}"


def writer(wf: str) -> Writer:
    return Writer(task_id=wf, turn=1, attempt=1)  # no attempt rows: the fence allows it


def make_events(wf: str, n: int, start: int = 0) -> list[AgentEvent]:
    return [
        AgentEvent(
            seq=start + i,
            timestamp=datetime.now(UTC),
            workflow_id=wf,
            task_id=wf,
            attempt_id=f"{wf}:1:1",
            type="token",
            payload={"i": start + i},
        )
        for i in range(n)
    ]


async def publish(t: EventTransport, wf: str, batch: str, events: list[AgentEvent]) -> None:
    await t.publish(wf, writer(wf), batch, events)


async def collect(t: EventTransport, wf: str, after: int) -> list[Item]:
    return [item async for item in t.read(wf, after)]


def offsets(items: list[Item]) -> list[int]:
    return [i[0] for i in items if not isinstance(i, Expired)]


# The shared suite (spike checks R1, R2, R3, R7).


async def test_resume_after_an_offset(transport: EventTransport) -> None:
    """R2: a reader stopped after offset N resumes at N+1, in order, with no repeat."""
    t, wf = transport, new_workflow()
    for b in range(3):
        await publish(t, wf, f"{wf}-b{b}", make_events(wf, 4, start=4 * b))
    got: list[int] = []

    async def tail() -> None:
        async for item in t.read(wf, 0, follow=True):
            assert not isinstance(item, Expired)
            got.append(item[0])
            if len(got) == 5:
                return

    await asyncio.wait_for(tail(), 30)
    assert got == [1, 2, 3, 4, 5], got
    await publish(t, wf, f"{wf}-b3", make_events(wf, 4, start=12))
    assert offsets(await collect(t, wf, got[-1])) == list(range(6, 17))
    seqs = [i[1].seq for i in await collect(t, wf, 0) if not isinstance(i, Expired)]
    assert seqs == list(range(16)), seqs


async def test_a_cancelled_follower_stops_and_a_new_one_resumes(transport: EventTransport) -> None:
    """R2: a following reader cancelled while it waits stops promptly; a new reader
    resumes after its last offset."""
    t, wf = transport, new_workflow()
    await publish(t, wf, f"{wf}-b0", make_events(wf, 3))
    reader = t.read(wf, 0, follow=True)
    got = [await asyncio.wait_for(anext(reader), 30) for _ in range(3)]
    assert offsets(got) == [1, 2, 3]
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(anext(reader), 0.5)  # nothing new: times out, cancelled
    await asyncio.wait_for(reader.aclose(), 5)
    await publish(t, wf, f"{wf}-b1", make_events(wf, 2, start=3))
    assert offsets(await collect(t, wf, 3)) == [4, 5]


async def test_pruned_events_are_reported_first(transport: EventTransport) -> None:
    """R3: asking below the retained base reports it first; asking at base-1 does not."""
    t, wf = transport, new_workflow()
    await publish(t, wf, f"{wf}-b0", make_events(wf, 20))
    assert await t.prune(wf, below=15) == 15
    items = await collect(t, wf, 5)
    assert items and items[0] == Expired(15), items[:2]
    assert offsets(items) == list(range(15, 21))
    assert sum(isinstance(i, Expired) for i in items) == 1
    items = await collect(t, wf, 14)
    assert not any(isinstance(i, Expired) for i in items)
    assert offsets(items) == list(range(15, 21))


async def test_pruning_during_a_read_is_reported(transport: EventTransport) -> None:
    """R3 during a read: a follower whose next events are pruned while it reads gets
    an expiry naming the new base, then the base onwards."""
    t, wf = transport, new_workflow()
    await publish(t, wf, f"{wf}-b0", make_events(wf, 5))
    reader = t.read(wf, 0, follow=True)
    first = [await asyncio.wait_for(anext(reader), 30) for _ in range(5)]
    assert offsets(first) == [1, 2, 3, 4, 5]
    await publish(t, wf, f"{wf}-b1", make_events(wf, 95, start=5))
    await t.prune(wf, below=50)
    await publish(t, wf, f"{wf}-b2", make_events(wf, 10, start=100))
    rest: list[Item] = []
    while not (offsets(rest) and offsets(rest)[-1] == 110):
        rest.append(await asyncio.wait_for(anext(reader), 30))
    await reader.aclose()
    expiries = [i for i in rest if isinstance(i, Expired)]
    assert expiries == [Expired(50)], rest[:3]
    assert offsets(rest[rest.index(expiries[0]) + 1 :]) == list(range(50, 111))


async def test_a_resent_batch_is_stored_once(transport: EventTransport) -> None:
    """R1: a batch re-sent at once and inside the horizon is stored once."""
    t, wf = transport, new_workflow()
    batch = make_events(wf, 5)
    await publish(t, wf, f"{wf}-b0", batch)
    await publish(t, wf, f"{wf}-b0", batch)
    assert await t.latest(wf) == 5
    await asyncio.sleep(HORIZON_S - 3)
    await publish(t, wf, f"{wf}-b0", batch)
    assert offsets(await collect(t, wf, 0)) == [1, 2, 3, 4, 5]


async def test_the_recorded_turn_round_trips(transport: EventTransport) -> None:
    """A recorded DSH turn, published in batches and read back, equals the recording."""
    recorded = [AgentEvent.model_validate_json(x) for x in FIXTURE.read_text().splitlines()]
    t, wf = transport, recorded[0].workflow_id + "-" + uuid.uuid4().hex[:8]
    recorded = [e.model_copy(update={"workflow_id": wf}) for e in recorded]
    for b, start in enumerate(range(0, len(recorded), BATCH)):
        await publish(t, wf, f"{wf}-b{b}", recorded[start : start + BATCH])
    items = await collect(t, wf, 0)
    assert offsets(items) == list(range(1, len(recorded) + 1))
    assert [i[1] for i in items if not isinstance(i, Expired)] == recorded


async def test_prune_with_nothing_left_sets_the_base_to_the_next_offset(
    transport: EventTransport,
) -> None:
    t, wf = transport, new_workflow()
    assert await t.prune(wf, below=3) is None
    await publish(t, wf, f"{wf}-b0", make_events(wf, 4))
    assert await t.prune(wf, below=100) == 5
    assert await collect(t, wf, 0) == [Expired(5)]


# Table only.


def blob_ref() -> BlobRef:
    return BlobRef(
        id=f"blob:{0:064x}",
        key=f"sha256/{0:064x}",
        checksum=f"sha256:{0:064x}",
        content_type="text/plain",
        bytes=1,
        retention_class="task",
        created_at=datetime.now(UTC),
    )


async def recorded_task(engine: AsyncEngine) -> str:
    start = TaskStart(
        task_id=f"task-test-{run_id()}",
        request_id="req-1",
        profile="openai",
        template="local-default",
        instructions_ref=blob_ref(),
    )
    await TaskRepository(engine).record_task(
        start, workflow_id=start.task_id, run_id="run-1", template_version=1, template_hash="x"
    )
    return start.task_id


async def test_a_superseded_attempt_publishes_nothing(engine: AsyncEngine) -> None:
    """R4: a batch from attempt 1 after attempt 2 started is refused and not stored."""
    t, task = TableTransport(engine), await recorded_task(engine)
    attempts = AttemptRepository(engine)
    await attempts.start(task, 1, 1, "worker-a")
    await t.publish(task, Writer(task, 1, 1), f"{task}:1:1:0", make_events(task, 2))
    await attempts.start(task, 1, 2, "worker-b")
    with pytest.raises(FenceRejected):
        await t.publish(task, Writer(task, 1, 1), f"{task}:1:1:1", make_events(task, 2, 2))
    with pytest.raises(FenceRejected):  # a newer turn fences an older one too
        await attempts.start(task, 2, 1, "worker-b")
        await t.publish(task, Writer(task, 1, 2), f"{task}:1:2:0", make_events(task, 1))
    assert await t.latest(task) == 2


async def test_publish_and_fenced_checkpoint_never_deadlock(engine: AsyncEngine) -> None:
    """D2's lock order: a publish and a fenced checkpoint insert of one task run
    concurrently 200 times without a deadlock."""
    t, task = TableTransport(engine), await recorded_task(engine)
    await AttemptRepository(engine).start(task, 1, 1, "worker-a")
    checkpoints = CheckpointRepository(engine)

    async def checkpoint(i: int) -> None:
        await checkpoints.insert_fenced(
            Checkpoint(f"{task}:1:1:{i}", task, 1, 1, i, task, 0, blob_ref(), None)
        )

    async def publish_one(i: int) -> None:
        await t.publish(task, Writer(task, 1, 1), f"{task}:1:1:{i}", make_events(task, 1, i))

    await asyncio.wait_for(
        asyncio.gather(*(f(i) for i in range(200) for f in (checkpoint, publish_one))), 120
    )
    assert await t.latest(task) == 200
    assert await checkpoints.count(task) == 200


async def test_resends_are_recognised_only_inside_the_horizon(engine: AsyncEngine) -> None:
    """D1: batch rows older than the horizon are deleted by the next publish."""
    t, wf = TableTransport(engine, horizon_s=2), new_workflow()
    await publish(t, wf, f"{wf}-b0", make_events(wf, 3))
    await asyncio.sleep(2.5)
    await publish(t, wf, f"{wf}-b1", make_events(wf, 1, 3))
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT batch_id FROM event_batches WHERE workflow_id = :w"), {"w": wf}
        )
        assert [r[0] for r in rows] == [f"{wf}-b1"]


async def test_prune_older_than_deletes_an_old_prefix(engine: AsyncEngine) -> None:
    """D4: `older_than` deletes the longest prefix whose events are all older."""
    t, wf = TableTransport(engine), new_workflow()
    await publish(t, wf, f"{wf}-b0", make_events(wf, 10))
    await asyncio.sleep(2)
    await publish(t, wf, f"{wf}-b1", make_events(wf, 5, 10))
    assert await t.prune(wf, older_than=timedelta(seconds=1)) == 11
    assert (await collect(t, wf, 0))[0] == Expired(11)
    assert offsets(await collect(t, wf, 10)) == list(range(11, 16))


class PublishesDuringFetch(TableTransport):
    """After the reader's second fetch has read its rows, a publisher commits a
    batch, so its NOTIFY lands between the reader's fetch and its wait."""

    fetches = 0
    published_at = 0.0

    async def _fetch(self, conn: AsyncConnection, workflow_id: str, after: int) -> list[Any]:
        rows = await super()._fetch(conn, workflow_id, after)
        self.fetches += 1
        if self.fetches == 2:
            await publish(self, workflow_id, f"{workflow_id}-late", make_events(workflow_id, 1, 1))
            self.published_at = time.monotonic()
            await asyncio.sleep(0.05)  # let the NOTIFY reach the reader's connection
        return rows


async def test_a_notify_during_a_fetch_is_not_lost(engine: AsyncEngine) -> None:
    t, wf = PublishesDuringFetch(engine), new_workflow()
    await publish(t, wf, f"{wf}-b0", make_events(wf, 1))
    got: list[float] = []
    async for _item in t.read(wf, 0, follow=True):
        got.append(time.monotonic())
        if len(got) == 2:
            break
    assert got[1] - t.published_at < POLL_S / 2, got[1] - t.published_at


async def test_followers_stop_when_cancelled_under_a_stream_of_publishes(
    engine: AsyncEngine,
) -> None:
    """A follower cancelled while notifications keep arriving always stops (the
    load benchmark found one that did not, with `asyncio.wait_for` on Python 3.11)."""
    t, wf = TableTransport(engine), new_workflow()
    stop = asyncio.Event()

    async def publisher() -> None:
        n = 0
        while not stop.is_set():
            await publish(t, wf, f"{wf}-b{n}", make_events(wf, 1, n))
            n += 1
            await asyncio.sleep(0.005)

    async def follow() -> None:
        async for _item in t.read(wf, 0, follow=True):
            pass

    publishing = asyncio.create_task(publisher())
    try:
        for _ in range(40):
            reader = asyncio.create_task(follow())
            await asyncio.sleep(0.02)
            reader.cancel()
            done, _ = await asyncio.wait({reader}, timeout=3)
            assert reader in done, "a cancelled follower kept running"
    finally:
        stop.set()
        await publishing


async def test_two_attempts_publishing_get_gap_free_offsets(engine: AsyncEngine) -> None:
    """R1: two attempts of one task, each publishing several batches through its own
    publisher, store every event once at offsets 1..N."""
    from harness_activity.events import AttemptEvents, BatchingPublisher

    t, task = TableTransport(engine), await recorded_task(engine)
    attempts = AttemptRepository(engine)
    emitted = 0
    for attempt in (1, 2):
        await attempts.start(task, 1, attempt, "worker")
        p = BatchingPublisher(t, Writer(task, 1, attempt), task, f"{task}:1:{attempt}")
        events = AttemptEvents(p, task, task, 1, attempt)
        for _ in range(150):
            events.emit("token", input_tokens=1, output_tokens=1)
        emitted += 150
        assert await p.close() is None
    items = await collect(t, task, 0)
    assert offsets(items) == list(range(1, emitted + 1))
    stored = [i[1] for i in items if not isinstance(i, Expired)]
    assert [e.attempt_id for e in stored] == [f"{task}:1:1"] * 150 + [f"{task}:1:2"] * 150


async def test_tail_on_the_table_reports_pruning_first(engine: AsyncEngine) -> None:
    """Task 3.2 on the table: prune below 15, then tail after 5 prints the expiry."""
    from orchestrator import cli

    t, wf = TableTransport(engine), new_workflow()
    await publish(t, wf, f"{wf}-b0", make_events(wf, 20))
    assert await t.prune(wf, below=15) == 15
    lines: list[str] = []

    async def closed() -> bool:
        return True

    await cli.print_events(t, wf, 5, follow=False, closed=closed, write=lines.append)
    assert lines[0] == "expired: events before 15 were pruned"
    assert [int(x.split("\t")[0]) for x in lines[1:]] == list(range(15, 21))

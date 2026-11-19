"""The task inbox (Phase 2 messaging task 2.2; R10-R13, R17-R19, R23, R25, R27, R30).

Runs against the real database: every scenario of those requirements, plus the
wake rows (D6) and the claim's rerun (D7).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.persistence.fence import FenceRejected
from common.persistence.messages import MessageRepository, Sender, idempotency_key
from common.persistence.repositories import AttemptRepository, TaskRepository, make_engine
from common.schemas import BlobRef, TaskStart
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
WAIT, MAX_WAIT = timedelta(minutes=5), timedelta(minutes=10)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


def ref() -> BlobRef:
    return BlobRef(
        id=f"blob:{0:064x}", key=f"sha256/{0:064x}", checksum=f"sha256:{0:064x}",
        content_type="text/plain", bytes=1, retention_class="task", created_at=datetime.now(UTC),
    )  # fmt: skip


async def task(engine: AsyncEngine, request: str) -> str:
    task_id = f"task-msg-{run_id()}"
    start = TaskStart(task_id=task_id, request_id=request, profile="dsh", template="local-dsh",
                      instructions_ref=ref())  # fmt: skip
    await TaskRepository(engine).record_task(
        start, workflow_id=task_id, run_id="run-1", template_version=1, template_hash="x"
    )
    await AttemptRepository(engine).start(task_id, 1, 1, "worker")
    return task_id


def me(task_id: str, turn: int = 1, attempt: int = 1) -> Sender:
    return Sender(task_id, turn, attempt)


def key(*parts: Any) -> str:
    return idempotency_key(str(parts[0]), 1, "send_to_agent", {"p": [str(p) for p in parts]})


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.connect() as conn:
        return list(await conn.execute(text(sql), params))


async def pair(engine: AsyncEngine) -> tuple[MessageRepository, str, str]:
    request = f"req-{uuid.uuid4().hex[:8]}"
    return MessageRepository(engine), await task(engine, request), await task(engine, request)


async def test_messages_stay_inside_their_request_and_refusals_are_recorded(
    engine: AsyncEngine,
) -> None:
    """R10, R11."""
    m, a, _ = await pair(engine)
    _, outsider, _ = await pair(engine)
    result = await m.send(me(a), outsider, "hello", key=key(a, outsider))
    assert not result.ok and "not a task of this request" in (result.reason or "")
    sql = "SELECT status, sender_task, recipient_task FROM task_messages WHERE message_id = :m"
    stored = await rows(engine, sql, m=result.message_id)
    assert stored[0][:3] == ("rejected", a, outsider)
    assert await m.claim(outsider, 2, datetime.now(UTC)) is not None
    assert (await m.claim(outsider, 2, datetime.now(UTC))).count == 0


async def test_an_identical_repeat_is_stored_once_and_a_message_reaches_one_turn(
    engine: AsyncEngine,
) -> None:
    """R12, R13: a retried attempt repeating the same send stores nothing; a claim
    rerun for the same turn returns the same rows and no later turn gets them."""
    m, a, b = await pair(engine)
    first = await m.send(me(a, attempt=1), b, "hi", key=key(a, b, "hi"))
    await AttemptRepository(engine).start(a, 1, 2, "worker")
    again = await m.send(me(a, attempt=2), b, "hi", key=key(a, b, "hi"))
    assert first.ok and again.message_id == first.message_id
    claim = await m.claim(b, 2, datetime.now(UTC))
    assert claim.message_ids == [first.message_id]
    assert (await m.claim(b, 2, datetime.now(UTC))).message_ids == [first.message_id]
    assert (await m.claim(b, 3, datetime.now(UTC))).count == 0
    read = await m.read_claimed(me(b, turn=2))
    assert [(d.sender_task, d.body) for d in read] == [(a, "hi")]


async def test_an_unanswered_question_expires_and_the_asker_is_told(engine: AsyncEngine) -> None:
    """R17: past its deadline the question expires and the asker's next claim holds it."""
    m, a, b = await pair(engine)
    asked = await m.ask(me(a), b, "price?", key=key(a, b, "q"), wait=timedelta(seconds=30),
                        max_wait=MAX_WAIT)  # fmt: skip
    assert asked.ok and asked.deadline is not None
    later = asked.deadline + timedelta(seconds=1)
    claim = await m.claim(a, 2, later)
    assert claim.message_ids == [asked.message_id] and claim.next_deadline is None
    told = await m.read_claimed(me(a, turn=2))
    assert [(d.kind, d.status) for d in told] == [("ask", "expired")]


async def test_a_late_reply_is_refused(engine: AsyncEngine) -> None:
    """R18: a reply to an expired question is refused and recorded."""
    m, a, b = await pair(engine)
    asked = await m.ask(me(a), b, "price?", key=key(a, b, "q"), wait=timedelta(seconds=1),
                        max_wait=MAX_WAIT)  # fmt: skip
    assert asked.deadline is not None
    await m.claim(a, 2, asked.deadline + timedelta(seconds=1))
    reply = await m.send(me(b), a, "12.50", key=key(b, a, "r"), reply_to=asked.correlation_id)
    assert not reply.ok and "expired" in (reply.reason or "")


async def test_a_reply_answers_and_reaches_the_asker(engine: AsyncEngine) -> None:
    m, a, b = await pair(engine)
    asked = await m.ask(me(a), b, "price?", key=key(a, b, "q"), wait=WAIT, max_wait=MAX_WAIT)
    await m.claim(b, 2, datetime.now(UTC))
    reply = await m.send(me(b), a, "12.50", key=key(b, a, "r"), reply_to=asked.correlation_id)
    assert reply.ok
    status = await rows(engine, "SELECT status FROM task_messages WHERE message_id = :m",
                        m=asked.message_id)  # fmt: skip
    assert status[0][0] == "answered"
    claim = await m.claim(a, 2, datetime.now(UTC))
    told = await m.read_claimed(me(a, turn=2))
    assert claim.count == 1 and told[0].reply_to == asked.correlation_id and told[0].body == "12.50"


async def test_finish_is_blocked_by_an_open_question_and_an_unread_reply(
    engine: AsyncEngine,
) -> None:
    """R19."""
    m, a, b = await pair(engine)
    asked = await m.ask(me(a), b, "price?", key=key(a, b, "q"), wait=WAIT, max_wait=MAX_WAIT)
    assert (await m.blocking_finish(me(a)))[0].startswith("open question")
    await m.claim(b, 2, datetime.now(UTC))
    await m.send(me(b), a, "12.50", key=key(b, a, "r"), reply_to=asked.correlation_id)
    assert (await m.blocking_finish(me(a)))[0].startswith("unread reply")
    await m.claim(a, 2, datetime.now(UTC))
    await m.read_claimed(me(a, turn=2))
    assert await m.blocking_finish(me(a, turn=2)) == []


async def test_questions_never_wait_in_a_cycle(engine: AsyncEngine) -> None:
    """R23: B asking A while A waits on B is refused; so is a task asking itself;
    and a longer chain A -> B -> C -> A."""
    request = f"req-{uuid.uuid4().hex[:8]}"
    m = MessageRepository(engine)
    a, b, c = [await task(engine, request) for _ in range(3)]
    assert (await m.ask(me(a), b, "?", key=key(a, b), wait=WAIT, max_wait=MAX_WAIT)).ok
    back = await m.ask(me(b), a, "?", key=key(b, a), wait=WAIT, max_wait=MAX_WAIT)
    assert not back.ok and "deadlock" in (back.reason or "")
    itself = await m.ask(me(a), a, "?", key=key(a, a), wait=WAIT, max_wait=MAX_WAIT)
    assert not itself.ok and "itself" in (itself.reason or "")
    assert (await m.ask(me(b), c, "?", key=key(b, c), wait=WAIT, max_wait=MAX_WAIT)).ok
    loop = await m.ask(me(c), a, "?", key=key(c, a), wait=WAIT, max_wait=MAX_WAIT)
    assert not loop.ok and "deadlock" in (loop.reason or "")


async def test_an_ended_task_closes_its_messages_and_is_refused(engine: AsyncEngine) -> None:
    """R24, R25, R30: B ends; A's question to B is cancelled and A is told; A's
    unread message to B is undelivered; sends to and from B are refused."""
    m, a, b = await pair(engine)
    asked = await m.ask(me(a), b, "price?", key=key(a, b, "q"), wait=WAIT, max_wait=MAX_WAIT)
    note = await m.send(me(a), b, "fyi", key=key(a, b, "fyi"))
    await m.claim(a, 2, datetime.now(UTC))  # A sleeps: nothing pending yet
    await m.end_task(b, "succeeded", {"status": "succeeded"})
    status = dict(await rows(engine, "SELECT message_id, status FROM task_messages "
                             "WHERE sender_task = :a", a=a))  # fmt: skip
    assert status[asked.message_id] == "cancelled" and status[note.message_id] == "undelivered"
    assert await rows(engine, "SELECT recipient_workflow FROM message_wakes "
                      "WHERE recipient_workflow = :a", a=a) == [(a,)]  # fmt: skip
    claim = await m.claim(a, 3, datetime.now(UTC))
    told = await m.read_claimed(me(a, turn=3))
    assert claim.count == 1 and (told[0].kind, told[0].status) == ("ask", "cancelled")
    to_b = await m.send(me(a, turn=3), b, "hello?", key=key(a, b, "again"))
    assert not to_b.ok and "has ended" in (to_b.reason or "")
    assert [u["message_id"] for u in (await m.context(a)).undelivered] == [note.message_id]
    from_b = await m.send(me(b), a, "late", key=key(b, a, "late"))
    assert not from_b.ok and "cannot send" in (from_b.reason or "")


async def test_a_stale_attempt_cannot_send(engine: AsyncEngine) -> None:
    """R27: a superseded attempt's send is refused and nothing is stored."""
    m, a, b = await pair(engine)
    await AttemptRepository(engine).start(a, 1, 2, "worker")
    with pytest.raises(FenceRejected):
        await m.send(me(a, attempt=1), b, "stale", key=key(a, b, "stale"))
    assert await rows(engine, "SELECT 1 FROM task_messages WHERE sender_task = :a", a=a) == []


async def test_only_a_sleeping_recipient_is_woken_once(engine: AsyncEngine) -> None:
    """D6: a running recipient gets no wake row; a sleeping one gets one, however
    many messages arrive."""
    m, a, b = await pair(engine)
    await m.send(me(a), b, "one", key=key(a, b, 1))
    assert await rows(engine, "SELECT 1 FROM message_wakes WHERE recipient_workflow = :b",
                      b=b) == []  # fmt: skip
    await m.claim(b, 2, datetime.now(UTC))
    await m.read_claimed(me(b, turn=2))
    assert (await m.claim(b, 3, datetime.now(UTC))).count == 0  # B sleeps
    for n in range(5):
        await m.send(me(a), b, f"m{n}", key=key(a, b, "burst", n))
    assert await rows(engine, "SELECT count(*) FROM message_wakes WHERE recipient_workflow = :b",
                      b=b) == [(1,)]  # fmt: skip


async def test_an_ask_deadline_is_clamped_to_the_profile_cap(engine: AsyncEngine) -> None:
    m, a, b = await pair(engine)
    asked = await m.ask(me(a), b, "?", key=key(a, b), wait=timedelta(hours=5),
                        max_wait=timedelta(minutes=2))  # fmt: skip
    assert asked.deadline is not None
    assert asked.deadline - datetime.now(UTC) < timedelta(minutes=2, seconds=5)


async def test_request_exists_for_join(engine: AsyncEngine) -> None:
    """Phase 2 messaging D5: --join may name only a request that has a task."""
    _, a, _ = await pair(engine)
    request = (await rows(engine, "SELECT request_id FROM tasks WHERE task_id = :a", a=a))[0][0]
    assert await TaskRepository(engine).request_exists(request)
    assert not await TaskRepository(engine).request_exists(f"req-{uuid.uuid4().hex}")

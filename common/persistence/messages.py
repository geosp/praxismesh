"""The task inbox: messages, questions and replies between tasks of one request
(Phase 2 messaging D6, D7, D10, D13, D17; migration 0006).

Lock order (D10): an attempt write (send, ask, reply, read_claimed) takes the
sender's task lock and ADR-0007's fence check first, then the request lock, a
two-key advisory lock apart from the task locks. The orchestrator's steps (claim,
end_task) are not attempt writes: they take only the request lock. Status checks,
the cycle walk and wake rows are all decided under the request lock.

A question is "open" while its status is pending, claimed or read and its deadline
has not passed. Its delivery to the recipient uses `claimed_turn`; telling the asker
it expired or was cancelled uses `notice_turn`.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.persistence.fence import NO_NEWER_ATTEMPT, TASK_LOCK, FenceRejected

MAX_BODY = 16_384
OPEN = ("pending", "claimed", "read")
OPEN_SQL = "('pending', 'claimed', 'read')"  # a question's open statuses, for SQL
_REQUEST_LOCK = text("SELECT pg_advisory_xact_lock(2, hashtext(:r))")
_COLUMNS = (
    "message_id, request_id, sender_task, recipient_task, kind, correlation_id, reply_to, "
    "deadline, status, reason, body, claimed_turn, notice_turn, created_at"
)


@dataclass(frozen=True)
class Sender:
    """The attempt a write comes from: the fence key (ADR-0007)."""

    task_id: str
    turn: int
    attempt: int


@dataclass(frozen=True)
class SendResult:
    """What a send, ask or reply did. `ok` false is a refusal stored as a rejected row
    (R11); `reason` is the message for the model."""

    ok: bool
    message_id: str
    correlation_id: str | None = None
    deadline: datetime | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Claim:
    """What `claim` returns to the Workflow: IDs, a count and the next deadline,
    never a body (R28)."""

    message_ids: list[str]
    next_deadline: datetime | None

    @property
    def count(self) -> int:
        return len(self.message_ids)


@dataclass(frozen=True)
class Delivered:
    """A row a woken turn reads: a message, question or reply to the task, or one of
    its own questions that expired or was cancelled."""

    message_id: str
    sender_task: str
    recipient_task: str
    kind: str
    correlation_id: str | None
    reply_to: str | None
    status: str
    body: str


@dataclass
class Context:
    """`get_task_context`: the request's tasks and the caller's undelivered messages."""

    request_id: str
    tasks: list[dict[str, Any]] = field(default_factory=list)
    undelivered: list[dict[str, Any]] = field(default_factory=list)


def idempotency_key(sender: str, turn: int, tool: str, arguments: dict[str, Any]) -> str:
    """Attempts of one turn share it, so a retried attempt repeating an identical call
    stores nothing new (D13); a regenerated call with other text is a new message."""
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{sender}\0{turn}\0{tool}\0{canonical}".encode()).hexdigest()


class MessageRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    # -- attempt writes (fenced) -------------------------------------------------

    async def send(
        self, sender: Sender, recipient: str, body: str, *, key: str, reply_to: str | None = None
    ) -> SendResult:
        """A message, or with `reply_to` a reply to that question (R10-R13, R18, R25)."""
        async with self.engine.begin() as conn:
            request = await self._enter(conn, sender)
            existing = await self._by_key(conn, key)
            if existing is not None:
                return existing
            refusal = await self._refusal(conn, sender.task_id, recipient, request, body)
            question = None
            if refusal is None and reply_to is not None:
                question, refusal = await self._question_for_reply(
                    conn, reply_to, sender.task_id, recipient
                )
            kind = "reply" if reply_to is not None else "send"
            if refusal is not None:
                return await self._reject(
                    conn, sender, recipient, request, kind, body, key, refusal
                )
            message_id = uuid.uuid4().hex
            await self._insert(
                conn, message_id, request, sender.task_id, recipient, kind, body, key,
                reply_to=reply_to,
            )  # fmt: skip
            if question is not None:
                await conn.execute(
                    text("UPDATE task_messages SET status = 'answered' WHERE message_id = :m"),
                    {"m": question},
                )
            await self._wake_if_sleeping(conn, recipient)
            return SendResult(True, message_id, correlation_id=reply_to)

    async def ask(
        self,
        sender: Sender,
        recipient: str,
        body: str,
        *,
        key: str,
        wait: timedelta,
        max_wait: timedelta,
    ) -> SendResult:
        """A question with a deadline, clamped to `max_wait` (D8); refused when it asks
        the asker itself or would close a wait cycle (R23)."""
        async with self.engine.begin() as conn:
            request = await self._enter(conn, sender)
            existing = await self._by_key(conn, key)
            if existing is not None:
                return existing
            refusal = await self._refusal(conn, sender.task_id, recipient, request, body)
            if refusal is None and recipient == sender.task_id:
                refusal = "a task cannot ask itself"
            if refusal is None and await self._waits_on(conn, recipient, sender.task_id):
                refusal = (
                    f"{recipient} is already waiting on {sender.task_id}: asking would deadlock"
                )
            if refusal is not None:
                return await self._reject(
                    conn, sender, recipient, request, "ask", body, key, refusal
                )
            message_id = uuid.uuid4().hex
            seconds = min(wait, max_wait).total_seconds()
            deadline = (
                await conn.execute(text("SELECT now() + make_interval(secs => :s)"), {"s": seconds})
            ).scalar_one()
            await self._insert(
                conn, message_id, request, sender.task_id, recipient, "ask", body, key,
                correlation_id=message_id, deadline=deadline,
            )  # fmt: skip
            await self._wake_if_sleeping(conn, recipient)
            return SendResult(True, message_id, correlation_id=message_id, deadline=deadline)

    async def read_claimed(self, sender: Sender) -> list[Delivered]:
        """The rows the attempt's turn claimed, oldest first; messages, questions and
        replies to the task become `read` (a fenced write: a stale attempt reads
        nothing and marks nothing)."""
        async with self.engine.begin() as conn:
            await self._enter(conn, sender)
            rows = await conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM task_messages WHERE "
                    "(recipient_task = :t AND claimed_turn = :turn) OR "
                    "(sender_task = :t AND notice_turn = :turn) ORDER BY created_at, message_id"
                ),
                {"t": sender.task_id, "turn": sender.turn},
            )
            delivered = [_delivered(r) for r in rows.mappings()]
            await conn.execute(
                text(
                    "UPDATE task_messages SET status = 'read' WHERE recipient_task = :t "
                    "AND claimed_turn = :turn AND status = 'claimed'"
                ),
                {"t": sender.task_id, "turn": sender.turn},
            )
        return delivered

    async def blocking_finish(self, sender: Sender) -> list[str]:
        """Why the task may not finish: its open questions and its unread replies
        (R19), read under the request lock so an ask in the same model step counts."""
        async with self.engine.begin() as conn:
            await self._enter(conn, sender)
            rows = await conn.execute(
                text(
                    "SELECT kind, correlation_id, reply_to, recipient_task, sender_task "
                    "FROM task_messages WHERE "
                    "(sender_task = :t AND kind = 'ask' AND status IN " + OPEN_SQL + " "
                    "AND deadline > now()) OR "
                    "(recipient_task = :t AND kind = 'reply' AND status IN ('pending', 'claimed')) "
                    "ORDER BY created_at"
                ),
                {"t": sender.task_id},
            )
            reasons = []
            for r in rows.mappings():
                if r["kind"] == "ask":
                    reasons.append(f"open question {r['correlation_id']} to {r['recipient_task']}")
                else:
                    reasons.append(f"unread reply from {r['sender_task']} to {r['reply_to']}")
        return reasons

    # -- orchestrator steps (request lock only) ----------------------------------

    async def claim(self, task_id: str, turn: int, now: datetime) -> Claim:
        """Expire the task's due questions, assign its pending rows to `turn`, and set
        whether it is sleeping (D7). A rerun for the same turn returns the same IDs.
        `now` is the Workflow's time, so expiry agrees with its timers."""
        async with self.engine.begin() as conn:
            await conn.execute(_REQUEST_LOCK, {"r": await self._request_of(conn, task_id)})
            await conn.execute(
                text(
                    "UPDATE task_messages SET status = 'expired' WHERE sender_task = :t "
                    "AND kind = 'ask' AND status IN " + OPEN_SQL + " AND deadline < :now"
                ),
                {"t": task_id, "now": now},
            )
            await conn.execute(
                text(
                    "UPDATE task_messages SET status = 'claimed', claimed_turn = :turn "
                    "WHERE recipient_task = :t AND status = 'pending' "
                    "AND (kind <> 'ask' OR deadline >= :now)"
                ),
                {"t": task_id, "turn": turn, "now": now},
            )
            await conn.execute(
                text(
                    "UPDATE task_messages SET notice_turn = :turn WHERE sender_task = :t "
                    "AND kind = 'ask' AND status IN ('expired', 'cancelled') "
                    "AND notice_turn IS NULL"
                ),
                {"t": task_id, "turn": turn},
            )
            ids = [
                r[0]
                for r in await conn.execute(
                    text(
                        "SELECT message_id FROM task_messages WHERE "
                        "(recipient_task = :t AND claimed_turn = :turn) OR "
                        "(sender_task = :t AND notice_turn = :turn) ORDER BY created_at, message_id"
                    ),
                    {"t": task_id, "turn": turn},
                )
            ]
            next_deadline = (
                await conn.execute(
                    text(
                        "SELECT min(deadline) FROM task_messages WHERE sender_task = :t "
                        "AND kind = 'ask' AND status IN " + OPEN_SQL + ""
                    ),
                    {"t": task_id},
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO task_inbox (task_id, sleeping) VALUES (:t, :s) "
                    "ON CONFLICT (task_id) DO UPDATE SET sleeping = EXCLUDED.sleeping"
                ),
                {"t": task_id, "s": not ids},
            )
        return Claim(ids, next_deadline)

    async def end_task(self, task_id: str, status: str, result: dict[str, Any]) -> None:
        """Record the task's end and close its messages in one transaction (D17):
        questions to and from it are cancelled, messages it never read become
        undelivered, and askers waiting on it are woken."""
        async with self.engine.begin() as conn:
            await conn.execute(_REQUEST_LOCK, {"r": await self._request_of(conn, task_id)})
            await conn.execute(
                text(
                    "UPDATE tasks SET status = :s, result = :r, updated_at = CURRENT_TIMESTAMP "
                    "WHERE task_id = :t"
                ),
                {"t": task_id, "s": status, "r": json.dumps(result)},
            )
            await conn.execute(
                text(
                    "UPDATE task_messages SET status = 'cancelled', reason = 'asker ended' "
                    "WHERE sender_task = :t AND kind = 'ask' AND status IN " + OPEN_SQL + ""
                ),
                {"t": task_id},
            )
            askers = await conn.execute(
                text(
                    "UPDATE task_messages SET status = 'cancelled', reason = :why "
                    "WHERE recipient_task = :t AND kind = 'ask' "
                    "AND status IN " + OPEN_SQL + " RETURNING sender_task"
                ),
                {"t": task_id, "why": f"{task_id} ended without replying"},
            )
            waiting = sorted({r[0] for r in askers})
            await conn.execute(
                text(
                    "UPDATE task_messages SET status = 'undelivered', reason = :why "
                    "WHERE recipient_task = :t AND kind <> 'ask' "
                    "AND status IN ('pending', 'claimed')"
                ),
                {"t": task_id, "why": f"{task_id} ended before reading it"},
            )
            for asker in waiting:
                await self._wake_if_sleeping(conn, asker)

    async def context(self, task_id: str) -> Context:
        """The request's tasks and the caller's undelivered messages (D15)."""
        async with self.engine.connect() as conn:
            request = await self._request_of(conn, task_id)
            tasks = await conn.execute(
                text(
                    "SELECT task_id, profile, status FROM tasks WHERE request_id = :r "
                    "ORDER BY created_at, task_id"
                ),
                {"r": request},
            )
            undelivered = await conn.execute(
                text(
                    "SELECT message_id, recipient_task, kind, reason FROM task_messages "
                    "WHERE sender_task = :t AND status = 'undelivered' ORDER BY created_at"
                ),
                {"t": task_id},
            )
            return Context(
                request,
                [dict(r) for r in tasks.mappings()],
                [dict(r) for r in undelivered.mappings()],
            )

    # -- helpers -----------------------------------------------------------------

    async def _enter(self, conn: AsyncConnection, sender: Sender) -> str:
        """The fence, then the request lock (D10). Returns the sender's request."""
        await conn.execute(TASK_LOCK, {"t": sender.task_id})
        fence = {"t": sender.task_id, "turn": sender.turn, "a": sender.attempt}
        if (await conn.execute(text("SELECT 1 WHERE " + NO_NEWER_ATTEMPT), fence)).first() is None:
            raise FenceRejected("a newer attempt owns this task")
        request = await self._request_of(conn, sender.task_id)
        await conn.execute(_REQUEST_LOCK, {"r": request})
        return request

    async def _request_of(self, conn: AsyncConnection, task_id: str) -> str:
        row = (
            await conn.execute(
                text("SELECT request_id FROM tasks WHERE task_id = :t"), {"t": task_id}
            )
        ).first()
        if row is None:
            raise LookupError(f"task {task_id} is not recorded")
        return str(row[0])

    async def _refusal(
        self, conn: AsyncConnection, sender: str, recipient: str, request: str, body: str
    ) -> str | None:
        if len(body) > MAX_BODY:
            return f"the message is longer than {MAX_BODY} characters"
        rows = await conn.execute(
            text("SELECT task_id, request_id, status FROM tasks WHERE task_id IN (:s, :r)"),
            {"s": sender, "r": recipient},
        )
        found = {r[0]: (r[1], r[2]) for r in rows}
        if found.get(sender, ("", ""))[1] != "running":
            return f"{sender} has ended and cannot send"
        if recipient not in found or found[recipient][0] != request:
            return f"{recipient} is not a task of this request"
        if found[recipient][1] != "running":
            return f"recipient {recipient} has ended"
        return None

    async def _question_for_reply(
        self, conn: AsyncConnection, correlation_id: str, replier: str, recipient: str
    ) -> tuple[str | None, str | None]:
        """The question's message ID, or the refusal text: a reply goes from the asked
        task to the asker (R16) while the question is open (R18)."""
        row = (
            await conn.execute(
                text(
                    "SELECT message_id, recipient_task, status, deadline < now() AS late, "
                    "sender_task "
                    "FROM task_messages WHERE correlation_id = :c AND kind = 'ask'"
                ),
                {"c": correlation_id},
            )
        ).first()
        if row is None or row[1] != replier:
            return None, f"there is no question {correlation_id} to {replier}"
        if row[4] != recipient:
            return None, f"question {correlation_id} was asked by {row[4]}; reply to it"
        if row[2] not in OPEN or row[3]:
            return None, f"question {correlation_id} is {'expired' if row[3] else row[2]}"
        return str(row[0]), None

    async def _waits_on(self, conn: AsyncConnection, start: str, target: str) -> bool:
        """Whether `start` waits, directly or through others, on an answer from
        `target`: follow the recipients of open questions, breadth first."""
        seen, frontier = {start}, [start]
        while frontier:
            rows = await conn.execute(
                text(
                    "SELECT DISTINCT recipient_task FROM task_messages WHERE kind = 'ask' "
                    "AND sender_task = ANY(:f) AND status IN " + OPEN_SQL + " "
                    "AND deadline > now()"
                ),
                {"f": frontier},
            )
            nxt = [r[0] for r in rows if r[0] not in seen]
            if target in nxt:
                return True
            seen.update(nxt)
            frontier = nxt
        return False

    async def _by_key(self, conn: AsyncConnection, key: str) -> SendResult | None:
        row = (
            await conn.execute(
                text(
                    "SELECT message_id, correlation_id, deadline, status, reason "
                    "FROM task_messages WHERE idempotency_key = :k"
                ),
                {"k": key},
            )
        ).first()
        if row is None:
            return None
        if row[3] == "rejected":
            return SendResult(False, row[0], reason=row[4])
        return SendResult(True, row[0], correlation_id=row[1], deadline=row[2])

    async def _insert(
        self,
        conn: AsyncConnection,
        message_id: str,
        request: str,
        sender: str,
        recipient: str,
        kind: str,
        body: str,
        key: str,
        *,
        status: str = "pending",
        reason: str | None = None,
        correlation_id: str | None = None,
        reply_to: str | None = None,
        deadline: datetime | None = None,
    ) -> None:
        await conn.execute(
            text(
                "INSERT INTO task_messages (message_id, request_id, sender_task, recipient_task, "
                "kind, correlation_id, reply_to, deadline, status, reason, body, idempotency_key) "
                "VALUES (:m, :req, :s, :r, :k, :c, :rt, :d, :st, :why, :b, :key)"
            ),
            {
                "m": message_id, "req": request, "s": sender, "r": recipient, "k": kind,
                "c": correlation_id, "rt": reply_to, "d": deadline, "st": status, "why": reason,
                "b": body[:MAX_BODY], "key": key,
            },
        )  # fmt: skip

    async def _reject(
        self,
        conn: AsyncConnection,
        sender: Sender,
        recipient: str,
        request: str,
        kind: str,
        body: str,
        key: str,
        reason: str,
    ) -> SendResult:
        """Store the refusal (R11) and report it."""
        message_id = uuid.uuid4().hex
        await self._insert(
            conn, message_id, request, sender.task_id, recipient, kind, body, key,
            status="rejected", reason=reason,
        )  # fmt: skip
        return SendResult(False, message_id, reason=reason)

    async def _wake_if_sleeping(self, conn: AsyncConnection, recipient: str) -> None:
        """One pending wake per sleeping recipient (D6); its workflow ID is its task ID."""
        # No RETURNING: it needs no wake row data back.
        woken = await conn.execute(
            text(
                "INSERT INTO message_wakes (recipient_workflow) "
                "SELECT task_id FROM task_inbox WHERE task_id = :r AND sleeping "
                "ON CONFLICT (recipient_workflow) DO NOTHING"
            ),
            {"r": recipient},
        )
        if woken.rowcount:
            await conn.execute(text("SELECT pg_notify('message_wakes', :r)"), {"r": recipient})


def _delivered(row: Any) -> Delivered:
    return Delivered(
        row["message_id"],
        row["sender_task"],
        row["recipient_task"],
        row["kind"],
        row["correlation_id"],
        row["reply_to"],
        row["status"],
        row["body"],
    )

"""PostgreSQL event-table transport (ADR-0009; Phase 2 events plan D1, D2).

Tables from migration 0005:
- `event_logs` holds each workflow's next offset and retained base;
- `agent_events (workflow_id, offset)` holds the events;
- `event_batches (workflow_id, batch_id)` records each batch in the same
  transaction as its events, so a re-send within the horizon stores nothing.

A publish takes ADR-0007's fence first (the task lock, then the newer-attempt
check), then the workflow's `event_logs` row lock, so offsets are gap-free and the
lock order matches every other fenced write. Each batch sends one `NOTIFY`; a
following reader `LISTEN`s on its own autocommit connection (a notification is
delivered only between transactions) and also polls every second.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.events.transport import RESEND_HORIZON_S, Item, Writer, expiry_for, guarded
from common.persistence.fence import NO_NEWER_ATTEMPT, TASK_LOCK, FenceRejected
from common.schemas.blob import BlobRef
from common.schemas.events import AgentEvent

CHANNEL = "agent_events"
PAGE = 1000
POLL_S = 1.0

_INSERT = text(
    'INSERT INTO agent_events (workflow_id, "offset", task_id, attempt_id, seq, type, '
    "payload, blob_ref, emitted_at) VALUES (:w, :o, :task, :attempt, :seq, :type, "
    "CAST(:payload AS json), CAST(:blob AS json), :emitted)"
)


class TableTransport:
    def __init__(
        self, engine: AsyncEngine, horizon_s: float = RESEND_HORIZON_S, *, fenced: bool = True
    ) -> None:
        # `fenced=False` exists only for the load benchmark's unfenced baseline
        # (Phase 2 events plan task 2.3); production always fences (ADR-0007).
        self.engine, self.horizon_s, self.fenced = engine, horizon_s, fenced

    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[AgentEvent]
    ) -> None:
        fence = {"t": writer.task_id, "turn": writer.turn, "a": writer.attempt}
        async with self.engine.begin() as conn:
            if self.fenced:
                await conn.execute(TASK_LOCK, {"t": writer.task_id})
                if (
                    await conn.execute(text("SELECT 1 WHERE " + NO_NEWER_ATTEMPT), fence)
                ).first() is None:
                    raise FenceRejected("a newer attempt owns this task")
            await conn.execute(
                text("INSERT INTO event_logs (workflow_id) VALUES (:w) ON CONFLICT DO NOTHING"),
                {"w": workflow_id},
            )
            next_offset = (
                await conn.execute(
                    text("SELECT next_offset FROM event_logs WHERE workflow_id = :w FOR UPDATE"),
                    {"w": workflow_id},
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "DELETE FROM event_batches WHERE workflow_id = :w "
                    "AND seen_at < now() - make_interval(secs => :h)"
                ),
                {"w": workflow_id, "h": self.horizon_s},
            )
            fresh = await conn.execute(
                text(
                    "INSERT INTO event_batches (workflow_id, batch_id) VALUES (:w, :b) "
                    "ON CONFLICT DO NOTHING RETURNING batch_id"
                ),
                {"w": workflow_id, "b": batch_id},
            )
            if fresh.first() is None:
                return  # a re-send within the horizon
            if events:
                await conn.execute(
                    _INSERT, [_row(workflow_id, next_offset + i, e) for i, e in enumerate(events)]
                )
            await conn.execute(
                text("UPDATE event_logs SET next_offset = :n WHERE workflow_id = :w"),
                {"w": workflow_id, "n": next_offset + len(events)},
            )
            await conn.execute(text("SELECT pg_notify(:c, :w)"), {"c": CHANNEL, "w": workflow_id})

    def read(
        self, workflow_id: str, after: int, *, follow: bool = False
    ) -> AsyncGenerator[Item, None]:
        return guarded(after, self._read(workflow_id, after, follow))

    async def _read(self, workflow_id: str, after: int, follow: bool) -> AsyncIterator[Item]:
        async with self.engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            woken = asyncio.Event()
            driver: Any = (await conn.get_raw_connection()).driver_connection

            def notified(*args: object) -> None:
                if args[3] == workflow_id:
                    woken.set()

            if follow:
                await driver.add_listener(CHANNEL, notified)
            try:
                bounds = await self._bounds(conn, workflow_id)
                if bounds is not None and bounds[0] > 1:
                    expired = expiry_for(after, bounds[1])
                    if expired is not None:
                        yield expired
                        after = expired.retained_base - 1
                position = after
                while True:
                    woken.clear()  # before the fetch, so a NOTIFY during it is kept
                    rows = await self._fetch(conn, workflow_id, position)
                    for row in rows:
                        position = row["offset"]
                        yield position, _event(row)
                    if len(rows) == PAGE:
                        continue
                    if not follow:
                        return
                    with contextlib.suppress(TimeoutError):  # the 1 s poll fallback
                        await asyncio.wait_for(woken.wait(), POLL_S)
            finally:
                if follow:
                    await driver.remove_listener(CHANNEL, notified)

    async def _bounds(self, conn: AsyncConnection, workflow_id: str) -> tuple[int, int] | None:
        row = (
            await conn.execute(
                text("SELECT next_offset, retained_base FROM event_logs WHERE workflow_id = :w"),
                {"w": workflow_id},
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def _fetch(self, conn: AsyncConnection, workflow_id: str, after: int) -> list[Any]:
        rows = await conn.execute(
            text(
                'SELECT "offset", task_id, attempt_id, seq, type, payload, blob_ref, emitted_at '
                'FROM agent_events WHERE workflow_id = :w AND "offset" > :after '
                'ORDER BY "offset" LIMIT :page'
            ),
            {"w": workflow_id, "after": after, "page": PAGE},
        )
        return [dict(r) | {"workflow_id": workflow_id} for r in rows.mappings()]

    async def latest(self, workflow_id: str) -> int | None:
        async with self.engine.connect() as conn:
            bounds = await self._bounds(conn, workflow_id)
        return bounds[0] - 1 if bounds and bounds[0] > 1 else None

    async def prune(
        self, workflow_id: str, *, below: int | None = None, older_than: timedelta | None = None
    ) -> int | None:
        if (below is None) == (older_than is None):
            raise ValueError("give exactly one of below and older_than")
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT next_offset, retained_base FROM event_logs "
                        "WHERE workflow_id = :w FOR UPDATE"
                    ),
                    {"w": workflow_id},
                )
            ).first()
            if row is None or row[0] == 1:
                return None
            next_offset, base = row
            if below is not None:
                cutoff = below
            else:
                assert older_than is not None
                newest = await conn.execute(
                    text(
                        'SELECT min("offset") FROM agent_events WHERE workflow_id = :w '
                        "AND stored_at >= now() - make_interval(secs => :s)"
                    ),
                    {"w": workflow_id, "s": older_than.total_seconds()},
                )
                cutoff = newest.scalar_one() or next_offset
            new_base = max(base, min(cutoff, next_offset))
            await conn.execute(
                text('DELETE FROM agent_events WHERE workflow_id = :w AND "offset" < :c'),
                {"w": workflow_id, "c": new_base},
            )
            await conn.execute(
                text("UPDATE event_logs SET retained_base = :b WHERE workflow_id = :w"),
                {"w": workflow_id, "b": new_base},
            )
            return int(new_base)

    async def close(self) -> None:
        return None  # the engine belongs to the caller


def _row(workflow_id: str, offset: int, e: AgentEvent) -> dict[str, Any]:
    return {
        "w": workflow_id,
        "o": offset,
        "task": e.task_id,
        "attempt": e.attempt_id,
        "seq": e.seq,
        "type": e.type,
        "payload": json.dumps(e.payload),
        "blob": e.blob_ref.model_dump_json() if e.blob_ref is not None else None,
        "emitted": e.timestamp,
    }


def _event(row: dict[str, Any]) -> AgentEvent:
    blob = row["blob_ref"]
    return AgentEvent(
        seq=row["seq"],
        timestamp=row["emitted_at"],
        workflow_id=row["workflow_id"],
        task_id=row["task_id"],
        attempt_id=row["attempt_id"],
        type=row["type"],
        payload=row["payload"] or {},
        blob_ref=BlobRef.model_validate(blob) if blob is not None else None,
    )

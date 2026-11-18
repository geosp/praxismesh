"""PostgreSQL event-table transport (plan D5, notes.md#d5; task 2.1).

One `spike76` schema in the disposable stack's database:
- `events (workflow_id, offset)` holds each event's JSON;
- `counters` holds each workflow's next offset and retained base;
- `batches (workflow_id, batch_id)` records each batch, in the same transaction as its
  events, so a re-send within the horizon stores nothing (R3).

Publish takes the counter row's lock, so offsets are gap-free per workflow. Each
batch sends one `NOTIFY`; a following reader `LISTEN`s and also polls every 1 s.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator

import asyncpg

from event_transport.models import AgentEvent
from event_transport.transport import Item, expiry_for

DSN = os.environ.get(
    "SPIKE_PG_DSN", "postgresql://praxismesh:change-me-app@127.0.0.1:35432/praxismesh"
)
CHANNEL = "spike76_events"
PAGE = 1000
POLL_S = 1.0

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS spike76;
CREATE TABLE IF NOT EXISTS spike76.counters (
    workflow_id text PRIMARY KEY,
    next_offset bigint NOT NULL DEFAULT 1,
    base bigint NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS spike76.events (
    workflow_id text NOT NULL,
    "offset" bigint NOT NULL,
    body jsonb NOT NULL,
    PRIMARY KEY (workflow_id, "offset")
);
CREATE TABLE IF NOT EXISTS spike76.batches (
    workflow_id text NOT NULL,
    batch_id text NOT NULL,
    seen_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workflow_id, batch_id)
);
"""


class TableTransport:
    def __init__(self, pool: asyncpg.Pool, horizon_s: float) -> None:
        self.pool, self.horizon_s = pool, horizon_s

    @classmethod
    async def connect(cls, horizon_s: float, dsn: str = DSN) -> TableTransport:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=20)
        async with pool.acquire() as conn:
            await conn.execute("SELECT pg_advisory_lock(7676)")  # one schema creator at a time
            try:
                await conn.execute(SCHEMA)
            finally:
                await conn.execute("SELECT pg_advisory_unlock(7676)")
        return cls(pool, horizon_s)

    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO spike76.counters (workflow_id) VALUES ($1) ON CONFLICT DO NOTHING",
                workflow_id,
            )
            next_offset = await conn.fetchval(
                "SELECT next_offset FROM spike76.counters WHERE workflow_id = $1 FOR UPDATE",
                workflow_id,
            )
            fresh = await conn.fetchval(
                "SELECT seen_at > now() - make_interval(secs => $3) FROM spike76.batches "
                "WHERE workflow_id = $1 AND batch_id = $2",
                workflow_id,
                batch_id,
                self.horizon_s,
            )
            if fresh:
                return  # a re-send within the horizon (R3)
            await conn.execute(
                "INSERT INTO spike76.batches (workflow_id, batch_id) VALUES ($1, $2) "
                "ON CONFLICT (workflow_id, batch_id) DO UPDATE SET seen_at = now()",
                workflow_id,
                batch_id,
            )
            await conn.executemany(
                'INSERT INTO spike76.events (workflow_id, "offset", body) VALUES ($1, $2, $3)',
                [(workflow_id, next_offset + i, e.model_dump_json()) for i, e in enumerate(events)],
            )
            await conn.execute(
                "UPDATE spike76.counters SET next_offset = $2 WHERE workflow_id = $1",
                workflow_id,
                next_offset + len(events),
            )
            await conn.execute("SELECT pg_notify($1, $2)", CHANNEL, workflow_id)

    async def _bounds(self, conn: asyncpg.Connection, workflow_id: str) -> tuple[int, int] | None:
        row = await conn.fetchrow(
            "SELECT next_offset, base FROM spike76.counters WHERE workflow_id = $1", workflow_id
        )
        return (row["next_offset"], row["base"]) if row else None

    async def read(
        self, workflow_id: str, after: int, *, follow: bool = False
    ) -> AsyncIterator[Item]:
        async with self.pool.acquire() as conn:
            woken = asyncio.Event()
            if follow:

                def notified(*args: object) -> None:
                    if args[3] == workflow_id:
                        woken.set()

                await conn.add_listener(CHANNEL, notified)
            try:
                bounds = await self._bounds(conn, workflow_id)
                if bounds is not None and bounds[0] > 1:
                    expired = expiry_for(after, bounds[1])
                    if expired is not None:
                        yield expired
                        after = expired.retained_base - 1
                position = after
                while True:
                    rows = await conn.fetch(
                        'SELECT "offset", body FROM spike76.events WHERE workflow_id = $1 '
                        'AND "offset" > $2 ORDER BY "offset" LIMIT $3',
                        workflow_id,
                        position,
                        PAGE,
                    )
                    for row in rows:
                        position = row["offset"]
                        yield position, AgentEvent.model_validate_json(row["body"])
                    if len(rows) == PAGE:
                        continue
                    if not follow:
                        return
                    woken.clear()
                    with contextlib.suppress(TimeoutError):  # the 1 s poll fallback
                        await asyncio.wait_for(woken.wait(), POLL_S)
            finally:
                if follow:
                    await conn.remove_listener(CHANNEL, notified)

    async def latest(self, workflow_id: str) -> int | None:
        async with self.pool.acquire() as conn:
            bounds = await self._bounds(conn, workflow_id)
        return bounds[0] - 1 if bounds and bounds[0] > 1 else None

    async def expire_below(self, workflow_id: str, offset: int) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                'DELETE FROM spike76.events WHERE workflow_id = $1 AND "offset" < $2',
                workflow_id,
                offset,
            )
            await conn.execute(
                "UPDATE spike76.counters SET base = GREATEST(base, $2) WHERE workflow_id = $1",
                workflow_id,
                offset,
            )

    async def roll_over(self, workflow_id: str) -> None:
        return None  # not hosted in a Workflow (R4 is n/a)

    async def close(self) -> None:
        await self.pool.close()

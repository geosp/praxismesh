"""The dispatcher: turns wake rows into `inbox` Signals (Phase 2 messaging D6).

Runs in the orchestrator worker. A send to a sleeping task commits a wake row and
`NOTIFY message_wakes` with the message (common/persistence/messages.py). The
dispatcher `LISTEN`s and also polls every second, takes rows with
`FOR UPDATE SKIP LOCKED` (so several orchestrator replicas share the work), and for
each row deletes it and then Signals the recipient's Workflow, in that row's own
transaction. A failed Signal rolls back the delete, so the row waits for the next
poll; a closed or missing Workflow keeps the delete (logged). Deleting before the
Signal matters: a sender's wake insert for the same recipient then waits for this
transaction and adds a new row, instead of finding the old one and being dropped
with it. A crash before the commit keeps every row. The Signal is only a hint: the
Workflow reads its inbox by claiming.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from common.events.transport import wait_set

log = logging.getLogger("praxis.dispatcher")
CHANNEL = "message_wakes"
POLL_S = 1.0
INBOX_SIGNAL = "inbox"
# Senders to a row in the batch wait for the drain to commit: keep each Signal short.
SIGNAL_TIMEOUT = timedelta(seconds=5)


class Dispatcher:
    def __init__(self, engine: AsyncEngine, client: Client, *, poll_s: float = POLL_S) -> None:
        self.engine, self.client, self.poll_s = engine, client, poll_s

    async def run(self) -> None:
        """Dispatch until cancelled. A lost or failed connection is retried, so the
        dispatcher outlives a database that is down when the worker starts."""
        while True:
            try:
                await self._listen_and_drain()
            except Exception:
                log.exception("dispatcher connection failed; retrying")
            await asyncio.sleep(self.poll_s)

    async def _listen_and_drain(self) -> None:
        woken = asyncio.Event()

        def notified(*args: object) -> None:
            woken.set()

        async with self.engine.connect() as conn:
            conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
            driver: Any = (await conn.get_raw_connection()).driver_connection
            await driver.add_listener(CHANNEL, notified)
            try:
                while True:
                    woken.clear()  # before draining, so a NOTIFY during it is kept
                    try:
                        await self.drain()
                    except Exception:  # the database or Temporal is down: poll again
                        log.exception("dispatching wakes failed")
                    if driver.is_closed():
                        raise ConnectionError("the LISTEN connection closed")
                    await wait_set(woken, self.poll_s)
            finally:
                with contextlib.suppress(Exception):  # the connection may be gone
                    await driver.remove_listener(CHANNEL, notified)

    async def drain(self) -> int:
        """Signal every pending wake once; returns how many rows were deleted.

        One transaction per row: a sender to that recipient waits for it, so it is
        held for one Signal (at most SIGNAL_TIMEOUT), never for a whole batch."""
        deleted, kept = 0, [0]  # ids whose Signal failed in this drain; 0 is never an id
        while True:
            async with self.engine.begin() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT id, recipient_workflow FROM message_wakes "
                            "WHERE id <> ALL(:kept) ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
                        ),
                        {"kept": kept},
                    )
                ).first()
                if row is None:
                    return deleted
                row_id, workflow_id = row
                await conn.execute(text("DELETE FROM message_wakes WHERE id = :id"), {"id": row_id})
                if not await self._signal(workflow_id):
                    await conn.rollback()  # keep the row for the next poll
                    kept.append(row_id)
                    continue
            deleted += 1

    async def _signal(self, workflow_id: str) -> bool:
        """True when the row can go: the Signal was accepted, or the Workflow is gone."""
        try:
            await self.client.get_workflow_handle(workflow_id).signal(
                INBOX_SIGNAL, rpc_timeout=SIGNAL_TIMEOUT
            )
        except RPCError as e:  # a timeout too: keep the row
            if e.status == RPCStatusCode.NOT_FOUND:  # closed or never started
                fields = {"workflow_id": workflow_id}
                log.info("wake for a closed workflow dropped", extra={"fields": fields})
                return True
            fields = {"workflow_id": workflow_id, "error": str(e)}
            log.warning("signal failed; keeping the wake", extra={"fields": fields})
            return False
        return True

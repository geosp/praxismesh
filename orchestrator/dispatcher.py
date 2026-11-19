"""The dispatcher: turns wake rows into `inbox` Signals (Phase 2 messaging D6).

Runs in the orchestrator worker. A send to a sleeping task commits a wake row and
`NOTIFY message_wakes` with the message (common/persistence/messages.py). The
dispatcher `LISTEN`s and also polls every second, takes rows with
`FOR UPDATE SKIP LOCKED` (so several orchestrator replicas share the work), Signals
each recipient's Workflow and deletes the row once the Signal was accepted, or when
the Workflow is closed or missing (logged). Any other error keeps the row for the
next poll. The Signal is only a hint: the Workflow reads its inbox by claiming.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from common.events.transport import wait_set

log = logging.getLogger("praxis.dispatcher")
CHANNEL = "message_wakes"
POLL_S = 1.0
BATCH = 50
INBOX_SIGNAL = "inbox"


class Dispatcher:
    def __init__(self, engine: AsyncEngine, client: Client, *, poll_s: float = POLL_S) -> None:
        self.engine, self.client, self.poll_s = engine, client, poll_s

    async def run(self) -> None:
        """Dispatch until cancelled."""
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
                    await wait_set(woken, self.poll_s)
            finally:
                await driver.remove_listener(CHANNEL, notified)

    async def drain(self) -> int:
        """Signal every pending wake once; returns how many rows were deleted."""
        deleted = 0
        while True:
            async with self.engine.begin() as conn:
                rows = list(
                    await conn.execute(
                        text(
                            "SELECT id, recipient_workflow FROM message_wakes ORDER BY id "
                            "FOR UPDATE SKIP LOCKED LIMIT :n"
                        ),
                        {"n": BATCH},
                    )
                )
                done = [row_id for row_id, workflow_id in rows if await self._signal(workflow_id)]
                if done:
                    await conn.execute(
                        text("DELETE FROM message_wakes WHERE id = ANY(:ids)"), {"ids": done}
                    )
            deleted += len(done)
            if len(rows) < BATCH or not done:
                return deleted

    async def _signal(self, workflow_id: str) -> bool:
        """True when the row can go: the Signal was accepted, or the Workflow is gone."""
        try:
            await self.client.get_workflow_handle(workflow_id).signal(INBOX_SIGNAL)
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND:  # closed or never started
                fields = {"workflow_id": workflow_id}
                log.info("wake for a closed workflow dropped", extra={"fields": fields})
                return True
            fields = {"workflow_id": workflow_id, "error": str(e)}
            log.warning("signal failed; keeping the wake", extra={"fields": fields})
            return False
        return True

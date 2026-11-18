"""A NOTIFY that arrives while the table reader is fetching still wakes it, so the
event arrives well before the 1 s poll fallback (impl review F38). Needs the
disposable stack; runs when SPIKE_TRANSPORTS includes `table`."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import asyncpg
import pytest
from event_transport.checks import make_events, new_workflow
from event_transport.table import POLL_S, TableTransport

pytestmark = pytest.mark.skipif(
    "table" not in os.environ.get("SPIKE_TRANSPORTS", ""), reason="needs the disposable stack"
)


class PublishesDuringFetch(TableTransport):
    """After the reader's second fetch has taken its snapshot, a publisher commits a
    batch, so its NOTIFY lands while the reader is still between fetch and wait."""

    fetches = 0
    published_at = 0.0

    async def _fetch(self, conn: asyncpg.Connection, workflow_id: str, after: int) -> list[Any]:
        rows = await super()._fetch(conn, workflow_id, after)
        self.fetches += 1
        if self.fetches == 2:
            await self.publish(workflow_id, f"{workflow_id}-late", make_events(workflow_id, 1, 1))
            self.published_at = time.monotonic()
            await asyncio.sleep(0.05)  # let the NOTIFY reach the reader's connection
        return rows


async def test_a_notify_during_a_fetch_is_not_lost() -> None:
    t = await PublishesDuringFetch.connect(60)
    try:
        wf = new_workflow()
        await t.publish(wf, f"{wf}-b0", make_events(wf, 1))
        got: list[float] = []
        async for _item in t.read(wf, 0, follow=True):
            got.append(time.monotonic())
            if len(got) == 2:
                break
        assert got[1] - t.published_at < POLL_S / 2, got[1] - t.published_at
    finally:
        await t.close()

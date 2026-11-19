"""The dispatcher keeps retrying when the database is down at start-up (review
round 1): it must not end, silently, on its first failed connect."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from orchestrator.dispatcher import Dispatcher


class DownEngine:
    def __init__(self) -> None:
        self.connects = 0

    def connect(self) -> Any:
        self.connects += 1
        raise OSError("database unavailable")


async def test_a_failed_first_connect_is_retried() -> None:
    engine = DownEngine()
    running = asyncio.create_task(Dispatcher(engine, None, poll_s=0.01).run())  # type: ignore[arg-type]
    await asyncio.sleep(0.3)
    try:
        assert not running.done(), running.exception() if running.done() else None
        assert engine.connects > 1
    finally:
        running.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await running

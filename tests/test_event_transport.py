"""`wait_set` keeps a cancellation that arrives as its event is set (the Phase 2
load benchmark found a follower that could not be stopped: Python 3.11's
`asyncio.wait_for` loses such a cancellation)."""

from __future__ import annotations

import asyncio

import pytest

from common.events.transport import wait_set


async def test_a_cancel_in_the_same_step_as_the_event_is_kept() -> None:
    event = asyncio.Event()
    waiter = asyncio.create_task(wait_set(event, 5))
    await asyncio.sleep(0)  # the waiter is now waiting on the event
    event.set()
    waiter.cancel()  # in the same step: wait_for would return normally here
    with pytest.raises(asyncio.CancelledError):
        await waiter


async def test_it_returns_whether_the_event_was_set() -> None:
    event = asyncio.Event()
    assert await wait_set(event, 0.01) is False
    event.set()
    assert await wait_set(event, 0.01) is True

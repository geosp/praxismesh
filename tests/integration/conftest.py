"""Session-wide checks for the integration suite."""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from tests.support.history_guard import LIMIT_BYTES, check_since
from tests.support.stack import temporal_client


@pytest.fixture(scope="session", autouse=True)
def history_payload_guard() -> Iterator[None]:
    """After the suite, fail if any Workflow it started carries a payload over
    64 KiB in its history (Phase 3A persistence plan R18, D9)."""
    # Visibility stores StartTime in whole seconds or coarser; start a bit early.
    since = datetime.now(UTC) - timedelta(seconds=5)
    yield

    async def check() -> list[str]:
        try:
            client = await temporal_client()
        except RuntimeError as e:  # the tests that needed Temporal failed already
            warnings.warn(f"history payload guard skipped: {e}", stacklevel=1)
            return []
        await asyncio.sleep(2)  # visibility lags behind the last starts
        return [
            f"{p.workflow_id} event {p.event_id} ({p.event_type}): {p.size} bytes"
            for p in await check_since(client, since)
        ]

    large = asyncio.run(check())
    if large:
        pytest.fail(
            f"{len(large)} history payload(s) over {LIMIT_BYTES} bytes:\n" + "\n".join(large),
            pytrace=False,
        )

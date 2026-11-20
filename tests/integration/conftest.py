"""Session-wide checks for the integration suite."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from tests.support.history_guard import guard_failure
from tests.support.stack import temporal_client


@pytest.fixture(scope="session", autouse=True)
def history_payload_guard() -> Iterator[None]:
    """After the suite, fail if any Workflow it started carries a payload over
    64 KiB in its history, or if Temporal cannot be reached to check (Phase 3A
    persistence plan R18, D9; review F84)."""
    # Visibility stores StartTime in whole seconds or coarser; start a bit early.
    since = datetime.now(UTC) - timedelta(seconds=5)
    yield
    failure = asyncio.run(guard_failure(since, connect=temporal_client))
    if failure:
        pytest.fail(failure, pytrace=False)

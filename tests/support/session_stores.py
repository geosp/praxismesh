"""An in-memory `SessionStore` for unit tests that need no database."""

from __future__ import annotations

from typing import Any

from agents import SQLiteSession

from common.persistence.repositories import Checkpoint
from harness_activity.session_store import SessionSnapshot, SessionStore


class MemorySessionStore:
    def __init__(self, task_id: str, engine: object = None) -> None:
        self._session = SQLiteSession(task_id)

    @property
    def session(self) -> SQLiteSession:
        return self._session

    async def load(self, checkpoint: Checkpoint | None) -> None:
        if checkpoint is None:
            await self._session.clear_session()
            return
        items = await self._session.get_items()
        for _ in range(len(items) - checkpoint.session_position):
            await self._session.pop_item()

    async def capture(self) -> SessionSnapshot:
        return SessionSnapshot(position=len(await self._session.get_items()))


async def store_contract(store: SessionStore) -> None:
    """Load, truncate and capture behave as run_harness_turn relies on (D1, R3)."""
    from datetime import UTC, datetime

    from common.schemas import BlobRef

    def at(position: int) -> Checkpoint:
        ref = BlobRef(
            id="r",
            key="k",
            checksum="sha256:" + "0" * 64,
            content_type="x",
            bytes=0,
            retention_class="task",
            created_at=datetime.now(UTC),
        )
        return Checkpoint("c", "t", 1, 1, 0, "t", position, ref, None)

    await store.load(None)
    assert (await store.capture()).position == 0
    items: list[Any] = [{"role": "user", "content": str(i)} for i in range(3)]
    await store.session.add_items(items)
    assert (await store.capture()).position == 3
    await store.load(at(1))  # a resume truncates
    snapshot = await store.capture()
    assert snapshot.position == 1 and snapshot.session_ref is None
    await store.load(None)
    assert (await store.capture()).position == 0

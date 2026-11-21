"""Session store: the seam between run_harness_turn and a runner's session state.

The Activity loads, truncates and captures a turn's conversation only through
this interface, and commits each capture through the fenced checkpoint insert
(plan 2026-11-15-dsh-production-harness, D1, D10). `openai_agents` keeps its
conversation in `SQLAlchemySession`; a DSH store keeps its session files as a
separate blob and returns its reference in the snapshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from agents.memory import Session
from sqlalchemy.ext.asyncio import AsyncEngine

from common.persistence.fence import refuse_if_deleted
from common.persistence.repositories import Checkpoint
from common.schemas import BlobRef

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionSnapshot:
    """What a checkpoint records about the session at capture time."""

    position: int
    session_ref: BlobRef | None = None  # DSH: the session blob (D1)
    session_digest: str | None = None


class SessionStore(Protocol):
    @property
    def session(self) -> Session:
        """What the runner reads and appends to."""
        ...

    async def load(self, checkpoint: Checkpoint | None) -> None:
        """Restore the session a checkpoint recorded (truncating anything after it),
        or start from empty when there is no checkpoint."""

    async def capture(self) -> SessionSnapshot:
        """Describe the session now, for the next fenced checkpoint."""


class FencedSQLAlchemySession(SQLAlchemySession):
    """`SQLAlchemySession` that adds no item once the task's request is deleted
    (Phase 3A persistence plan R25, review F117). The task lock is held across
    the SDK's own insert: a delete that commits first is refused here, and one
    that starts meanwhile finds the lock taken, retries, and redacts the item."""

    def __init__(self, task_id: str, *, engine: AsyncEngine) -> None:
        super().__init__(task_id, engine=engine)
        self._task_id, self._engine = task_id, engine

    async def add_items(self, items: list[Any]) -> None:
        async with self._engine.begin() as conn:
            await refuse_if_deleted(conn, self._task_id)
            await super().add_items(items)  # on the SDK's own connection


class SQLAlchemySessionStore:
    def __init__(self, task_id: str, engine: AsyncEngine) -> None:
        self._session = FencedSQLAlchemySession(task_id, engine=engine)

    @property
    def session(self) -> SQLAlchemySession:
        return self._session

    async def load(self, checkpoint: Checkpoint | None) -> None:
        if checkpoint is None:
            await self._session.clear_session()
            return
        items = await self._session.get_items()
        if len(items) < checkpoint.session_position:
            log.warning(
                "session shorter than its checkpoint",
                extra={"fields": {"items": len(items), "position": checkpoint.session_position}},
            )
        for _ in range(len(items) - checkpoint.session_position):
            await self._session.pop_item()

    async def capture(self) -> SessionSnapshot:
        return SessionSnapshot(position=len(await self._session.get_items()))

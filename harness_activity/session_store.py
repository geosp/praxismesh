"""Session store: the seam between run_harness_turn and a runner's session state.

The Activity loads, truncates and captures a turn's conversation only through
this interface (plan 2026-11-15-dsh-production-harness, D1). `openai_agents`
keeps its conversation in `SQLAlchemySession`; a DSH store will keep its session
files as a separate blob.
"""

from __future__ import annotations

import logging
from typing import Protocol

from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from agents.memory import Session
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)


class SessionStore(Protocol):
    @property
    def session(self) -> Session:
        """What the runner reads and appends to."""
        ...

    async def restore(self, position: int) -> None:
        """Truncate the session back to a checkpoint's position."""

    async def reset(self) -> None:
        """Start the turn's conversation from empty."""

    async def position(self) -> int:
        """The position a checkpoint taken now would record."""


class SQLAlchemySessionStore:
    def __init__(self, task_id: str, engine: AsyncEngine) -> None:
        self._session = SQLAlchemySession(task_id, engine=engine)

    @property
    def session(self) -> SQLAlchemySession:
        return self._session

    async def restore(self, position: int) -> None:
        items = await self._session.get_items()
        if len(items) < position:
            log.warning(
                "session shorter than its checkpoint",
                extra={"fields": {"items": len(items), "position": position}},
            )
        for _ in range(len(items) - position):
            await self._session.pop_item()

    async def reset(self) -> None:
        await self._session.clear_session()

    async def position(self) -> int:
        return len(await self._session.get_items())

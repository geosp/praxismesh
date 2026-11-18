"""The `praxis_comms` role (Phase 2 messaging D13, migration 0006): it may write
the message tables and read tasks, and nothing else. Needs PRAXIS_COMMS_DB_URL and a
database whose role was created by infra/db/roles.sh."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.integration


@pytest.fixture
async def comms() -> AsyncIterator[AsyncEngine]:
    url = os.environ.get("PRAXIS_COMMS_DB_URL")
    if not url:
        pytest.fail("PRAXIS_COMMS_DB_URL is not set (infra/.env.example)")
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


async def test_the_comms_role_writes_messages_and_reads_tasks(comms: AsyncEngine) -> None:
    key = uuid.uuid4().hex
    async with comms.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO task_messages (message_id, request_id, sender_task, recipient_task, "
                "kind, status, body, idempotency_key) "
                "VALUES (:k, 'req', 'task-a', 'task-b', 'send', 'pending', 'hi', :k)"
            ),
            {"k": key},
        )
        await conn.execute(
            text(
                "INSERT INTO message_wakes (recipient_workflow) VALUES (:k) ON CONFLICT DO NOTHING"
            ),
            {"k": key},
        )
        await conn.execute(text("SELECT count(*) FROM tasks"))
        await conn.execute(text("SELECT count(*) FROM task_inbox"))


async def test_the_comms_role_cannot_write_tasks(comms: AsyncEngine) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with comms.begin() as conn:
            await conn.execute(text("UPDATE tasks SET status = 'failed' WHERE false"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with comms.begin() as conn:
            await conn.execute(text("SELECT count(*) FROM checkpoints"))

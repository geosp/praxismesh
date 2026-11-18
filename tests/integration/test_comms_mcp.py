"""The comms MCP server through an MCP client (Phase 2 messaging task 3.1; R26).

Starts `python -m comms_mcp` over stdio with the identity a worker gives it, and
calls each tool. Needs the stack's database with the praxis_comms role and
PRAXIS_COMMS_DB_URL.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.persistence.repositories import AttemptRepository, TaskRepository, make_engine
from common.schemas import BlobRef, TaskStart
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


async def task(engine: AsyncEngine, request: str) -> str:
    task_id = f"task-mcp-{run_id()}"
    ref = BlobRef(
        id=f"blob:{0:064x}", key=f"sha256/{0:064x}", checksum=f"sha256:{0:064x}",
        content_type="text/plain", bytes=1, retention_class="task", created_at=datetime.now(UTC),
    )  # fmt: skip
    start = TaskStart(task_id=task_id, request_id=request, profile="dsh", template="local-dsh",
                      instructions_ref=ref)  # fmt: skip
    await TaskRepository(engine).record_task(
        start, workflow_id=task_id, run_id="run-1", template_version=1, template_hash="x"
    )
    await AttemptRepository(engine).start(task_id, 1, 1, "worker")
    return task_id


@asynccontextmanager
async def comms(task_id: str, max_ask_wait: int = 600) -> AsyncIterator[ClientSession]:
    url = os.environ.get("PRAXIS_COMMS_DB_URL")
    if not url:
        pytest.fail("PRAXIS_COMMS_DB_URL is not set (infra/.env.example)")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(ROOT),
        "PRAXIS_COMMS_DB_URL": url,
        "PRAXIS_TASK_ID": task_id,
        "PRAXIS_TURN": "1",
        "PRAXIS_ATTEMPT": "1",
        "PRAXIS_MAX_ASK_WAIT": str(max_ask_wait),
    }
    params = StdioServerParameters(command=sys.executable, args=["-m", "comms_mcp"], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


async def call(session: ClientSession, tool: str, **arguments: Any) -> tuple[bool, Any]:
    result = await session.call_tool(tool, arguments)
    body = result.content[0].text if result.content else ""  # type: ignore[union-attr]
    if result.is_error:
        return False, body
    return True, json.loads(body)


async def test_each_tool_through_the_client(engine: AsyncEngine) -> None:
    request = f"req-{uuid.uuid4().hex[:8]}"
    a, b = await task(engine, request), await task(engine, request)
    async with comms(a, max_ask_wait=60) as session:
        names = {t.name for t in (await session.list_tools()).tools}
        assert names == {"send_to_agent", "ask_agent", "post_status", "get_task_context"}
        ok, sent = await call(session, "send_to_agent", task_id=b, text="hello")
        assert ok and sent["message_id"]
        ok, asked = await call(
            session, "ask_agent", task_id=b, text="price?", deadline_seconds=3600
        )
        assert ok and asked["correlation_id"] and "waiting" in asked["next"]
        deadline = datetime.fromisoformat(asked["deadline"])
        assert (deadline - datetime.now(UTC)).total_seconds() < 65  # capped at 60 s
        ok, status = await call(session, "post_status", stage="working", progress=40)
        assert ok and status == {"stage": "working", "progress": 40}
        ok, _ = await call(session, "post_status", stage="working", progress=140)
        assert not ok
        ok, context = await call(session, "get_task_context")
        assert ok and context["you"] == a and {t["task_id"] for t in context["tasks"]} == {a, b}


async def test_a_cross_request_send_is_refused(engine: AsyncEngine) -> None:
    a = await task(engine, f"req-{uuid.uuid4().hex[:8]}")
    outsider = await task(engine, f"req-{uuid.uuid4().hex[:8]}")
    async with comms(a) as session:
        ok, error = await call(session, "send_to_agent", task_id=outsider, text="hello")
    assert not ok and "not a task of this request" in error


async def test_the_sender_is_always_the_calling_task(engine: AsyncEngine) -> None:
    """R26: an argument naming another sender cannot make a message come from it."""
    request = f"req-{uuid.uuid4().hex[:8]}"
    a, b = await task(engine, request), await task(engine, request)
    async with comms(a) as session:
        await call(session, "send_to_agent", task_id=b, text="from a", sender=b)
    async with engine.connect() as conn:
        senders = {r[0] for r in await conn.execute(
            text("SELECT sender_task FROM task_messages WHERE recipient_task = :b"), {"b": b}
        )}  # fmt: skip
    assert senders <= {a}


async def test_a_send_wakes_a_sleeping_recipient_as_the_comms_role(engine: AsyncEngine) -> None:
    """D6 through the role comms_mcp uses: the wake row's ON CONFLICT needs its grants."""
    from common.persistence.messages import MessageRepository

    request = f"req-{uuid.uuid4().hex[:8]}"
    a, b = await task(engine, request), await task(engine, request)
    assert (await MessageRepository(engine).claim(b, 2, datetime.now(UTC))).count == 0  # B sleeps
    async with comms(a) as session:
        ok, _ = await call(session, "send_to_agent", task_id=b, text="wake up")
    assert ok
    async with engine.connect() as conn:
        woken = (await conn.execute(
            text("SELECT count(*) FROM message_wakes WHERE recipient_workflow = :b"), {"b": b}
        )).scalar_one()  # fmt: skip
    assert woken == 1

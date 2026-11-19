"""The dispatcher against the stack's database and Temporal (Phase 2 messaging task
4.5; D6, R14): a wake row becomes an `inbox` Signal; with the dispatcher stopped the
row waits, and a restarted dispatcher delivers it; a wake for a closed Workflow is
deleted and logged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from common.persistence.repositories import make_engine
from orchestrator.dispatcher import Dispatcher
from tests.support.stack import temporal_client

pytestmark = pytest.mark.integration
QUEUE = f"dispatcher-test-{uuid.uuid4().hex[:8]}"


@workflow.defn(name="InboxProbe")
class InboxProbe:
    def __init__(self) -> None:
        self.signals = 0

    @workflow.signal(name="inbox")
    def inbox(self) -> None:
        self.signals += 1

    @workflow.query
    def count(self) -> int:
        return self.signals

    @workflow.run
    async def run(self) -> None:
        await workflow.wait_condition(lambda: self.signals >= 1, timeout=timedelta(minutes=5))


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


async def wake(engine: AsyncEngine, workflow_id: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO message_wakes (recipient_workflow) VALUES (:w)"), {"w": workflow_id}
        )
        await conn.execute(text("SELECT pg_notify('message_wakes', :w)"), {"w": workflow_id})


async def pending(engine: AsyncEngine, workflow_id: str) -> int:
    async with engine.connect() as conn:
        return int(
            (
                await conn.execute(
                    text("SELECT count(*) FROM message_wakes WHERE recipient_workflow = :w"),
                    {"w": workflow_id},
                )
            ).scalar_one()
        )


async def eventually(check: object, timeout_s: float = 15.0) -> None:
    async def poll() -> None:
        while not await check():  # type: ignore[operator]
            await asyncio.sleep(0.1)

    await asyncio.wait_for(poll(), timeout_s)


async def test_a_wake_waits_for_a_stopped_dispatcher_and_is_then_delivered(
    engine: AsyncEngine,
) -> None:
    client: Client = await temporal_client()
    workflow_id = f"inbox-probe-{uuid.uuid4().hex[:8]}"
    # The probe lives beside database code the sandbox will not import.
    async with Worker(
        client,
        task_queue=QUEUE,
        workflows=[InboxProbe],
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        handle = await client.start_workflow(InboxProbe.run, id=workflow_id, task_queue=QUEUE)
        await wake(engine, workflow_id)  # the dispatcher is not running yet
        await asyncio.sleep(1.5)
        assert await pending(engine, workflow_id) == 1
        assert await handle.query(InboxProbe.count) == 0
        dispatching = asyncio.create_task(Dispatcher(engine, client, poll_s=0.5).run())
        try:

            async def delivered() -> bool:
                return await pending(engine, workflow_id) == 0

            await eventually(delivered)
            await handle.result()
        finally:
            dispatching.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await dispatching


async def test_a_wake_for_a_closed_workflow_is_deleted_and_logged(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    client: Client = await temporal_client()
    closed = f"inbox-closed-{uuid.uuid4().hex[:8]}"  # never started: not found
    await wake(engine, closed)
    with caplog.at_level(logging.INFO, logger="praxis.dispatcher"):
        deleted = await Dispatcher(engine, client).drain()
    assert deleted >= 1 and await pending(engine, closed) == 0
    assert any("closed workflow" in r.getMessage() for r in caplog.records)

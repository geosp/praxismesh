"""Shared pieces of the messaging acceptance tests (Phase 2 messaging phase 03):
the orchestrator with its dispatcher and a `local-dsh` worker in this process,
task submission into one request, and the request's message rows."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from temporalio.client import Client, WorkflowHandle

import workers.main
from common.blob_store.s3 import S3BlobStore
from common.observability import disable_sdk_tracing
from common.persistence.repositories import RecordingBlobStore, make_engine
from common.schemas import TaskResult, TaskStart
from orchestrator.dispatcher import Dispatcher
from orchestrator.submit import prepare_task, start_task
from registry.loader import Registry
from tests.support.dsh import DshContainer
from tests.support.stack import run_id

RESULT_TIMEOUT_S = 300


def finish(status: str, summary: str) -> dict[str, Any]:
    return {"tool": "finish_task", "args": {"status": status, "summary": summary}}


@asynccontextmanager
async def stack(
    registry: Registry, container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client]:
    """The orchestrator worker with its dispatcher, and a `local-dsh` worker, as
    `workers.main` builds them, on queues of their own."""
    monkeypatch.setattr(workers.main, "load_registry", lambda: registry)
    monkeypatch.setenv("PRAXIS_QUEUE_PREFIX", f"agents-{run_id()}.")
    monkeypatch.setenv("DSH_CONTROL", str(container.control))
    disable_sdk_tracing()
    client = await workers.main.connect("praxis-test")
    orchestrator = await workers.main.build_worker(client, "orchestrator", None)
    worker = await workers.main.build_worker(client, "template", "local-dsh")
    engine = make_engine()
    dispatching = asyncio.create_task(Dispatcher(engine, client, poll_s=0.5).run())
    try:
        async with orchestrator, worker:
            yield client
    finally:
        dispatching.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dispatching
        await engine.dispose()


async def submit(
    client: Client, registry: Registry, instructions: str, join: str | None = None
) -> tuple[TaskStart, WorkflowHandle[Any, Any]]:
    engine = make_engine()
    try:
        s3 = S3BlobStore.from_env()
        await s3.ensure_bucket()
        request: dict[str, Any] = {"profile": "dsh", "instructions": instructions}
        if join is not None:
            request["join_request"] = join
        start = await prepare_task(
            request, registry, RecordingBlobStore(s3, engine), base_dir=Path.cwd()
        )
    finally:
        await engine.dispose()
    return start, await start_task(client, start)


async def result_of(handle: WorkflowHandle[Any, Any]) -> TaskResult:
    return TaskResult.model_validate(await asyncio.wait_for(handle.result(), RESULT_TIMEOUT_S))


async def messages(request_id: str) -> list[tuple[Any, ...]]:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT sender_task, recipient_task, kind, status, body FROM task_messages "
                    "WHERE request_id = :r ORDER BY created_at"
                ),
                {"r": request_id},
            )
            return [tuple(r) for r in rows]
    finally:
        await engine.dispose()


async def query(sql: str, **params: Any) -> list[tuple[Any, ...]]:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return [tuple(r) for r in await conn.execute(text(sql), params)]
    finally:
        await engine.dispose()


async def eventually(check: Any, what: str, timeout_s: float = 120) -> None:
    for _ in range(int(timeout_s * 4)):
        if await check():
            return
        await asyncio.sleep(0.25)
    raise AssertionError(f"timed out waiting for {what}")


async def sleeping(task_id: str) -> bool:
    rows = await query("SELECT sleeping FROM task_inbox WHERE task_id = :t", t=task_id)
    return bool(rows and rows[0][0])


async def inbox_signals(client: Client, task_id: str) -> int:
    """`inbox` Signals in the task's current Workflow run."""
    from temporalio.api.enums.v1 import EventType

    history = await client.get_workflow_handle(task_id).fetch_history()
    return sum(
        1
        for e in history.events
        if e.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED
        and e.workflow_execution_signaled_event_attributes.signal_name == "inbox"
    )


async def correlation_id(asker: str) -> str:
    rows = await query(
        "SELECT correlation_id FROM task_messages WHERE sender_task = :t AND kind = 'ask'",
        t=asker,
    )
    return str(rows[0][0])

"""Two agents talking (Phase 2 messaging task 1.2 of phase 03; R14, R16).

Two `dsh` tasks in one request run through `TaskWorkflow` on the local stack: the
orchestrator (with its dispatcher) and a `local-dsh` template worker built by
`workers.main`, a real DSH container, and the fake model with one script per
agent (D16). B starts waiting. A asks B and waits. B is woken by the question and
replies; A is woken by the reply and finishes with the answer.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Iterator
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
from registry.loader import Registry, load_registry
from tests.support.dsh import DshContainer, build_image, make_dsh_registry, start_container
from tests.support.fake_model import FakeModel
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
PRICE = "12.50"
RESULT_TIMEOUT_S = 300


def finish(status: str, summary: str) -> dict[str, Any]:
    return {"tool": "finish_task", "args": {"status": status, "summary": summary}}


SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "default": [finish("done", "no script")],
    "asker": [
        {"tool": "ask_agent", "args": {"task_id": "${input:ask task (\\S+)}",
                                       "text": "What is the price?", "deadline_seconds": 600}},
        finish("waiting", "asked for the price"),
        finish("done", "${input:Reply from \\S+ to your question \\S+: ([^\\n]*)}"),
    ],
    "answerer": [
        finish("waiting", "waiting for questions"),
        {"tool": "send_to_agent", "args": {"task_id": "${input:Question \\S+ from (\\S+)}",
                                           "text": PRICE,
                                           "reply_to": "${input:Question (\\S+) from}"}},
        finish("done", "answered"),
    ],
}  # fmt: skip


@pytest.fixture(scope="module")
def container() -> Iterator[DshContainer]:
    found = start_container(build_image())
    try:
        yield found
    finally:
        found.stop()


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


async def test_a_asks_b_and_resumes_with_the_answer(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = load_registry(
        make_dsh_registry(tmp_path / "registry", heartbeat_timeout="PT5S", turn_timeout="PT2M")
    )
    with FakeModel(SCRIPTS) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, container, monkeypatch) as client:
            b, b_handle = await submit(
                client, registry, "[script:answerer] Answer price questions."
            )
            a, a_handle = await submit(
                client, registry, f"[script:asker] Please ask task {b.task_id} for the price.",
                join=b.request_id,
            )  # fmt: skip
            a_result, b_result = await asyncio.gather(result_of(a_handle), result_of(b_handle))

    assert a.request_id == b.request_id
    # R16: A resumed with B's answer; R14: B slept until the question woke it.
    assert (a_result.status, a_result.summary) == ("succeeded", PRICE)
    assert (b_result.status, b_result.summary) == ("succeeded", "answered")
    assert a_result.turns == 2 and b_result.turns == 2
    assert await messages(a.request_id) == [
        (a.task_id, b.task_id, "ask", "answered", "What is the price?"),
        (b.task_id, a.task_id, "reply", "read", PRICE),
    ]

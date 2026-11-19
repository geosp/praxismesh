"""How tasks end with messages in flight (Phase 2 messaging phase 03, task 1.4;
R19, R30), on the local stack with real DSH containers and the fake model's
per-agent scripts (D16)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from temporalio.client import Client

import workers.main
from common.observability import disable_sdk_tracing
from common.persistence.repositories import make_engine
from orchestrator.dispatcher import Dispatcher
from registry.loader import Registry, load_registry
from tests.support.agents import eventually, finish, messages, result_of, stack, submit
from tests.support.dsh import DshContainer, build_image, make_dsh_registry, start_container
from tests.support.fake_model import FakeModel, text_of
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
PRICE = "12.50"
REPLY = "${input:Reply from \\S+ to your question \\S+: ([^\\n]*)}"
SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "default": [finish("done", "no script")],
    # R19: finish_task("done") with the question open is refused; the model waits.
    "eager": [
        {"tool": "ask_agent", "args": {"task_id": "${input:ask task (\\S+)}", "text": "price?"}},
        finish("done", "finished too early"),
        finish("waiting", "asked"),
        finish("done", REPLY),
    ],
    "answerer": [
        finish("waiting", "waiting for questions"),
        {"tool": "send_to_agent", "args": {"task_id": "${input:Question \\S+ from (\\S+)}",
                                           "text": PRICE,
                                           "reply_to": "${input:Question (\\S+) from}"}},
        finish("done", "answered"),
    ],
    # R30: B works on and ends `done`; a message sent meanwhile is never read.
    "busy": [
        {"tool": "run_command", "args": {"command": "sh -c 'sleep 10'"}},
        finish("done", "ended"),
    ],
    "late": [
        {"tool": "send_to_agent", "args": {"task_id": "${input:tell task (\\S+)}",
                                           "text": "too late"}},
        {"tool": "run_command", "args": {"command": "sh -c 'sleep 20'"}},
        {"tool": "get_task_context", "args": {}},
        finish("done", "${result.2.undelivered.0.recipient_task}"),
    ],
}  # fmt: skip


@pytest.fixture(scope="module")
def containers() -> Iterator[tuple[DshContainer, DshContainer]]:
    image = build_image()
    first = start_container(image)
    try:
        second = start_container(image)
        try:
            yield first, second
        finally:
            second.stop()
    finally:
        first.stop()


def registry_in(tmp_path: Path) -> Registry:
    return load_registry(
        make_dsh_registry(tmp_path / "registry", heartbeat_timeout="PT5S", turn_timeout="PT2M")
    )


@asynccontextmanager
async def two_workers(
    registry: Registry,
    containers: tuple[DshContainer, DshContainer],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Client]:
    """The orchestrator with its dispatcher and two `local-dsh` workers, one per DSH
    container, so two tasks' turns run at the same time."""
    monkeypatch.setattr(workers.main, "load_registry", lambda: registry)
    monkeypatch.setenv("PRAXIS_QUEUE_PREFIX", f"endings-{run_id()}.")
    disable_sdk_tracing()
    client = await workers.main.connect("praxis-test")
    orchestrator = await workers.main.build_worker(client, "orchestrator", None)
    built = []
    for container in containers:
        # One worker per client and queue: each worker gets its own client.
        own = await workers.main.connect("praxis-test")
        monkeypatch.setenv("DSH_CONTROL", str(container.control))
        built.append(await workers.main.build_worker(own, "template", "local-dsh"))
    engine = make_engine()
    dispatching = asyncio.create_task(Dispatcher(engine, client, poll_s=0.5).run())
    try:
        async with orchestrator, built[0], built[1]:
            yield client
    finally:
        dispatching.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await dispatching
        await engine.dispose()


async def test_done_with_an_open_question_is_refused_and_the_task_waits(
    containers: tuple[DshContainer, DshContainer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R19: A's finish_task("done") is refused while its question is open; A then
    waits, is woken by B's reply and finishes with it."""
    registry = registry_in(tmp_path)
    with FakeModel(SCRIPTS) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, containers[0], monkeypatch) as client:
            b, b_handle = await submit(
                client, registry, "[script:answerer] Answer price questions."
            )
            a, a_handle = await submit(
                client, registry, f"[script:eager] Please ask task {b.task_id} for the price.",
                join=b.request_id,
            )  # fmt: skip
            a_result, b_result = await asyncio.gather(result_of(a_handle), result_of(b_handle))
        told = [
            text_of(m) for request in fake.state.requests for m in request["messages"]
            if m.get("role") == "tool" and "cannot finish while" in text_of(m)
        ]  # fmt: skip

    assert told and "open question" in told[0]
    assert (a_result.status, a_result.summary, a_result.turns) == ("succeeded", PRICE, 2)
    assert b_result.status == "succeeded"
    assert [(m[2], m[3]) for m in await messages(a.request_id)] == [
        ("ask", "answered"),
        ("reply", "read"),
    ]


async def test_an_unread_message_to_an_ended_task_is_listed_as_undelivered(
    containers: tuple[DshContainer, DshContainer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R30: B ends `done` without reading A's message; A's get_task_context lists
    it as undelivered."""
    registry = registry_in(tmp_path)
    with FakeModel(SCRIPTS) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with two_workers(registry, containers, monkeypatch) as client:
            b, b_handle = await submit(client, registry, "[script:busy] Work for a while.")

            async def b_is_working() -> bool:  # B's command step was served
                return any("[script:busy]" in str(r["messages"]) for r in fake.state.requests)

            await eventually(b_is_working, "B's turn to start")
            a, a_handle = await submit(
                client, registry, f"[script:late] Please tell task {b.task_id} something.",
                join=b.request_id,
            )  # fmt: skip
            a_result, b_result = await asyncio.gather(result_of(a_handle), result_of(b_handle))

    assert (b_result.status, b_result.summary, b_result.turns) == ("succeeded", "ended", 1)
    assert (a_result.status, a_result.summary) == ("succeeded", b.task_id)
    assert [(m[2], m[3]) for m in await messages(a.request_id)] == [("send", "undelivered")]

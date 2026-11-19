"""Two agents talking (Phase 2 messaging task 1.2 of phase 03; R14, R16).

Two `dsh` tasks in one request run through `TaskWorkflow` on the local stack: the
orchestrator (with its dispatcher) and a `local-dsh` template worker built by
`workers.main`, a real DSH container, and the fake model with one script per
agent (D16). B starts waiting. A asks B and waits. B is woken by the question and
replies; A is woken by the reply and finishes with the answer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from registry.loader import load_registry
from tests.support.agents import (
    correlation_id,
    eventually,
    finish,
    inbox_signals,
    messages,
    result_of,
    sleeping,
    stack,
    submit,
)
from tests.support.dsh import DshContainer, build_image, make_dsh_registry, start_container
from tests.support.fake_model import FakeModel, text_of

pytestmark = pytest.mark.integration
PRICE = "12.50"


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

            async def b_asleep() -> bool:
                return await sleeping(b.task_id)

            await eventually(b_asleep, "B to wait")  # R14: B is waiting when A asks
            a, a_handle = await submit(
                client, registry, f"[script:asker] Please ask task {b.task_id} for the price.",
                join=b.request_id,
            )  # fmt: skip
            a_result, b_result = await asyncio.gather(result_of(a_handle), result_of(b_handle))
            b_signals = await inbox_signals(client, b.task_id)
        question = await correlation_id(a.task_id)
        # R16: A's woken turn was given the reply with its question's correlation ID.
        woken_inputs = [
            text_of(m) for r in fake.state.requests if "[script:asker]" in str(r["messages"])
            for m in r["messages"] if m.get("role") == "user" and "Reply from" in text_of(m)
        ]  # fmt: skip

    assert a.request_id == b.request_id
    assert b_signals >= 1  # R14: the question woke the sleeping B through an inbox Signal
    assert woken_inputs and f"your question {question}: {PRICE}" in woken_inputs[-1]
    # R16: A resumed with B's answer; R14: B slept until the question woke it.
    assert (a_result.status, a_result.summary) == ("succeeded", PRICE)
    assert (b_result.status, b_result.summary) == ("succeeded", "answered")
    assert a_result.turns == 2 and b_result.turns == 2
    assert await messages(a.request_id) == [
        (a.task_id, b.task_id, "ask", "answered", "What is the price?"),
        (b.task_id, a.task_id, "reply", "read", PRICE),
    ]

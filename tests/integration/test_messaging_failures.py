"""Messaging failure cases on the local stack (Phase 2 messaging phase 03, task
1.3; R10, R13, R17, R24).

Each case runs `dsh` tasks through `TaskWorkflow` with a real DSH container and the
fake model's per-agent scripts (D16). A "silent" task waits and never answers.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from temporalio.client import WorkflowFailureError, WorkflowHandle

import workers.main
from common.observability import disable_sdk_tracing
from registry.loader import Registry, load_registry
from tests.integration.test_dsh_outcomes import kill_proc, start_worker_proc
from tests.support.agents import (
    eventually,
    finish,
    messages,
    query,
    result_of,
    sleeping,
    stack,
    submit,
)
from tests.support.dsh import DshContainer, build_image, make_dsh_registry, start_container
from tests.support.fake_model import FakeModel, tool_results
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
ASK = {"tool": "ask_agent", "args": {"task_id": "${input:ask task (\\S+)}", "text": "price?",
                                     "deadline_seconds": "${input:within (\\d+) s}"}}  # fmt: skip
MESSAGE = "${input:Message from \\S+: ([^\\n]*)}"
TOLD = "${input:Your question \\S+ to \\S+: ([^\\n]*)}"
SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "default": [finish("done", "no script")],
    "silent": [finish("waiting", "waiting")],  # woken or not, it waits again
    "asker": [ASK, finish("waiting", "asked"), finish("done", TOLD)],
    "outsider": [
        {"tool": "send_to_agent", "args": {"task_id": "${input:tell task (\\S+)}", "text": "hi"}},
        finish("done", "tried"),
    ],
    # The send commits, then the step's command holds the attempt open: a kill
    # there loses the attempt before its next checkpoint, so the rerun repeats
    # the identical send (R13).
    "sender": [
        {"tools": [
            {"tool": "send_to_agent", "args": {"task_id": "${input:tell task (\\S+)}",
                                               "text": "exactly once"}},
            {"tool": "run_command", "args": {"command": "sh -c 'sleep 30'"}},
        ]},
        finish("done", "sent"),
    ],
    "reader": [finish("waiting", "waiting"), finish("done", MESSAGE)],
}  # fmt: skip


@pytest.fixture(scope="module")
def container() -> Iterator[DshContainer]:
    found = start_container(build_image())
    try:
        yield found
    finally:
        found.stop()


def registry_in(tmp_path: Path) -> Path:
    return make_dsh_registry(tmp_path / "registry", heartbeat_timeout="PT5S", turn_timeout="PT2M")


async def cancelled(handle: WorkflowHandle[Any, Any]) -> None:
    await handle.cancel()
    with contextlib.suppress(WorkflowFailureError):
        await asyncio.wait_for(handle.result(), 60)


async def test_an_unanswered_question_times_out(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R17: no reply by the deadline; the asker is woken and told."""
    registry = load_registry(registry_in(tmp_path))
    with FakeModel(SCRIPTS) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, container, monkeypatch) as client:
            b, b_handle = await submit(client, registry, "[script:silent] Never answer.")
            a, a_handle = await submit(
                client, registry, f"[script:asker] Please ask task {b.task_id} within 3 s.",
                join=b.request_id,
            )  # fmt: skip
            a_result = await result_of(a_handle)
            await cancelled(b_handle)

    assert (a_result.status, a_result.summary) == ("succeeded", "no answer came by the deadline.")
    assert [(m[2], m[3]) for m in await messages(a.request_id)] == [("ask", "expired")]


async def test_a_cross_request_message_is_refused(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R10: a task of another request is not reachable; the refusal is recorded."""
    registry = load_registry(registry_in(tmp_path))
    with FakeModel(SCRIPTS) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, container, monkeypatch) as client:
            b, b_handle = await submit(client, registry, "[script:silent] Never answer.")
            a, a_handle = await submit(
                client, registry, f"[script:outsider] Please tell task {b.task_id} hi."
            )
            a_result = await result_of(a_handle)
            await cancelled(b_handle)
        refusals = [
            r for request in fake.state.requests for m in request["messages"]
            if m.get("role") == "tool" and "not a task of this request" in str(m.get("content"))
            for r in [m]
        ]  # fmt: skip

    assert a.request_id != b.request_id and a_result.status == "succeeded"
    assert refusals, "the model was told why the send was refused"
    rows = await query(
        "SELECT recipient_task, status, reason FROM task_messages WHERE sender_task = :t",
        t=a.task_id,
    )
    assert len(rows) == 1 and rows[0][:2] == (b.task_id, "rejected")
    assert "not a task of this request" in rows[0][2]
    assert await messages(b.request_id) == []  # B's request has no message


async def test_a_cancelled_recipient_tells_the_waiting_asker(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R24: B ends while A waits on its question; A is woken and told."""
    registry = load_registry(registry_in(tmp_path))
    with FakeModel(SCRIPTS) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, container, monkeypatch) as client:
            b, b_handle = await submit(client, registry, "[script:silent] Never answer.")
            a, a_handle = await submit(
                client, registry, f"[script:asker] Please ask task {b.task_id} within 600 s.",
                join=b.request_id,
            )  # fmt: skip

            async def both_asleep_with_the_question() -> bool:
                rows = await messages(a.request_id)
                return bool(rows) and await sleeping(a.task_id) and await sleeping(b.task_id)

            await eventually(both_asleep_with_the_question, "A waiting on its question to B")
            await cancelled(b_handle)
            a_result = await result_of(a_handle)

    told = "it was cancelled: the other task ended without replying."
    assert (a_result.status, a_result.summary) == ("succeeded", told)
    assert [(m[2], m[3]) for m in await messages(a.request_id)] == [("ask", "cancelled")]


async def test_a_send_before_a_killed_worker_is_delivered_once(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R13: A's send commits, then its worker is SIGKILLed before the turn's next
    checkpoint. The rerun repeats the identical send; B gets one message."""
    reg_dir = registry_in(tmp_path)
    registry: Registry = load_registry(reg_dir)
    prefix = f"agents-kill-{run_id()}."
    monkeypatch.setenv("PRAXIS_QUEUE_PREFIX", prefix)
    with FakeModel(SCRIPTS) as fake:
        env = {**os.environ, "PRAXIS_REGISTRY": str(reg_dir), "VLLM_BASE_URL": fake.base_url,
               "DSH_CONTROL": str(container.control), "LOG_LEVEL": "INFO"}  # fmt: skip
        env.pop("METRICS_PORT", None)
        procs = tmp_path / "procs"
        orch = start_worker_proc(procs, "orchestrator", env, "orchestrator")
        worker_a = start_worker_proc(procs, "worker-a", env, "template", "local-dsh")
        worker_b = None
        try:
            await asyncio.sleep(2.5)
            for name, p in (("orchestrator", orch), ("worker-a", worker_a)):
                if p.poll() is not None:
                    log = (procs / f"{name}.log").read_text()[-2000:]
                    raise RuntimeError(f"{name} exited early:\n{log}")
            disable_sdk_tracing()
            client = await workers.main.connect("praxis-test")
            b, b_handle = await submit(client, registry, "[script:reader] Read your messages.")

            async def b_asleep() -> bool:
                return await sleeping(b.task_id)

            await eventually(b_asleep, "B to sleep")
            a, a_handle = await submit(
                client, registry, f"[script:sender] Please tell task {b.task_id} once.",
                join=b.request_id,
            )  # fmt: skip

            async def sent() -> bool:
                return bool(await messages(a.request_id))

            await eventually(sent, "A's send to commit")
            kill_proc(worker_a)  # during the step's `sleep 30`, before the next checkpoint
            worker_b = start_worker_proc(procs, "worker-b", env, "template", "local-dsh")
            a_result, b_result = await asyncio.gather(result_of(a_handle), result_of(b_handle))
        finally:
            for proc in (orch, worker_a, worker_b):
                if proc is not None and proc.poll() is None:
                    kill_proc(proc)
        # The model was asked for the sending step once per attempt.
        first_steps = sum(
            1 for request in fake.state.requests
            if "[script:sender]" in str(request["messages"])
            and tool_results(request["messages"]) == 0
        )  # fmt: skip

    assert (a_result.status, a_result.attempts) == ("succeeded", 2)
    attempts = await query(
        "SELECT attempt, outcome FROM task_attempts WHERE task_id = :t AND turn = 1 "
        "ORDER BY attempt",
        t=a.task_id,
    )
    assert attempts == [(1, "lost"), (2, "done")]
    assert first_steps == 2  # the rerun repeated the identical send
    rows = await messages(a.request_id)
    assert [(r[0], r[1], r[2], r[4]) for r in rows] == [
        (a.task_id, b.task_id, "send", "exactly once")
    ]
    assert (b_result.status, b_result.summary) == ("succeeded", "exactly once")

"""Waiting runs stay bounded (Phase 2 messaging phase 03, task 1.5; R33).

A `dsh` task B runs through `TaskWorkflow` on the local stack with a real DSH
container and the fake model (D16). The test itself is the other task of the
request, S: a recorded task with an attempt, sending through `MessageRepository`.
The registry is a copy whose `dsh` profile allows 200 wakes and whose `local-dsh`
template caps them at 200.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client

from common.persistence.messages import MessageRepository, Sender, idempotency_key
from common.persistence.repositories import AttemptRepository, TaskRepository, make_engine
from common.schemas import BlobRef, TaskStart
from registry.loader import Registry, load_registry
from registry.lock import update
from tests.support.agents import eventually, finish, query, result_of, sleeping, stack, submit
from tests.support.dsh import DshContainer, build_image, make_dsh_registry, start_container
from tests.support.fake_model import FakeModel
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
WAKES = 100
HISTORY_BOUND = 2000
REPLY = "${input:Reply from \\S+ to your question \\S+: ([^\\n]*)}"
SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "default": [finish("done", "no script")],
    # Ask S, then wait through every woken turn; the last step reads the reply.
    "patient": [
        {"tool": "ask_agent", "args": {"task_id": "${input:ask task (\\S+)}",
                                       "text": "tell me when", "deadline_seconds": 1800}},
        *[finish("waiting", f"waiting {n}") for n in range(WAKES + 1)],
        finish("done", REPLY),
    ],
    # Work through one turn while messages arrive, then read them all at once.
    "busy": [
        {"tool": "run_command", "args": {"command": "sh -c 'sleep 15'"}},
        finish("waiting", "worked"),
        finish("done", "${input:(\\d+) messages\\nContinue}"),  # the last one listed
    ],
}  # fmt: skip


@pytest.fixture(scope="module")
def container() -> Iterator[DshContainer]:
    found = start_container(build_image())
    try:
        yield found
    finally:
        found.stop()


def history_registry(tmp_path: Path) -> Registry:
    """The test profile and template (R33): 200 wakes, a 30-minute ask wait."""
    target = make_dsh_registry(
        tmp_path / "registry", heartbeat_timeout="PT5S", turn_timeout="PT2M", max_wakes_cap=200
    )
    profile = target / "profiles" / "dsh.yaml"
    data = yaml.safe_load(profile.read_text())
    profile.write_text(
        yaml.safe_dump({**data, "max_wakes": 200, "max_ask_wait": "PT30M"}, sort_keys=False)
    )
    (target / "registry.lock").unlink()
    assert update(target, check=False) == []
    return load_registry(target)


async def sender_in(request_id: str) -> Sender:
    """S: a task of B's request with an attempt, so its sends pass the fence."""
    task_id = f"task-s-{run_id()}"
    ref = BlobRef(
        id=f"blob:{0:064x}", key=f"sha256/{0:064x}", checksum=f"sha256:{0:064x}",
        content_type="text/plain", bytes=1, retention_class="task", created_at=datetime.now(UTC),
    )  # fmt: skip
    engine = make_engine()
    try:
        start = TaskStart(task_id=task_id, request_id=request_id, profile="dsh",
                          template="local-dsh", instructions_ref=ref)  # fmt: skip
        await TaskRepository(engine).record_task(
            start, workflow_id=task_id, run_id="run-1", template_version=1, template_hash="x"
        )
        await AttemptRepository(engine).start(task_id, 1, 1, "test")
    finally:
        await engine.dispose()
    return Sender(task_id, 1, 1)


async def runs(client: Client, workflow_id: str, first_run: str) -> list[tuple[str, int, int]]:
    """Each run of the Continue-As-New chain: its ID, events and `inbox` Signals."""
    found, run = [], first_run
    while run:
        history = await client.get_workflow_handle(workflow_id, run_id=run).fetch_history()
        signals = sum(
            1 for e in history.events
            if e.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_SIGNALED
            and e.workflow_execution_signaled_event_attributes.signal_name == "inbox"
        )  # fmt: skip
        found.append((run, len(history.events), signals))
        last = history.events[-1]
        run = (
            last.workflow_execution_continued_as_new_event_attributes.new_execution_run_id
            if last.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CONTINUED_AS_NEW
            else ""
        )
    return found


async def test_a_task_woken_100_times_keeps_every_run_bounded(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = history_registry(tmp_path)
    engine = make_engine()
    messages = MessageRepository(engine)
    try:
        with FakeModel(SCRIPTS) as fake:
            monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
            async with stack(registry, container, monkeypatch) as client:
                request = f"req-{run_id()}"
                s = await sender_in(request)
                b, b_handle = await submit(
                    client, registry, f"[script:patient] Please ask task {s.task_id} and wait.",
                    join=request,
                )  # fmt: skip

                async def b_asleep() -> bool:
                    return await sleeping(b.task_id)

                for n in range(WAKES):  # back to back: each send wakes B once
                    await eventually(b_asleep, f"B asleep before wake {n + 1}")
                    key = idempotency_key(s.task_id, 1, "send_to_agent", {"n": n})
                    assert (await messages.send(s, b.task_id, f"ping {n}", key=key)).ok

                    async def read(body: str = f"ping {n}") -> bool:  # this wake's turn read it
                        rows = await query(
                            "SELECT status FROM task_messages WHERE recipient_task = :t "
                            "AND body = :b",
                            t=b.task_id,
                            b=body,
                        )
                        return bool(rows) and rows[0][0] == "read"

                    await eventually(read, f"B woken by wake {n + 1}")
                await eventually(b_asleep, "B asleep after the last wake")
                question = await query(
                    "SELECT correlation_id FROM task_messages WHERE sender_task = :t "
                    "AND kind = 'ask'",
                    t=b.task_id,
                )
                key = idempotency_key(s.task_id, 1, "send_to_agent", {"reply": True})
                assert (
                    await messages.send(s, b.task_id, "now", key=key, reply_to=question[0][0])
                ).ok
                result = await result_of(b_handle)
                chain = await runs(client, b.task_id, b_handle.first_execution_run_id or "")
    finally:
        await engine.dispose()

    print("R33 runs (run id, events, inbox signals):", chain)
    assert (result.status, result.summary) == ("succeeded", "now")
    assert len(chain) >= 2  # the reply came after a new run started
    assert all(events < HISTORY_BOUND for _, events, _ in chain), chain
    assert sum(signals for *_, signals in chain) >= WAKES  # every wake was a Signal


async def test_50_messages_during_one_turn_bring_at_most_one_signal(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = history_registry(tmp_path)
    engine = make_engine()
    messages = MessageRepository(engine)
    try:
        with FakeModel(SCRIPTS) as fake:
            monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
            async with stack(registry, container, monkeypatch) as client:
                request = f"req-{run_id()}"
                s = await sender_in(request)
                b, b_handle = await submit(
                    client, registry, "[script:busy] Work, then read your messages.",
                    join=request,
                )  # fmt: skip

                async def b_is_working() -> bool:
                    return any("[script:busy]" in str(r["messages"]) for r in fake.state.requests)

                await eventually(b_is_working, "B's turn to start")
                for n in range(50):
                    key = idempotency_key(s.task_id, 1, "send_to_agent", {"n": n})
                    assert (await messages.send(s, b.task_id, f"{n + 1} messages", key=key)).ok
                result = await result_of(b_handle)
                chain = await runs(client, b.task_id, b_handle.first_execution_run_id or "")
    finally:
        await engine.dispose()

    print("R33 runs (run id, events, inbox signals):", chain)
    assert (result.status, result.summary, result.turns) == ("succeeded", "50", 2)
    assert sum(signals for *_, signals in chain) <= 1, chain

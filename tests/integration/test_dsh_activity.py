"""A DSH turn through `run_harness_turn`, with the real database and a real DSH
container (DSH migration plan D1, D6, D9, R11, R12, R16; phase 02 task 2.4).

The model is the deterministic fake; the DSH container is built from
`infra/dsh/Dockerfile` and the test process plays the worker.
"""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import tarfile
import time
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.testing import ActivityEnvironment

from common.blob_store import MemoryBlobStore
from common.persistence.repositories import (
    CheckpointRepository,
    TaskRepository,
    UsageLedgerRepository,
    make_engine,
)
from common.schemas import TaskStart, TurnInput, TurnOutcome
from harness_activity.activity import HarnessActivities
from harness_activity.config import build_config
from harness_activity.dsh import runner as dsh_runner
from harness_activity.dsh.launcher_client import LauncherClient
from harness_activity.dsh.ledger import DSH_MAX_OUTPUT_TOKENS, UsageLedger
from harness_activity.dsh.pins import RuntimePinMismatch
from harness_activity.dsh.runner import DshRunner
from harness_activity.events import MemorySink
from harness_activity.runner import AttemptContext, RunnerFailure, Usage
from registry.loader import load_registry
from tests.support.dsh import DshContainer, MemoryLedgerStore, build_image, start_container
from tests.support.fake_model import FakeModel
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
INSTRUCTIONS = "Write the order summary for SKU-1."
SCRIPT: list[dict[str, Any]] = [
    {"tool": "lookup_price", "args": {"sku": "SKU-1"}},
    {"tool": "write_file", "args": {"path": "order-summary.md", "content": "Total: 37.50\n"}},
    {"tool": "finish_task", "args": {"status": "done", "summary": "Wrote the summary."}},
]


@pytest.fixture(scope="module")
def container() -> Iterator[DshContainer]:
    found = start_container(build_image())
    try:
        yield found
    finally:
        found.stop()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


@dataclasses.dataclass
class Harness:
    acts: HarnessActivities
    blobs: MemoryBlobStore
    sink: MemorySink
    task_id: str
    heartbeats: list[dict[str, Any]]

    def env(self, attempt: int, details: dict[str, Any] | None) -> ActivityEnvironment:
        env = ActivityEnvironment()
        env.info = dataclasses.replace(
            env.info,
            attempt=attempt,
            heartbeat_details=[details] if details is not None else [],
            heartbeat_timeout=timedelta(seconds=3),
            start_to_close_timeout=timedelta(minutes=5),
            workflow_id=self.task_id,
        )
        env.on_heartbeat = lambda *d: self.heartbeats.append(d[0])
        return env

    def turn(self) -> TurnInput:
        return TurnInput(
            task_id=self.task_id,
            turn=1,
            template="local-dsh",
            template_version=1,
            template_hash=load_registry().templates["local-dsh"].hash,
            remaining_tokens=1_000_000,
            remaining_wall_time=timedelta(minutes=10),
            request_id="req-dsh-activity",
        )


async def harness(engine: AsyncEngine, container: DshContainer) -> Harness:
    blobs, sink = MemoryBlobStore(), MemorySink()
    task_id = f"task-dsh-{run_id()}"
    instructions = await blobs.put(INSTRUCTIONS.encode(), retention="task")
    data = await blobs.put(b"input data", retention="task")
    start = TaskStart(
        task_id=task_id,
        request_id="req-1",
        profile="dsh",
        template="local-dsh",
        instructions_ref=instructions,
        input_refs={"input.txt": data},
        outputs=["order-summary.md"],
    )
    await TaskRepository(engine).record_task(
        start, workflow_id=task_id, run_id="run-1", template_version=1, template_hash="x"
    )
    runner = DshRunner(container.control, UsageLedgerRepository(engine), blobs, sink)
    acts = HarnessActivities(
        load_registry(),
        engine,
        blobs,
        runner,
        container.attempts,
        "test-dsh-worker",
        open_attempt=runner.open_attempt,
    )
    return Harness(acts, blobs, sink, task_id, [])


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.connect() as conn:
        return list((await conn.execute(text(sql), params)).all())


def names(data: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        return tar.getnames()


async def test_dsh_turn_through_the_activity(
    engine: AsyncEngine, container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = await harness(engine, container)
    with FakeModel(SCRIPT) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        outcome: TurnOutcome = await h.env(1, None).run(h.acts.run_harness_turn, h.turn())
        first = fake.state.requests[0]
    assert outcome.status == "done" and outcome.summary == "Wrote the summary."
    assert (outcome.tokens_in, outcome.tokens_out) == (300, 30) and outcome.usage_known
    assert (outcome.tool_calls, outcome.inner_turns) == (3, 3)
    assert [a.path for a in outcome.outputs] == ["order-summary.md"]
    assert await h.blobs.get(outcome.outputs[0].ref) == b"Total: 37.50\n"
    # The model saw the bare tool names and the template's model, as with openai_agents.
    assert "finish_task" in {t["function"]["name"] for t in first["tools"]}
    assert INSTRUCTIONS in json.dumps(first["messages"])

    # D6, D1: a barrier checkpoint before the second and third request and a final
    # one, each with the session as its own blob; the workspace holds no session.
    latest = await CheckpointRepository(engine).latest(h.task_id)
    assert latest is not None and latest.seq == 2 and latest.session_position == 0
    assert latest.finish is not None and latest.finish["status"] == "done"
    assert latest.session_ref is not None and latest.session_digest is not None
    session_files = names(await h.blobs.get(latest.session_ref))
    assert any(name.endswith("session.v4.jsonl") for name in session_files)
    workspace_files = names(await h.blobs.get(latest.workspace_ref))
    assert "order-summary.md" in workspace_files and "input.txt" in workspace_files
    assert not any("session" in name for name in workspace_files)

    # R11: usage is what the gateway ledger settled.
    ledger = await rows(
        engine,
        "SELECT input_tokens, output_tokens, settled_at IS NOT NULL FROM usage_ledger "
        "WHERE task_id = :t ORDER BY request_id",
        t=h.task_id,
    )
    assert [tuple(r) for r in ledger] == [(100, 10, True)] * 3
    attempt = await rows(
        engine,
        "SELECT outcome, tokens_in, tokens_out, tool_calls, usage_known FROM task_attempts "
        "WHERE task_id = :t",
        t=h.task_id,
    )
    assert [tuple(r) for r in attempt] == [("done", 300, 30, 3, True)]

    # R16: ordered events with the attempt's identity, and no prompt or tool text.
    events = h.sink.events
    assert [e.seq for e in events] == list(range(len(events)))
    assert {e.attempt_id for e in events} == {f"{h.task_id}:1:1"}
    assert {e.workflow_id for e in events} == {h.task_id}
    assert [e.type for e in events] == ["token", "tool_call", "tool_result"] * 3
    assert [e.payload["tool"] for e in events if e.type == "tool_call"] == [
        "lookup_price",
        "write_file",
        "finish_task",
    ]
    dumped = json.dumps([e.payload for e in events])
    assert "37.50" not in dumped and "order summary" not in dumped.lower()

    # The attempt is gone from the DSH container and the shared volume.
    assert container.attempt_cgroups() == []
    assert not (container.attempts / h.task_id).exists()


async def test_dsh_resumes_and_charges_a_lost_request(
    engine: AsyncEngine, container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Attempt 1 is cancelled while its third model request is in flight. Attempt 2
    restores the session blob and workspace from the barrier checkpoint, charges
    the unobserved request conservatively (D9) and finishes the turn."""
    h = await harness(engine, container)
    script = [SCRIPT[0], SCRIPT[1], {**SCRIPT[2], "pause": True}]
    with FakeModel(script) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        env = h.env(1, None)
        first = asyncio.create_task(env.run(h.acts.run_harness_turn, h.turn()))
        until = time.monotonic() + 60
        while fake.state.paused_step != 2:
            assert time.monotonic() < until and not first.done()
            await asyncio.sleep(0.05)
        stopped = time.monotonic()
        env.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert time.monotonic() - stopped < 5  # a cooperative stop, within the grace (R8)
        assert container.attempt_cgroups() == []
        assert not (container.attempts / h.task_id).exists()

        outcome: TurnOutcome = await h.env(2, h.heartbeats[-1]).run(
            h.acts.run_harness_turn, h.turn()
        )
        resumed = fake.state.requests[-1]

    assert outcome.status == "done" and outcome.attempts == 2
    # The conversation and the file survived without the old attempt tree (R5).
    replayed = json.dumps(resumed["messages"])
    assert "lookup_price" in replayed and "wrote 13 characters" in replayed
    assert await h.blobs.get(outcome.outputs[0].ref) == b"Total: 37.50\n"
    # D9, R12, R13: two settled requests, one unknown charged conservatively, then
    # the resumed request.
    window = load_registry().templates["local-dsh"].template.context_window
    assert window is not None and not outcome.usage_known
    assert outcome.tokens_in == 200 + window + 100
    assert outcome.tokens_out == 20 + DSH_MAX_OUTPUT_TOKENS + 10
    attempts = await rows(
        engine,
        "SELECT attempt, outcome, failure_category, tokens_in, usage_known FROM task_attempts "
        "WHERE task_id = :t ORDER BY attempt",
        t=h.task_id,
    )
    assert [tuple(r) for r in attempts] == [
        (1, "cancelled", "DshCancelled", None, False),
        (2, "done", None, outcome.tokens_in, False),
    ]


async def test_deadline_stops_a_running_command_within_the_grace(
    container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8: the deadline fires while a command runs. The launcher still takes the
    stop, the runtime exits on SIGTERM, and the command dies with the attempt."""
    runner = container.runner()
    script = [{"tool": "run_command", "args": {"command": "sh -c 'sleep 50'"}}]
    with FakeModel(script) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        registry = load_registry()
        config = build_config(registry, registry.templates["local-dsh"], "task-deadline-1")
        deadline = time.monotonic() + 4
        scope = await runner.open_attempt(
            AttemptContext(f"task-deadline-{run_id()}", 1, 1, "wf", 1_000_000, deadline)
        )
        try:
            with pytest.raises(RunnerFailure) as failure:
                await runner.run(
                    config, scope.workspace, scope.store.session, "go", _no_op, Usage()
                )
            stopped_after = time.monotonic() - deadline
        finally:
            await scope.close()
    assert (failure.value.category, failure.value.retryable) == ("DshTurnDeadline", True)
    assert stopped_after < 5 and len(fake.state.requests) == 1
    assert container.attempt_cgroups() == []
    left = container.exec(
        "sh",
        "-c",
        "for c in /proc/[0-9]*/cmdline; do tr '\\0' ' ' < $c; echo; done | grep -c '[s]leep 50'",
    )
    assert left.stdout.strip() == "0"  # the command died with the attempt


TOOL_THEN_DONE: list[dict[str, Any]] = [SCRIPT[0], SCRIPT[2]]


async def run_one(
    runner: DshRunner, seconds: float, before: Any, task: str
) -> tuple[RunnerFailure, float]:
    """One attempt with a deadline `seconds` from now; the failure and how long
    after the deadline the run ended."""
    registry = load_registry()
    config = build_config(registry, registry.templates["local-dsh"], task)
    deadline = time.monotonic() + seconds
    scope = await runner.open_attempt(AttemptContext(task, 1, 1, "wf", 1_000_000, deadline))
    try:
        with pytest.raises(RunnerFailure) as failure:
            await runner.run(config, scope.workspace, scope.store.session, "go", before, Usage())
        return failure.value, time.monotonic() - deadline
    finally:
        await scope.close()


async def test_deadline_during_the_barrier_is_a_retryable_deadline(
    container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8, R9, D6 (review F60): the deadline fires while the barrier holds the
    attempt frozen and commits. The stop is cooperative, so it is a retryable
    `DshTurnDeadline`, not a forced stop, and the commit in progress is abandoned."""
    entered: list[float] = []
    committed: list[float] = []

    async def slow_commit(usage: Usage) -> None:
        entered.append(time.monotonic())
        await asyncio.sleep(60)
        committed.append(time.monotonic())

    with FakeModel(TOOL_THEN_DONE) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        failure, after = await run_one(
            container.runner(), 12, slow_commit, f"task-barrier-deadline-{run_id()}"
        )
    assert entered and entered[0] < time.monotonic() - after  # the barrier was running
    assert (failure.category, failure.retryable) == ("DshTurnDeadline", True)
    assert after < 5 and committed == []
    assert container.attempt_cgroups() == []


async def test_failed_thaw_is_a_retryable_checkpoint_failure(
    container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D6 (review F60): a barrier whose thaw fails leaves the attempt frozen. It is
    stopped and classified as a retryable checkpoint failure, not a forced stop."""
    original = LauncherClient.request

    async def no_thaw(self: LauncherClient, op: str, **fields: Any) -> dict[str, Any]:
        if op == "thaw":
            return {"ok": False}
        return await original(self, op, **fields)

    monkeypatch.setattr(LauncherClient, "request", no_thaw)
    with FakeModel(TOOL_THEN_DONE) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        failure, after = await run_one(
            container.runner(), 60, _no_op, f"task-barrier-thaw-{run_id()}"
        )
    assert (failure.category, failure.retryable) == ("DshCheckpointFailure", True)
    assert after < 0  # stopped at once, not at the deadline
    assert container.attempt_cgroups() == []


async def test_attempt_on_an_unpinned_runtime_is_refused(container: DshContainer) -> None:
    """R17 (review F62): the worker checked its container at start-up; the container
    was then recreated from another image. Opening an attempt re-checks the pin and
    refuses, retryably, before anything is created."""
    runner = DshRunner(
        container.control, MemoryLedgerStore(), MemoryBlobStore(), pinned="sha256:" + "0" * 64
    )
    task = f"task-unpinned-{run_id()}"
    with pytest.raises(RuntimePinMismatch):
        await runner.open_attempt(AttemptContext(task, 1, 1, "wf", 1_000, time.monotonic() + 60))
    assert container.attempt_cgroups() == [] and not (container.attempts / task).exists()
    # The pinned runtime opens normally.
    scope = await container.runner().open_attempt(
        AttemptContext(task, 1, 1, "wf", 1_000, time.monotonic() + 60)
    )
    await scope.close()


async def test_failed_final_freeze_is_a_retryable_checkpoint_failure(
    container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R5, D6 (review F67): the runtime finished, but the attempt could not be
    frozen, so something it started may still change the workspace. The run fails
    retryably instead of returning a result the final checkpoint would capture."""
    original = LauncherClient.request

    async def no_freeze(self: LauncherClient, op: str, **fields: Any) -> dict[str, Any]:
        if op == "freeze":
            return {"ok": False}
        return await original(self, op, **fields)

    monkeypatch.setattr(LauncherClient, "request", no_freeze)
    with FakeModel([SCRIPT[2]]) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        failure, _ = await run_one(container.runner(), 60, _no_op, f"task-final-freeze-{run_id()}")
    assert (failure.category, failure.retryable) == ("DshCheckpointFailure", True)
    assert container.attempt_cgroups() == []


# A runtime that keeps running after the gateway denies its request: it sends two
# model requests with the granted catalog, then waits, exiting only on SIGTERM.
STUBBORN_DRIVER = """
import json, os, signal, socket, sys, time
signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
tree = "/run/attempt"
tools = json.load(open(tree + "/config/tools.json"))
model = json.load(open(tree + "/config/input.json"))["model"]
def post(n):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": str(n)}],
        "tools": [{"type": "function", "function": {"name": "mcp__praxis__" + t["name"]}}
                  for t in tools]}).encode()
    s = socket.socket(socket.AF_UNIX); s.connect(tree + "/ipc/gateway.sock")
    s.sendall(b"POST /v1/chat/completions HTTP/1.1\\r\\nAuthorization: Bearer "
              + os.environ["PRAXIS_MODEL_KEY"].encode()
              + b"\\r\\nContent-Length: " + str(len(body)).encode() + b"\\r\\n\\r\\n" + body)
    while s.recv(65536): pass
post(1); post(2)
time.sleep(60)
"""


async def test_step_limit_stops_a_runtime_that_does_not_exit(
    container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8 (review F64): the step limit denies the second request; a runtime that
    keeps running anyway is stopped within the 5 s grace, and the turn ends as a
    `continue` at the inner-turn limit, not at the deadline."""
    monkeypatch.setattr(dsh_runner, "DRIVER", ["python", "-c", STUBBORN_DRIVER])
    registry = load_registry()
    task = f"task-step-limit-{run_id()}"
    config = dataclasses.replace(
        build_config(registry, registry.templates["local-dsh"], task), inner_max_turns=1
    )
    runner = container.runner()
    denied: list[float] = []
    original = UsageLedger.admit

    async def admit(self: UsageLedger, purpose: str, step: int, deny: str | None = None) -> Any:
        record = await original(self, purpose, step, deny)
        if record.denial:
            denied.append(time.monotonic())
        return record

    monkeypatch.setattr(UsageLedger, "admit", admit)
    with FakeModel([SCRIPT[0], SCRIPT[0]]) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        scope = await runner.open_attempt(
            AttemptContext(task, 1, 1, "wf", 1_000_000, time.monotonic() + 60)
        )
        try:
            result = await runner.run(
                config, scope.workspace, scope.store.session, "go", _no_op, Usage()
            )
            ended = time.monotonic()
        finally:
            await scope.close()
    assert (result.status, result.summary) == ("continue", "inner-turn limit reached")
    assert denied and ended - denied[0] < 5.0
    assert container.attempt_cgroups() == []


async def _no_op(usage: Usage) -> None:
    return None

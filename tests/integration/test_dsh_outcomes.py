"""R18: the spike's outcome cases on the production path (DSH migration plan task
2.5; spikes/dsh-harness/run_tasks.py, docs/spikes/dsh-phase02-r2-evidence.json).

Each case runs through `TaskWorkflow` on the local stack: the orchestrator and a
`local-dsh` template worker built by `workers.main.build_worker`, a real DSH
container, and the deterministic fake model as the scripted provider. The
registry is a copy with a two-step inner limit and short timeouts.

Every case's expected TaskResult is read from the spike's record. What differs,
by decision (plan D11, decision log 2026-11-16):

- The fake model reports 100 input and 10 output tokens per completion; the
  spike's fixture reported 7 and 3. Tokens are compared per answered request.
- The spike's fixture provider told its gateway that a failure came before
  generation. The production gateway can prove that only for a request the
  endpoint refused (4xx). A malformed response, a dropped connection or a request
  still in flight at the deadline leaves usage unknown: it is charged
  conservatively and the result says `usage_known = false` (D9, R12, R13).
- Inner turns are cumulative over the attempts of a turn, like tokens, so a
  retried or lost attempt's model steps count too (`extra_inner_turns`).
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle

import workers.main
from common.blob_store.s3 import S3BlobStore
from common.observability import disable_sdk_tracing
from common.persistence.repositories import (
    Checkpoint,
    CheckpointRepository,
    RecordingBlobStore,
    make_engine,
)
from common.schemas import TaskResult
from harness_activity.dsh import runner as dsh_runner
from harness_activity.dsh.ledger import DSH_MAX_OUTPUT_TOKENS, unknown_charge
from orchestrator.submit import prepare_task, start_task
from registry.loader import Registry, load_registry
from tests.support.dsh import DshContainer, build_image, make_dsh_registry, start_container
from tests.support.fake_model import FakeModel
from tests.support.stack import run_id
from tests.support.worker_procs import ROOT, descendants

pytestmark = pytest.mark.integration
EVIDENCE = {
    summary["case"]: summary
    for summary in json.loads((ROOT / "docs/spikes/dsh-phase02-r2-evidence.json").read_text())[
        "driver_summaries"
    ].values()
    if "case" in summary
}
SPIKE_REQUEST = (7, 3)  # what the spike's fixture reported for every completion

ARTIFACT = b"controlled fixture artifact\n"
SUMMARY = "Controlled fixture completed."
QUESTION = "Which fixture value should be used?"
INNER_LIMIT = 2
TURNS = 6  # the `dsh` profile's max_turns
WINDOW = 32768  # local-dsh's context_window


def finish(**changes: Any) -> dict[str, Any]:
    return {"tool": "finish_task", "args": {"status": "done", "summary": SUMMARY, **changes}}


DONE = finish()
ONE_REQUEST = (100, 10)  # what the fake model reports for every completion


@dataclass(frozen=True)
class Case:
    """What the production run adds to, or changes from, the spike's record."""

    script: list[dict[str, Any]]
    # (turn, attempt, outcome, failure_category) of every attempt row.
    rows: list[tuple[int, int, str, str | None]] = field(
        default_factory=lambda: [(1, 1, "done", None)]
    )
    unknown: int = 0  # requests whose usage was never observed
    extra_inner_turns: int = 0  # steps of retried or lost attempts (D11)
    settings: dict[str, Any] = field(default_factory=dict)


def spike(name: str) -> dict[str, Any]:
    """The TaskResult the spike recorded for a case."""
    result: dict[str, Any] = EVIDENCE[name]["result"]
    return result


def answered(name: str) -> int:
    """Model requests the endpoint answered with a completion, from the spike."""
    tokens_in = spike(name)["tokens_in"]
    assert tokens_in % SPIKE_REQUEST[0] == 0
    return int(tokens_in // SPIKE_REQUEST[0])


def retried(category: str) -> list[tuple[int, int, str, str | None]]:
    return [(1, 1, "failed", category), (1, 2, "done", None)]


CONTINUES: list[tuple[int, int, str, str | None]] = [
    (turn, 1, "continue", None) for turn in range(1, TURNS + 1)
]
CASES: dict[str, Case] = {
    "done": Case([DONE]),
    # The model answers in text and never calls finish_task: every turn continues
    # until the profile's turn budget is used up.
    "plain-text": Case([{"text": '{"status":"succeeded"}'}], rows=CONTINUES),
    # Every finish_task is invalid, so each turn stops at the inner-turn limit.
    "inner-limit": Case([finish(status="succeeded")], rows=CONTINUES),
    "needs-input": Case(
        [finish(status="needs_input", summary="Fixture needs an owner choice.",
                questions=[QUESTION])],
        rows=[(1, 1, "needs_input", None)],
    ),
    # An invalid completion is an admitted call that fails; the model corrects it.
    "invalid-status": Case([finish(status="succeeded"), DONE]),
    "invalid-payload": Case([finish(summary={"invalid": "object"}), DONE]),
    "invalid-reference": Case(
        [finish(artifacts=[{"path": "../escape", "ref": {"checksum": "bad"}}]), DONE]
    ),
    # Refused before generation: nothing was used, and the turn is retried.
    "retry-model": Case(
        [{**DONE, "fault": "overloaded"}], rows=retried("DshProviderFailure"),
        extra_inner_turns=1,
    ),
    "retry-protocol": Case(
        [{**DONE, "fault": "malformed"}], rows=retried("DshUsageUnknown"), unknown=1,
        extra_inner_turns=1,
    ),
    "retry-infrastructure": Case(
        [{**DONE, "fault": "disconnect"}], rows=retried("DshUsageUnknown"), unknown=1,
        extra_inner_turns=1,
    ),
    "bad-request": Case(
        [{**DONE, "fault": "rejected", "always": True}],
        rows=[(1, 1, "failed", "HarnessInputError")],
    ),
    # The model stalls on the first attempt; the turn deadline stops it.
    "deadline": Case(
        [{**DONE, "pause": True}], rows=retried("DshUsageUnknown"), unknown=1,
        extra_inner_turns=1, settings={"turn_timeout": "PT30S"},
    ),
}  # fmt: skip


@pytest.fixture(scope="module")
def container() -> Iterator[DshContainer]:
    found = start_container(build_image())
    try:
        yield found
    finally:
        found.stop()


@pytest.fixture(autouse=True)
def _nothing_left(container: DshContainer) -> Iterator[None]:
    yield
    assert container.leftovers() == {}  # no attempt process, cgroup or tree


def registry_for(tmp_path: Path, **settings: Any) -> Registry:
    base = {"inner_max_turns": INNER_LIMIT, "heartbeat_timeout": "PT5S", "turn_timeout": "PT2M"}
    return load_registry(make_dsh_registry(tmp_path / "registry", **{**base, **settings}))


@asynccontextmanager
async def stack(
    registry: Registry, container: DshContainer, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client]:
    """The orchestrator and a `local-dsh` template worker, as `workers.main` builds
    them, on queues of their own and paired with the test's DSH container."""
    monkeypatch.setattr(workers.main, "load_registry", lambda: registry)
    monkeypatch.setenv("PRAXIS_QUEUE_PREFIX", f"dsh-{run_id()}.")
    monkeypatch.setenv("DSH_CONTROL", str(container.control))
    disable_sdk_tracing()
    client = await workers.main.connect("praxis-test")
    orchestrator = await workers.main.build_worker(client, "orchestrator", None)
    worker = await workers.main.build_worker(client, "template", "local-dsh")
    async with orchestrator, worker:
        yield client


async def submit(
    client: Client, registry: Registry, tmp_path: Path
) -> tuple[str, WorkflowHandle[Any, Any]]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "answer.txt").write_bytes(ARTIFACT)
    engine = make_engine()
    try:
        s3 = S3BlobStore.from_env()
        await s3.ensure_bucket()
        start = await prepare_task(
            {
                "profile": "dsh",
                "instructions": "Execute the controlled completion fixture.",
                "input_files": ["answer.txt"],
                "outputs": ["answer.txt"],
            },
            registry,
            RecordingBlobStore(s3, engine),
            base_dir=inputs,
        )
    finally:
        await engine.dispose()
    return start.task_id, await start_task(client, start)


async def query(sql: str, **params: Any) -> list[tuple[Any, ...]]:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            return [tuple(row) for row in (await conn.execute(text(sql), params)).all()]
    finally:
        await engine.dispose()


async def attempt_rows(task_id: str) -> list[tuple[Any, ...]]:
    return await query(
        "SELECT turn, attempt, outcome, failure_category FROM task_attempts "
        "WHERE task_id = :t ORDER BY turn, attempt",
        t=task_id,
    )


async def ledger_totals(task_id: str) -> tuple[int, int, int]:
    """Settled input and output tokens, and the requests never settled with usage."""
    rows = await query(
        "SELECT coalesce(sum(input_tokens), 0), coalesce(sum(output_tokens), 0), "
        "count(*) FILTER (WHERE input_tokens IS NULL) FROM usage_ledger WHERE task_id = :t",
        t=task_id,
    )
    return int(rows[0][0]), int(rows[0][1]), int(rows[0][2])


async def check_usage(result: TaskResult, task_id: str, unknown: int) -> None:
    """R11-R13: usage is the ledger's settled totals, plus the conservative charge
    for every request whose usage was never observed, which makes it not known."""
    tokens_in, tokens_out, unsettled = await ledger_totals(task_id)
    charge_in, charge_out = unknown_charge(unsettled, WINDOW)
    assert unsettled == unknown
    assert (result.tokens_in, result.tokens_out) == (tokens_in + charge_in, tokens_out + charge_out)
    assert result.usage_known is (unknown == 0)


@pytest.mark.parametrize("name", sorted(CASES))
async def test_outcome_case(
    name: str, container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, recorded = CASES[name], spike(name)
    registry = registry_for(tmp_path, **case.settings)
    with FakeModel(case.script) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, container, monkeypatch) as client:
            task_id, handle = await submit(client, registry, tmp_path)
            result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), 300))
        served = len(fake.state.served)

    # R18: the spike's TaskResult, with only the recorded differences.
    for key in ("status", "failure_reason", "summary", "questions", "turns", "attempts"):
        assert getattr(result, key) == recorded[key], key
    assert [a.path for a in result.artifacts] == [a["path"] for a in recorded["artifacts"]]
    assert result.template == "local-dsh"
    assert result.inner_turns == recorded["inner_turns"] + case.extra_inner_turns
    assert await attempt_rows(task_id) == case.rows and len(case.rows) == recorded["attempts"]
    await check_usage(result, task_id, case.unknown)
    requests = answered(name)
    assert result.tokens_in == requests * ONE_REQUEST[0] + case.unknown * WINDOW
    # No request after finish_task or past the inner limit reached the endpoint.
    faults = sum(1 for _, _, outcome, _ in case.rows if outcome == "failed")
    assert served == requests + faults
    if result.status == "succeeded":
        (artifact,) = result.artifacts
        assert artifact.path == "answer.txt" and artifact.ref.retention_class == "audit"
        assert await S3BlobStore.from_env().get(artifact.ref) == ARTIFACT
    else:
        assert result.artifacts == []


async def test_lost_after_finish_completes_without_restarting_the_runtime(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R18 `lost-after-finish`: attempt 1 is lost after its finish checkpoint is
    committed, before the attempt row is finished. Attempt 2 restores that finish
    without starting the DSH runtime again, and the lost attempt's usage stays in
    the turn total."""
    registry = registry_for(tmp_path)
    original = CheckpointRepository.insert_fenced
    runs: list[tuple[int, int]] = []
    original_run = dsh_runner.DshRunner.run

    async def inject_loss(self: CheckpointRepository, cp: Checkpoint) -> None:
        await original(self, cp)
        if cp.finish is not None and cp.attempt == 1:
            raise RuntimeError("injected worker loss after finish checkpoint")

    async def count_run(self: dsh_runner.DshRunner, *args: Any, **kw: Any) -> Any:
        attempt = await self._attempt_for(args[1])
        runs.append((attempt.context.turn, attempt.context.attempt))
        return await original_run(self, *args, **kw)

    monkeypatch.setattr(CheckpointRepository, "insert_fenced", inject_loss)
    monkeypatch.setattr(dsh_runner.DshRunner, "run", count_run)
    with FakeModel([DONE]) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, container, monkeypatch) as client:
            task_id, handle = await submit(client, registry, tmp_path)
            result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), 300))
        served = len(fake.state.served)

    recorded = spike("lost-after-finish")
    for key in ("status", "summary", "turns", "attempts"):
        assert getattr(result, key) == recorded[key], key
    # D11: the lost attempt's model step counts, as its tokens do.
    assert result.inner_turns == recorded["inner_turns"] + 1
    assert runs == [(1, 1)] and served == 1  # attempt 2 never started DSH or hit the model
    assert await attempt_rows(task_id) == [
        (1, 1, "lost", "lost_or_timed_out"),
        (1, 2, "done", None),
    ]
    await check_usage(result, task_id, unknown=0)
    assert (result.tokens_in, result.tokens_out) == ONE_REQUEST
    assert answered("lost-after-finish") == 1
    (artifact,) = result.artifacts
    assert await S3BlobStore.from_env().get(artifact.ref) == ARTIFACT


async def test_cancel_stops_the_attempt_within_the_grace_and_stays_clean(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R18 `cancel`, R8, R12: cancelling the workflow while the model request is
    held stops the attempt cooperatively within the 5 s grace, as the spike
    recorded; the attempt row is `cancelled` with its in-flight request's usage
    unknown, and the container stays clean through the 10 s window."""
    (recorded,) = EVIDENCE["cancel"]["native_attempts"]
    assert (recorded["stop_reason"], recorded["cooperative_stop"]) == ("cancelled", True)
    registry = registry_for(tmp_path)
    with FakeModel([{**DONE, "pause": True}]) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, container, monkeypatch) as client:
            task_id, handle = await submit(client, registry, tmp_path)
            until = asyncio.get_running_loop().time() + 60
            while fake.state.paused_step != 0:
                assert asyncio.get_running_loop().time() < until
                await asyncio.sleep(0.05)
            trigger = asyncio.get_running_loop().time()
            await handle.cancel()
            with contextlib.suppress(WorkflowFailureError):
                await asyncio.wait_for(handle.result(), 60)
            # Wait for the Activity to finish stopping the attempt and closing its row.
            while (
                container.leftovers()
                or not (rows := await attempt_rows(task_id))
                or rows[0][2] == "started"
            ):
                assert asyncio.get_running_loop().time() < trigger + 5.0
                await asyncio.sleep(0.05)
            stopped_in = asyncio.get_running_loop().time() - trigger
            assert stopped_in < 5.0
            assert rows == [(1, 1, "cancelled", "DshCancelled")]  # cooperative, not forced
            usage = await query(
                "SELECT tokens_in, tokens_out, usage_known FROM task_attempts WHERE task_id = :t",
                t=task_id,
            )
            assert usage == [(None, None, False)]  # F59: unknown, never 0
            assert await container.stays_clean(10.0) == {}


async def test_forced_stop_is_recorded_as_a_non_retryable_failure(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8, R9: when the runtime ignores SIGTERM, the launcher kills the cgroup after
    the 5 s grace; the attempt is recorded failed (`DshForcedStop`, non-retryable)
    and nothing remains during the following 10 s window."""
    registry = registry_for(tmp_path, turn_timeout="PT25S")
    ignore_term = (
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
    )
    monkeypatch.setattr(dsh_runner, "DRIVER", ["python", "-c", ignore_term])
    with FakeModel([DONE]) as fake:
        monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
        async with stack(registry, container, monkeypatch) as client:
            task_id, handle = await submit(client, registry, tmp_path)
            result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), 120))
            assert await container.stays_clean(10.0) == {}

    assert (result.status, result.failure_reason) == (
        "failed",
        "harness turn 1 failed: DshForcedStop",
    )
    assert (result.turns, result.attempts) == (1, 1)
    assert await attempt_rows(task_id) == [(1, 1, "failed", "DshForcedStop")]


async def test_command_isolation_blocks_session_other_attempts_and_reaps_background(
    container: DshContainer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R15: through a full turn, a command cannot read the session file or another
    attempt's tree, and a backgrounded process dies when the attempt ends."""
    other = container.attempts / "other-task/1/1/workspace"
    other.mkdir(parents=True)
    (other / "secret.txt").write_text("other-attempt-secret")
    # Each probe prints a label, so the test sees that it ran and what it saw.
    probe_cmd = (
        "sh -c '"
        "echo other:; cat /attempts/other-task/1/1/workspace/secret.txt 2>/dev/null; "
        "echo attempts:; ls -A /attempts 2>/dev/null; "
        "echo session:; cat /attempts/*/1/1/home/sessions/* /run/attempt/home/sessions/* "
        "../home/sessions/* 2>/dev/null; "
        "echo end:; (sleep 55 >/dev/null 2>&1 &); "
        "echo isolated-ok"
        "'"
    )
    script = [
        {"tool": "run_command", "args": {"command": probe_cmd}},
        DONE,
    ]
    registry = registry_for(tmp_path)
    try:
        with FakeModel(script) as fake:
            monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)
            async with stack(registry, container, monkeypatch) as client:
                task_id, handle = await submit(client, registry, tmp_path)
                result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), 120))
            second_req = fake.state.requests[1]
    finally:
        shutil.rmtree(container.attempts / "other-task", ignore_errors=True)

    assert result.status == "succeeded" and await attempt_rows(task_id) == [(1, 1, "done", None)]
    tool_outputs = [m["content"] for m in second_req["messages"] if m.get("role") == "tool"]
    assert len(tool_outputs) == 1 and "isolated-ok" in tool_outputs[0]
    # Review F90: every probe ran and saw nothing; the session file holds the
    # task's instructions, so reading it would show them.
    seen = tool_outputs[0]
    labels = ["other:", "attempts:", "session:", "end:"]
    assert all(label in seen for label in labels)
    between = [seen.split(a, 1)[1].split(b, 1)[0].strip() for a, b in itertools.pairwise(labels)]
    assert between == ["", "", ""]
    assert "other-attempt-secret" not in seen and "controlled completion fixture" not in seen
    # Neither the backgrounded `sleep 55` nor any attempt process survived.
    assert container.attempt_processes() == []


def start_worker_proc(
    scratch: Path, name: str, env: dict[str, str], *args: str
) -> subprocess.Popen[bytes]:
    scratch.mkdir(parents=True, exist_ok=True)
    log = open(scratch / f"{name}.log", "wb")  # noqa: SIM115
    return subprocess.Popen(
        [sys.executable, "-m", "workers.main", *args],
        cwd=ROOT,
        env={**env, "PRAXIS_SCRATCH": str(scratch / name)},
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def kill_proc(proc: subprocess.Popen[bytes]) -> None:
    for pid in [*descendants(proc.pid), proc.pid]:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
    proc.wait(timeout=10)


def stop_proc(proc: subprocess.Popen[bytes]) -> None:
    for pid in [proc.pid, *descendants(proc.pid)]:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGSTOP)


def resume_proc(proc: subprocess.Popen[bytes]) -> None:
    for pid in [proc.pid, *descendants(proc.pid)]:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGCONT)


async def test_worker_sigkill_reaps_attempt_and_replacement_recovers(
    container: DshContainer, tmp_path: Path
) -> None:
    """R5, R10, R12, R13: a real `workers.main template local-dsh` host process is
    SIGKILLed mid-turn after the barrier committed a checkpoint (with a file edit).
    Within 10 s the launcher reaps the attempt's processes, cgroup and tree. A
    replacement worker resumes from the committed checkpoint, preserves the edit
    and conversation without the old attempt tree, charges the lost request
    conservatively, and finishes the task."""
    reg_dir = make_dsh_registry(
        tmp_path / "registry",
        inner_max_turns=4,
        heartbeat_timeout="PT5S",
        turn_timeout="PT2M",
    )
    registry = load_registry(reg_dir)
    steps: list[dict[str, Any]] = [
        {"tool": "write_file", "args": {"path": "answer.txt", "content": "recovered edit\n"}},
        {"tool": "lookup_price", "args": {"sku": "SKU-1"}, "pause": True},
        DONE,
    ]
    prefix = f"dsh-kill-{run_id()}."
    with FakeModel(steps) as fake:
        env = {
            **os.environ,
            "PRAXIS_REGISTRY": str(reg_dir),
            "PRAXIS_QUEUE_PREFIX": prefix,
            "VLLM_BASE_URL": fake.base_url,
            "DSH_CONTROL": str(container.control),
            "LOG_LEVEL": "INFO",
        }
        env.pop("METRICS_PORT", None)
        orch = start_worker_proc(tmp_path / "procs", "orchestrator", env, "orchestrator")
        worker_a = start_worker_proc(tmp_path / "procs", "worker-a", env, "template", "local-dsh")
        worker_b: subprocess.Popen[bytes] | None = None
        try:
            await asyncio.sleep(2.5)
            for name, p in (("orchestrator", orch), ("worker-a", worker_a)):
                if p.poll() is not None:
                    log_txt = (tmp_path / "procs" / f"{name}.log").read_text()[-2000:]
                    raise RuntimeError(f"{name} exited early:\n{log_txt}")
            old_prefix = os.environ.get("PRAXIS_QUEUE_PREFIX")
            os.environ["PRAXIS_QUEUE_PREFIX"] = prefix
            try:
                disable_sdk_tracing()
                client = await workers.main.connect("praxis-test")
                task_id, handle = await submit(client, registry, tmp_path)
            finally:
                if old_prefix is None:
                    os.environ.pop("PRAXIS_QUEUE_PREFIX", None)
                else:
                    os.environ["PRAXIS_QUEUE_PREFIX"] = old_prefix

            # Wait until the barrier before step 1 committed a checkpoint and step 1 is held.
            until = time.monotonic() + 60
            while True:
                cp = await query(
                    "SELECT count(*) FROM checkpoints WHERE task_id = :t AND seq >= 0",
                    t=task_id,
                )
                if fake.state.paused_step == 1 and cp[0][0] > 0:
                    break
                assert time.monotonic() < until
                await asyncio.sleep(0.1)

            kill_time = time.monotonic()
            kill_proc(worker_a)

            # R10: within 10 s of worker SIGKILL, no process, cgroup or tree remains.
            while container.leftovers() and time.monotonic() < kill_time + 10.0:
                await asyncio.sleep(0.1)
            assert container.leftovers() == {}

            # Release the held model call and start the replacement worker after
            # attempt 1's heartbeat timeout expires, so attempt 2 takes over cleanly.
            fake.state.release.set()
            before_resume = len(fake.state.requests)
            worker_b = start_worker_proc(
                tmp_path / "procs", "worker-b", env, "template", "local-dsh"
            )
            result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), 180))
            resumed_req = fake.state.requests[before_resume]
        finally:
            for proc in (orch, worker_a, worker_b):
                if proc is not None and proc.poll() is None:
                    kill_proc(proc)

    assert (result.status, result.turns, result.attempts) == ("succeeded", 1, 2)
    assert await attempt_rows(task_id) == [
        (1, 1, "lost", "lost_or_timed_out"),
        (1, 2, "done", None),
    ]
    # R5: the conversation and edit survived without the old attempt tree.
    replayed = json.dumps(resumed_req["messages"])
    assert "recovered edit" in replayed or "wrote 15 characters" in replayed
    (artifact,) = result.artifacts
    assert await S3BlobStore.from_env().get(artifact.ref) == b"recovered edit\n"
    # R11, R12, R13: 1 settled request before the kill, 1 unknown request in flight
    # at the kill (charged conservatively), and 2 settled requests on attempt 2.
    await check_usage(result, task_id, unknown=1)
    assert result.tokens_in == 3 * ONE_REQUEST[0] + WINDOW
    assert result.tokens_out == 3 * ONE_REQUEST[1] + DSH_MAX_OUTPUT_TOKENS
    attempts_usage = await query(
        "SELECT attempt, tokens_in, tokens_out, usage_known FROM task_attempts "
        "WHERE task_id = :t ORDER BY attempt",
        t=task_id,
    )
    assert attempts_usage == [
        (1, None, None, False),
        (2, result.tokens_in, result.tokens_out, False),
    ]


async def test_stale_dsh_attempt_writes_no_checkpoint_outcome_or_artifact(
    container: DshContainer, tmp_path: Path
) -> None:
    """R6, R7: worker A is frozen (SIGSTOP) while its second model request is held.
    After its heartbeat times out, worker B (on a second DSH container) finishes the
    task with its own edit. When worker A resumes (SIGCONT) and its held call
    completes, the transactional fence rejects its checkpoint, outcome and artifact."""
    second = start_container(build_image())
    reg_dir = make_dsh_registry(
        tmp_path / "registry",
        inner_max_turns=4,
        heartbeat_timeout="PT5S",
        turn_timeout="PT2M",
    )
    registry = load_registry(reg_dir)
    steps: list[dict[str, Any]] = [
        {"tool": "write_file", "args": {"path": "answer.txt", "content": "from attempt 1\n"}},
        {"tool": "lookup_price", "args": {"sku": "SKU-1"}, "pause": True},
        {"tool": "write_file", "args": {"path": "answer.txt", "content": "winner output\n"}},
        DONE,
    ]
    prefix = f"dsh-stale-{run_id()}."
    orch = worker_a = worker_b = None
    try:
        with FakeModel(steps) as fake:
            base_env = {
                **os.environ,
                "PRAXIS_REGISTRY": str(reg_dir),
                "PRAXIS_QUEUE_PREFIX": prefix,
                "VLLM_BASE_URL": fake.base_url,
                "LOG_LEVEL": "INFO",
            }
            base_env.pop("METRICS_PORT", None)
            orch = start_worker_proc(tmp_path / "procs", "orchestrator", base_env, "orchestrator")
            worker_a = start_worker_proc(
                tmp_path / "procs",
                "worker-a",
                {**base_env, "DSH_CONTROL": str(container.control)},
                "template",
                "local-dsh",
            )
            await asyncio.sleep(2.5)
            old_prefix = os.environ.get("PRAXIS_QUEUE_PREFIX")
            os.environ["PRAXIS_QUEUE_PREFIX"] = prefix
            try:
                disable_sdk_tracing()
                client = await workers.main.connect("praxis-test")
                task_id, handle = await submit(client, registry, tmp_path)
            finally:
                if old_prefix is None:
                    os.environ.pop("PRAXIS_QUEUE_PREFIX", None)
                else:
                    os.environ["PRAXIS_QUEUE_PREFIX"] = old_prefix

            until = time.monotonic() + 60
            while fake.state.paused_step != 1:
                assert time.monotonic() < until
                await asyncio.sleep(0.1)

            # Freeze worker A so its heartbeats stop while its request is held.
            stop_proc(worker_a)
            worker_b = start_worker_proc(
                tmp_path / "procs",
                "worker-b",
                {**base_env, "DSH_CONTROL": str(second.control)},
                "template",
                "local-dsh",
            )
            result = TaskResult.model_validate(await asyncio.wait_for(handle.result(), 180))
            cp_before = await query(
                "SELECT count(*) FROM checkpoints WHERE task_id = :t AND attempt = 1",
                t=task_id,
            )
            # Release the held response and wake worker A: it must be fenced.
            fake.state.release.set()
            resume_proc(worker_a)
            await asyncio.sleep(6)
            cp_after = await query(
                "SELECT count(*) FROM checkpoints WHERE task_id = :t AND attempt = 1",
                t=task_id,
            )
            rows = await attempt_rows(task_id)
    finally:
        for p in (orch, worker_a, worker_b):
            if p is not None and p.poll() is None:
                kill_proc(p)
        second.stop()

    assert (result.status, result.attempts) == ("succeeded", 2)
    assert cp_after == cp_before  # R6: no late checkpoint from attempt 1
    assert rows == [(1, 1, "lost", "lost_or_timed_out"), (1, 2, "done", None)]
    # R7: the task result has attempt 2's output, never attempt 1's.
    (artifact,) = result.artifacts
    assert await S3BlobStore.from_env().get(artifact.ref) == b"winner output\n"

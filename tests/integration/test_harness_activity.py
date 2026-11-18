"""`run_harness_turn` driven directly, with a scripted runner and the real database
(spec execution/durability, execution/task-workflow; informal durability review).

Each test fixes one durability promise that the kill tests cannot pin down:
fresh-start and truncating restore, lost-attempt usage, live heartbeats, the
superseded path, the finish shortcut and template-version refusals.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from agents.memory import Session
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from common.blob_store import MemoryBlobStore
from common.errors import TemplateVersionUnavailable
from common.events import EventTransport, Expired, TableTransport, Writer
from common.observability.logging import JsonFormatter
from common.persistence.repositories import (
    AttemptRepository,
    Checkpoint,
    CheckpointRepository,
    TaskRepository,
    make_engine,
)
from common.schemas import BlobRef, CompleteTaskInput, TaskStart, TurnInput
from harness_activity import workspace as ws
from harness_activity.activity import CONTINUE_MESSAGE, HarnessActivities, HarnessInputError
from harness_activity.config import HarnessConfig
from harness_activity.events import AttemptEvents
from harness_activity.runner import (
    BeforeModelCall,
    RunnerFailure,
    RunResult,
    StopRun,
    Superseded,
    Usage,
)
from orchestrator.activities import OrchestratorActivities
from registry.loader import load_registry
from tests.support.stack import run_id

pytestmark = pytest.mark.integration
INSTRUCTIONS = "Activity test instructions."

Script = Callable[["Seen", BeforeModelCall, Usage, Path, Session], Awaitable[RunResult]]


@dataclasses.dataclass
class Seen:
    input_text: str = ""
    items: int = -1
    files: list[str] = dataclasses.field(default_factory=list)
    started_at: float = 0.0
    calls: int = 0


class ScriptedRunner:
    """A `HarnessRunner` that records what it was given and runs a script."""

    def __init__(self, script: Script) -> None:
        self.script = script
        self.seen = Seen()

    async def run(
        self,
        config: HarnessConfig,
        workspace: Path,
        session: Session,
        input_text: str,
        before_model_call: BeforeModelCall,
        usage: Usage,
        events: AttemptEvents,
    ) -> RunResult:
        self.seen.calls += 1
        self.seen.started_at = time.monotonic()
        self.seen.input_text = input_text
        self.seen.items = len(await session.get_items())
        self.seen.files = sorted(p.name for p in workspace.iterdir() if p.is_file())
        return await self.script(self.seen, before_model_call, usage, workspace, session)


async def done(
    seen: Seen, before: BeforeModelCall, usage: Usage, ws_: Path, s: Session
) -> RunResult:
    await before(usage)
    usage.tokens_in += 20
    usage.inner_turns += 1
    return RunResult("done", usage, summary="ok")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _model_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:9")  # never called


@dataclasses.dataclass
class Harness:
    acts: HarnessActivities
    runner: ScriptedRunner
    blobs: MemoryBlobStore
    task_id: str
    heartbeats: list[tuple[float, dict[str, Any]]]

    def env(self, attempt: int = 1, details: dict[str, Any] | None = None) -> ActivityEnvironment:
        env = ActivityEnvironment()
        env.info = dataclasses.replace(
            env.info,
            attempt=attempt,
            heartbeat_details=[details] if details is not None else [],
            heartbeat_timeout=timedelta(seconds=3),
            workflow_id=self.task_id,
        )
        env.on_heartbeat = lambda *d: self.heartbeats.append((time.monotonic(), d[0]))
        return env

    def turn(
        self, remaining_tokens: int = 1_000_000, template_hash: str | None = None
    ) -> TurnInput:
        loaded = load_registry().templates["local-default"]
        return TurnInput(
            task_id=self.task_id,
            turn=1,
            template="local-default",
            template_version=1,
            template_hash=template_hash or loaded.hash,
            remaining_tokens=remaining_tokens,
            remaining_wall_time=timedelta(minutes=10),
            request_id="req-activity-test",
        )

    async def run(self, attempt: int = 1, details: dict[str, Any] | None = None, **kw: Any) -> Any:
        return await self.env(attempt, details).run(self.acts.run_harness_turn, self.turn(**kw))


async def harness(
    engine: AsyncEngine,
    tmp_path: Path,
    script: Script,
    blobs: Any = None,
    events: EventTransport | None = None,
) -> Harness:
    store = blobs or MemoryBlobStore()
    task_id = f"task-act-{run_id()}"
    instructions = await store.put(INSTRUCTIONS.encode(), retention="task")
    data = await store.put(b"input data", retention="task")
    start = TaskStart(
        task_id=task_id,
        request_id="req-1",
        profile="openai",
        template="local-default",
        instructions_ref=instructions,
        input_refs={"input.txt": data},
    )
    await TaskRepository(engine).record_task(
        start, workflow_id=task_id, run_id="run-1", template_version=1, template_hash="x"
    )
    runner = ScriptedRunner(script)
    acts = HarnessActivities(
        load_registry(), engine, store, runner, tmp_path, "test-worker", events=events
    )
    return Harness(acts, runner, store, task_id, [])


async def add_checkpoint(
    h: Harness,
    engine: AsyncEngine,
    position: int,
    files: dict[str, str],
    finish: dict[str, Any] | None = None,
    seq: int = 1,
) -> str:
    root = Path(f"/tmp/praxis-cp-{run_id()}")
    root.mkdir()
    for name, content in files.items():
        (root / name).write_text(content)
    ref: BlobRef = await h.blobs.put(ws.pack(root), retention="task")
    cp_id = f"{h.task_id}:1:1:{seq}"
    await CheckpointRepository(engine).insert(
        Checkpoint(cp_id, h.task_id, 1, 1, seq, h.task_id, position, ref, finish)
    )
    return cp_id


async def count(engine: AsyncEngine, sql: str, **params: Any) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(sql), params)).scalar_one())


async def test_restore_without_checkpoint(engine: AsyncEngine, tmp_path: Path) -> None:
    h = await harness(engine, tmp_path, done)
    stale = SQLAlchemySession(h.task_id, engine=engine)
    await stale.add_items([{"role": "user", "content": "stale"}])  # from a lost attempt
    outcome = await h.run()
    assert outcome.status == "done"
    seen = h.runner.seen
    assert seen.input_text == INSTRUCTIONS and seen.items == 0 and seen.files == ["input.txt"]


async def test_restore_truncates_session(engine: AsyncEngine, tmp_path: Path) -> None:
    h = await harness(engine, tmp_path, done)
    session = SQLAlchemySession(h.task_id, engine=engine)
    await session.add_items([{"role": "user", "content": INSTRUCTIONS}])
    await add_checkpoint(h, engine, position=1, files={"edit.txt": "kept"})
    # Items saved after that checkpoint, by an attempt that was then lost.
    await session.add_items(
        [{"role": "user", "content": "after-1"}, {"role": "user", "content": "after-2"}]
    )
    await h.run(attempt=2)
    seen = h.runner.seen
    assert seen.input_text == CONTINUE_MESSAGE and seen.items == 1
    assert seen.files == ["edit.txt"]


async def test_lost_attempt_usage_is_seeded_and_counted(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    h = await harness(engine, tmp_path, done)
    outcome = await h.run(attempt=2, details={"tokens_in": 50, "tool_calls": 2})
    assert (outcome.tokens_in, outcome.tool_calls, outcome.attempts) == (70, 2, 2)


async def test_lost_attempt_tokens_count_against_budget(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    async def wants_a_model_call(
        seen: Seen, before: BeforeModelCall, usage: Usage, w: Path, s: Session
    ) -> RunResult:
        try:
            await before(usage)
        except StopRun as e:
            return RunResult("continue", usage, summary=str(e))
        usage.tokens_in += 100  # a model call that must not happen
        return RunResult("done", usage)

    h = await harness(engine, tmp_path, wants_a_model_call)
    # The lost attempt used the whole remaining budget: no further model call.
    outcome = await h.run(attempt=2, details={"tokens_in": 100}, remaining_tokens=100)
    assert outcome.status == "continue" and "budget" in outcome.summary
    assert outcome.tokens_in == 100


async def test_usage_is_heartbeated_live(engine: AsyncEngine, tmp_path: Path) -> None:
    async def slow(
        seen: Seen, before: BeforeModelCall, usage: Usage, w: Path, s: Session
    ) -> RunResult:
        await before(usage)
        usage.tokens_in += 100
        usage.tool_calls += 1
        await asyncio.sleep(2.5)  # e.g. a long command after the model call
        return RunResult("done", usage)

    h = await harness(engine, tmp_path, slow)
    await h.run()
    during = [d for t, d in h.heartbeats if t < h.runner.seen.started_at + 2.4]
    assert any(d["tokens_in"] == 100 and d["tool_calls"] == 1 for d in during)
    assert all(d["attempts"] == 1 for _, d in h.heartbeats)  # the real attempt (M1)
    assert all(
        d.get("checkpoint_id") for t, d in h.heartbeats if t > h.runner.seen.started_at + 0.5
    )


async def test_heartbeats_during_restore(engine: AsyncEngine, tmp_path: Path) -> None:
    class SlowBlobs(MemoryBlobStore):
        async def get(self, ref: BlobRef) -> bytes:
            await asyncio.sleep(2.5)
            return await super().get(ref)

    h = await harness(engine, tmp_path, done, blobs=SlowBlobs())
    began = time.monotonic()
    await h.run()
    before_runner = [t for t, _ in h.heartbeats if t < h.runner.seen.started_at]
    assert len(before_runner) >= 2 and before_runner[0] - began < 1.0


async def test_superseded_attempt_writes_nothing(engine: AsyncEngine, tmp_path: Path) -> None:
    h = await harness(engine, tmp_path, done)
    async with engine.begin() as conn:  # a newer attempt already owns the turn
        await conn.execute(
            text(
                "INSERT INTO task_attempts (task_id, turn, attempt, worker_identity, outcome, "
                "retention_class) VALUES (:t, 1, 2, 'other', 'started', 'audit')"
            ),
            {"t": h.task_id},
        )
    with pytest.raises(Exception, match="newer attempt") as raised:
        await h.run(attempt=1)
    assert isinstance(raised.value, Superseded) or "Superseded" in repr(raised.value)
    assert (
        await count(engine, "SELECT count(*) FROM checkpoints WHERE task_id = :t", t=h.task_id) == 0
    )
    outcome = await count(
        engine,
        "SELECT count(*) FROM task_attempts "
        "WHERE task_id = :t AND attempt = 1 AND outcome = 'started'",
        t=h.task_id,
    )
    assert outcome == 0  # a stale attempt writes no row at all (review F28)


async def test_finish_does_not_overwrite_a_lost_row(engine: AsyncEngine, tmp_path: Path) -> None:
    async def lost_meanwhile(
        seen: Seen, before: BeforeModelCall, usage: Usage, w: Path, s: Session
    ) -> RunResult:
        await before(usage)
        async with engine.begin() as conn:  # attempt 2 started and marked us lost
            await conn.execute(
                text(
                    "UPDATE task_attempts SET outcome = 'lost' WHERE task_id = :t AND attempt = 1"
                ),
                {"t": seen_task[0]},
            )
        return RunResult("done", usage)

    seen_task: list[str] = []
    h = await harness(engine, tmp_path, lost_meanwhile)
    seen_task.append(h.task_id)
    await h.run(attempt=1)
    lost = await count(
        engine,
        "SELECT count(*) FROM task_attempts "
        "WHERE task_id = :t AND attempt = 1 AND outcome = 'lost'",
        t=h.task_id,
    )
    assert lost == 1


async def test_terminal_failure_does_not_close_a_newer_attempt(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """A stale Activity that fails after its retry starts may close only itself;
    the newer attempt remains authoritative and open (gate follow-up N1)."""

    async def fail_after_retry_started(
        seen: Seen, before: BeforeModelCall, usage: Usage, w: Path, s: Session
    ) -> RunResult:
        await AttemptRepository(engine).start(seen_task[0], 1, 2, "replacement-worker")
        raise HarnessInputError("stale attempt failed after its retry started")

    seen_task: list[str] = []
    h = await harness(engine, tmp_path, fail_after_retry_started)
    seen_task.append(h.task_id)
    with pytest.raises(ApplicationError) as raised:
        await h.run(attempt=1)
    assert raised.value.type == "HarnessInputError"
    assert await open_rows(engine, h.task_id) == [
        (1, "lost", "lost_or_timed_out"),
        (2, "started", None),
    ]


async def test_finish_shortcut(engine: AsyncEngine, tmp_path: Path) -> None:
    h = await harness(engine, tmp_path, done)
    cp_id = await add_checkpoint(
        h,
        engine,
        position=0,
        files={"order-summary.md": "x"},
        finish={"status": "done", "summary": "already finished", "questions": []},
    )
    outcome = await h.run(attempt=2)
    assert h.runner.seen.calls == 0  # the runner is not started again
    assert outcome.status == "done" and outcome.summary == "already finished"
    assert outcome.checkpoint_id == cp_id


async def test_template_refusals_are_not_attempts(engine: AsyncEngine, tmp_path: Path) -> None:
    h = await harness(engine, tmp_path, done)
    with pytest.raises(TemplateVersionUnavailable):
        await h.run(attempt=1, template_hash="sha256:other-version")
    assert h.heartbeats[-1][1]["refusals"] == 1
    assert h.runner.seen.calls == 0
    outcome = await h.run(attempt=3, details={"refusals": 2})
    assert outcome.attempts == 1


async def open_rows(engine: AsyncEngine, task_id: str) -> list[tuple[int, str, str | None]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT attempt, outcome, failure_category FROM task_attempts "
                "WHERE task_id = :t ORDER BY attempt"
            ),
            {"t": task_id},
        )
        return [(int(a), str(o), c) for a, o, c in rows]


async def test_attempts_exhausted_closes_rows_and_reports_usage(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """Attempt 6 of a turn lost 5 times: the last open row is closed as lost, and the
    error carries the turn's usage and its 5 real attempts (gate F1, F2)."""
    h = await harness(engine, tmp_path, done)
    async with engine.begin() as conn:  # attempt 5 started, then its worker was lost
        await conn.execute(
            text(
                "INSERT INTO task_attempts (task_id, turn, attempt, worker_identity, outcome, "
                "retention_class) VALUES (:t, 1, 5, 'lost-worker', 'started', 'audit')"
            ),
            {"t": h.task_id},
        )
    with pytest.raises(ApplicationError) as raised:
        await h.run(attempt=6, details={"tokens_in": 400, "tokens_out": 40, "inner_turns": 6})
    assert raised.value.type == "AttemptsExhausted" and raised.value.non_retryable
    details = raised.value.details[0]
    assert (details["tokens_in"], details["attempts"], details["inner_turns"]) == (400, 5, 6)
    assert await open_rows(engine, h.task_id) == [(5, "lost", "lost_or_timed_out")]
    assert h.runner.seen.calls == 0


async def test_missing_model_url_closes_the_row(
    engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = await harness(engine, tmp_path, done)
    monkeypatch.delenv("VLLM_BASE_URL")
    with pytest.raises(ApplicationError) as raised:
        await h.run()
    assert raised.value.type == "CapabilityError"
    assert await open_rows(engine, h.task_id) == [(1, "failed", "CapabilityError")]


async def test_complete_task_closes_rows_left_open(engine: AsyncEngine, tmp_path: Path) -> None:
    """When schedule_to_close expires no Activity code runs; complete_task closes
    the rows that were left open (gate F2)."""
    h = await harness(engine, tmp_path, done)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO task_attempts (task_id, turn, attempt, worker_identity, outcome, "
                "retention_class) VALUES (:t, 1, 3, 'gone', 'started', 'audit')"
            ),
            {"t": h.task_id},
        )
    acts = OrchestratorActivities(load_registry(), TaskRepository(engine))
    resolved = await ActivityEnvironment().run(
        acts.resolve_capabilities,
        TaskStart(
            task_id=h.task_id,
            request_id="req-1",
            profile="openai",
            template="local-default",
            instructions_ref=(await h.blobs.put(b"x", retention="task")),
        ),
    )
    await ActivityEnvironment().run(
        acts.complete_task,
        CompleteTaskInput(
            task_id=h.task_id,
            status="failed",
            failure_reason="timeout",
            resolved=resolved,
            turns=1,
            attempts=3,
            tokens_in=0,
            tokens_out=0,
            inner_turns=9,
        ),
    )
    assert await open_rows(engine, h.task_id) == [(3, "failed", "task_completed")]
    row = await TaskRepository(engine).get(h.task_id)
    assert row is not None and row["result"]["inner_turns"] == 9  # real Activity pass-through (M3)


async def test_activity_metrics_are_recorded(
    engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Activity duration and heartbeat lag are recorded (worker metrics; gate F3)."""
    from prometheus_client import REGISTRY

    count = "praxis_activity_seconds_count"
    labels = {"activity": "run_harness_turn", "outcome": "done"}
    before = REGISTRY.get_sample_value(count, labels) or 0
    lag_before = (
        REGISTRY.get_sample_value(
            "praxis_heartbeat_lag_seconds_count", {"activity": "run_harness_turn"}
        )
        or 0
    )
    token_labels = [
        {"template": "local-default@1", "direction": direction} for direction in ("in", "out")
    ]
    tokens_before = [REGISTRY.get_sample_value("praxis_tokens_total", t) or 0 for t in token_labels]
    cp_bytes_before = REGISTRY.get_sample_value("praxis_checkpoint_bytes_count") or 0
    cp_seconds_before = REGISTRY.get_sample_value("praxis_checkpoint_seconds_count") or 0
    bytes_sum_before = REGISTRY.get_sample_value("praxis_checkpoint_bytes_sum") or 0
    seconds_sum_before = REGISTRY.get_sample_value("praxis_checkpoint_seconds_sum") or 0

    # Build the expected archives independently of the instrumented pack calls.
    expected = tmp_path / "expected"
    expected.mkdir()
    (expected / "input.txt").write_bytes(b"input data")
    first_size = len(ws.pack(expected))
    (expected / "edit.txt").write_text("recorded edit")
    final_size = len(ws.pack(expected))
    pack = ws.pack
    elapsed = iter((0.25, 0.5))
    clock = [100.0]

    def timed_pack(root: Path) -> bytes:
        data = pack(root)
        clock[0] += next(elapsed)
        return data

    # Replace only this module's clock, leaving asyncio's real clock intact.
    monkeypatch.setattr(
        "harness_activity.activity.time", SimpleNamespace(monotonic=lambda: clock[0])
    )
    monkeypatch.setattr(ws, "pack", timed_pack)

    async def measured_run(
        seen: Seen, before: BeforeModelCall, usage: Usage, w: Path, s: Session
    ) -> RunResult:
        await before(usage)
        (w / "edit.txt").write_text("recorded edit")
        usage.tokens_in += 20
        usage.tokens_out += 7
        return RunResult("done", usage, summary="ok")

    h = await harness(engine, tmp_path, measured_run)
    await h.run()
    assert REGISTRY.get_sample_value(count, labels) == before + 1
    for labels_, baseline, used in zip(token_labels, tokens_before, (20, 7), strict=True):
        assert REGISTRY.get_sample_value("praxis_tokens_total", labels_) == baseline + used
    assert REGISTRY.get_sample_value("praxis_checkpoint_bytes_count") == cp_bytes_before + 2
    assert REGISTRY.get_sample_value("praxis_checkpoint_seconds_count") == cp_seconds_before + 2
    assert (
        REGISTRY.get_sample_value("praxis_checkpoint_bytes_sum")
        == bytes_sum_before + first_size + final_size
    )
    assert REGISTRY.get_sample_value("praxis_checkpoint_seconds_sum") == seconds_sum_before + 0.75
    lag_after = REGISTRY.get_sample_value(
        "praxis_heartbeat_lag_seconds_count", {"activity": "run_harness_turn"}
    )
    assert (lag_after or 0) > lag_before


async def test_log_lines_carry_request_and_task_ids(
    engine: AsyncEngine, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Harness and orchestrator log lines carry the request, task and workflow IDs
    (RFC Observability; gate F8)."""
    caplog.set_level(logging.INFO)
    h = await harness(engine, tmp_path, done)
    await h.run()
    acts = OrchestratorActivities(load_registry(), TaskRepository(engine))
    env = ActivityEnvironment()
    env.info = dataclasses.replace(env.info, workflow_id=h.task_id)
    await env.run(
        acts.resolve_capabilities,
        TaskStart(
            task_id=h.task_id,
            request_id="req-activity-test",
            profile="openai",
            template="local-default",
            instructions_ref=(await h.blobs.put(b"y", retention="task")),
        ),
    )
    lines = [json.loads(JsonFormatter().format(r)) for r in caplog.records]
    harness_line = next(x for x in lines if x["logger"] == "praxis.harness")
    orchestrator_line = next(x for x in lines if x["logger"] == "praxis.orchestrator")
    for line in (harness_line, orchestrator_line):
        assert line["request_id"] == "req-activity-test"
        assert line["task_id"] == h.task_id and line["workflow_id"] == h.task_id
    assert harness_line["turn"] == 1 and harness_line["worker"] == "test-worker"


async def start_newer(engine: AsyncEngine, task_id: str) -> None:
    from common.persistence.repositories import AttemptRepository

    await AttemptRepository(engine).start(task_id, 1, 2, "other")


async def test_newer_attempt_mid_run_fences_the_finish(engine: AsyncEngine, tmp_path: Path) -> None:
    """D10 at Activity level (review F5): the newer attempt starts after the stale
    one's last pre-call check, so only the fenced finish checkpoint can stop it."""

    async def script(
        seen: Seen, before: BeforeModelCall, usage: Usage, ws_: Path, s: Session
    ) -> RunResult:
        await before(usage)  # current: checkpoint 0 is committed
        await start_newer(engine, h.task_id)
        return RunResult("done", usage, summary="ok")

    h = await harness(engine, tmp_path, script)
    with pytest.raises(Exception) as raised:
        await h.run(attempt=1)
    assert isinstance(raised.value, Superseded) or "Superseded" in repr(raised.value)
    sql = "SELECT count(*) FROM checkpoints WHERE task_id = :t AND finish IS NOT NULL"
    assert await count(engine, sql, t=h.task_id) == 0
    rows = (
        "SELECT count(*) FROM task_attempts WHERE task_id = :t AND attempt = 1 AND outcome = 'done'"
    )
    assert await count(engine, rows, t=h.task_id) == 0


async def test_newer_attempt_before_publication_blocks_artifacts(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """D10 for artifact publication (review F6): a newer attempt that starts after the
    finish checkpoint stops the stale attempt before any audit blob is written."""

    async def script(
        seen: Seen, before: BeforeModelCall, usage: Usage, ws: Path, s: Session
    ) -> RunResult:
        await before(usage)
        (ws / "out.txt").write_text("result")
        return RunResult("done", usage, summary="ok")

    h = await harness(engine, tmp_path, script)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE tasks SET outputs = :o WHERE task_id = :t"),
            {"o": '["out.txt"]', "t": h.task_id},
        )
    original = h.acts.checkpoints.insert_fenced

    async def then_newer(cp: Any) -> None:
        await original(cp)
        if cp.finish is not None:
            await start_newer(engine, h.task_id)

    h.acts.checkpoints.insert_fenced = then_newer  # type: ignore[method-assign]
    with pytest.raises(Exception) as raised:
        await h.run(attempt=1)
    assert isinstance(raised.value, Superseded) or "Superseded" in repr(raised.value)
    audit = [o for o in h.blobs.objects.values() if o.retention == "audit"]
    assert audit == []


async def test_session_store_contract(engine: AsyncEngine) -> None:
    """The production store meets the same contract as the conformance store (R3)."""
    from harness_activity.session_store import SQLAlchemySessionStore
    from tests.support.session_stores import store_contract

    await store_contract(SQLAlchemySessionStore(f"task-store-{run_id()}", engine))


# Phase 2 events plan task 2.2: the attempt's event stream (R5, R6, R8, R9).


async def stored(t: EventTransport, task_id: str) -> list[Any]:
    return [i[1] async for i in t.read(task_id, 0) if not isinstance(i, Expired)]


class Superseding(TableTransport):
    """Starts a newer attempt of the turn just before its first publish, so the
    attempt's flush is refused."""

    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__(engine)
        self.fired = False

    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[Any]
    ) -> None:
        if not self.fired:
            self.fired = True
            await AttemptRepository(self.engine).start(
                writer.task_id, writer.turn, writer.attempt + 1, "other-worker"
            )
        await super().publish(workflow_id, writer, batch_id, events)


async def finish_writes(engine: AsyncEngine, task_id: str, attempt: int) -> tuple[int, str]:
    checkpoints = await count(
        engine, "SELECT count(*) FROM checkpoints WHERE task_id = :t AND attempt = :a",
        t=task_id, a=attempt,
    )  # fmt: skip
    async with engine.connect() as conn:
        outcome = (
            await conn.execute(
                text("SELECT outcome FROM task_attempts WHERE task_id = :t AND attempt = :a"),
                {"t": task_id, "a": attempt},
            )
        ).scalar_one()
    return checkpoints, outcome


async def test_an_attempt_opens_with_reset_and_ends_with_status(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    t = TableTransport(engine)
    h = await harness(engine, tmp_path, done, events=t)
    outcome = await h.run()
    assert outcome.status == "done"
    events = await stored(t, h.task_id)
    assert [(e.seq, e.type) for e in events] == [(0, "reset"), (1, "status")]
    assert events[0].payload == {"restored_from": None}
    assert events[1].payload == {"status": "done"}
    assert {e.attempt_id for e in events} == {f"{h.task_id}:1:1"}


async def test_a_retried_attempt_resets_from_its_checkpoint(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """R9: after a lost attempt 1, attempt 2's events start with a reset naming the
    checkpoint it restored, and offsets follow seq within each attempt."""
    t = TableTransport(engine)

    async def emits(seen: Seen, before: BeforeModelCall, usage: Usage, w: Path, s: Session) -> Any:
        await before(usage)
        return RunResult("done", usage, summary="ok")

    h = await harness(engine, tmp_path, emits, events=t)
    await AttemptRepository(engine).start(h.task_id, 1, 1, "lost-worker")
    cp_id = await add_checkpoint(h, engine, position=0, files={"a.txt": "x"})
    await h.run(attempt=2)
    events = await stored(t, h.task_id)
    assert events[0].type == "reset" and events[0].payload == {"restored_from": cp_id}
    assert [e.seq for e in events] == list(range(len(events)))
    assert events[-1].payload == {"status": "done"}


async def test_a_refused_final_flush_makes_no_finish_write(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """R5 on the normal path: no finish checkpoint, artifact or outcome row."""
    t = Superseding(engine)

    async def no_model_call(
        seen: Seen, b: BeforeModelCall, usage: Usage, w: Path, s: Session
    ) -> Any:
        (w / "order-summary.md").write_text("summary")
        return RunResult("done", usage, summary="ok")

    h = await harness(engine, tmp_path, no_model_call, events=t)
    with pytest.raises(Exception, match="newer attempt") as raised:
        await h.run()
    assert isinstance(raised.value, Superseded) or "Superseded" in repr(raised.value)
    # The newer attempt marked this one lost; this attempt wrote no finish.
    assert await finish_writes(engine, h.task_id, 1) == (0, "lost")
    assert await stored(t, h.task_id) == []


async def test_a_refused_flush_on_the_finish_shortcut_makes_no_finish_write(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """R5 on the restore short-circuit: a checkpoint already holds the finish."""
    t = Superseding(engine)
    h = await harness(engine, tmp_path, done, events=t)
    await AttemptRepository(engine).start(h.task_id, 1, 1, "lost-worker")
    await add_checkpoint(
        h, engine, position=0, files={"order-summary.md": "x"},
        finish={"status": "done", "summary": "already finished", "questions": []},
    )  # fmt: skip
    with pytest.raises(Exception, match="newer attempt"):
        await h.run(attempt=2)
    assert h.runner.seen.calls == 0
    assert await finish_writes(engine, h.task_id, 2) == (0, "lost")


async def test_a_runner_failure_stores_its_events_and_keeps_its_error(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """R8: a failing attempt's events, with a final status, are stored; the
    runner's classified failure still reaches Temporal."""
    t = TableTransport(engine)

    async def fails(seen: Seen, b: BeforeModelCall, usage: Usage, w: Path, s: Session) -> Any:
        raise RunnerFailure("DshTurnDeadline", True)

    h = await harness(engine, tmp_path, fails, events=t)
    with pytest.raises(ApplicationError) as raised:
        await h.run()
    assert raised.value.type == "DshTurnDeadline"
    events = await stored(t, h.task_id)
    assert [e.type for e in events] == ["reset", "status"]
    assert events[-1].payload == {"status": "failed", "error": "DshTurnDeadline"}


async def test_a_cancelled_attempt_stores_its_events(engine: AsyncEngine, tmp_path: Path) -> None:
    """R8 under cancellation: the flush runs shielded and the cancel propagates."""
    t = TableTransport(engine)
    started = asyncio.Event()

    async def waits(seen: Seen, b: BeforeModelCall, usage: Usage, w: Path, s: Session) -> Any:
        started.set()
        await asyncio.sleep(60)
        raise AssertionError("not cancelled")

    h = await harness(engine, tmp_path, waits, events=t)
    env = h.env()
    running = asyncio.create_task(env.run(h.acts.run_harness_turn, h.turn()))
    await asyncio.wait_for(started.wait(), 10)
    env.cancel()
    with pytest.raises(BaseException) as raised:
        await asyncio.wait_for(running, 20)
    assert isinstance(raised.value, asyncio.CancelledError) or "Cancel" in repr(raised.value)
    events = await stored(t, h.task_id)
    assert [e.type for e in events] == ["reset", "status"]
    assert events[-1].payload["status"] == "cancelled"


async def test_an_attempt_that_fails_early_still_opens_with_reset(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """R9: a failure before the runner starts (here, opening the attempt) still
    stores a reset first, then the failure status."""
    t = TableTransport(engine)
    h = await harness(engine, tmp_path, done, events=t)

    async def cannot_open(context: Any) -> Any:
        raise RuntimeError("launcher unreachable")

    h.acts.open_attempt = cannot_open
    with pytest.raises(Exception, match="launcher unreachable"):
        await h.run()
    events = await stored(t, h.task_id)
    assert [e.type for e in events] == ["reset", "status"]
    assert events[0].payload == {"restored_from": None}
    assert events[1].payload == {"status": "failed", "error": "RuntimeError"}


class HangsAlways(TableTransport):
    """Every publish blocks, as a database that stopped answering; it records the
    events it was asked to store."""

    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__(engine)
        self.asked: list[Any] = []

    async def publish(
        self, workflow_id: str, writer: Writer, batch_id: str, events: list[Any]
    ) -> None:
        self.asked.extend(events)
        await asyncio.sleep(3600)


async def test_a_final_flush_that_times_out_raises_events_unavailable(
    engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8, D2: the bounded final flush fails retryably with EventsUnavailable, makes
    no finish write, and the failure path does not wait on it again."""
    from harness_activity import events as events_module

    monkeypatch.setattr(events_module, "CLOSE_TIMEOUT_S", 0.3)

    async def finishes(seen: Seen, b: BeforeModelCall, u: Usage, w: Path, s: Session) -> Any:
        return RunResult("done", u, summary="ok")  # no model call: no mid-turn checkpoint

    hangs = HangsAlways(engine)
    h = await harness(engine, tmp_path, finishes, events=hangs)
    with pytest.raises(Exception) as raised:
        await asyncio.wait_for(h.run(), 10)
    assert "EventsUnavailable" in repr(raised.value) or type(raised.value).__name__ == (
        "EventsUnavailable"
    )
    assert await finish_writes(engine, h.task_id, 1) == (0, "started")
    assert [e.type for e in hangs.asked].count("status") == 1  # no second status


async def test_a_failed_checkpoint_lookup_still_opens_with_reset(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """R9: the failure path emits the reset when the lookup itself failed."""
    t = TableTransport(engine)
    h = await harness(engine, tmp_path, done, events=t)

    async def lookup_fails(task_id: str) -> Any:
        raise ConnectionError("database unreachable")

    h.acts.checkpoints.latest = lookup_fails  # type: ignore[method-assign]
    with pytest.raises(Exception, match="database unreachable"):
        await h.run()
    events = await stored(t, h.task_id)
    assert [e.type for e in events] == ["reset", "status"]
    assert events[1].payload == {"status": "failed", "error": "ConnectionError"}


async def test_a_lost_waiting_turn_keeps_its_outputs_without_rerunning(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """Phase 2 messaging D18: a `waiting` finish is recorded like `done`, so a lost
    attempt after it goes straight to finish, with the turn's outputs."""
    h = await harness(engine, tmp_path, done)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE tasks SET outputs = CAST(:o AS json) WHERE task_id = :t"),
            {"o": '["order-summary.md"]', "t": h.task_id},
        )
    await AttemptRepository(engine).start(h.task_id, 1, 1, "lost-worker")
    await add_checkpoint(
        h, engine, position=0, files={"order-summary.md": "draft"},
        finish={"status": "waiting", "summary": "asked B", "questions": []},
    )  # fmt: skip
    outcome = await h.run(attempt=2)
    assert h.runner.seen.calls == 0
    assert outcome.status == "waiting" and outcome.summary == "asked B"
    assert [a.path for a in outcome.outputs] == ["order-summary.md"]


class ChecksFinish(ScriptedRunner):
    """Calls the config's finish check from a worker thread, as a tool body does."""

    async def run(self, config: HarnessConfig, *args: Any) -> RunResult:
        assert config.finish_check is not None
        self.blocking = await asyncio.to_thread(config.finish_check)
        usage: Usage = args[4]
        return RunResult("waiting", usage, summary="asked")


async def test_the_finish_check_reaches_the_inbox_from_a_tool_thread(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    """Phase 2 messaging R19: the Activity's check, called from a thread, sees the
    task's open question."""
    from common.persistence.messages import MessageRepository, Sender, idempotency_key

    h = await harness(engine, tmp_path, done)
    async with engine.begin() as conn:
        request = (await conn.execute(
            text("SELECT request_id FROM tasks WHERE task_id = :t"), {"t": h.task_id}
        )).scalar_one()  # fmt: skip
    other = f"task-act-{run_id()}"
    await TaskRepository(engine).record_task(
        TaskStart(task_id=other, request_id=request, profile="openai", template="local-default",
                  instructions_ref=await h.blobs.put(b"x", retention="task")),
        workflow_id=other, run_id="run-1", template_version=1, template_hash="x",
    )  # fmt: skip
    await AttemptRepository(engine).start(h.task_id, 1, 1, "worker")
    asked = await MessageRepository(engine).ask(
        Sender(h.task_id, 1, 1), other, "price?",
        key=idempotency_key(h.task_id, 1, "ask_agent", {}),
        wait=timedelta(minutes=5), max_wait=timedelta(minutes=10),
    )  # fmt: skip
    assert asked.ok
    runner = ChecksFinish(done)
    h.acts.runner = runner
    outcome = await h.run(attempt=2)
    assert outcome.status == "waiting"
    assert runner.blocking == [f"open question {asked.correlation_id} to {other}"]

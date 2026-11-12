"""`run_harness_turn` driven directly, with a scripted runner and the real database
(spec execution/durability, execution/task-workflow; informal durability review).

Each test fixes one durability promise that the kill tests cannot pin down:
fresh-start and truncating restore, lost-attempt usage, live heartbeats, the
superseded path, the finish shortcut and template-version refusals.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from agents.memory import Session
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio.testing import ActivityEnvironment

from common.blob_store import MemoryBlobStore
from common.errors import TemplateVersionUnavailable
from common.persistence.repositories import (
    Checkpoint,
    CheckpointRepository,
    TaskRepository,
    make_engine,
)
from common.schemas import BlobRef, TaskStart, TurnInput
from harness_activity import workspace as ws
from harness_activity.activity import CONTINUE_MESSAGE, HarnessActivities
from harness_activity.config import HarnessConfig
from harness_activity.runner import BeforeModelCall, RunResult, StopRun, Superseded, Usage
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
        )

    async def run(self, attempt: int = 1, details: dict[str, Any] | None = None, **kw: Any) -> Any:
        return await self.env(attempt, details).run(self.acts.run_harness_turn, self.turn(**kw))


async def harness(
    engine: AsyncEngine, tmp_path: Path, script: Script, blobs: Any = None
) -> Harness:
    store = blobs or MemoryBlobStore()
    task_id = f"task-act-{run_id()}"
    instructions = await store.put(INSTRUCTIONS.encode(), retention="task")
    data = await store.put(b"input data", retention="task")
    start = TaskStart(
        task_id=task_id,
        request_id="req-1",
        profile="default",
        template="local-default",
        instructions_ref=instructions,
        input_refs={"input.txt": data},
    )
    await TaskRepository(engine).record_task(
        start, workflow_id=task_id, run_id="run-1", template_version=1, template_hash="x"
    )
    runner = ScriptedRunner(script)
    acts = HarnessActivities(load_registry(), engine, store, runner, tmp_path, "test-worker")
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
    assert outcome == 1  # no outcome written by the superseded attempt


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

"""Phase 1 persistence: migration 0003, retention classes, repositories and the
openai-agents session store on our tables (specs persistence/app-database,
execution/durability, execution/task-workflow)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import MemoryBlobStore
from common.errors import TaskAlreadyExists
from common.persistence.repositories import (
    AttemptRepository,
    Checkpoint,
    CheckpointRepository,
    FenceRejected,
    RecordingBlobStore,
    TaskRepository,
    make_engine,
)
from common.persistence.retention import PHASE1_TABLES
from common.schemas import BlobRef, TaskStart
from tests.support.stack import run_id

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


def blob_ref(n: int = 0) -> BlobRef:
    return BlobRef(
        id=f"blob:{n:064x}",
        key=f"sha256/{n:064x}",
        checksum=f"sha256:{n:064x}",
        content_type="text/plain",
        bytes=1,
        retention_class="task",
        created_at=datetime.now(UTC),
    )


def task_start() -> TaskStart:
    return TaskStart(
        task_id=f"task-test-{run_id()}",
        request_id="req-1",
        profile="default",
        template="local-default",
        instructions_ref=blob_ref(),
    )


async def record(engine: AsyncEngine, start: TaskStart, run: str = "run-1") -> None:
    await TaskRepository(engine).record_task(
        start, workflow_id=start.task_id, run_id=run, template_version=1, template_hash="sha256:x"
    )


async def test_every_phase1_table_requires_retention(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE column_name = 'retention_class' AND is_nullable = 'NO'"
            )
        )
        tables = {r[0] for r in rows}
    assert set(PHASE1_TABLES) <= tables


async def test_retention_class_is_checked(engine: AsyncEngine) -> None:
    with pytest.raises(Exception, match="retention_class"):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO blob_objects "
                    "(key, checksum, bytes, content_type, retention_class) "
                    "VALUES ('k', 'c', 1, 't', 'forever')"
                )
            )


async def test_record_task_is_idempotent_per_run_and_rejects_reuse(engine: AsyncEngine) -> None:
    start = task_start()
    await record(engine, start, "run-1")
    await record(engine, start, "run-1")  # a retry from the same run
    with pytest.raises(TaskAlreadyExists):
        await record(engine, start, "run-2")
    row = await TaskRepository(engine).get(start.task_id)
    assert row is not None and row["run_id"] == "run-1" and row["retention_class"] == "audit"


async def test_restore_prefers_latest_turn(engine: AsyncEngine) -> None:
    start = task_start()
    await record(engine, start)
    repo = CheckpointRepository(engine)
    for turn, attempt, seq in [(1, 1, 0), (1, 3, 4), (2, 1, 0), (1, 2, 9)]:
        await repo.insert(
            Checkpoint(
                f"cp-{start.task_id}-{turn}-{attempt}-{seq}",
                start.task_id,
                turn,
                attempt,
                seq,
                start.task_id,
                seq,
                blob_ref(seq),
                None,
            )
        )
    latest = await repo.latest(start.task_id)
    assert latest is not None and (latest.turn, latest.attempt, latest.seq) == (2, 1, 0)
    assert await repo.latest("task-none-0000000") is None


async def test_new_attempt_marks_previous_lost(engine: AsyncEngine) -> None:
    start = task_start()
    await record(engine, start)
    attempts = AttemptRepository(engine)
    await attempts.start(start.task_id, 1, 1, "worker-a")
    await attempts.start(start.task_id, 1, 2, "worker-b")
    assert await attempts.newer_attempt_exists(start.task_id, 1, 1)
    async with engine.connect() as conn:
        rows: dict[int, str] = dict(
            (
                await conn.execute(
                    text("SELECT attempt, outcome FROM task_attempts WHERE task_id = :t"),
                    {"t": start.task_id},
                )
            ).all()
        )
    assert rows == {1: "lost", 2: "started"}


async def test_recording_blob_store_keeps_strongest_class(engine: AsyncEngine) -> None:
    store = RecordingBlobStore(MemoryBlobStore(), engine)
    data = f"recording {run_id()}".encode()
    ref = await store.put(data, retention="ephemeral")
    await store.put(data, retention="audit")
    await store.put(data, retention="task")
    async with engine.connect() as conn:
        cls = (
            await conn.execute(
                text("SELECT retention_class FROM blob_objects WHERE key = :k"), {"k": ref.key}
            )
        ).scalar_one()
    assert cls == "audit"
    await store.delete(ref)


async def test_sdk_session_uses_migrated_tables(engine: AsyncEngine) -> None:
    session_id = f"task-session-{run_id()}"
    session = SQLAlchemySession(session_id, engine=engine)  # create_tables=False
    await session.add_items(
        [{"role": "user", "content": "hello"}, {"role": "user", "content": "x"}]
    )
    assert len(await session.get_items()) == 2
    await session.pop_item()
    assert len(await session.get_items()) == 1
    async with engine.connect() as conn:
        classes = {
            r[0]
            for r in await conn.execute(
                text(
                    "SELECT retention_class FROM agent_messages WHERE session_id = :s "
                    "UNION SELECT retention_class FROM agent_sessions WHERE session_id = :s"
                ),
                {"s": session_id},
            )
        }
    assert classes == {"task"}
    await session.clear_session()


def checkpoint_for(task_id: str, turn: int, attempt: int) -> Checkpoint:
    return Checkpoint(
        f"{task_id}:{turn}:{attempt}:0", task_id, turn, attempt, 0, task_id, 0, blob_ref(), None
    )


async def test_stale_attempt_cannot_checkpoint_or_finish(engine: AsyncEngine) -> None:
    """D10: the newer-attempt check and the write are one statement."""
    start = task_start()
    await record(engine, start)
    attempts, checkpoints = AttemptRepository(engine), CheckpointRepository(engine)
    await attempts.start(start.task_id, 1, 1, "worker-a")
    await checkpoints.insert_fenced(checkpoint_for(start.task_id, 1, 1))  # current: allowed
    await attempts.start(start.task_id, 1, 2, "worker-b")
    with pytest.raises(FenceRejected):
        await checkpoints.insert_fenced(checkpoint_for(start.task_id, 1, 1))
    with pytest.raises(FenceRejected):
        await attempts.finish(
            start.task_id,
            1,
            1,
            outcome="done",
            tokens_in=1,
            tokens_out=1,
            tool_calls=0,
            fenced=True,
        )
    assert await checkpoints.count(start.task_id) == 1
    await attempts.finish(
        start.task_id, 1, 2, outcome="done", tokens_in=1, tokens_out=1, tool_calls=0, fenced=True
    )


async def test_older_turn_is_fenced_by_a_newer_turn(engine: AsyncEngine) -> None:
    start = task_start()
    await record(engine, start)
    attempts, checkpoints = AttemptRepository(engine), CheckpointRepository(engine)
    await attempts.start(start.task_id, 1, 1, "worker-a")
    await attempts.start(start.task_id, 2, 1, "worker-a")
    with pytest.raises(FenceRejected):
        await checkpoints.insert_fenced(checkpoint_for(start.task_id, 1, 1))


async def test_fenced_insert_waits_for_a_concurrent_start(engine: AsyncEngine) -> None:
    """D10 under concurrency: a newer attempt's uncommitted start must still fence
    the stale attempt's checkpoint (review F1)."""
    import asyncio

    start = task_start()
    await record(engine, start)
    attempts, checkpoints = AttemptRepository(engine), CheckpointRepository(engine)
    await attempts.start(start.task_id, 1, 1, "worker-a")
    async with engine.begin() as conn:  # attempt 2's start, still in flight
        await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:t))"), {"t": start.task_id})
        await conn.execute(
            text(
                "INSERT INTO task_attempts (task_id, turn, attempt, worker_identity, outcome, "
                "retention_class) VALUES (:t, 1, 2, 'worker-b', 'started', 'audit')"
            ),
            {"t": start.task_id},
        )
        stale = asyncio.create_task(checkpoints.insert_fenced(checkpoint_for(start.task_id, 1, 1)))
        await asyncio.sleep(0.3)
        assert not stale.done()  # the stale insert waits for the task lock
    with pytest.raises(FenceRejected):
        await stale


async def test_start_waits_for_the_task_lock(engine: AsyncEngine) -> None:
    """The real `start` takes the per-task lock (review F26)."""
    import asyncio

    start = task_start()
    await record(engine, start)
    attempts = AttemptRepository(engine)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:t))"), {"t": start.task_id})
        starting = asyncio.create_task(attempts.start(start.task_id, 1, 1, "worker-a"))
        await asyncio.sleep(0.3)
        assert not starting.done()
    await starting


async def test_refusal_fences_older_attempts(engine: AsyncEngine) -> None:
    """A refused Temporal attempt is still newer than the attempts before it (F27)."""
    start = task_start()
    await record(engine, start)
    attempts, checkpoints = AttemptRepository(engine), CheckpointRepository(engine)
    await attempts.start(start.task_id, 1, 1, "worker-a")
    await attempts.record_refusal(start.task_id, 1, 2, "worker-b")
    with pytest.raises(FenceRejected):
        await checkpoints.insert_fenced(checkpoint_for(start.task_id, 1, 1))
    with pytest.raises(FenceRejected):
        await attempts.finish(
            start.task_id,
            1,
            1,
            outcome="done",
            tokens_in=1,
            tokens_out=1,
            tool_calls=0,
            fenced=True,
        )
    await attempts.start(start.task_id, 1, 3, "worker-c")  # the next real attempt runs


async def test_late_stale_start_is_refused(engine: AsyncEngine) -> None:
    """A stale attempt that only reaches `start` after a newer one writes no row (F28)."""
    start = task_start()
    await record(engine, start)
    attempts = AttemptRepository(engine)
    await attempts.start(start.task_id, 1, 2, "worker-b")
    with pytest.raises(FenceRejected):
        await attempts.start(start.task_id, 1, 1, "worker-a")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT attempt FROM task_attempts WHERE task_id = :t"), {"t": start.task_id}
            )
        ).all()
    assert [r[0] for r in rows] == [2]


async def test_fenced_finish_rejects_a_newer_turn(engine: AsyncEngine) -> None:
    """The fence clause inside the finish UPDATE does the work for a newer turn (F29)."""
    start = task_start()
    await record(engine, start)
    attempts = AttemptRepository(engine)
    await attempts.start(start.task_id, 1, 1, "worker-a")
    await attempts.start(start.task_id, 2, 1, "worker-a")
    with pytest.raises(FenceRejected):
        await attempts.finish(
            start.task_id,
            1,
            1,
            outcome="done",
            tokens_in=1,
            tokens_out=1,
            tool_calls=0,
            fenced=True,
        )
    async with engine.connect() as conn:
        outcome = (
            await conn.execute(
                text("SELECT outcome FROM task_attempts WHERE task_id = :t AND turn = 1"),
                {"t": start.task_id},
            )
        ).scalar_one()
    assert outcome == "started"


async def test_checkpoint_round_trips_a_session_blob(engine: AsyncEngine) -> None:
    """D1: a DSH checkpoint carries its session blob ref and digest (task 2.1)."""
    start = task_start()
    await record(engine, start)
    attempts, checkpoints = AttemptRepository(engine), CheckpointRepository(engine)
    await attempts.start(start.task_id, 1, 1, "worker-a")
    cp = checkpoint_for(start.task_id, 1, 1)
    session = blob_ref(7)
    await checkpoints.insert_fenced(
        Checkpoint(
            cp.checkpoint_id, cp.task_id, 1, 1, 0, cp.session_id, 0, cp.workspace_ref, None,
            session_ref=session, session_digest="sha256:" + "f" * 64,
        )
    )  # fmt: skip
    latest = await checkpoints.latest(start.task_id)
    assert latest is not None and latest.session_ref == session
    assert latest.session_digest == "sha256:" + "f" * 64 and latest.session_position == 0


async def test_unknown_usage_is_stored_as_null_never_zero(engine: AsyncEngine) -> None:
    """D7, R12: an attempt whose usage was not observed keeps NULL tokens."""
    start = task_start()
    await record(engine, start)
    attempts = AttemptRepository(engine)
    await attempts.start(start.task_id, 1, 1, "worker-a")
    await attempts.finish(
        start.task_id, 1, 1, outcome="failed", tokens_in=None, tokens_out=None, tool_calls=0,
        fenced=True, usage_known=False,
    )  # fmt: skip
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT tokens_in, tokens_out, usage_known FROM task_attempts "
                    "WHERE task_id = :t"
                ),
                {"t": start.task_id},
            )
        ).one()
    assert tuple(row) == (None, None, False)

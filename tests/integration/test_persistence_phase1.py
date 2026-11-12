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

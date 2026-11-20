"""Every writer of a stored `BlobRef` indexes it in its own transaction (Phase 3A
persistence plan phase 01 task 2.1; R1, D2)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.events import TableTransport, Writer
from common.persistence.fence import FenceRejected
from common.persistence.messages import MessageRepository
from common.persistence.refs import DELETE_OPERATION, index_refs, upload_holder
from common.persistence.repositories import (
    AttemptRepository,
    Checkpoint,
    CheckpointRepository,
    TaskRepository,
    make_engine,
)
from common.schemas import BlobRef, TaskStart
from common.schemas.events import AgentEvent

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


def blob_ref(label: str) -> BlobRef:
    hexdigest = uuid.uuid5(uuid.NAMESPACE_URL, label).hex * 2
    return BlobRef(
        id=f"blob:{hexdigest}",
        key=f"sha256/{hexdigest}",
        checksum=f"sha256:{hexdigest}",
        content_type="text/plain",
        bytes=1,
        retention_class="transcript",
        created_at=datetime.now(UTC),
    )


def new_task() -> str:
    return f"task-test-{uuid.uuid4().hex[:12]}"


async def index_rows(engine: AsyncEngine, task_id: str) -> set[tuple[str, str, str, str, str]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT holder_table, holder_key, holder_column, blob_key, retention_class "
                "FROM blob_refs WHERE task_id = :t AND removed_at IS NULL"
            ),
            {"t": task_id},
        )
        return {tuple(r) for r in rows}


async def record(engine: AsyncEngine, task_id: str, request: str = "req-index") -> TaskStart:
    start = TaskStart(
        task_id=task_id,
        request_id=request,
        profile="openai",
        template="local-default",
        instructions_ref=blob_ref(f"{task_id} instructions"),
        input_refs={"a.txt": blob_ref(f"{task_id} a"), "b.txt": blob_ref(f"{task_id} b")},
    )
    await TaskRepository(engine).record_task(
        start, workflow_id=task_id, run_id="run-1", template_version=1, template_hash="sha256:x"
    )
    return start


async def test_record_task_indexes_instructions_and_inputs(engine: AsyncEngine) -> None:
    task = new_task()
    start = await record(engine, task)
    await record(engine, task)  # a retry of the same run changes nothing
    assert await index_rows(engine, task) == {
        ("tasks", task, "instructions_ref", start.instructions_ref.key, "transcript"),
        ("tasks", task, "input_refs", start.input_refs["a.txt"].key, "transcript"),
        ("tasks", task, "input_refs", start.input_refs["b.txt"].key, "transcript"),
    }
    async with engine.connect() as conn:
        requests = await conn.execute(
            text("SELECT DISTINCT request_id FROM blob_refs WHERE task_id = :t"), {"t": task}
        )
        assert [r[0] for r in requests] == ["req-index"]


def checkpoint(task: str, attempt: int, session: bool = True) -> Checkpoint:
    return Checkpoint(
        f"{task}:1:{attempt}:0",
        task,
        1,
        attempt,
        0,
        task,
        0,
        blob_ref(f"{task} workspace {attempt}"),
        None,
        session_ref=blob_ref(f"{task} session {attempt}") if session else None,
    )


async def test_checkpoint_inserts_index_their_blobs(engine: AsyncEngine) -> None:
    task = new_task()
    await record(engine, task)
    await AttemptRepository(engine).start(task, 1, 1, "worker-a")
    fenced = checkpoint(task, 1)
    await CheckpointRepository(engine).insert_fenced(fenced)
    unfenced = Checkpoint(f"{task}:2:1:0", task, 2, 1, 0, task, 0, blob_ref(f"{task} ws2"), None)
    await CheckpointRepository(engine).insert(unfenced)
    rows = {r for r in await index_rows(engine, task) if r[0] == "checkpoints"}
    assert rows == {
        ("checkpoints", f"{task}/1/1/0", "workspace_ref", fenced.workspace_ref.key, "checkpoint"),
        (
            "checkpoints",
            f"{task}/1/1/0",
            "session_ref",
            blob_ref(f"{task} session 1").key,
            "checkpoint",
        ),
        ("checkpoints", f"{task}/2/1/0", "workspace_ref", unfenced.workspace_ref.key, "checkpoint"),
    }


async def test_refused_fenced_checkpoint_leaves_no_index_row(engine: AsyncEngine) -> None:
    task = new_task()
    await record(engine, task)
    attempts = AttemptRepository(engine)
    await attempts.start(task, 1, 1, "worker-a")
    await attempts.start(task, 1, 2, "worker-b")
    with pytest.raises(FenceRejected):
        await CheckpointRepository(engine).insert_fenced(checkpoint(task, 1))
    assert {r for r in await index_rows(engine, task) if r[0] == "checkpoints"} == set()


async def test_event_publish_indexes_attachments(engine: AsyncEngine) -> None:
    task = new_task()
    await record(engine, task)
    attachment = blob_ref(f"{task} attachment")
    events = [
        AgentEvent(
            seq=i,
            timestamp=datetime.now(UTC),
            workflow_id=task,
            task_id=task,
            attempt_id=f"{task}:1:1",
            type="tool_result",
            payload={},
            blob_ref=attachment if i == 1 else None,
        )
        for i in range(2)
    ]
    await TableTransport(engine).publish(task, Writer(task, 1, 1), f"{task}:1:1:0", events)
    rows = {r for r in await index_rows(engine, task) if r[0] == "agent_events"}
    assert rows == {("agent_events", f"{task}/2", "blob_ref", attachment.key, "transcript")}


async def test_conflict_keeps_the_stronger_class_and_a_delete_mark(engine: AsyncEngine) -> None:
    task = new_task()
    ref = blob_ref(f"{task} upload")
    async with engine.begin() as conn:
        await index_refs(conn, upload_holder(task), [ref], task_id=task, retention="artifact")
        await index_refs(conn, upload_holder(task), [ref], task_id=task, retention="checkpoint")
    assert await index_rows(engine, task) == {("upload", task, "", ref.key, "artifact")}

    for removed_by, live in (("gc:op-1", True), (f"{DELETE_OPERATION}op-2", False)):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE blob_refs SET removed_at = now(), removed_by = :by WHERE task_id = :t"
                ),
                {"t": task, "by": removed_by},
            )
            await index_refs(conn, upload_holder(task), [ref], task_id=task, retention="artifact")
        assert bool(await index_rows(engine, task)) is live, removed_by
    async with engine.connect() as conn:
        request = await conn.execute(
            text("SELECT request_id FROM blob_refs WHERE task_id = :t"), {"t": task}
        )
        assert request.scalar_one() is None  # an upload reference names no request


@pytest.mark.parametrize("status", ["succeeded", "failed", "needs_input"])
async def test_end_task_sets_ended_at_and_indexes_artifacts(
    engine: AsyncEngine, status: str
) -> None:
    """R1, R20: in end_task's transaction."""
    task = new_task()
    await record(engine, task, request=f"req-{task}")
    artifact = blob_ref(f"{task} artifact")
    result = {
        "task_id": task,
        "status": status,
        "artifacts": [{"path": "out.md", "ref": artifact.model_dump(mode="json")}],
    }
    await MessageRepository(engine).end_task(task, status, result)
    await MessageRepository(engine).end_task(task, status, result)  # a retried Activity
    row = await TaskRepository(engine).get(task)
    assert row is not None and row["status"] == status and row["ended_at"] is not None
    assert row["ended_at"] <= datetime.now(UTC)
    assert ("tasks", task, "result", artifact.key, "artifact") in await index_rows(engine, task)
    async with engine.connect() as conn:
        request = await conn.execute(
            text(
                "SELECT request_id FROM blob_refs WHERE task_id = :t AND holder_column = 'result'"
            ),
            {"t": task},
        )
        assert request.scalar_one() == f"req-{task}"


async def test_a_retried_end_task_keeps_a_redaction(engine: AsyncEngine) -> None:
    """Review F82 (R11, R25): `end_task` committed, the worker died before Temporal
    recorded it, a delete redacted the result; the retry must not write it back."""
    task = new_task()
    await record(engine, task, request=f"req-{task}")
    artifact = blob_ref(f"{task} artifact")
    result = {
        "task_id": task,
        "status": "succeeded",
        "summary": "secret summary",
        "artifacts": [{"path": "out.md", "ref": artifact.model_dump(mode="json")}],
    }
    await MessageRepository(engine).end_task(task, "succeeded", result)
    redacted = {"task_id": task, "status": "succeeded", "summary": "[deleted]", "artifacts": []}
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE tasks SET result = :r WHERE task_id = :t"),
            {"t": task, "r": json.dumps(redacted)},
        )
    await MessageRepository(engine).end_task(task, "succeeded", result)  # the retry
    row = await TaskRepository(engine).get(task)
    assert row is not None and row["result"] == redacted


class IndexFailed(Exception):
    pass


async def _fail(*args: object, **kwargs: object) -> None:
    raise IndexFailed


async def test_a_failed_index_write_rolls_back_its_holder_row(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review F87 (R1, R20): the index rows and the holder row commit together, so a
    failed index write leaves no task row, no ended task and no event row."""
    import common.events.table as table_module
    import common.persistence.messages as messages_module
    import common.persistence.repositories as repositories_module

    task = new_task()
    with monkeypatch.context() as m:
        m.setattr(repositories_module, "index_refs", _fail)
        m.setattr(repositories_module, "index_keys", _fail)
        with pytest.raises(IndexFailed):
            await record(engine, task)
    assert await TaskRepository(engine).get(task) is None

    await record(engine, task)
    artifact = blob_ref(f"{task} artifact")
    result = {"artifacts": [{"path": "out.md", "ref": artifact.model_dump(mode="json")}]}
    with monkeypatch.context() as m:
        m.setattr(messages_module, "index_keys", _fail)
        with pytest.raises(IndexFailed):
            await MessageRepository(engine).end_task(task, "succeeded", result)
    row = await TaskRepository(engine).get(task)
    assert row is not None and row["ended_at"] is None and row["status"] != "succeeded"

    event = AgentEvent(
        seq=0,
        timestamp=datetime.now(UTC),
        workflow_id=task,
        task_id=task,
        attempt_id=f"{task}:1:1",
        type="tool_result",
        payload={},
        blob_ref=blob_ref(f"{task} attachment"),
    )
    with monkeypatch.context() as m:
        m.setattr(table_module, "index_refs", _fail)
        with pytest.raises(IndexFailed):
            await TableTransport(engine).publish(task, Writer(task, 1, 1), f"{task}:1:1:0", [event])
    async with engine.connect() as conn:
        events = await conn.execute(
            text("SELECT count(*) FROM agent_events WHERE task_id = :t"), {"t": task}
        )
        assert events.scalar_one() == 0

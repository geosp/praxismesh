"""Tasks with stored blobs, for the removal tests (Phase 3A persistence plan phase
02): a task recorded and ended through the real writers, with its uploads held by
it, so its references are the ones production writes."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store import BlobExpired
from common.events import TableTransport, Writer
from common.persistence.messages import MessageRepository
from common.persistence.repositories import RecordingBlobStore, TaskRepository
from common.schemas import BlobRef, TaskResult, TaskStart
from common.schemas.events import AgentEvent
from orchestrator.lifecycle import WorkflowStatus


def new_task_id(prefix: str = "task-life") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class StoredTask:
    task_id: str
    request_id: str
    instructions: BlobRef
    inputs: dict[str, BlobRef] = field(default_factory=dict)
    artifacts: dict[str, BlobRef] = field(default_factory=dict)


async def record_task(
    engine: AsyncEngine,
    store: RecordingBlobStore,
    *,
    task_id: str | None = None,
    request_id: str | None = None,
    inputs: dict[str, bytes] | None = None,
) -> StoredTask:
    """Upload the instructions and inputs for a new task and record it, `running`."""
    task = task_id or new_task_id()
    instructions = await store.put(
        f"instructions {task}".encode(), retention="transcript", task_id=task
    )
    refs = {
        path: await store.put(data, retention="transcript", task_id=task)
        for path, data in (inputs or {}).items()
    }
    start = TaskStart(
        task_id=task,
        request_id=request_id or f"req-{task}",
        profile="openai",
        template="local-default",
        instructions_ref=instructions,
        input_refs=refs,
    )
    await TaskRepository(engine).record_task(
        start, workflow_id=task, run_id="run-1", template_version=1, template_hash="sha256:x"
    )
    return StoredTask(task, start.request_id, instructions, refs)


async def end_task(
    engine: AsyncEngine,
    store: RecordingBlobStore,
    stored: StoredTask,
    *,
    artifacts: dict[str, bytes] | None = None,
    status: str = "succeeded",
    ended_at: datetime | None = None,
    questions: list[str] | None = None,
) -> StoredTask:
    """Upload the artifacts and end the task through `end_task`; `ended_at`, if
    given, is then set as if the task had ended then."""
    for path, data in (artifacts or {}).items():
        stored.artifacts[path] = await store.put(data, retention="artifact", task_id=stored.task_id)
    result = TaskResult(
        task_id=stored.task_id,
        status=status,  # type: ignore[arg-type]
        summary=f"summary of {stored.task_id}",
        artifacts=[{"path": p, "ref": r} for p, r in stored.artifacts.items()],  # type: ignore[misc]
        questions=questions or [],
        failure_reason="it broke" if status == "failed" else None,
        tier_used="local",
        template="local-default",
        template_version=1,
        template_hash="sha256:x",
        turns=1,
        attempts=1,
        tokens_in=10,
        tokens_out=5,
    )
    await MessageRepository(engine).end_task(stored.task_id, status, result.model_dump(mode="json"))
    if ended_at is not None:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE tasks SET ended_at = :at WHERE task_id = :t"),
                {"at": ended_at, "t": stored.task_id},
            )
    return stored


async def session_ids(engine: AsyncEngine, task_id: str) -> dict[str, set[str]]:
    """The session IDs a task's rows carry (Phase 3A persistence plan phase 02
    task 3.1: a delete redacts `agent_sessions` by `session_id` = task ID)."""
    async with engine.connect() as conn:
        found: dict[str, set[str]] = {}
        for name, sql in (
            ("checkpoints", "SELECT DISTINCT session_id FROM checkpoints WHERE task_id = :t"),
            # A session the task's attempts wrote, by the checkpoints that name it.
            (
                "agent_sessions",
                "SELECT DISTINCT s.session_id FROM agent_sessions s JOIN checkpoints c "
                "ON c.session_id = s.session_id WHERE c.task_id = :t",
            ),
            (
                "agent_messages",
                "SELECT DISTINCT m.session_id FROM agent_messages m JOIN checkpoints c "
                "ON c.session_id = m.session_id WHERE c.task_id = :t",
            ),
        ):
            found[name] = {r[0] for r in await conn.execute(text(sql), {"t": task_id})}
        return found


# ---- shared by the removal tests (review F134) ----


async def one(engine: AsyncEngine, sql: str, **params: object) -> Any:
    """The single value `sql` returns, or None."""
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar_one_or_none()


async def expired(store: RecordingBlobStore, ref: BlobRef) -> bool:
    """Whether reading `ref` reports it expired (R9)."""
    try:
        await store.get(ref)
    except BlobExpired:
        return True
    return False


async def publish_events(
    engine: AsyncEngine,
    workflow: str,
    n: int,
    *,
    turn: int = 1,
    attachment: BlobRef | None = None,
) -> None:
    """`n` token events for `workflow` (its task ID), in batches of 64, through
    the fenced publish; the first carries `attachment`, if any."""
    transport = TableTransport(engine)
    for start in range(0, n, 64):
        events = [
            AgentEvent(
                seq=i,
                timestamp=datetime.now(UTC),
                workflow_id=workflow,
                task_id=workflow,
                attempt_id=f"{workflow}:{turn}:1",
                type="tool_result" if i == 0 and attachment else "token",
                payload={"i": i},
                blob_ref=attachment if i == 0 else None,
            )
            for i in range(start, min(start + 64, n))
        ]
        await transport.publish(
            workflow,
            Writer(workflow, turn, 1),
            f"{workflow}:{turn}:1:{start}:{uuid.uuid4().hex[:6]}",
            events,
        )


@dataclass(frozen=True)
class Tombstone:
    action: str
    subject: str
    details: dict[str, Any]


async def tombstones(engine: AsyncEngine, operation: str) -> list[Tombstone]:
    """A run's tombstones, in the order written."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT action, subject, details FROM audit_log WHERE operation_id = :o ORDER BY id"
            ),
            {"o": operation},
        )
        return [
            Tombstone(r[0], r[1], r[2] if isinstance(r[2], dict) else json.loads(r[2]))
            for r in rows
        ]


class FakeTemporal:
    """Workflow statuses by task ID; an unknown ID is `missing`. Records each ask."""

    def __init__(self, status: dict[str, WorkflowStatus] | None = None) -> None:
        self.status = status or {}
        self.asked: list[str] = []

    async def __call__(self, task_id: str) -> WorkflowStatus:
        self.asked.append(task_id)
        return self.status.get(task_id, "missing")


async def content_rows(engine: AsyncEngine, task_id: str, request_id: str) -> None:
    """A row with content in each table notes.md#redact lists and gc expires by
    class: a session and its item, an idempotency key, a message, a sample
    order and an inbox row."""
    async with engine.begin() as conn:
        for sql, params in (
            ("INSERT INTO agent_sessions (session_id) VALUES (:t)", {}),
            (
                "INSERT INTO agent_messages (session_id, message_data) VALUES (:t, :m)",
                {"m": json.dumps({"role": "user", "content": "secret plan"})},
            ),
            (
                "INSERT INTO idempotency_keys (key, task_id, tool, result) "
                "VALUES (:key, :t, 'order', CAST(:r AS json))",
                {"key": f"{task_id}:k", "r": json.dumps({"order": "secret order"})},
            ),
            (
                "INSERT INTO task_messages (message_id, request_id, sender_task, "
                "recipient_task, kind, status, body, idempotency_key) VALUES (:m, :r, "
                ":t, :t, 'send', 'read', 'secret note', :m)",
                {"m": f"{task_id}:msg", "r": request_id},
            ),
            (
                "INSERT INTO sample_orders (task_id, sku, qty, idempotency_key) "
                "VALUES (:t, 'SKU-1', 3, :key)",
                {"key": f"{task_id}:order"},
            ),
            ("INSERT INTO task_inbox (task_id) VALUES (:t)", {}),
        ):
            await conn.execute(text(sql), {"t": task_id, **params})


class Borrowed:
    """A test's engine handed to code that disposes of its own (the CLI)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)

    async def dispose(self) -> None:
        return None

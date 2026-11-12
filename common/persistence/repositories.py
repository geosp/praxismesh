"""Repositories for the Phase 1 tables (RFC Phase 1, migration 0003). All database
access happens in Activities or the CLI, never in Workflow code (plan §5)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from common.blob_store import BlobStore
from common.blob_store.base import RETENTION_ORDER
from common.errors import TaskAlreadyExists
from common.persistence.settings import app_database_url
from common.schemas import BlobRef, RetentionClass, TaskStart


def make_engine() -> AsyncEngine:
    return create_async_engine(app_database_url(), pool_pre_ping=True)


def _ref_json(ref: BlobRef) -> str:
    return ref.model_dump_json()


class TaskRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def record_task(
        self,
        start: TaskStart,
        *,
        workflow_id: str,
        run_id: str,
        template_version: int,
        template_hash: str,
    ) -> None:
        """Insert the task's row. A row from another run means the task ID was
        reused: refuse, so the new run never reaches the old run's idempotency
        keys. A retry from the same run finds its own row and succeeds."""
        async with self.engine.begin() as conn:
            inserted = await conn.execute(
                text(
                    """
                    INSERT INTO tasks (task_id, workflow_id, run_id, request_id, profile,
                        template, template_version, template_hash, instructions_ref,
                        input_refs, outputs, status, retention_class)
                    VALUES (:task_id, :workflow_id, :run_id, :request_id, :profile,
                        :template, :template_version, :template_hash, :instructions_ref,
                        :input_refs, :outputs, 'running', 'audit')
                    ON CONFLICT (task_id) DO NOTHING
                    RETURNING task_id
                    """
                ),
                {
                    "task_id": start.task_id,
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "request_id": start.request_id,
                    "profile": start.profile,
                    "template": start.template,
                    "template_version": template_version,
                    "template_hash": template_hash,
                    "instructions_ref": _ref_json(start.instructions_ref),
                    "input_refs": json.dumps(
                        {
                            path: ref.model_dump(mode="json")
                            for path, ref in start.input_refs.items()
                        }
                    ),
                    "outputs": json.dumps(start.outputs),
                },
            )
            if inserted.first() is not None:
                return
            existing = (
                await conn.execute(
                    text("SELECT run_id FROM tasks WHERE task_id = :t"), {"t": start.task_id}
                )
            ).scalar_one()
        if existing != run_id:
            raise TaskAlreadyExists(f"task {start.task_id} was already run (run {existing})")

    async def get(self, task_id: str) -> dict[str, Any] | None:
        async with self.engine.connect() as conn:
            row = (
                (await conn.execute(text("SELECT * FROM tasks WHERE task_id = :t"), {"t": task_id}))
                .mappings()
                .first()
            )
        return dict(row) if row else None


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    task_id: str
    turn: int
    attempt: int
    seq: int
    session_id: str
    session_position: int
    workspace_ref: BlobRef
    finish: dict[str, Any] | None


class AttemptRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def start(self, task_id: str, turn: int, attempt: int, worker: str) -> None:
        """Record an attempt as started, and mark earlier unfinished attempts of the
        same turn as lost (RFC: cumulative usage and lost attempts)."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE task_attempts SET outcome = 'lost',
                        failure_category = COALESCE(failure_category, 'worker_lost'),
                        ended_at = CURRENT_TIMESTAMP
                    WHERE task_id = :t AND turn = :turn AND attempt < :a AND outcome = 'started'
                    """
                ),
                {"t": task_id, "turn": turn, "a": attempt},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO task_attempts (task_id, turn, attempt, worker_identity,
                        outcome, retention_class)
                    VALUES (:t, :turn, :a, :w, 'started', 'audit')
                    ON CONFLICT (task_id, turn, attempt) DO UPDATE
                        SET worker_identity = EXCLUDED.worker_identity
                    """
                ),
                {"t": task_id, "turn": turn, "a": attempt, "w": worker},
            )

    async def finish(
        self,
        task_id: str,
        turn: int,
        attempt: int,
        *,
        outcome: str,
        tokens_in: int,
        tokens_out: int,
        tool_calls: int,
        failure_category: str | None = None,
    ) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE task_attempts SET outcome = :o, failure_category = :f,
                        tokens_in = :ti, tokens_out = :to, tool_calls = :tc,
                        ended_at = CURRENT_TIMESTAMP
                    WHERE task_id = :t AND turn = :turn AND attempt = :a
                    """
                ),
                {
                    "t": task_id,
                    "turn": turn,
                    "a": attempt,
                    "o": outcome,
                    "f": failure_category,
                    "ti": tokens_in,
                    "to": tokens_out,
                    "tc": tool_calls,
                },
            )

    async def newer_attempt_exists(self, task_id: str, turn: int, attempt: int) -> bool:
        async with self.engine.connect() as conn:
            found = await conn.execute(
                text(
                    "SELECT 1 FROM task_attempts WHERE task_id = :t AND turn = :turn "
                    "AND attempt > :a LIMIT 1"
                ),
                {"t": task_id, "turn": turn, "a": attempt},
            )
            return found.first() is not None


class CheckpointRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def insert(self, cp: Checkpoint) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO checkpoints (checkpoint_id, task_id, turn, attempt, seq,
                        session_id, session_position, workspace_ref, finish, retention_class)
                    VALUES (:id, :t, :turn, :a, :seq, :sid, :pos, :ws, :finish, 'task')
                    """
                ),
                {
                    "id": cp.checkpoint_id,
                    "t": cp.task_id,
                    "turn": cp.turn,
                    "a": cp.attempt,
                    "seq": cp.seq,
                    "sid": cp.session_id,
                    "pos": cp.session_position,
                    "ws": _ref_json(cp.workspace_ref),
                    "finish": json.dumps(cp.finish) if cp.finish is not None else None,
                },
            )

    async def latest(self, task_id: str) -> Checkpoint | None:
        """The checkpoint to restore: newest turn, then attempt, then sequence."""
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM checkpoints WHERE task_id = :t "
                            "ORDER BY turn DESC, attempt DESC, seq DESC LIMIT 1"
                        ),
                        {"t": task_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"],
            task_id=row["task_id"],
            turn=row["turn"],
            attempt=row["attempt"],
            seq=row["seq"],
            session_id=row["session_id"],
            session_position=row["session_position"],
            workspace_ref=BlobRef.model_validate(row["workspace_ref"]),
            finish=row["finish"],
        )


class RecordingBlobStore:
    """A `BlobStore` that also records every stored blob in `blob_objects`, with the
    strongest retention class requested so far (RFC: retention from the first write)."""

    def __init__(self, inner: BlobStore, engine: AsyncEngine) -> None:
        self.inner = inner
        self.engine = engine

    async def put(
        self,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str = "application/octet-stream",
        retention: RetentionClass,
    ) -> BlobRef:
        ref = await self.inner.put(data, content_type=content_type, retention=retention)
        order = " ".join(f"WHEN '{k}' THEN {v}" for k, v in RETENTION_ORDER.items())
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    f"""
                    INSERT INTO blob_objects (key, checksum, bytes, content_type, retention_class)
                    VALUES (:k, :c, :b, :ct, :r)
                    ON CONFLICT (key) DO UPDATE SET retention_class = CASE
                        WHEN (CASE EXCLUDED.retention_class {order} END)
                           > (CASE blob_objects.retention_class {order} END)
                        THEN EXCLUDED.retention_class ELSE blob_objects.retention_class END
                    """
                ),
                {
                    "k": ref.key,
                    "c": ref.checksum,
                    "b": ref.bytes,
                    "ct": ref.content_type,
                    "r": ref.retention_class,
                },
            )
        return ref

    async def get(self, ref: BlobRef) -> bytes:
        return await self.inner.get(ref)

    def stream(self, ref: BlobRef) -> AsyncIterator[bytes]:
        return self.inner.stream(ref)

    async def stat(self, ref: BlobRef) -> BlobRef:
        return await self.inner.stat(ref)

    async def delete(self, ref: BlobRef) -> None:
        await self.inner.delete(ref)
        async with self.engine.begin() as conn:
            await conn.execute(text("DELETE FROM blob_objects WHERE key = :k"), {"k": ref.key})

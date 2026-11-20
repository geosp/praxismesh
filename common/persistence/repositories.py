"""Repositories for the Phase 1 tables (RFC Phase 1, migration 0003). All database
access happens in Activities or the CLI, never in Workflow code (plan §5)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from common.blob_store import BlobStore
from common.blob_store.base import collect, content_key, current_class
from common.errors import TaskAlreadyExists
from common.persistence.fence import NO_NEWER_ATTEMPT as _NO_NEWER_ATTEMPT
from common.persistence.fence import TASK_LOCK as _TASK_LOCK
from common.persistence.fence import FenceRejected
from common.persistence.refs import (
    checkpoint_holder,
    index_keys,
    index_refs,
    rank_sql,
    task_holder,
    upload_holder,
)
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
                # The index rows commit with the row (D2).
                await index_refs(
                    conn,
                    task_holder(start.task_id, "instructions_ref"),
                    [start.instructions_ref],
                    task_id=start.task_id,
                    request_id=start.request_id,
                )
                await index_refs(
                    conn,
                    task_holder(start.task_id, "input_refs"),
                    start.input_refs.values(),
                    task_id=start.task_id,
                    request_id=start.request_id,
                )
                return
            existing = (
                await conn.execute(
                    text("SELECT run_id FROM tasks WHERE task_id = :t"), {"t": start.task_id}
                )
            ).scalar_one()
        if existing != run_id:
            raise TaskAlreadyExists(f"task {start.task_id} was already run (run {existing})")

    async def request_exists(self, request_id: str) -> bool:
        """Whether some task belongs to `request_id` (Phase 2 messaging D5)."""
        async with self.engine.connect() as conn:
            found = await conn.execute(
                text("SELECT 1 FROM tasks WHERE request_id = :r LIMIT 1"), {"r": request_id}
            )
            return found.first() is not None

    async def sample_orders(self, task_id: str) -> list[dict[str, Any]]:
        """The sample MCP server's orders for a task (demo and status only)."""
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT sku, qty FROM sample_orders WHERE task_id = :t ORDER BY order_id"),
                {"t": task_id},
            )
            return [dict(r) for r in rows.mappings()]

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
    # A DSH session blob (DSH migration plan D1); None for openai_agents.
    session_ref: BlobRef | None = None
    session_digest: str | None = None


class AttemptRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def start(self, task_id: str, turn: int, attempt: int, worker: str) -> None:
        """Record an attempt as started, and mark earlier unfinished attempts of the
        same turn as lost (RFC: cumulative usage and lost attempts)."""
        async with self.engine.begin() as conn:
            await conn.execute(_TASK_LOCK, {"t": task_id})
            current = await conn.execute(
                text("SELECT 1 WHERE " + _NO_NEWER_ATTEMPT),
                {"t": task_id, "turn": turn, "a": attempt},
            )
            if current.first() is None:  # a stale attempt that started late (review F28)
                raise FenceRejected("a newer attempt owns this task")
            await conn.execute(
                text(
                    """
                    UPDATE task_attempts SET outcome = 'lost',
                        failure_category = COALESCE(failure_category, 'lost_or_timed_out'),
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
        tokens_in: int | None,
        tokens_out: int | None,
        tool_calls: int,
        failure_category: str | None = None,
        fenced: bool = False,
        usage_known: bool = True,
    ) -> None:
        """Record an attempt's outcome. With `fenced`, refuse (FenceRejected) when a
        newer attempt exists, in the same transaction as the update (D10)."""
        async with self.engine.begin() as conn:
            if fenced:
                await conn.execute(_TASK_LOCK, {"t": task_id})
            done = await conn.execute(
                text(
                    """
                    UPDATE task_attempts SET outcome = :o, failure_category = :f,
                        tokens_in = :ti, tokens_out = :to, tool_calls = :tc,
                        usage_known = :uk, ended_at = CURRENT_TIMESTAMP
                    WHERE task_id = :t AND turn = :turn AND attempt = :a
                        AND outcome = 'started'
                    """
                    + (" AND " + _NO_NEWER_ATTEMPT if fenced else "")
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
                    "uk": usage_known and tokens_in is not None and tokens_out is not None,
                },
            )
            if fenced and done.rowcount == 0:
                newer = await conn.execute(
                    text("SELECT 1 WHERE NOT " + _NO_NEWER_ATTEMPT),
                    {"t": task_id, "turn": turn, "a": attempt},
                )
                if newer.first() is not None:
                    raise FenceRejected("a newer attempt owns this task")

    async def record_refusal(
        self,
        task_id: str,
        turn: int,
        attempt: int,
        worker: str,
        category: str = "template_version_unavailable",
    ) -> None:
        """Record a Temporal attempt that refused the task (wrong template version).

        It never runs, but it is newer than the attempts before it, so it must fence
        them (D10, review F27). Earlier open rows of the turn become lost, as in start."""
        async with self.engine.begin() as conn:
            await conn.execute(_TASK_LOCK, {"t": task_id})
            await conn.execute(
                text(
                    """
                    UPDATE task_attempts SET outcome = 'lost',
                        failure_category = COALESCE(failure_category, 'lost_or_timed_out'),
                        ended_at = CURRENT_TIMESTAMP
                    WHERE task_id = :t AND turn = :turn AND attempt < :a AND outcome = 'started'
                    """
                ),
                {"t": task_id, "turn": turn, "a": attempt},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO task_attempts (task_id, turn, attempt, worker_identity, outcome,
                        failure_category, ended_at, retention_class)
                    VALUES (:t, :turn, :a, :w, 'refused', :c, CURRENT_TIMESTAMP, 'audit')
                    ON CONFLICT (task_id, turn, attempt) DO NOTHING
                    """
                ),
                {"t": task_id, "turn": turn, "a": attempt, "w": worker, "c": category},
            )

    async def assert_current(self, task_id: str, turn: int, attempt: int) -> None:
        """Raise FenceRejected if a newer turn or attempt of the task has started.

        Used right before publishing artifacts, which are blobs and cannot share the
        attempt row's transaction (D10, review F6)."""
        async with self.engine.begin() as conn:
            await conn.execute(_TASK_LOCK, {"t": task_id})
            current = await conn.execute(
                text("SELECT 1 WHERE " + _NO_NEWER_ATTEMPT),
                {"t": task_id, "turn": turn, "a": attempt},
            )
            if current.first() is None:
                raise FenceRejected("a newer attempt owns this task")

    async def close_unfinished(
        self,
        task_id: str,
        turn: int | None,
        category: str,
        *,
        outcome: str = "failed",
        through_attempt: int | None = None,
    ) -> None:
        """Close open attempt rows: one turn's when it fails for good, or (with
        `turn=None`) the whole task's when the task completes (gate F2).

        A failing Activity supplies `through_attempt` so a stale attempt cannot
        close a newer attempt that Temporal has already started (gate follow-up
        N1). Task-wide completion intentionally leaves it unset.
        """
        async with self.engine.begin() as conn:
            # The rows close without a finish: give them the ledger's usage (F101),
            # and so do rows a newer start or refusal marked lost, which no later
            # attempt may have reached (F134).
            await conn.execute(
                text(
                    _ledger_usage_sql(
                        "a.outcome IN ('started', 'lost') "
                        "AND (CAST(:turn AS INTEGER) IS NULL OR a.turn = :turn) "
                        "AND (CAST(:through_attempt AS INTEGER) IS NULL "
                        "OR a.attempt <= :through_attempt)"
                    )
                ),
                {"t": task_id, "turn": turn, "through_attempt": through_attempt},
            )
            await conn.execute(
                text(
                    "UPDATE task_attempts SET outcome = :o, failure_category = :c, "
                    "ended_at = CURRENT_TIMESTAMP "
                    "WHERE task_id = :t AND outcome = 'started' "
                    "AND (CAST(:turn AS INTEGER) IS NULL OR turn = :turn) "
                    "AND (CAST(:through_attempt AS INTEGER) IS NULL "
                    "OR attempt <= :through_attempt)"
                ),
                {
                    "t": task_id,
                    "turn": turn,
                    "c": category,
                    "o": outcome,
                    "through_attempt": through_attempt,
                },
            )

    async def list(self, task_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT turn, attempt, worker_identity, outcome, failure_category, "
                    "tokens_in, tokens_out, tool_calls, started_at, ended_at "
                    "FROM task_attempts WHERE task_id = :t ORDER BY turn, attempt"
                ),
                {"t": task_id},
            )
            return [dict(r) for r in rows.mappings()]

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


def _ledger_usage_sql(rows: str) -> str:
    """Set the usage of the attempt rows `rows` selects (alias `a`, task `:t`) to
    the ledger's usage of their turn through each attempt: the settled tokens, or
    NULL with `usage_known` false when a request up to it was never observed. Rows
    of turns with no ledger rows (openai_agents) and rows already unknown are left
    alone (D7, review F68, F101)."""
    through = (
        "FROM usage_ledger l WHERE l.task_id = :t AND l.turn = a.turn AND l.attempt <= a.attempt"
    )
    return f"""
        UPDATE task_attempts a SET
            tokens_in = CASE WHEN s.unknown > 0 THEN NULL ELSE s.tokens_in END,
            tokens_out = CASE WHEN s.unknown > 0 THEN NULL ELSE s.tokens_out END,
            usage_known = s.unknown = 0
        FROM (
            SELECT a.turn, a.attempt,
                (SELECT coalesce(sum(l.input_tokens), 0) {through}) AS tokens_in,
                (SELECT coalesce(sum(l.output_tokens), 0) {through}) AS tokens_out,
                (SELECT count(*) {through} AND l.input_tokens IS NULL) AS unknown
            FROM task_attempts a WHERE a.task_id = :t AND {rows}
                AND EXISTS (SELECT 1 {through})
        ) s
        WHERE a.task_id = :t AND a.turn = s.turn AND a.attempt = s.attempt AND a.usage_known
    """


class CheckpointRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def insert_fenced(self, cp: Checkpoint) -> None:
        """Insert in one statement that refuses if a newer attempt exists."""
        async with self.engine.begin() as conn:
            await conn.execute(_TASK_LOCK, {"t": cp.task_id})
            done = await conn.execute(
                text(
                    """
                    INSERT INTO checkpoints (checkpoint_id, task_id, turn, attempt, seq,
                        session_id, session_position, workspace_ref, finish, session_ref,
                        session_digest)
                    SELECT :id, :t, :turn, :a, :seq, :sid, :pos, :ws, :finish, :sref, :sdig
                    WHERE """
                    + _NO_NEWER_ATTEMPT
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
                    "sref": _ref_json(cp.session_ref) if cp.session_ref is not None else None,
                    "sdig": cp.session_digest,
                },
            )
            if done.rowcount != 1:
                raise FenceRejected("a newer attempt owns this task")
            await _index_checkpoint(conn, cp)

    async def insert(self, cp: Checkpoint) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO checkpoints (checkpoint_id, task_id, turn, attempt, seq,
                        session_id, session_position, workspace_ref, finish)
                    VALUES (:id, :t, :turn, :a, :seq, :sid, :pos, :ws, :finish)
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
            await _index_checkpoint(conn, cp)

    async def count(self, task_id: str) -> int:
        async with self.engine.connect() as conn:
            found = await conn.execute(
                text("SELECT count(*) FROM checkpoints WHERE task_id = :t"), {"t": task_id}
            )
            return int(found.scalar_one())

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
            session_ref=(
                BlobRef.model_validate(row["session_ref"]) if row["session_ref"] else None
            ),
            session_digest=row["session_digest"],
        )


async def _index_checkpoint(conn: AsyncConnection, cp: Checkpoint) -> None:
    """The checkpoint's index rows, in its insert's transaction (D2): a refused
    fenced insert rolls them back with the row."""
    for column, ref in (("workspace_ref", cp.workspace_ref), ("session_ref", cp.session_ref)):
        if ref is not None:
            await index_refs(
                conn,
                checkpoint_holder(cp.task_id, cp.turn, cp.attempt, cp.seq, column),
                [ref],
                task_id=cp.task_id,
            )


class UsageLedgerRepository:
    """Durable model-request rows (DSH migration plan D7, D9). Implements the
    gateway ledger's `LedgerStore`."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def dispatch(
        self, task_id: str, turn: int, attempt: int, request_id: str, purpose: str
    ) -> bool:
        """Write the row before the request is sent, fenced like every attempt write:
        a stale attempt dispatches nothing, so no spend escapes the totals a newer
        attempt took from the ledger (D10, review F61)."""
        async with self.engine.begin() as conn:
            await conn.execute(_TASK_LOCK, {"t": task_id})
            done = await conn.execute(
                text(
                    "INSERT INTO usage_ledger (task_id, turn, attempt, request_id, purpose) "
                    "SELECT :t, :turn, :a, :r, :p WHERE " + _NO_NEWER_ATTEMPT
                ),
                {"t": task_id, "turn": turn, "a": attempt, "r": request_id, "p": purpose},
            )
            return done.rowcount == 1

    async def settle(
        self,
        task_id: str,
        turn: int,
        attempt: int,
        request_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE usage_ledger SET input_tokens = :i, output_tokens = :o, "
                    "settled_at = CURRENT_TIMESTAMP WHERE task_id = :t AND turn = :turn "
                    "AND attempt = :a AND request_id = :r AND settled_at IS NULL"
                ),
                {
                    "t": task_id,
                    "turn": turn,
                    "a": attempt,
                    "r": request_id,
                    "i": input_tokens,
                    "o": output_tokens,
                },
            )

    async def close_unknown(
        self, task_id: str, turn: int, attempt: int
    ) -> tuple[int, int, int, int]:
        """Close the requests earlier attempts of this turn dispatched but never
        settled, mark those attempts' usage unknown (NULL tokens, never 0), and
        return `(unknown_requests, settled_tokens_in, settled_tokens_out,
        settled_requests)` for earlier attempts of this turn.

        The totals are derived from the ledger rows each time, so every later
        attempt reconstructs the exact settled usage plus conservative unknown
        charge even when a worker was killed between heartbeats (D9, R11)."""
        params = {"t": task_id, "turn": turn, "a": attempt}
        earlier = "task_id = :t AND turn = :turn AND attempt < :a"
        async with self.engine.begin() as conn:
            await conn.execute(_TASK_LOCK, {"t": task_id})
            await conn.execute(
                text(
                    f"UPDATE usage_ledger SET settled_at = CURRENT_TIMESTAMP "
                    f"WHERE {earlier} AND settled_at IS NULL"
                ),
                params,
            )
            await conn.execute(
                text(
                    f"UPDATE task_attempts SET usage_known = false, tokens_in = NULL, "
                    f"tokens_out = NULL WHERE {earlier} AND attempt IN (SELECT attempt FROM "
                    f"usage_ledger WHERE {earlier} AND input_tokens IS NULL)"
                ),
                params,
            )
            # A lost attempt's row holds the turn's usage through that attempt, like
            # every attempt row: exact from the ledger, or unknown if any request up
            # to it was never observed; never the 0 it was created with (review F68).
            await conn.execute(
                text(_ledger_usage_sql("a.turn = :turn AND a.attempt < :a AND a.outcome = 'lost'")),
                params,
            )
            settled = await conn.execute(
                text(
                    f"SELECT coalesce(sum(input_tokens), 0), coalesce(sum(output_tokens), 0), "
                    f"count(*) FILTER (WHERE input_tokens IS NOT NULL) "
                    f"FROM usage_ledger WHERE {earlier}"
                ),
                params,
            )
            settled_in, settled_out, settled_count = settled.one()
            found = await conn.execute(
                text(f"SELECT count(*) FROM usage_ledger WHERE {earlier} AND input_tokens IS NULL"),
                params,
            )
            return (
                int(found.scalar_one()),
                int(settled_in),
                int(settled_out),
                int(settled_count),
            )

    async def task_totals(self, task_id: str) -> tuple[int, int, int, int]:
        """The whole task's settled input and output tokens, its requests whose usage
        was never observed, and all its requests (R11, D11, review F98, F136)."""
        async with self.engine.connect() as conn:
            found = await conn.execute(
                text(
                    "SELECT coalesce(sum(input_tokens), 0), coalesce(sum(output_tokens), 0), "
                    "count(*) FILTER (WHERE input_tokens IS NULL), count(*) "
                    "FROM usage_ledger WHERE task_id = :t"
                ),
                {"t": task_id},
            )
            tokens_in, tokens_out, unknown, requests = found.one()
        return int(tokens_in), int(tokens_out), int(unknown), int(requests)

    async def unknown_requests(self, task_id: str, turn: int, attempt: int) -> int:
        """Requests this attempt dispatched whose usage was never observed."""
        async with self.engine.connect() as conn:
            found = await conn.execute(
                text(
                    "SELECT count(*) FROM usage_ledger WHERE task_id = :t AND turn = :turn "
                    "AND attempt = :a AND input_tokens IS NULL"
                ),
                {"t": task_id, "turn": turn, "a": attempt},
            )
            return int(found.scalar_one())


class RecordingBlobStore:
    """A `BlobStore` that also records every stored blob in `blob_objects`, with the
    strongest retention class requested so far (RFC: retention from the first write),
    and the upload reference of the task it was stored for (Phase 3A persistence
    plan D2, D10; notes.md#revive)."""

    def __init__(self, inner: BlobStore, engine: AsyncEngine) -> None:
        self.inner = inner
        self.engine = engine

    async def put(
        self,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str = "application/octet-stream",
        retention: RetentionClass,
        task_id: str | None = None,
    ) -> BlobRef:
        """Record the blob, then upload it (notes.md#revive):

        1. collect the bytes and compute the key;
        2. in one transaction, `blob_objects` row first (locked by the upsert,
           the order every removal uses), clear any removal mark, set
           `last_put_at`, and write the task's upload reference;
        3. upload through the inner store, which skips bytes it already holds.
        """
        body = await collect(data)
        key, checksum = content_key(body)
        retention = current_class(retention)
        stronger_class = (
            f"CASE WHEN {rank_sql('EXCLUDED.retention_class')} "
            f"> {rank_sql('blob_objects.retention_class')} "
            "THEN EXCLUDED.retention_class ELSE blob_objects.retention_class END"
        )
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO blob_objects (key, checksum, bytes, content_type, "
                    "retention_class, last_put_at) VALUES (:k, :c, :b, :ct, :r, now()) "
                    f"ON CONFLICT (key) DO UPDATE SET retention_class = {stronger_class}, "
                    "removed_at = NULL, removed_by = NULL, bucket_deleted_at = NULL, "
                    "last_put_at = now()"
                ),
                {"k": key, "c": checksum, "b": len(body), "ct": content_type, "r": retention},
            )
            if task_id is not None:
                await index_keys(
                    conn, upload_holder(task_id), [key], task_id=task_id, retention=retention
                )
        return await self.inner.put(body, content_type=content_type, retention=retention)

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

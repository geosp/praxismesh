"""Operator removals: `gc`, `events prune`, and `request delete` (Phase 3A
persistence plan D4, D5, D6, D11; notes.md#d2, notes.md#d3). Each holds D4's run
lock, runs through the removal engine in batches of at most 500 rows, each with
its tombstone, and prints its plan with `--dry-run`."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.blob_store.base import BlobStore, BucketObject
from common.errors import PraxisError
from common.events import TableTransport
from common.persistence import refs
from common.persistence.refs import Reference, event_holder
from common.persistence.removal import (
    BATCH_LIMIT,
    Batch,
    RefKey,
    RemovalEngine,
    operation_id,
    run_lock,
)
from common.persistence.retention import DEFAULT_LIFETIME, SAFETY_WINDOW
from common.schemas import RetentionClass


@dataclass
class Totals:
    """What a run removed (or, dry, would remove), summed over its batches, and
    by reason for the plan a dry run prints."""

    operation: str
    batches: int = 0
    rows: int = 0
    references: int = 0
    blobs: int = 0
    by_reason: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, rows: int, references: int, blobs: int, reason: str = "") -> None:
        self.batches += 1
        self.rows += rows
        self.references += references
        self.blobs += blobs
        if reason:
            counts = self.by_reason.setdefault(reason, {"rows": 0, "references": 0, "blobs": 0})
            counts["rows"] += rows
            counts["references"] += references
            counts["blobs"] += blobs

    def report(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "batches": self.batches,
            "rows": self.rows,
            "references": self.references,
            "blobs": self.blobs,
            "by_reason": self.by_reason,
        }


@dataclass
class _Range:
    start: int = 0
    end: int = 0


def event_batch(
    transport: TableTransport,
    workflow_id: str,
    *,
    below: int | None,
    older_than: timedelta | None,
    limit: int | None,
    operation: str,
    action: str = "events.prune",
    subject: str | None = None,
    details: dict[str, object] | None = None,
) -> tuple[Batch, _Range]:
    """One batch pruning a workflow's events below `below` (or older than
    `older_than`), at most `limit` of them. The range is fixed in `collect`,
    before the locks, and the prune is given exactly that range."""
    span = _Range()

    async def collect(conn: AsyncConnection) -> Sequence[RefKey]:
        row = (
            await conn.execute(
                text("SELECT next_offset, retained_base FROM event_logs WHERE workflow_id = :w"),
                {"w": workflow_id},
            )
        ).first()
        if row is None:
            span.start = span.end = 0
            return []
        next_offset, base = row
        end = await transport.cutoff(conn, workflow_id, below, older_than, next_offset)
        end = min(end, next_offset)
        if limit is not None:
            end = min(end, base + limit)
        span.start, span.end = base, max(base, end)
        found = await conn.execute(
            text(
                "SELECT holder_table, holder_key, holder_column, blob_key FROM blob_refs "
                "WHERE holder_table = 'agent_events' AND holder_key = ANY(:k) "
                "AND removed_at IS NULL ORDER BY holder_key, blob_key"
            ),
            {"k": [event_holder(workflow_id, o).key for o in range(span.start, span.end)]},
        )
        return [RefKey(*r) for r in found]

    async def rows(conn: AsyncConnection) -> int:
        if span.end <= span.start:
            return 0
        base = await transport.prune(workflow_id, below=span.end, conn=conn, removed_by=operation)
        return (base or span.start) - span.start

    batch = Batch(
        action,
        subject or f"task:{workflow_id}",
        rows=rows,
        collect=collect,
        details={"workflow_id": workflow_id, **(details or {})},
    )
    return batch, span


async def prune_events(
    engine: AsyncEngine,
    blobs: BlobStore,
    workflow_id: str,
    *,
    below: int | None = None,
    older_than: timedelta | None = None,
    dry_run: bool = False,
) -> tuple[Totals, int | None]:
    """`agentctl events prune` through the engine (D11): batches of at most 500
    events until the prefix is gone. Returns the totals and the new retained
    base. A dry run reports the whole prefix and changes nothing."""
    if (below is None) == (older_than is None):
        raise ValueError("give exactly one of below and older_than")
    operation = operation_id("prune")
    async with run_lock(engine):  # D4: one removal run at a time
        totals = await _prune_events(
            engine, blobs, workflow_id, operation, below, older_than, dry_run
        )
    async with engine.connect() as conn:
        found = await conn.execute(
            text("SELECT retained_base FROM event_logs WHERE workflow_id = :w"),
            {"w": workflow_id},
        )
        base = found.scalar_one_or_none()
    return totals, None if base is None else int(base)


async def _prune_events(
    engine: AsyncEngine,
    blobs: BlobStore,
    workflow_id: str,
    operation: str,
    below: int | None,
    older_than: timedelta | None,
    dry_run: bool,
) -> Totals:
    removal = RemovalEngine(engine, blobs, operation, dry_run=dry_run)
    transport = TableTransport(engine)
    totals = Totals(operation)
    async with removal.session():
        await removal.finish_pending()
        while True:
            batch, _ = event_batch(
                transport,
                workflow_id,
                below=below,
                older_than=older_than,
                limit=BATCH_LIMIT,
                operation=operation,
            )
            result = await removal.run(batch)
            if result.rows == 0:
                break  # the prefix is gone; an empty batch commits nothing
            totals.add(result.rows, result.references, result.blobs)
    return totals


# ---- gc (R6, R7, R8; D3, D4, D5) ----

WorkflowStatus = Literal["running", "closed", "missing"]
# The status of a task's Workflow (its ID is the task ID), from Temporal.
StatusOf = Callable[[str], Awaitable[WorkflowStatus]]


class Bucket(BlobStore, Protocol):
    """The inner store, which can also list its objects (the orphan check)."""

    async def list_objects(self) -> dict[str, BucketObject]: ...


class GcRefused(PraxisError):
    """`gc` will not run while a stored reference is unindexed (D4)."""


@dataclass(frozen=True)
class RowRule:
    """Rows of one table that expire with their task (notes.md#d3): `column`
    names the task, and the row expires `retention`'s lifetime after the task's
    `ended_at`. `extra` adds a condition on the row (alias `x`)."""

    table: str
    column: str
    retention: RetentionClass
    extra: str = ""


ROW_RULES: tuple[RowRule, ...] = (
    RowRule("checkpoints", "task_id", "checkpoint"),
    RowRule("agent_messages", "session_id", "transcript"),
    RowRule("agent_sessions", "session_id", "transcript"),
    # A message expires from the later end of its sender and recipient.
    RowRule(
        "task_messages",
        "sender_task",
        "transcript",
        "AND EXISTS (SELECT 1 FROM tasks r WHERE r.task_id = x.recipient_task "
        "AND r.ended_at IS NOT NULL AND r.ended_at + make_interval(secs => :life) < :now)",
    ),
    RowRule("task_inbox", "task_id", "transcript"),
    RowRule("idempotency_keys", "task_id", "transcript"),
    RowRule("sample_orders", "task_id", "artifact"),
    # Kept until its recipient ends (ADR-0010), then a day.
    RowRule("message_wakes", "recipient_workflow", "ephemeral"),
    RowRule("event_batches", "workflow_id", "ephemeral"),
)
# Holders whose references leave with their rows (the rules above, and events).
ROW_HOLDERS = ("checkpoints", "agent_events")
EVENT_RETENTION: RetentionClass = "transcript"  # event_logs, agent_events (d3)
END_OF_LOG = 2**62  # prune "below" this: the whole log


def _life(lifetimes: Mapping[RetentionClass, timedelta | None], cls: RetentionClass) -> int | None:
    life = lifetimes[cls]
    return None if life is None else int(life.total_seconds())


async def _expired_tasks(
    conn: AsyncConnection, rule: RowRule, now: datetime, life: int
) -> list[str]:
    found = await conn.execute(
        text(
            f"SELECT DISTINCT x.{rule.column} FROM {rule.table} x "
            f"JOIN tasks t ON t.task_id = x.{rule.column} WHERE t.ended_at IS NOT NULL "
            f"AND t.ended_at + make_interval(secs => :life) < :now {rule.extra} "
            f"ORDER BY 1"
        ),
        {"life": life, "now": now},
    )
    return [row[0] for row in found]


def row_batch(
    rule: RowRule, task_id: str, now: datetime, life: int, *, action: str = "gc"
) -> Batch:
    """Delete up to 500 of the task's expired rows of `rule`'s table; for
    checkpoints, with the references they hold."""
    params = {"t": task_id, "life": life, "now": now, "n": BATCH_LIMIT}
    chosen: list[str] = []

    async def collect(conn: AsyncConnection) -> Sequence[RefKey]:
        if rule.table != "checkpoints":
            return []
        found = await conn.execute(
            text(
                "SELECT checkpoint_id, task_id || '/' || turn || '/' || attempt || '/' || seq "
                "FROM checkpoints WHERE task_id = :t ORDER BY turn, attempt, seq LIMIT :n"
            ),
            params,
        )
        rows = found.all()
        chosen[:] = [r[0] for r in rows]
        held = await conn.execute(
            text(
                "SELECT holder_table, holder_key, holder_column, blob_key FROM blob_refs "
                "WHERE holder_table = 'checkpoints' AND holder_key = ANY(:k) "
                "AND removed_at IS NULL ORDER BY holder_key, holder_column, blob_key"
            ),
            {"k": [r[1] for r in rows]},
        )
        return [RefKey(*r) for r in held]

    async def rows(conn: AsyncConnection) -> int:
        if rule.table == "checkpoints":
            deleted = await conn.execute(
                text("DELETE FROM checkpoints WHERE checkpoint_id = ANY(:c)"), {"c": chosen}
            )
            return deleted.rowcount
        deleted = await conn.execute(
            text(
                f"DELETE FROM {rule.table} WHERE ctid = ANY(ARRAY(SELECT x.ctid FROM "
                f"{rule.table} x WHERE x.{rule.column} = :t {rule.extra} LIMIT :n))"
            ),
            params,
        )
        return deleted.rowcount

    return Batch(
        action,
        f"task:{task_id}",
        rows=rows,
        collect=collect,
        details={"reason": f"{rule.table} expired", "class": rule.retention},
    )


def _by_task(references: Iterable[Reference]) -> dict[str, list[RefKey]]:
    grouped: dict[str, list[RefKey]] = {}
    for r in references:
        grouped.setdefault(r.task_id, []).append(
            RefKey(r.holder_table, r.holder_key, r.holder_column, r.blob_key)
        )
    return grouped


def _chunks(items: Sequence[RefKey], size: int = BATCH_LIMIT) -> list[Sequence[RefKey]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def gc(
    engine: AsyncEngine,
    bucket: Bucket,
    status_of: StatusOf,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    lifetimes: Mapping[RetentionClass, timedelta | None] = DEFAULT_LIFETIME,
    window: timedelta = SAFETY_WINDOW,
) -> Totals:
    """`agentctl gc`: remove everything whose expiry has passed (R6) and nothing
    else (R7), orphans only past the safety window (R8). Refuses while any
    stored reference is unindexed (D4)."""
    operation = operation_id("gc")
    async with run_lock(engine):
        removal = RemovalEngine(engine, bucket, operation, dry_run=dry_run)
        async with removal.session():
            return await _gc(
                engine, removal, bucket, status_of, now or datetime.now(UTC), lifetimes, window
            )


async def _gc(
    engine: AsyncEngine,
    removal: RemovalEngine,
    bucket: Bucket,
    status_of: StatusOf,
    now: datetime,
    lifetimes: Mapping[RetentionClass, timedelta | None],
    window: timedelta,
) -> Totals:
    totals = Totals(removal.operation)
    async with engine.connect() as conn:
        missing = await refs.unindexed(conn)
    if missing:
        raise GcRefused(
            f"{len(missing)} stored reference(s) are not indexed; run "
            "'agentctl reconcile --reindex' first, then gc again"
        )
    await removal.finish_pending()

    async def drain(make: Callable[[], Batch], reason: str) -> None:
        while True:
            result = await removal.run(make())
            if (result.rows, result.references, result.blobs) == (0, 0, 0):
                return
            totals.add(result.rows, result.references, result.blobs, reason)

    # 1. Rows that expired with their task, with the references they hold.
    for rule in ROW_RULES:
        life = _life(lifetimes, rule.retention)
        if life is None:
            continue
        async with _read(engine, removal) as conn:
            tasks = await _expired_tasks(conn, rule, now, life)
        for task_id in tasks:
            await drain(
                lambda r=rule, t=task_id, s=life: row_batch(r, t, now, s),  # type: ignore[misc]
                f"{rule.table} expired",
            )

    # 2. Events, through the prune (D11), to the end of each expired task's log.
    life = _life(lifetimes, EVENT_RETENTION)
    if life is not None:
        async with _read(engine, removal) as conn:
            found = await conn.execute(
                text(
                    "SELECT l.workflow_id FROM event_logs l JOIN tasks t "
                    "ON t.task_id = l.workflow_id WHERE t.ended_at IS NOT NULL "
                    "AND t.ended_at + make_interval(secs => :life) < :now "
                    "AND l.retained_base < l.next_offset ORDER BY 1"
                ),
                {"life": life, "now": now},
            )
            logs = [row[0] for row in found]
        transport = TableTransport(engine)
        for workflow_id in logs:
            await drain(
                lambda w=workflow_id: event_batch(  # type: ignore[misc]
                    transport,
                    w,
                    below=END_OF_LOG,
                    older_than=None,
                    limit=BATCH_LIMIT,
                    operation=removal.operation,
                    action="gc",
                    details={"reason": "events expired", "class": EVENT_RETENTION},
                )[0],
                "events expired",
            )

    # 3. References past their expiry whose holder row stays (tasks, uploads).
    async with _read(engine, removal) as conn:
        expired = [
            r for r in await refs.expired(conn, now, lifetimes) if r.holder_table not in ROW_HOLDERS
        ]
    for task_id, held in _by_task(expired).items():
        for chunk in _chunks(held):
            result = await removal.run(
                Batch(
                    "gc",
                    f"task:{task_id}",
                    chunk,
                    details={"reason": "references expired"},
                )
            )
            totals.add(result.rows, result.references, result.blobs, "references expired")

    # 4. Uploads of a task with no row, once Temporal has no live Workflow (D5).
    async with _read(engine, removal) as conn:
        rowless = await refs.rowless_uploads(conn, now, window)
    for task_id, held in _by_task(rowless).items():
        if await status_of(task_id) == "running":
            continue  # queued for a worker: its inputs are kept (R7)
        for chunk in _chunks(held):
            result = await removal.run(
                Batch(
                    "gc",
                    f"task:{task_id}",
                    chunk,
                    details={"reason": "uploads of a task that never started"},
                )
            )
            totals.add(result.rows, result.references, result.blobs, "row-less uploads")

    # 5. Orphans: bucket objects with no live reference, past the window (R8).
    listing = await bucket.list_objects()
    async with _read(engine, removal) as conn:
        orphans = [o for o in await refs.orphaned(conn, listing) if o.last_put_at < now - window]
    for start in range(0, len(orphans), BATCH_LIMIT):
        some = orphans[start : start + BATCH_LIMIT]
        result = await removal.run(
            Batch(
                "gc",
                "orphans",
                details={"reason": "orphaned past the safety window"},
                orphans={o.key: o.last_put_at for o in some},
            )
        )
        totals.add(result.rows, result.references, result.blobs, "orphans")
    return totals


@asynccontextmanager
async def _read(engine: AsyncEngine, removal: RemovalEngine) -> AsyncIterator[AsyncConnection]:
    """A connection for the run's planning queries: the dry run's own (so it sees
    its earlier batches), or a fresh one."""
    if removal.dry_connection is not None:
        yield removal.dry_connection
        return
    async with engine.connect() as conn:
        yield conn

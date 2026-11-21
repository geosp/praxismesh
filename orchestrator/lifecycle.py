"""Operator removals: `events prune` now; `gc` and `request delete` join it (Phase
3A persistence plan D4, D6, D11). Each runs through the removal engine in
batches of at most 500 rows, each with its tombstone, and prints its plan with
`--dry-run`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.blob_store.base import BlobStore
from common.events import TableTransport
from common.persistence.refs import event_holder
from common.persistence.removal import (
    BATCH_LIMIT,
    Batch,
    RefKey,
    RemovalEngine,
    operation_id,
)


@dataclass
class Totals:
    """What a run removed (or, dry, would remove), summed over its batches."""

    operation: str
    batches: int = 0
    rows: int = 0
    references: int = 0
    blobs: int = 0

    def add(self, rows: int, references: int, blobs: int) -> None:
        self.batches += 1
        self.rows += rows
        self.references += references
        self.blobs += blobs


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
    removal = RemovalEngine(engine, blobs, operation)
    transport = TableTransport(engine)
    totals = Totals(operation)
    if not dry_run:
        await removal.finish_pending()
    while True:
        batch, _ = event_batch(
            transport,
            workflow_id,
            below=below,
            older_than=older_than,
            limit=None if dry_run else BATCH_LIMIT,
            operation=operation,
        )
        result = await removal.run(batch, dry_run=dry_run)
        if result.rows == 0:
            break  # the prefix is gone; an empty batch commits nothing
        totals.add(result.rows, result.references, result.blobs)
        if dry_run:
            break  # one unlimited, rolled-back batch is the whole plan
    async with engine.connect() as conn:
        found = await conn.execute(
            text("SELECT retained_base FROM event_logs WHERE workflow_id = :w"),
            {"w": workflow_id},
        )
        base = found.scalar_one_or_none()
    return totals, None if base is None else int(base)

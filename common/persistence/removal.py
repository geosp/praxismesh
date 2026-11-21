"""The removal engine shared by `gc`, `request delete` and `events prune` (Phase 3A
persistence plan R3, R13, R15, D6; notes.md#d6, notes.md#revive).

One batch is one transaction, in this order:

1. take the task locks the batch names, in task-ID order (a delete's first
   batch; review F81), then lock the `blob_objects` rows of every key its
   references name, in key order (the order `put` uses);
2. delete, prune or redact the rows (the batch's own statements);
3. mark the references removed;
4. mark each blob left with no live reference (`removed_at`, `removed_by`);
5. write the batch's tombstone to `audit_log`.

Then, per marked blob, the bucket step: lock its row, and only if the mark still
stands (a `put` that committed first has cleared it) delete the object through
the inner store, holding the lock until the delete returns, and set
`bucket_deleted_at`. A run first finishes every blob marked by an earlier run
without its bucket step (R15). It never calls `RecordingBlobStore.delete`,
which would delete the `blob_objects` row.

A dry run executes the same batch and rolls it back, so it reports exactly what
the batch would change and changes nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.blob_store.base import BlobStore
from common.persistence.audit import AuditRepository
from common.persistence.fence import TASK_LOCK
from common.schemas import BlobRef

BATCH_LIMIT = 500  # rows per batch at most (D4)


def operation_id(kind: str) -> str:
    """A run's operation ID, shared by all its tombstones and marks: `gc:…`,
    `delete:…` (refs.DELETE_OPERATION) or `prune:…`."""
    return f"{kind}:{uuid.uuid4().hex}"


@dataclass(frozen=True)
class RefKey:
    """One `blob_refs` row, by its primary key."""

    holder_table: str
    holder_key: str
    holder_column: str
    blob_key: str


async def live_references(
    conn: AsyncConnection, task_ids: Sequence[str], *, holder_table: str | None = None
) -> list[RefKey]:
    """The live references the tasks hold, optionally of one holder table, in
    primary-key order."""
    found = await conn.execute(
        text(
            "SELECT holder_table, holder_key, holder_column, blob_key FROM blob_refs "
            "WHERE task_id = ANY(:t) AND removed_at IS NULL "
            "AND (CAST(:h AS text) IS NULL OR holder_table = :h) "
            "ORDER BY holder_table, holder_key, holder_column, blob_key"
        ),
        {"t": list(task_ids), "h": holder_table},
    )
    return [RefKey(*row) for row in found]


# The batch's own row changes, run inside its transaction; returns rows changed.
RowChange = Callable[[AsyncConnection], Awaitable[int]]


@dataclass
class Batch:
    """One removal batch: the references to mark, the row changes to make and
    what its tombstone says (counts are added by the engine)."""

    action: str  # the tombstone's action, for example "gc" or "request.delete"
    subject: str  # what it acts on, for example "request:REQ" or "task:T"
    references: Sequence[RefKey] = ()
    rows: RowChange | None = None
    details: dict[str, Any] = field(default_factory=dict)
    task_locks: Sequence[str] = ()


@dataclass(frozen=True)
class BatchResult:
    rows: int
    references: int
    blobs: int
    marked: tuple[str, ...]  # keys marked by this batch, for its bucket step
    tombstone: int | None  # audit_log ID; None for a dry run


class RemovalEngine:
    """Runs removal batches for one operation. `blobs` is the inner store (the
    bucket), never `RecordingBlobStore`."""

    def __init__(
        self,
        engine: AsyncEngine,
        blobs: BlobStore,
        operation: str,
        *,
        actor: str | None = None,
    ) -> None:
        self.engine = engine
        self.blobs = blobs
        self.operation = operation
        self.actor = actor

    async def run(self, batch: Batch, *, dry_run: bool = False) -> BatchResult:
        """Commit one batch (steps 1-5), then its bucket step. A dry run rolls the
        transaction back and skips the bucket."""
        async with self.engine.connect() as conn:
            transaction = await conn.begin()
            try:
                result = await self._batch(conn, batch, dry_run=dry_run)
            except BaseException:
                await transaction.rollback()
                raise
            if dry_run:
                await transaction.rollback()
                return result
            await transaction.commit()
        await self.finish(result.marked)
        return result

    async def _batch(self, conn: AsyncConnection, batch: Batch, *, dry_run: bool) -> BatchResult:
        for task_id in sorted(set(batch.task_locks)):
            await conn.execute(TASK_LOCK, {"t": task_id})
        refs = list(dict.fromkeys(batch.references))
        keys = sorted({r.blob_key for r in refs})
        if keys:
            await conn.execute(
                text("SELECT key FROM blob_objects WHERE key = ANY(:k) ORDER BY key FOR UPDATE"),
                {"k": keys},
            )
        rows = await batch.rows(conn) if batch.rows is not None else 0
        marked_refs = await self._mark_references(conn, refs)
        marked = await self._mark_free_blobs(conn, keys)
        counts = {"rows": rows, "references": marked_refs, "blobs": len(marked)}
        tombstone = await AuditRepository.append(
            conn,
            batch.action,
            batch.subject,
            {**batch.details, **counts},
            operation_id=self.operation,
            actor=self.actor,
        )
        return BatchResult(
            rows, marked_refs, len(marked), tuple(marked), None if dry_run else tombstone
        )

    async def _mark_references(self, conn: AsyncConnection, refs: Iterable[RefKey]) -> int:
        params = [
            {
                "ht": r.holder_table,
                "hk": r.holder_key,
                "hc": r.holder_column,
                "b": r.blob_key,
                "op": self.operation,
            }
            for r in refs
        ]
        if not params:
            return 0
        changed = 0
        for p in params:
            result = await conn.execute(
                text(
                    "UPDATE blob_refs SET removed_at = now(), removed_by = :op "
                    "WHERE holder_table = :ht AND holder_key = :hk AND holder_column = :hc "
                    "AND blob_key = :b AND removed_at IS NULL"
                ),
                p,
            )
            changed += result.rowcount
        return changed

    async def _mark_free_blobs(self, conn: AsyncConnection, keys: list[str]) -> list[str]:
        """Mark each of `keys` with no live reference left; already-marked blobs
        are not counted again. A key with no `blob_objects` row gets a marked row,
        so the bucket step still removes its object."""
        if not keys:
            return []
        free = await conn.execute(
            text(
                "SELECT k FROM unnest(CAST(:k AS text[])) AS k WHERE NOT EXISTS "
                "(SELECT 1 FROM blob_refs r WHERE r.blob_key = k AND r.removed_at IS NULL) "
                "ORDER BY k"
            ),
            {"k": keys},
        )
        free_keys = [row[0] for row in free]
        if not free_keys:
            return []
        await conn.execute(
            text(
                "INSERT INTO blob_objects (key, checksum, bytes, content_type, retention_class) "
                "SELECT k, 'sha256:' || substr(k, 8), 0, 'application/octet-stream', "
                "'ephemeral' FROM unnest(CAST(:k AS text[])) AS k ON CONFLICT (key) DO NOTHING"
            ),
            {"k": free_keys},
        )
        marked = await conn.execute(
            text(
                "UPDATE blob_objects SET removed_at = now(), removed_by = :op "
                "WHERE key = ANY(:k) AND removed_at IS NULL RETURNING key"
            ),
            {"k": free_keys, "op": self.operation},
        )
        return sorted(row[0] for row in marked)

    async def pending(self) -> list[str]:
        """Blobs marked by any earlier run whose bucket step never finished."""
        async with self.engine.connect() as conn:
            found = await conn.execute(
                text(
                    "SELECT key FROM blob_objects WHERE removed_at IS NOT NULL "
                    "AND bucket_deleted_at IS NULL ORDER BY key"
                )
            )
            return [row[0] for row in found]

    async def finish_pending(self) -> int:
        """Run the bucket step for every blob an earlier run left marked (R15).
        Call it once at the start of a run, before new batches."""
        return await self.finish(await self.pending())

    async def finish(self, keys: Iterable[str]) -> int:
        """The bucket step for each key; returns the objects deleted."""
        deleted = 0
        for key in keys:
            deleted += await self._bucket_step(key)
        return deleted

    async def _bucket_step(self, key: str) -> int:
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT key, checksum, bytes, content_type, retention_class, created_at, "
                        "removed_at FROM blob_objects WHERE key = :k FOR UPDATE"
                    ),
                    {"k": key},
                )
            ).first()
            if row is None or row.removed_at is None:
                return 0  # a `put` cleared the mark first: keep the object
            await self.blobs.delete(_ref(row))  # a missing object is not an error
            await self.after_bucket_delete(key)
            await conn.execute(
                text("UPDATE blob_objects SET bucket_deleted_at = now() WHERE key = :k"),
                {"k": key},
            )
            return 1

    async def after_bucket_delete(self, key: str) -> None:
        """Test hook: called after the object is deleted, before the row records
        it, inside the row's lock. A crash here leaves `bucket_deleted_at` null,
        and the next run deletes the (already missing) object again."""


def _ref(row: Any) -> BlobRef:
    return BlobRef(
        id=f"blob:{row.checksum.removeprefix('sha256:')}",
        key=row.key,
        checksum=row.checksum,
        content_type=row.content_type,
        bytes=row.bytes,
        retention_class=row.retention_class,
        created_at=row.created_at or datetime.now(UTC),
    )

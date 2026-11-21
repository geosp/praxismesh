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

A dry run executes the same batches in one transaction and rolls it back, so it
reports exactly what the run would change and changes nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.blob_store.base import BlobStore
from common.errors import PraxisError
from common.persistence.audit import AuditRepository
from common.persistence.refs import is_content_key
from common.schemas import BlobRef

BATCH_LIMIT = 500  # rows per batch at most (D4)

# The session-level advisory lock every removal command and `agentctl backup`
# hold for their whole run (D4): class 3, key 0.
RUN_LOCK = (3, 0)


class RemovalBusy(PraxisError):
    """Another `gc`, `request delete`, `events prune` or backup is running."""


class TaskBusy(RemovalBusy):
    """A batch could not take a task's lock at once: an attempt is writing."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"task {task_id} is busy writing; try again")
        self.task_id = task_id


# The transaction form of fence.TASK_LOCK, without waiting.
TRY_TASK_LOCK = text("SELECT pg_try_advisory_xact_lock(hashtext(:t))")


@asynccontextmanager
async def run_lock(engine: AsyncEngine) -> AsyncIterator[None]:
    """Hold D4's run lock on a dedicated connection for the body; fail at once,
    without waiting, if another run holds it. The lock is the session's, so it
    lasts across the run's batch transactions and ends with the connection."""
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        got = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:c, :k)"), {"c": RUN_LOCK[0], "k": RUN_LOCK[1]}
        )
        if not got:
            raise RemovalBusy(
                "another gc, request delete, events prune or backup is running; "
                "try again when it ends"
            )
        try:
            yield
        finally:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:c, :k)"), {"c": RUN_LOCK[0], "k": RUN_LOCK[1]}
            )


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
# Computes the batch's references inside its transaction, before any lock: for
# a removal that learns its range only from the rows (an events prune).
Collect = Callable[[AsyncConnection], Awaitable[Sequence["RefKey"]]]


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
    collect: Collect | None = None  # adds references, before the locks
    record_empty: bool = False  # commit a tombstone even if nothing changes
    # Orphans to mark: bucket key -> the last upload time the caller saw. Each is
    # marked only if it still has no live reference and no upload since then.
    orphans: Mapping[str, datetime] = field(default_factory=dict)


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
        dry_run: bool = False,
    ) -> None:
        self.engine = engine
        self.blobs = blobs
        self.operation = operation
        self.actor = actor
        self.dry_run = dry_run
        self._dry: AsyncConnection | None = None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[RemovalEngine]:
        """The scope of a run. A dry run is one transaction for the whole run,
        rolled back at the end: each batch sees the batches before it, so the
        plan is exactly what the real run would do, and nothing changes."""
        if not self.dry_run:
            yield self
            return
        async with self.engine.connect() as conn:
            transaction = await conn.begin()
            self._dry = conn
            try:
                yield self
            finally:
                self._dry = None
                await transaction.rollback()

    @property
    def dry_connection(self) -> AsyncConnection | None:
        """The dry run's connection while its session is open: a dry run's
        planning queries read through it, so they see its earlier batches."""
        return self._dry

    async def run(self, batch: Batch) -> BatchResult:
        """Commit one batch (steps 1-5), then its bucket step. In a dry run the
        batch joins the run's transaction and the bucket is never touched."""
        if self.dry_run:
            if self._dry is None:
                raise RuntimeError("a dry run's batches run inside session()")
            savepoint = await self._dry.begin_nested()
            result = await self._batch(self._dry, batch, dry_run=True)
            if (result.rows, result.references, result.blobs) == (0, 0, 0):
                await savepoint.rollback()
            else:
                await savepoint.commit()
            return result
        async with self.engine.connect() as conn:
            transaction = await conn.begin()
            try:
                result = await self._batch(conn, batch, dry_run=False)
            except BaseException:
                await transaction.rollback()
                raise
            empty = (result.rows, result.references, result.blobs) == (0, 0, 0)
            if empty and not batch.record_empty:
                # Nothing to commit: an empty batch leaves no tombstone.
                await transaction.rollback()
                return BatchResult(0, 0, 0, (), None)
            await transaction.commit()
        await self.finish(result.marked)
        return result

    async def finish_pending(self) -> int:
        """Run the bucket step for every blob an earlier run left marked (R15).
        Call it once at the start of a run, before new batches; a dry run skips it."""
        if self.dry_run:
            return 0
        return await self.finish(await self.pending())

    async def _batch(self, conn: AsyncConnection, batch: Batch, *, dry_run: bool) -> BatchResult:
        for task_id in sorted(set(batch.task_locks)):
            # Without waiting: an attempt's message write holds its task lock and
            # then waits for the request lock a delete holds (messages._enter), so
            # waiting here could never end. The caller releases and retries.
            got = await conn.scalar(TRY_TASK_LOCK, {"t": task_id})
            if not got:
                raise TaskBusy(task_id)
        collected = await batch.collect(conn) if batch.collect is not None else ()
        refs = list(dict.fromkeys([*batch.references, *collected]))
        keys = sorted({r.blob_key for r in refs} | set(batch.orphans))
        if keys:
            # Every key gets a row before the lock, so no key goes unlocked: a
            # `put` racing this batch waits for it (review F126). An orphan's row
            # keeps the upload time the caller saw, so `_mark_orphans` can tell a
            # new upload; a referenced key's row is only a placeholder.
            await _ensure_rows(conn, {k: batch.orphans.get(k) for k in keys})
            await conn.execute(
                text("SELECT key FROM blob_objects WHERE key = ANY(:k) ORDER BY key FOR UPDATE"),
                {"k": keys},
            )
        rows = await batch.rows(conn) if batch.rows is not None else 0
        marked_refs = await self._mark_references(conn, refs)
        marked = await self._mark_free_blobs(conn, sorted({r.blob_key for r in refs}))
        marked = sorted([*marked, *await self._mark_orphans(conn, batch.orphans)])
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

    async def _mark_references(self, conn: AsyncConnection, refs: Sequence[RefKey]) -> int:
        """Mark the references and count those this transaction marked, including
        any the row changes marked themselves (a prune marks its events'):
        `now()` is the transaction's start time, the same for every mark in it."""
        if not refs:
            return 0
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
        where = "holder_table = :ht AND holder_key = :hk AND holder_column = :hc AND blob_key = :b"
        await conn.execute(
            text(
                f"UPDATE blob_refs SET removed_at = now(), removed_by = :op "
                f"WHERE {where} AND removed_at IS NULL"
            ),
            params,
        )
        marked = 0
        for p in params:
            found = await conn.execute(
                text(
                    f"SELECT count(*) FROM blob_refs WHERE {where} "
                    "AND removed_by = :op AND removed_at = now()"
                ),
                p,
            )
            marked += int(found.scalar_one())
        return marked

    async def _mark_free_blobs(self, conn: AsyncConnection, keys: list[str]) -> list[str]:
        """Mark each of `keys` with no live reference left, in one statement under
        the batch's row locks; already-marked blobs are not counted again."""
        if not keys:
            return []
        marked = await conn.execute(
            text(
                "UPDATE blob_objects b SET removed_at = now(), removed_by = :op "
                "WHERE b.key = ANY(:k) AND b.removed_at IS NULL AND NOT EXISTS "
                "(SELECT 1 FROM blob_refs r WHERE r.blob_key = b.key AND r.removed_at IS NULL) "
                "RETURNING b.key"
            ),
            {"k": keys, "op": self.operation},
        )
        return sorted(row[0] for row in marked)

    async def _mark_orphans(
        self, conn: AsyncConnection, orphans: Mapping[str, datetime]
    ) -> list[str]:
        """Mark orphans that are still orphans: no live reference, and no upload
        since the time the caller saw (a `put` after the bucket listing keeps
        its blob). `_ensure_rows` gave a key with no row one, at that time."""
        marked: list[str] = []
        for key, seen in sorted(orphans.items()):
            if not is_content_key(key):
                continue  # never recorded: its row could not be addressed (F119)
            found = await conn.execute(
                text(
                    "UPDATE blob_objects SET removed_at = now(), removed_by = :op "
                    "WHERE key = :k AND removed_at IS NULL AND last_put_at <= :seen "
                    "AND NOT EXISTS (SELECT 1 FROM blob_refs r WHERE r.blob_key = :k "
                    "AND r.removed_at IS NULL) RETURNING key"
                ),
                {"k": key, "seen": seen, "op": self.operation},
            )
            marked += [row[0] for row in found]
        return marked

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


async def _ensure_rows(conn: AsyncConnection, keys: Mapping[str, datetime | None]) -> None:
    """Insert a placeholder `blob_objects` row for each content key that has none:
    the batch can then lock it, and the bucket step can remove its object. Its
    `last_put_at` is the time given (an orphan's last upload seen), else now."""
    rows = [{"k": key, "seen": seen} for key, seen in sorted(keys.items()) if is_content_key(key)]
    if rows:
        await conn.execute(
            text(
                "INSERT INTO blob_objects (key, checksum, bytes, content_type, retention_class, "
                "last_put_at) VALUES (:k, 'sha256:' || substr(:k, 8), 0, "
                "'application/octet-stream', 'ephemeral', coalesce(CAST(:seen AS timestamptz), "
                "now())) ON CONFLICT (key) DO NOTHING"
            ),
            rows,
        )


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

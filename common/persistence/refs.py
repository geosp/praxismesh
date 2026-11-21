"""The reference index (`blob_refs`) and its checks (Phase 3A persistence plan D2,
D4, D5; notes.md#d2).

One row per holder and blob. A holder is a row that stores a `BlobRef` (table,
primary key as text, column), or a task for its own uploads (`upload`, task ID,
''). A live reference has `removed_at` null; removed references stay, marked.

The checks, shared by migration tests, `gc` and `reconcile`:
- *unindexed*: a `BlobRef` stored in a row with no index row for that holder;
- *dangling*: a live reference whose blob is marked removed or missing from the
  bucket;
- *orphaned*: a bucket object with no live reference that is not marked for
  removal, aged by `last_put_at`, or by the bucket's `LastModified` when it has
  no `blob_objects` row (review F80: a blob whose references are all removed but
  whose mark was cleared is reached here).

Expiry is computed here, never stored. All functions run on the caller's
connection, so they join the caller's transaction.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from common.blob_store.base import RETENTION_ORDER, BucketObject, current_class
from common.persistence.fence import DELETED
from common.persistence.retention import DEFAULT_LIFETIME, REFERENCE_CLASS, SAFETY_WINDOW
from common.schemas import BlobRef, RetentionClass

UPLOAD = "upload"  # holder table of an upload reference
# A delete's operation ID starts with this; its marks are never cleared (D10, R25).
DELETE_OPERATION = "delete:"

# Every BlobRef stored in a row (notes.md#refs), with its holder and its class
# from notes.md#d3's blob table, never the class in the JSON. Identical to
# migration 0007's REFERENCES; a unit test keeps them in step.
REFERENCES = """
SELECT t.instructions_ref->>'key' AS blob_key, 'tasks' AS holder_table,
    t.task_id AS holder_key, 'instructions_ref' AS holder_column, t.task_id,
    t.request_id, 'transcript' AS retention_class
FROM tasks t WHERE json_typeof(t.instructions_ref) = 'object'
UNION
SELECT e.value->>'key', 'tasks', t.task_id, 'input_refs', t.task_id, t.request_id,
    'transcript'
FROM tasks t, json_each(CASE WHEN json_typeof(t.input_refs) = 'object'
    THEN t.input_refs ELSE '{}'::json END) e
UNION
SELECT a.value->'ref'->>'key', 'tasks', t.task_id, 'result', t.task_id, t.request_id,
    'artifact'
FROM tasks t, json_array_elements(CASE WHEN json_typeof(t.result) = 'object'
    AND json_typeof(t.result->'artifacts') = 'array'
    THEN t.result->'artifacts' ELSE '[]'::json END) a
UNION
SELECT c.workspace_ref->>'key', 'checkpoints',
    c.task_id || '/' || c.turn || '/' || c.attempt || '/' || c.seq, 'workspace_ref',
    c.task_id, t.request_id, 'checkpoint'
FROM checkpoints c LEFT JOIN tasks t ON t.task_id = c.task_id
WHERE json_typeof(c.workspace_ref) = 'object'
UNION
SELECT c.session_ref->>'key', 'checkpoints',
    c.task_id || '/' || c.turn || '/' || c.attempt || '/' || c.seq, 'session_ref',
    c.task_id, t.request_id, 'checkpoint'
FROM checkpoints c LEFT JOIN tasks t ON t.task_id = c.task_id
WHERE c.session_ref IS NOT NULL AND json_typeof(c.session_ref) = 'object'
UNION
SELECT e.blob_ref->>'key', 'agent_events', e.workflow_id || '/' || e."offset",
    'blob_ref', e.task_id, t.request_id, 'transcript'
FROM agent_events e LEFT JOIN tasks t ON t.task_id = e.task_id
WHERE e.blob_ref IS NOT NULL AND json_typeof(e.blob_ref) = 'object'
"""

_COLUMNS = "blob_key, holder_table, holder_key, holder_column, task_id, request_id, retention_class"
_CONTENT_KEY = re.compile(r"^sha256/([0-9a-f]{64})$")


def rank_sql(column: str) -> str:
    """A SQL expression ranking the class in `column` by `RETENTION_ORDER`."""
    cases = " ".join(f"WHEN '{c}' THEN {n}" for c, n in RETENTION_ORDER.items())
    return f"(CASE {column} {cases} END)"


def _lifetime_sql(column: str, lifetimes: Mapping[RetentionClass, timedelta | None]) -> str:
    """Seconds of the class's lifetime, NULL for a class that is kept."""
    cases = " ".join(
        f"WHEN '{c}' THEN {int(life.total_seconds())}"
        for c, life in lifetimes.items()
        if life is not None
    )
    return f"(CASE {column} {cases} END)"


@dataclass(frozen=True)
class Holder:
    """What holds a reference: a row's table, primary key as text and column, or
    (`upload`, task ID, '') for a task's own uploads."""

    table: str
    key: str
    column: str


def task_holder(task_id: str, column: str) -> Holder:
    return Holder("tasks", task_id, column)


def checkpoint_holder(task_id: str, turn: int, attempt: int, seq: int, column: str) -> Holder:
    return Holder("checkpoints", f"{task_id}/{turn}/{attempt}/{seq}", column)


def event_holder(workflow_id: str, offset: int) -> Holder:
    return Holder("agent_events", f"{workflow_id}/{offset}", "blob_ref")


def upload_holder(task_id: str) -> Holder:
    return Holder(UPLOAD, task_id, "")


async def delete_mark(conn: AsyncConnection, task_id: str) -> str | None:
    """The operation of a delete that marked the task's references, if any: such
    a task is deleted and its late uploads revive nothing (R25; review F80, F81).
    A task with a `deleted` attempt row is deleted too, even if the delete marked
    none of its references (review F125)."""
    found = await conn.execute(
        text(
            "SELECT removed_by FROM blob_refs WHERE task_id = :t "
            "AND removed_by LIKE :d ORDER BY removed_at LIMIT 1"
        ),
        {"t": task_id, "d": f"{DELETE_OPERATION}%"},
    )
    mark = found.scalar_one_or_none()
    if mark is not None:
        return str(mark)
    fenced = await conn.execute(text(f"SELECT 1 WHERE {DELETED}"), {"t": task_id})
    return f"{DELETE_OPERATION}{task_id}" if fenced.first() is not None else None


async def index_refs(
    conn: AsyncConnection,
    holder: Holder,
    refs: Iterable[BlobRef],
    *,
    task_id: str,
    request_id: str | None = None,
    retention: RetentionClass | None = None,
) -> None:
    await index_keys(
        conn,
        holder,
        [ref.key for ref in refs],
        task_id=task_id,
        request_id=request_id,
        retention=retention,
    )


async def index_keys(
    conn: AsyncConnection,
    holder: Holder,
    blob_keys: Iterable[str],
    *,
    task_id: str,
    request_id: str | None = None,
    retention: RetentionClass | None = None,
    removed_by: str | None = None,
) -> None:
    """Write the holder's `blob_refs` rows in the caller's transaction (D2).

    The class is `retention`, or the holder's class from notes.md#d3. The request
    is `request_id`, or the task's from `tasks`; an upload reference has none. On
    conflict the stronger class wins and a GC mark is cleared; a delete's mark
    stays, so a deleted task never makes its reference live again (R25).
    `removed_by` writes the rows already marked by that operation (a deleted
    task's late upload, review F81).
    """
    cls = current_class(retention or REFERENCE_CLASS[(holder.table, holder.column)])
    keys = sorted(set(blob_keys))
    if not keys:
        return
    request = (
        "NULL"
        if holder.table == UPLOAD
        else "coalesce(CAST(:r AS text), (SELECT request_id FROM tasks WHERE task_id = :t))"
    )
    kept = f"blob_refs.removed_by LIKE '{DELETE_OPERATION}%'"
    await conn.execute(
        text(
            f"INSERT INTO blob_refs ({_COLUMNS}, removed_at, removed_by) "
            f"VALUES (:b, :ht, :hk, :hc, :t, {request}, :c, "
            "CASE WHEN CAST(:m AS text) IS NOT NULL THEN now() END, :m) "
            "ON CONFLICT (holder_table, holder_key, holder_column, blob_key) DO UPDATE SET "
            f"retention_class = CASE WHEN {rank_sql('EXCLUDED.retention_class')} "
            f"> {rank_sql('blob_refs.retention_class')} THEN EXCLUDED.retention_class "
            "ELSE blob_refs.retention_class END, "
            f"removed_at = CASE WHEN {kept} THEN blob_refs.removed_at "
            "ELSE EXCLUDED.removed_at END, "
            f"removed_by = CASE WHEN {kept} THEN blob_refs.removed_by "
            "ELSE EXCLUDED.removed_by END"
        ),
        [
            {
                "b": key,
                "ht": holder.table,
                "hk": holder.key,
                "hc": holder.column,
                "t": task_id,
                "r": request_id,
                "c": cls,
                "m": removed_by,
            }
            for key in keys
        ],
    )


@dataclass(frozen=True)
class Reference:
    blob_key: str
    holder_table: str
    holder_key: str
    holder_column: str
    task_id: str
    request_id: str | None
    retention_class: str


@dataclass(frozen=True)
class Orphan:
    key: str
    last_put_at: datetime


@dataclass(frozen=True)
class Reindexed:
    references: int
    blobs: int


def _refs(rows: Iterable[object]) -> list[Reference]:
    return [Reference(*row) for row in rows]  # type: ignore[misc]


async def unindexed(conn: AsyncConnection) -> list[Reference]:
    rows = await conn.execute(
        text(
            f"SELECT {_COLUMNS} FROM ({REFERENCES}) r WHERE r.blob_key IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM blob_refs b WHERE b.holder_table = r.holder_table "
            "AND b.holder_key = r.holder_key AND b.holder_column = r.holder_column "
            "AND b.blob_key = r.blob_key) "
            "ORDER BY holder_table, holder_key, holder_column, blob_key"
        )
    )
    return _refs(rows)


async def dangling(conn: AsyncConnection, bucket: Mapping[str, BucketObject]) -> list[Reference]:
    """Live references whose blob is marked removed or not in the bucket listing."""
    rows = await conn.execute(
        text(
            "SELECT r.blob_key, r.holder_table, r.holder_key, r.holder_column, r.task_id, "
            "r.request_id, r.retention_class, b.removed_at IS NOT NULL AS marked "
            "FROM blob_refs r LEFT JOIN blob_objects b ON b.key = r.blob_key "
            "WHERE r.removed_at IS NULL "
            "ORDER BY r.blob_key, r.holder_table, r.holder_key, r.holder_column"
        )
    )
    return [Reference(*row[:7]) for row in rows if row.marked or row.blob_key not in bucket]


async def orphaned(conn: AsyncConnection, bucket: Mapping[str, BucketObject]) -> list[Orphan]:
    """Bucket objects with no live reference and no removal mark (a marked one
    waits for the bucket step), with their last upload time."""
    held = {
        row[0]
        for row in await conn.execute(
            text(
                "SELECT DISTINCT blob_key FROM blob_refs "
                "WHERE blob_key = ANY(:k) AND removed_at IS NULL"
            ),
            {"k": list(bucket)},
        )
    }
    recorded = {
        row[0]: (row[1], row[2])
        for row in await conn.execute(
            text(
                "SELECT key, last_put_at, removed_at IS NOT NULL FROM blob_objects "
                "WHERE key = ANY(:k)"
            ),
            {"k": list(bucket)},
        )
    }
    return [
        Orphan(key, recorded[key][0] if key in recorded else obj.last_modified)
        for key, obj in sorted(bucket.items())
        if key not in held and not (key in recorded and recorded[key][1])
    ]


async def expired(
    conn: AsyncConnection,
    now: datetime,
    lifetimes: Mapping[RetentionClass, timedelta | None] = DEFAULT_LIFETIME,
) -> list[Reference]:
    """Live references past their expiry (notes.md#d2): their task ended longer
    ago than the class's lifetime, or they are `ephemeral` and older than its
    lifetime. Upload references of a task with no row are `rowless_uploads`."""
    life = _lifetime_sql("r.retention_class", lifetimes)
    rows = await conn.execute(
        text(
            f"SELECT r.blob_key, r.holder_table, r.holder_key, r.holder_column, r.task_id, "
            f"r.request_id, r.retention_class FROM blob_refs r "
            f"LEFT JOIN tasks t ON t.task_id = r.task_id WHERE r.removed_at IS NULL AND ("
            f"(t.ended_at IS NOT NULL AND t.ended_at + make_interval(secs => {life}) < :now) "
            f"OR (r.retention_class = 'ephemeral' "
            f"AND r.created_at + make_interval(secs => {life}) < :now)) "
            f"ORDER BY r.task_id, r.holder_table, r.holder_key, r.holder_column, r.blob_key"
        ),
        {"now": now},
    )
    return _refs(rows)


async def rowless_uploads(
    conn: AsyncConnection, now: datetime, window: timedelta = SAFETY_WINDOW
) -> list[Reference]:
    """Live upload references of a task with no `tasks` row, whose blob was last
    uploaded more than `window` ago. They expire only if Temporal reports the
    task's Workflow missing or closed, which the caller asks (D5)."""
    rows = await conn.execute(
        text(
            "SELECT r.blob_key, r.holder_table, r.holder_key, r.holder_column, r.task_id, "
            "r.request_id, r.retention_class FROM blob_refs r "
            "JOIN blob_objects b ON b.key = r.blob_key "
            "WHERE r.removed_at IS NULL AND r.holder_table = :upload "
            "AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.task_id = r.task_id) "
            "AND b.last_put_at < :cutoff ORDER BY r.task_id, r.blob_key"
        ),
        {"upload": UPLOAD, "cutoff": now - window},
    )
    return _refs(rows)


async def reindex(conn: AsyncConnection, bucket: Mapping[str, BucketObject]) -> Reindexed:
    """Index every unindexed reference, as migration 0007's backfill does, and add
    a `blob_objects` row (`last_put_at` now) for each content-addressed bucket
    object that has none. Running it again changes nothing."""
    added = await conn.execute(
        text(
            f"INSERT INTO blob_refs ({_COLUMNS}) SELECT {_COLUMNS} FROM ({REFERENCES}) r "
            "WHERE r.blob_key IS NOT NULL ON CONFLICT DO NOTHING RETURNING blob_key"
        )
    )
    added_keys = [row[0] for row in added]
    new_keys = sorted(set(added_keys))
    strongest = (
        f"(SELECT r.retention_class FROM blob_refs r WHERE r.blob_key = b.key "
        f"ORDER BY {rank_sql('r.retention_class')} DESC LIMIT 1)"
    )
    if new_keys:
        # A newly indexed reference may need a longer-lived blob class.
        await conn.execute(
            text(
                f"UPDATE blob_objects b SET retention_class = {strongest} "
                f"WHERE b.key = ANY(:k) AND {rank_sql(strongest)} "
                f"> {rank_sql('b.retention_class')}"
            ),
            {"k": new_keys},
        )
    blobs = 0
    for key, obj in sorted(bucket.items()):
        match = _CONTENT_KEY.match(key)
        if match is None:
            continue  # not a content key: reported as an orphan, never recorded
        inserted = await conn.execute(
            text(
                "INSERT INTO blob_objects (key, checksum, bytes, content_type, retention_class, "
                "last_put_at) SELECT :k, :c, :b, 'application/octet-stream', "
                f"coalesce({strongest.replace('b.key', ':k')}, 'ephemeral'), now() "
                "ON CONFLICT (key) DO NOTHING RETURNING key"
            ),
            {"k": key, "c": f"sha256:{match.group(1)}", "b": obj.size},
        )
        blobs += len(inserted.all())
    return Reindexed(references=len(added_keys), blobs=blobs)

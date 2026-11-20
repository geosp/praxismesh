"""Phase 3A persistence plan, phase 01: the reference index, §4.13's classes, the
audit log and task end times (plan D2, D3; notes.md#d2, notes.md#d3).

- `blob_refs`: one row per holder and blob. A holder is a row (table, primary
  key as text, column) or, for an upload, the task (`upload`, task ID, '').
  Removed references stay, marked by `removed_at`/`removed_by`.
- `audit_log`: append-only; a trigger refuses UPDATE and DELETE (R14).
- `tasks.ended_at`; `blob_objects.removed_at`, `removed_by`, `last_put_at` and
  `bucket_deleted_at`.
- Retention classes become ephemeral, checkpoint, transcript, artifact and audit.
  Every check still allows `task`, so an old worker started by mistake inserts.
  Each table's `task` and `audit` rows move to the table's class; each blob
  takes the longest-lived class of its index rows, or `ephemeral` with none.

The backfill reads the JSON columns in SQL. Each index row's class comes from
its holder table and column, never from the stored JSON. `last_put_at` is set to
the migration time, since the old `put` never recorded a repeat upload.
`common/persistence/refs.py` holds the same reference query for the checks and
`reconcile --reindex`; a test keeps them in step.

Downgrade works only before new code writes anything and with no Workflow
running (plan, Rollout & rollback).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("CURRENT_TIMESTAMP")
OLD = ("ephemeral", "task", "audit")
NEW = ("ephemeral", "checkpoint", "transcript", "artifact", "audit", "task")
RANK = (
    "CASE {c} WHEN 'ephemeral' THEN 0 WHEN 'checkpoint' THEN 1 WHEN 'transcript' THEN 2 "
    "WHEN 'task' THEN 2 WHEN 'artifact' THEN 3 WHEN 'audit' THEN 4 END"
)

# Each table's class (notes.md#d3), and its class and server default before 0007.
# blob_objects has no default: it takes its blob's class.
TABLES: dict[str, tuple[str, str | None]] = {
    "tasks": ("audit", None),
    "task_attempts": ("audit", None),
    "checkpoints": ("checkpoint", None),
    "idempotency_keys": ("transcript", "audit"),
    "sample_orders": ("artifact", "task"),
    "agent_sessions": ("transcript", "task"),
    "agent_messages": ("transcript", "task"),
    "usage_ledger": ("audit", "audit"),
    "event_logs": ("transcript", "task"),
    "agent_events": ("transcript", "task"),
    "event_batches": ("ephemeral", "task"),
    "task_messages": ("transcript", "task"),
    "task_inbox": ("transcript", "task"),
    "message_wakes": ("ephemeral", "ephemeral"),
}
# The class each table's rows had before 0007 (for the downgrade).
OLD_CLASS = {
    "tasks": "audit",
    "task_attempts": "audit",
    "checkpoints": "task",
    "idempotency_keys": "audit",
    "sample_orders": "task",
    "agent_sessions": "task",
    "agent_messages": "task",
    "usage_ledger": "audit",
    "event_logs": "task",
    "agent_events": "task",
    "event_batches": "task",
    "task_messages": "task",
    "task_inbox": "task",
}

# Every BlobRef stored in a row (notes.md#refs), with its holder and its class
# from notes.md#d3's blob table. Columns: blob_key, holder_table, holder_key,
# holder_column, task_id, request_id, retention_class. Kept identical to
# common/persistence/refs.py's REFERENCES.
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

ENDED = "('succeeded', 'failed', 'needs_input')"


def _check(table: str, classes: tuple[str, ...]) -> None:
    name = f"{table}_retention_class_check"
    op.drop_constraint(name, table, type_="check")
    values = ", ".join(f"'{c}'" for c in classes)
    op.create_check_constraint(name, table, f"retention_class IN ({values})")


def _default(table: str, value: str | None) -> None:
    op.alter_column(
        table, "retention_class", server_default=sa.text(f"'{value}'") if value else None
    )


def upgrade() -> None:
    op.create_table(
        "blob_refs",
        sa.Column("blob_key", sa.Text, nullable=False),
        sa.Column("holder_table", sa.Text, nullable=False),
        sa.Column("holder_key", sa.Text, nullable=False),
        sa.Column("holder_column", sa.Text, nullable=False),
        sa.Column("task_id", sa.Text, nullable=False),
        sa.Column("request_id", sa.Text),
        sa.Column("retention_class", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.Column("removed_by", sa.Text),
        sa.PrimaryKeyConstraint("holder_table", "holder_key", "holder_column", "blob_key"),
        sa.CheckConstraint(
            "retention_class IN (" + ", ".join(f"'{c}'" for c in NEW) + ")",
            name="blob_refs_retention_class_check",
        ),
    )
    op.create_index("blob_refs_blob_key", "blob_refs", ["blob_key"])
    op.create_index("blob_refs_task", "blob_refs", ["task_id"])
    op.create_index("blob_refs_request", "blob_refs", ["request_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("operation_id", sa.Text),
        sa.Column("details", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("retention_class", sa.Text, nullable=False, server_default=sa.text("'audit'")),
        sa.CheckConstraint(
            "retention_class IN (" + ", ".join(f"'{c}'" for c in NEW) + ")",
            name="audit_log_retention_class_check",
        ),
    )
    op.create_index("audit_log_operation", "audit_log", ["operation_id"])
    op.execute(
        """
        CREATE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % refused', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"
    )

    op.add_column("tasks", sa.Column("ended_at", sa.DateTime(timezone=True)))
    op.add_column("blob_objects", sa.Column("removed_at", sa.DateTime(timezone=True)))
    op.add_column("blob_objects", sa.Column("removed_by", sa.Text))
    # Existing rows get the migration time (notes.md#d2).
    op.add_column(
        "blob_objects",
        sa.Column("last_put_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.add_column("blob_objects", sa.Column("bucket_deleted_at", sa.DateTime(timezone=True)))

    for table in (*TABLES, "blob_objects"):
        _check(table, NEW)
    for table, (cls, _) in TABLES.items():
        op.execute(
            f"UPDATE {table} SET retention_class = '{cls}' "
            "WHERE retention_class IN ('task', 'audit')"
        )
        _default(table, cls)

    op.execute(f"UPDATE tasks SET ended_at = updated_at WHERE status IN {ENDED}")
    op.execute(
        "INSERT INTO blob_refs (blob_key, holder_table, holder_key, holder_column, task_id, "
        f"request_id, retention_class) SELECT * FROM ({REFERENCES}) r "
        "WHERE r.blob_key IS NOT NULL ON CONFLICT DO NOTHING"
    )
    op.execute(
        f"""
        UPDATE blob_objects b SET retention_class = coalesce(
            (SELECT r.retention_class FROM blob_refs r WHERE r.blob_key = b.key
             ORDER BY {RANK.format(c="r.retention_class")} DESC LIMIT 1),
            'ephemeral')
        """
    )


def downgrade() -> None:
    op.execute(
        "UPDATE blob_objects SET retention_class = CASE retention_class "
        "WHEN 'artifact' THEN 'audit' WHEN 'checkpoint' THEN 'task' "
        "WHEN 'transcript' THEN 'task' ELSE retention_class END"
    )
    for table, (_, old_default) in TABLES.items():
        old = OLD_CLASS.get(table)
        if old is not None:
            op.execute(
                f"UPDATE {table} SET retention_class = '{old}' "
                "WHERE retention_class NOT IN ('ephemeral', 'task', 'audit')"
            )
        _default(table, old_default)
    for table in (*TABLES, "blob_objects"):
        _check(table, OLD)
    op.drop_column("blob_objects", "bucket_deleted_at")
    op.drop_column("blob_objects", "last_put_at")
    op.drop_column("blob_objects", "removed_by")
    op.drop_column("blob_objects", "removed_at")
    op.drop_column("tasks", "ended_at")
    op.execute("DROP TRIGGER audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION audit_log_append_only()")
    op.drop_index("audit_log_operation", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("blob_refs_request", table_name="blob_refs")
    op.drop_index("blob_refs_task", table_name="blob_refs")
    op.drop_index("blob_refs_blob_key", table_name="blob_refs")
    op.drop_table("blob_refs")

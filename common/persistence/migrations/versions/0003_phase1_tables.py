"""Phase 1 tables: tasks, attempts, checkpoints, idempotency, blob metadata,
sample orders, and the openai-agents session store (RFC Phase 1, migration 0003).

Every table has `retention_class NOT NULL` limited to ephemeral, task or audit.
Tables that an SDK or the sample server writes default it to 'task', so their
inserts still record a class. The session tables mirror the layout that
`agents.extensions.memory.SQLAlchemySession` expects; it never creates them.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("CURRENT_TIMESTAMP")


def retention(default: str | None = None) -> list[sa.Column[str] | sa.CheckConstraint]:
    column = sa.Column(
        "retention_class",
        sa.Text,
        nullable=False,
        server_default=sa.text(f"'{default}'") if default else None,
    )
    check = sa.CheckConstraint("retention_class IN ('ephemeral', 'task', 'audit')")
    return [column, check]


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("task_id", sa.Text, primary_key=True),
        sa.Column("workflow_id", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("request_id", sa.Text, nullable=False),
        sa.Column("profile", sa.Text, nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("template_version", sa.Integer, nullable=False),
        sa.Column("template_hash", sa.Text, nullable=False),
        sa.Column("instructions_ref", sa.JSON, nullable=False),
        sa.Column("input_refs", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("outputs", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("result", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        *retention(),
    )
    op.create_table(
        "task_attempts",
        sa.Column("task_id", sa.Text, sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("turn", sa.Integer, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("worker_identity", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("failure_category", sa.Text),
        sa.Column("tokens_in", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("task_id", "turn", "attempt"),
        *retention(),
    )
    op.create_table(
        "checkpoints",
        sa.Column("checkpoint_id", sa.Text, nullable=False, unique=True),
        sa.Column("task_id", sa.Text, sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("turn", sa.Integer, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("session_position", sa.Integer, nullable=False),
        sa.Column("workspace_ref", sa.JSON, nullable=False),
        sa.Column("finish", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.PrimaryKeyConstraint("task_id", "turn", "attempt", "seq"),
        *retention(),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("task_id", sa.Text, nullable=False),
        sa.Column("tool", sa.Text, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        *retention("audit"),
    )
    op.create_table(
        "blob_objects",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("checksum", sa.Text, nullable=False),
        sa.Column("bytes", sa.BigInteger, nullable=False),
        sa.Column("content_type", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        *retention(),
    )
    op.create_table(
        "sample_orders",
        sa.Column("order_id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("task_id", sa.Text, nullable=False),
        sa.Column("sku", sa.Text, nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        *retention("task"),
    )
    # Layout of agents.extensions.memory.SQLAlchemySession (openai-agents 0.24.0).
    op.create_table(
        "agent_sessions",
        sa.Column("session_id", sa.String, primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=False), nullable=False, server_default=NOW),
        *retention("task"),
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String,
            sa.ForeignKey("agent_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_data", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), nullable=False, server_default=NOW),
        *retention("task"),
    )
    op.create_index(
        "idx_agent_messages_session_time", "agent_messages", ["session_id", "created_at"]
    )


def downgrade() -> None:
    for table in (
        "agent_messages",
        "agent_sessions",
        "sample_orders",
        "blob_objects",
        "idempotency_keys",
        "checkpoints",
        "task_attempts",
        "tasks",
    ):
        op.drop_table(table)

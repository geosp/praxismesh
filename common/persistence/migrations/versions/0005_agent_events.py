"""Phase 2 events plan D1: the agent event log (ADR-0009).

Additive only:
- `event_logs` holds each workflow's next offset and retained base; a publish
  locks its row, so offsets are gap-free per workflow;
- `agent_events` holds the events, keyed by workflow and offset; its columns
  mirror `AgentEvent`;
- `event_batches` holds the batch IDs seen in the last 600 s, so a re-sent batch
  is stored once (each publish deletes older rows of its workflow).

Every row carries retention class `task` (plan §4.13).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("CURRENT_TIMESTAMP")


def _retention() -> list[sa.SchemaItem]:
    return [
        sa.Column("retention_class", sa.Text, nullable=False, server_default=sa.text("'task'")),
        sa.CheckConstraint("retention_class IN ('ephemeral', 'task', 'audit')"),
    ]


def upgrade() -> None:
    op.create_table(
        "event_logs",
        sa.Column("workflow_id", sa.Text, primary_key=True),
        sa.Column("next_offset", sa.BigInteger, nullable=False, server_default="1"),
        sa.Column("retained_base", sa.BigInteger, nullable=False, server_default="1"),
        *_retention(),
    )
    op.create_table(
        "agent_events",
        sa.Column("workflow_id", sa.Text, nullable=False),
        sa.Column("offset", sa.BigInteger, nullable=False),
        sa.Column("task_id", sa.Text, nullable=False),
        sa.Column("attempt_id", sa.Text, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("blob_ref", sa.JSON),
        sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        *_retention(),
        sa.PrimaryKeyConstraint("workflow_id", "offset"),
    )
    op.create_table(
        "event_batches",
        sa.Column("workflow_id", sa.Text, nullable=False),
        sa.Column("batch_id", sa.Text, nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        *_retention(),
        sa.PrimaryKeyConstraint("workflow_id", "batch_id"),
    )


def downgrade() -> None:
    op.drop_table("event_batches")
    op.drop_table("agent_events")
    op.drop_table("event_logs")

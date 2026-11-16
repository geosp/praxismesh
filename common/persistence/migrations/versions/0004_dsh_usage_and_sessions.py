"""DSH migration plan D7: explicit unknown usage, a usage ledger, session blobs.

Additive only, so the previous code keeps working against this schema:
- `task_attempts.tokens_in/tokens_out` become nullable; `usage_known` (default
  true) marks rows whose usage could not be observed (stored as NULL, never 0);
- `usage_ledger` records each model request before dispatch and its settled
  usage after (D9), keyed by task, turn, attempt and request;
- `checkpoints.session_ref` / `session_digest` hold a DSH session blob (D1);
  `session_position` stays the integer it is for openai_agents (0 for DSH).

Code rolled back below this migration is not supported (plan, Rollout).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.alter_column("task_attempts", "tokens_in", nullable=True)
    op.alter_column("task_attempts", "tokens_out", nullable=True)
    op.add_column(
        "task_attempts",
        sa.Column("usage_known", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "usage_ledger",
        sa.Column("task_id", sa.Text, sa.ForeignKey("tasks.task_id"), nullable=False),
        sa.Column("turn", sa.Integer, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("request_id", sa.Text, nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("input_tokens", sa.BigInteger),
        sa.Column("output_tokens", sa.BigInteger),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("retention_class", sa.Text, nullable=False, server_default=sa.text("'audit'")),
        sa.CheckConstraint("retention_class IN ('ephemeral', 'task', 'audit')"),
        sa.PrimaryKeyConstraint("task_id", "turn", "attempt", "request_id"),
    )
    op.add_column("checkpoints", sa.Column("session_ref", sa.JSON))
    op.add_column("checkpoints", sa.Column("session_digest", sa.Text))


def downgrade() -> None:
    op.drop_column("checkpoints", "session_digest")
    op.drop_column("checkpoints", "session_ref")
    op.drop_table("usage_ledger")
    op.drop_column("task_attempts", "usage_known")
    op.execute("UPDATE task_attempts SET tokens_in = 0 WHERE tokens_in IS NULL")
    op.execute("UPDATE task_attempts SET tokens_out = 0 WHERE tokens_out IS NULL")
    op.alter_column("task_attempts", "tokens_in", nullable=False)
    op.alter_column("task_attempts", "tokens_out", nullable=False)

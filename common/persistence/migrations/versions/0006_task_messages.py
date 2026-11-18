"""Phase 2 messaging D6, D13: the inbox, its wake rows and the comms role's grants.

Additive only:
- `task_messages`: one row per message, question or reply between tasks of a
  request, with its status, deadline, idempotency key and the turn that claimed it
  (`agent_messages` is the openai_agents session store's table, migration 0003);
- `task_inbox`: per task, whether it is sleeping (its last claim found nothing);
  only a sleeping task gets a wake row;
- `message_wakes`: at most one pending wake per recipient Workflow, turned into an
  `inbox` Signal by the dispatcher.

`praxis_comms` (created by infra/db/roles.sh) gets only what comms_mcp needs; the
grants apply when the role exists, and roles.sh grants them again if it is created
later.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("CURRENT_TIMESTAMP")
GRANTS = {
    "task_messages": "SELECT, INSERT, UPDATE",
    "task_inbox": "SELECT",
    "message_wakes": "INSERT",
    "tasks": "SELECT",
    "task_attempts": "SELECT",
}


def _retention(default: str) -> list[sa.schema.SchemaItem]:
    return [
        sa.Column(
            "retention_class", sa.Text, nullable=False, server_default=sa.text(f"'{default}'")
        ),
        sa.CheckConstraint("retention_class IN ('ephemeral', 'task', 'audit')"),
    ]


def _for_comms_role(statements: str) -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'praxis_comms') "
        f"THEN {statements} END IF; END $$"
    )


def upgrade() -> None:
    op.create_table(
        "task_messages",
        sa.Column("message_id", sa.Text, primary_key=True),
        sa.Column("request_id", sa.Text, nullable=False),
        sa.Column("sender_task", sa.Text, nullable=False),
        sa.Column("recipient_task", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("correlation_id", sa.Text),
        sa.Column("reply_to", sa.Text),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("claimed_turn", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        *_retention("task"),
        sa.CheckConstraint("kind IN ('send', 'ask', 'reply')"),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'read', 'answered', 'expired', 'cancelled', "
            "'undelivered', 'rejected')"
        ),
        sa.CheckConstraint("length(body) <= 16384"),
    )
    op.create_index("task_messages_recipient", "task_messages", ["recipient_task", "status"])
    op.create_index("task_messages_sender", "task_messages", ["sender_task", "status"])
    op.create_index("task_messages_request", "task_messages", ["request_id"])
    op.create_table(
        "task_inbox",
        sa.Column("task_id", sa.Text, primary_key=True),
        sa.Column("sleeping", sa.Boolean, nullable=False, server_default=sa.false()),
        *_retention("task"),
    )
    op.create_table(
        "message_wakes",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("recipient_workflow", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        *_retention("ephemeral"),
    )
    _for_comms_role(
        " ".join(f"GRANT {privs} ON {table} TO praxis_comms;" for table, privs in GRANTS.items())
    )


def downgrade() -> None:
    _for_comms_role(" ".join(f"REVOKE ALL ON {table} FROM praxis_comms;" for table in GRANTS))
    op.drop_table("message_wakes")
    op.drop_table("task_inbox")
    op.drop_index("task_messages_request", table_name="task_messages")
    op.drop_index("task_messages_sender", table_name="task_messages")
    op.drop_index("task_messages_recipient", table_name="task_messages")
    op.drop_table("task_messages")

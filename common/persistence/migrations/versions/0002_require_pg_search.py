"""Require the pg_search extension (ADR-0002).

Creating the extension needs the superuser, so infra/db/init.sh installs it.
This revision only checks that it is there and fails with a clear message if
not. Downgrading is a no-op.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    installed = (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'pg_search'"))
        .scalar()
    )
    if installed is None:
        raise RuntimeError(
            "pg_search is not installed in the praxismesh database; "
            "infra/db/init.sh installs it on a fresh volume (run make reset)"
        )


def downgrade() -> None:
    pass

"""The append-only audit log (`audit_log`, migration 0007; Phase 3A persistence
plan R13, R14, D6). A removal batch writes its tombstone here, in the batch's own
transaction; a trigger refuses UPDATE and DELETE."""

from __future__ import annotations

import getpass
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


def cli_actor() -> str:
    """`cli:<OS user>`: an operator running the CLI is the only actor (plan,
    Assumptions)."""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):  # no passwd entry, for example in a container
        user = "unknown"
    return f"cli:{user}"


class AuditRepository:
    @staticmethod
    async def append(
        conn: AsyncConnection,
        action: str,
        subject: str,
        details: dict[str, Any],
        *,
        operation_id: str | None = None,
        actor: str | None = None,
    ) -> int:
        """Append one row in the caller's transaction and return its ID. `details`
        holds counts, reasons and IDs, never removed content."""
        row = await conn.execute(
            text(
                "INSERT INTO audit_log (actor, action, subject, operation_id, details) "
                "VALUES (:actor, :action, :subject, :op, CAST(:details AS json)) RETURNING id"
            ),
            {
                "actor": actor or cli_actor(),
                "action": action,
                "subject": subject,
                "op": operation_id,
                "details": json.dumps(details),
            },
        )
        return int(row.scalar_one())

"""The audit log is append-only for the app role (Phase 3A persistence plan R14)."""

from __future__ import annotations

import pytest
from sqlalchemy import exc, text

from common.persistence.audit import AuditRepository, cli_actor
from common.persistence.repositories import make_engine
from tests.support.stack import run_id

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET subject = 'changed' WHERE operation_id = :op",
        "DELETE FROM audit_log WHERE operation_id = :op",
    ],
)
async def test_app_role_cannot_change_audit_rows(statement: str) -> None:
    engine = make_engine()
    op = f"test-{run_id()}"
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO audit_log (actor, action, subject, operation_id) "
                    "VALUES ('test', 'check', 'subject', :op)"
                ),
                {"op": op},
            )
        with pytest.raises(exc.DBAPIError, match="audit_log is append-only"):
            async with engine.begin() as conn:
                await conn.execute(text(statement), {"op": op})
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT subject FROM audit_log WHERE operation_id = :op"), {"op": op}
            )
            assert row.scalar_one() == "subject"
    finally:
        await engine.dispose()


async def test_append_joins_the_callers_transaction() -> None:
    engine = make_engine()
    op = f"test-{run_id()}"
    details = {"reason": "test", "rows": 2, "references": 3, "blobs": 1}
    try:
        with pytest.raises(RuntimeError, match="rolled back"):
            async with engine.begin() as conn:
                await AuditRepository.append(conn, "gc", "rolled-back", {}, operation_id=op)
                raise RuntimeError("rolled back")
        async with engine.begin() as conn:
            row_id = await AuditRepository.append(conn, "gc", "batch 1", details, operation_id=op)
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, actor, action, subject, details, retention_class, created_at "
                    "FROM audit_log WHERE operation_id = :op"
                ),
                {"op": op},
            )
            (row,) = list(rows)
    finally:
        await engine.dispose()
    assert row.id == row_id and row.actor == cli_actor() and row.actor.startswith("cli:")
    assert (row.action, row.subject, row.details) == ("gc", "batch 1", details)
    assert row.retention_class == "audit" and row.created_at is not None

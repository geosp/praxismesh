"""The audit log is append-only for the app role (Phase 3A persistence plan R14)."""

from __future__ import annotations

import pytest
from sqlalchemy import exc, text

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

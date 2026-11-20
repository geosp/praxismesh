"""Migration 0007 on a scratch database: the reference backfill, the class remap,
end times, and a downgrade and upgrade again (Phase 3A persistence plan phase 01
task 1.1; R2, R19).

The superuser creates the scratch database, so the stack's own `praxismesh`
database is never migrated or seeded here.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from common.blob_store.base import content_key, make_ref
from common.persistence.settings import app_database_url

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "common" / "persistence" / "alembic.ini"
NOW = datetime(2026, 11, 1, tzinfo=UTC)


def superuser_url(database: str = "postgres") -> Any:
    return app_database_url(user="postgres", database=database, password_var="POSTGRES_PASSWORD")


async def migrate(database: str, target: str, *, down: bool = False) -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database"] = database
    step = command.downgrade if down else command.upgrade
    # env.py runs its own event loop, so it runs in a thread.
    await asyncio.to_thread(step, config, target)


@pytest.fixture
async def scratch() -> AsyncIterator[tuple[str, AsyncEngine]]:
    name = f"praxis_scratch_{uuid.uuid4().hex[:10]}"
    admin = create_async_engine(superuser_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f"CREATE DATABASE {name} OWNER praxismesh TEMPLATE template0"))
    db_admin = create_async_engine(superuser_url(name))
    async with db_admin.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search CASCADE"))
    await db_admin.dispose()
    engine = create_async_engine(app_database_url(database=name))
    try:
        yield name, engine
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        await admin.dispose()


def ref(label: str, retention: str) -> dict[str, Any]:
    key, checksum = content_key(label.encode())
    out = make_ref(key, checksum, "text/plain", len(label), "task", NOW).model_dump(mode="json")
    out["retention_class"] = retention  # recorded as the old code wrote it
    return out


REFS = {
    "instructions": ref("instructions", "task"),
    "input": ref("input file", "task"),
    "artifact": ref("artifact", "audit"),
    "workspace": ref("workspace", "task"),
    "session": ref("session", "task"),
    "event": ref("event attachment", "task"),
    "running": ref("running instructions", "task"),
}
ORPHAN = content_key(b"orphan")[0]


async def seed(conn: AsyncConnection) -> None:
    """One row of every kind in notes.md#refs, at migration 0006."""
    task = "task-ended"
    for task_id, status, instructions, inputs, result in (
        (
            task,
            "succeeded",
            REFS["instructions"],
            {"in.txt": REFS["input"]},
            {"task_id": task, "artifacts": [{"path": "out.txt", "ref": REFS["artifact"]}]},
        ),
        ("task-running", "running", REFS["running"], {}, None),
    ):
        await conn.execute(
            text(
                "INSERT INTO tasks (task_id, workflow_id, run_id, request_id, profile, template, "
                "template_version, template_hash, instructions_ref, input_refs, status, result, "
                "updated_at, retention_class) VALUES (:t, :t, 'run', 'req-1', 'p', 'tpl', 1, "
                "'h', :i, :in, :s, :r, :u, 'audit')"
            ),
            {
                "t": task_id,
                "i": json.dumps(instructions),
                "in": json.dumps(inputs),
                "s": status,
                "r": json.dumps(result) if result else None,
                "u": NOW,
            },
        )
    await conn.execute(
        text(
            "INSERT INTO task_attempts (task_id, turn, attempt, worker_identity, outcome, "
            "retention_class) VALUES (:t, 1, 1, 'w', 'done', 'audit')"
        ),
        {"t": task},
    )
    await conn.execute(
        text(
            "INSERT INTO checkpoints (checkpoint_id, task_id, turn, attempt, seq, session_id, "
            "session_position, workspace_ref, session_ref, retention_class) "
            "VALUES ('cp-1', :t, 1, 1, 0, :t, 0, :w, :s, 'task'), "
            "('cp-2', :t, 1, 1, 1, :t, 0, :w, NULL, 'task')"
        ),
        {"t": task, "w": json.dumps(REFS["workspace"]), "s": json.dumps(REFS["session"])},
    )
    await conn.execute(
        text(
            'INSERT INTO agent_events (workflow_id, "offset", task_id, attempt_id, seq, type, '
            "blob_ref, emitted_at) VALUES (:t, 1, :t, 'a', 1, 'status', :b, :n), "
            "(:t, 2, :t, 'a', 2, 'status', NULL, :n)"
        ),
        {"t": task, "b": json.dumps(REFS["event"]), "n": NOW},
    )
    for name, r in (*REFS.items(), ("orphan", {"key": ORPHAN, "retention_class": "task"})):
        await conn.execute(
            text(
                "INSERT INTO blob_objects (key, checksum, bytes, content_type, retention_class) "
                "VALUES (:k, :c, 1, 'text/plain', :r)"
            ),
            {"k": r["key"], "c": f"sha256:{name}", "r": r["retention_class"]},
        )
    defaults = (
        "INSERT INTO sample_orders (task_id, sku, qty, idempotency_key) VALUES (:t, 's', 1, 'k')",
        "INSERT INTO agent_sessions (session_id) VALUES (:t)",
        "INSERT INTO agent_messages (session_id, message_data) VALUES (:t, 'hi')",
        "INSERT INTO idempotency_keys (key, task_id, tool, result) VALUES ('k', :t, 'x', '{}')",
        "INSERT INTO usage_ledger (task_id, turn, attempt, request_id, purpose) "
        "VALUES (:t, 1, 1, 'r', 'turn')",
        "INSERT INTO event_logs (workflow_id, next_offset) VALUES (:t, 3)",
        "INSERT INTO event_batches (workflow_id, batch_id) VALUES (:t, 'b')",
        "INSERT INTO task_messages (message_id, request_id, sender_task, recipient_task, kind, "
        "status, body, idempotency_key) VALUES ('m', 'req-1', :t, 'task-running', 'send', "
        "'pending', 'hello', 'mk')",
        "INSERT INTO task_inbox (task_id) VALUES (:t)",
        "INSERT INTO message_wakes (recipient_workflow) VALUES ('task-running')",
    )
    for sql in defaults:
        await conn.execute(text(sql), {"t": task})


EXPECTED_CLASS = {
    "tasks": {"audit"},
    "task_attempts": {"audit"},
    "checkpoints": {"checkpoint"},
    "idempotency_keys": {"transcript"},
    "sample_orders": {"artifact"},
    "agent_sessions": {"transcript"},
    "agent_messages": {"transcript"},
    "usage_ledger": {"audit"},
    "event_logs": {"transcript"},
    "agent_events": {"transcript"},
    "event_batches": {"ephemeral"},
    "task_messages": {"transcript"},
    "task_inbox": {"transcript"},
    "message_wakes": {"ephemeral"},
}
EXPECTED_REFS = {
    ("tasks", "task-ended", "instructions_ref", REFS["instructions"]["key"], "transcript"),
    ("tasks", "task-ended", "input_refs", REFS["input"]["key"], "transcript"),
    ("tasks", "task-ended", "result", REFS["artifact"]["key"], "artifact"),
    ("tasks", "task-running", "instructions_ref", REFS["running"]["key"], "transcript"),
    ("checkpoints", "task-ended/1/1/0", "workspace_ref", REFS["workspace"]["key"], "checkpoint"),
    ("checkpoints", "task-ended/1/1/0", "session_ref", REFS["session"]["key"], "checkpoint"),
    ("checkpoints", "task-ended/1/1/1", "workspace_ref", REFS["workspace"]["key"], "checkpoint"),
    ("agent_events", "task-ended/1", "blob_ref", REFS["event"]["key"], "transcript"),
}
EXPECTED_BLOBS = {
    REFS["instructions"]["key"]: "transcript",
    REFS["input"]["key"]: "transcript",
    REFS["artifact"]["key"]: "artifact",
    REFS["workspace"]["key"]: "checkpoint",
    REFS["session"]["key"]: "checkpoint",
    REFS["event"]["key"]: "transcript",
    REFS["running"]["key"]: "transcript",
    ORPHAN: "ephemeral",
}


async def classes(conn: AsyncConnection, table: str) -> set[str]:
    rows = await conn.execute(text(f"SELECT DISTINCT retention_class FROM {table}"))
    return {r[0] for r in rows}


async def assert_migrated(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        for table, expected in EXPECTED_CLASS.items():
            assert await classes(conn, table) == expected, table
        refs = await conn.execute(
            text(
                "SELECT holder_table, holder_key, holder_column, blob_key, retention_class, "
                "task_id, request_id, removed_at FROM blob_refs"
            )
        )
        rows = list(refs)
        assert {tuple(r[:5]) for r in rows} == EXPECTED_REFS
        assert all(r.task_id in r.holder_key and r.request_id == "req-1" for r in rows)
        assert all(r.removed_at is None for r in rows)
        blobs = await conn.execute(
            text("SELECT key, retention_class, last_put_at, removed_at FROM blob_objects")
        )
        blob_rows = list(blobs)
        assert {r.key: r.retention_class for r in blob_rows} == EXPECTED_BLOBS
        assert all(r.last_put_at is not None and r.removed_at is None for r in blob_rows)
        ended = await conn.execute(text("SELECT task_id, ended_at FROM tasks ORDER BY task_id"))
        assert {r.task_id: r.ended_at for r in ended} == {"task-ended": NOW, "task-running": None}


async def test_migration_0007_backfills_remaps_and_round_trips(
    scratch: tuple[str, AsyncEngine],
) -> None:
    name, engine = scratch
    await migrate(name, "0006")
    async with engine.begin() as conn:
        await seed(conn)

    await migrate(name, "0007")
    await assert_migrated(engine)

    await migrate(name, "0006", down=True)
    async with engine.connect() as conn:
        for table in ("blob_refs", "audit_log"):
            missing = await conn.execute(text(f"SELECT to_regclass('public.{table}')"))
            assert missing.scalar() is None
        assert await classes(conn, "checkpoints") == {"task"}
        assert await classes(conn, "idempotency_keys") == {"audit"}
        assert await classes(conn, "sample_orders") == {"task"}
        blobs = await conn.execute(text("SELECT key, retention_class FROM blob_objects"))
        old = {"artifact": "audit", "ephemeral": "ephemeral"}
        assert {r.key: r.retention_class for r in blobs} == {
            k: old.get(v, "task") for k, v in EXPECTED_BLOBS.items()
        }

    await migrate(name, "0007")
    await assert_migrated(engine)


async def test_new_defaults_and_checks(scratch: tuple[str, AsyncEngine]) -> None:
    name, engine = scratch
    await migrate(name, "0007")
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO event_logs (workflow_id) VALUES ('w')"))
        assert await classes(conn, "event_logs") == {"transcript"}
        # An old worker's 'task' still inserts (notes.md#d3).
        await conn.execute(
            text("INSERT INTO task_inbox (task_id, retention_class) VALUES ('t', 'task')")
        )
    with pytest.raises(Exception, match="retention_class_check"):
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO task_inbox (task_id, retention_class) VALUES ('u', 'forever')")
            )

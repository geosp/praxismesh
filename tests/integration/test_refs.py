"""The reference checks, the expiry query and reindex on a scratch database at
head (Phase 3A persistence plan phase 01 task 1.4; R2, D4, D5; notes.md#d2).

Each check reads the whole database, so these tests run on their own database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from common.blob_store.base import BucketObject, content_key, make_ref
from common.persistence import refs
from tests.support.scratch_db import scratch_database

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    async with scratch_database("head") as (_, engine):
        yield engine


def key(label: str) -> str:
    return content_key(label.encode())[0]


def ref_json(label: str) -> str:
    k, checksum = content_key(label.encode())
    return make_ref(k, checksum, "text/plain", len(label), "transcript", NOW).model_dump_json()


def listing(*keys: str, modified: datetime = NOW) -> dict[str, BucketObject]:
    return {k: BucketObject(k, 1, modified) for k in keys}


async def add_task(
    conn: AsyncConnection,
    task_id: str,
    *,
    status: str = "running",
    ended: datetime | None = None,
    instructions: str | None = None,
) -> None:
    await conn.execute(
        text(
            "INSERT INTO tasks (task_id, workflow_id, run_id, request_id, profile, template, "
            "template_version, template_hash, instructions_ref, status, ended_at) "
            "VALUES (:t, :t, 'run', 'req', 'p', 'tpl', 1, 'h', :i, :s, :e)"
        ),
        {"t": task_id, "i": ref_json(instructions or task_id), "s": status, "e": ended},
    )


async def add_ref(
    conn: AsyncConnection, blob: str, holder: tuple[str, str, str], task_id: str, **extra: Any
) -> None:
    values = {"created_at": NOW, "retention_class": "checkpoint"} | extra
    await conn.execute(
        text(
            "INSERT INTO blob_refs (blob_key, holder_table, holder_key, holder_column, task_id, "
            "retention_class, created_at) VALUES (:b, :ht, :hk, :hc, :t, :c, :at)"
        ),
        {
            "b": blob,
            "ht": holder[0],
            "hk": holder[1],
            "hc": holder[2],
            "t": task_id,
            "c": values["retention_class"],
            "at": values["created_at"],
        },
    )


async def add_blob(conn: AsyncConnection, blob: str, **extra: Any) -> None:
    await conn.execute(
        text(
            "INSERT INTO blob_objects (key, checksum, bytes, content_type, retention_class, "
            "last_put_at, removed_at) VALUES (:k, 'sha256:x', 1, 'text/plain', 'transcript', "
            ":p, :r)"
        ),
        {"k": blob, "p": extra.get("last_put_at", NOW), "r": extra.get("removed_at")},
    )


async def test_unindexed_then_reindex_twice(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await add_task(conn, "task-a")
        await conn.execute(
            text(
                "INSERT INTO checkpoints (checkpoint_id, task_id, turn, attempt, seq, "
                "session_id, session_position, workspace_ref) "
                "VALUES ('cp', 'task-a', 1, 2, 3, 's', 0, :w)"
            ),
            {"w": ref_json("workspace")},
        )
        found = await refs.unindexed(conn)
        assert {(r.holder_table, r.holder_key, r.holder_column) for r in found} == {
            ("tasks", "task-a", "instructions_ref"),
            ("checkpoints", "task-a/1/2/3", "workspace_ref"),
        }
        assert {r.retention_class for r in found} == {"transcript", "checkpoint"}

        bucket = listing(key("task-a"), key("workspace"), key("bucket only"), "not/a/content-key")
        first = await refs.reindex(conn, bucket)
        assert first == refs.Reindexed(references=2, blobs=3)
        assert await refs.unindexed(conn) == []
        second = await refs.reindex(conn, bucket)
        assert second == refs.Reindexed(references=0, blobs=0)

        blobs = await conn.execute(text("SELECT key, retention_class FROM blob_objects"))
        assert {r.key: r.retention_class for r in blobs} == {
            key("task-a"): "transcript",
            key("workspace"): "checkpoint",
            key("bucket only"): "ephemeral",
        }


async def test_dangling_references(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await add_ref(conn, key("missing"), ("upload", "task-x", ""), "task-x")
        await add_ref(conn, key("marked"), ("upload", "task-x", ""), "task-x")
        await add_ref(conn, key("present"), ("upload", "task-x", ""), "task-x")
        await add_ref(
            conn, key("gone but removed"), ("upload", "task-y", ""), "task-y", created_at=NOW
        )
        await conn.execute(
            text("UPDATE blob_refs SET removed_at = now() WHERE blob_key = :k"),
            {"k": key("gone but removed")},
        )
        await add_blob(conn, key("marked"), removed_at=NOW)
        await add_blob(conn, key("present"))
        found = await refs.dangling(conn, listing(key("marked"), key("present")))
        assert {r.blob_key for r in found} == {key("missing"), key("marked")}


async def test_orphans_with_their_age(engine: AsyncEngine) -> None:
    old = NOW - timedelta(hours=25)
    modified = NOW - timedelta(hours=3)
    async with engine.begin() as conn:
        await add_blob(conn, key("recorded orphan"), last_put_at=old)
        await add_ref(conn, key("held"), ("upload", "task-x", ""), "task-x")
        bucket = listing(key("recorded orphan"), key("bucket only"), key("held"), modified=modified)
        found = await refs.orphaned(conn, bucket)
    assert found == [
        refs.Orphan(k, at)
        for k, at in sorted({key("recorded orphan"): old, key("bucket only"): modified}.items())
    ]


async def test_expiry(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for task_id, ended in (
            ("task-8d", NOW - timedelta(days=8)),
            ("task-6d", NOW - timedelta(days=6)),
            ("task-running", None),
        ):
            await add_task(conn, task_id, status="succeeded" if ended else "running", ended=ended)
            await add_ref(conn, key(f"{task_id} ws"), ("checkpoints", task_id, "w"), task_id)
            # A stale attempt's late upload expires with its task (notes.md#d2).
            await add_ref(
                conn,
                key(f"{task_id} late"),
                ("upload", task_id, ""),
                task_id,
                created_at=NOW,
            )
            await add_ref(
                conn,
                key(f"{task_id} audit"),
                ("tasks", task_id, "x"),
                task_id,
                retention_class="audit",
                created_at=NOW - timedelta(days=3650),
            )
        await add_ref(
            conn,
            key("old ephemeral"),
            ("upload", "task-running", "e"),
            "task-running",
            retention_class="ephemeral",
            created_at=NOW - timedelta(days=2),
        )
        await add_ref(
            conn,
            key("new ephemeral"),
            ("upload", "task-running", "f"),
            "task-running",
            retention_class="ephemeral",
            created_at=NOW - timedelta(hours=2),
        )
        found = await refs.expired(conn, NOW)
    assert {r.blob_key for r in found} == {
        key("task-8d ws"),
        key("task-8d late"),
        key("old ephemeral"),
    }


async def test_rowless_uploads_wait_for_the_window(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for label, put_at in (("25h", NOW - timedelta(hours=25)), ("1h", NOW - timedelta(hours=1))):
            await add_blob(conn, key(label), last_put_at=put_at)
            await add_ref(conn, key(label), ("upload", f"task-{label}", ""), f"task-{label}")
        await add_task(conn, "task-with-row")
        await add_blob(conn, key("has row"), last_put_at=NOW - timedelta(days=3))
        await add_ref(conn, key("has row"), ("upload", "task-with-row", ""), "task-with-row")
        found = await refs.rowless_uploads(conn, NOW)
    assert [(r.task_id, r.blob_key) for r in found] == [("task-25h", key("25h"))]

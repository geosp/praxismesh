"""Retention classes, their order and lifetimes, and each table's class against
notes.md#d3, the one source (Phase 3A persistence plan phase 01 task 1.3; R4, R5,
D3)."""

from __future__ import annotations

import importlib.util
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import get_args

import pytest

from common.blob_store import MemoryBlobStore
from common.blob_store.base import RETENTION_ORDER, content_key, current_class, stronger
from common.blob_store.memory import _Object
from common.persistence.retention import (
    APP_TABLES,
    DEFAULT_LIFETIME,
    REFERENCE_CLASS,
    TABLE_CLASS,
)
from common.schemas import BlobRef, RetentionClass

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/notes.md"
MIGRATION = ROOT / "common/persistence/migrations/versions/0007_blob_refs_and_classes.py"
CLASSES: tuple[RetentionClass, ...] = get_args(RetentionClass)


def d3_tables() -> list[tuple[str, str]]:
    """(cell of table names, cell of class) for each row of d3's first table."""
    section = NOTES.read_text().split("\n## d3\n", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0] not in ("Rows", "---") and not cells[0].startswith("-"):
            rows.append((cells[0], cells[1]))
        elif rows and not line.startswith("|"):
            break
    return rows


def notes_table_class() -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for names, cls in d3_tables():
        # A parenthesis explains the anchor; its backticked names are columns.
        tables = re.findall(r"`([a-z_]+)`", re.sub(r"\([^)]*\)", "", names))
        value = re.fullmatch(r"`([a-z]+)`", cls)
        for table in tables:
            found[table] = value.group(1) if value else None
    return found


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0007", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_app_table_has_its_d3_class() -> None:
    notes = notes_table_class()
    assert set(notes) == set(APP_TABLES)
    assert notes == TABLE_CLASS


def test_migration_0007_uses_the_same_classes() -> None:
    tables = migration().TABLES
    assert {t: cls for t, (cls, _) in tables.items()} == {
        t: c for t, c in TABLE_CLASS.items() if t not in ("blob_objects", "blob_refs", "audit_log")
    }


def test_reference_classes_match_d3_blob_table() -> None:
    assert set(REFERENCE_CLASS.values()) == {"transcript", "checkpoint", "artifact"}
    assert REFERENCE_CLASS[("tasks", "result")] == "artifact"
    assert REFERENCE_CLASS[("checkpoints", "workspace_ref")] == "checkpoint"
    assert REFERENCE_CLASS[("checkpoints", "session_ref")] == "checkpoint"


def test_order_and_lifetimes() -> None:
    assert set(RETENTION_ORDER) == set(CLASSES) == set(DEFAULT_LIFETIME)
    ordered = sorted((c for c in CLASSES if c != "task"), key=RETENTION_ORDER.__getitem__)
    assert ordered == ["ephemeral", "checkpoint", "transcript", "artifact", "audit"]
    assert RETENTION_ORDER["task"] == RETENTION_ORDER["transcript"]
    assert {
        "ephemeral": timedelta(days=1),
        "checkpoint": timedelta(days=7),
        "transcript": timedelta(days=30),
        "artifact": timedelta(days=90),
        "audit": None,
        "task": timedelta(days=30),
    } == DEFAULT_LIFETIME


@pytest.mark.parametrize("other", CLASSES)
def test_stronger_never_returns_task(other: RetentionClass) -> None:
    pairs: tuple[tuple[RetentionClass, RetentionClass], ...] = (("task", other), (other, "task"))
    for a, b in pairs:
        result = stronger(a, b)
        assert result != "task"
        assert RETENTION_ORDER[result] == max(
            RETENTION_ORDER[current_class(a)], RETENTION_ORDER[current_class(b)]
        )


def test_old_payloads_still_decode() -> None:
    key, checksum = content_key(b"x")
    ref = BlobRef(
        id="blob:x",
        key=key,
        checksum=checksum,
        content_type="text/plain",
        bytes=1,
        retention_class="task",
        created_at=datetime.now(UTC),
    )
    assert BlobRef.model_validate_json(ref.model_dump_json()).retention_class == "task"


async def test_repeat_put_over_task_metadata() -> None:
    """An object stored by Phase 1-2 code carries `task`; a repeat put never
    returns it (notes.md#d3)."""
    store = MemoryBlobStore()
    data = b"stored before migration 0007"
    key, _ = content_key(data)
    store.objects[key] = _Object(data, "text/plain", "task", datetime.now(UTC))
    assert (await store.put(data, retention="checkpoint")).retention_class == "transcript"
    assert (await store.put(data, retention="artifact")).retention_class == "artifact"


async def test_task_is_never_written() -> None:
    store = MemoryBlobStore()
    assert (await store.put(b"new", retention="task")).retention_class == "transcript"

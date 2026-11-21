"""restore.sh's first step, `python -m orchestrator.backup check-backup DIR`
(Phase 3A persistence plan R16, D8; impl-review F179): a backup is checked
before anything is dropped. It needs its whole manifest, this checkout's
backup format and migration head, and every dump and object at the size the
manifest gives."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.backup import FORMAT, MANIFEST, RestoreRefused, check_backup, checkout_head


def make_backup(root: Path, **manifest: Any) -> Path:
    for db in ("praxismesh", "temporal", "temporal_visibility"):
        (root / f"{db}.dump").write_bytes(b"PGDMP" + db.encode())
    (root / "blobs" / "sha256").mkdir(parents=True)
    (root / "blobs" / "sha256" / "ab").write_bytes(b"object")
    body: dict[str, Any] = {
        "format": FORMAT,
        "migration": checkout_head(),
        "databases": {
            db: {"file": f"{db}.dump", "bytes": len(b"PGDMP" + db.encode())}
            for db in ("praxismesh", "temporal", "temporal_visibility")
        },
        "objects": [{"key": "sha256/ab", "bytes": 6, "content_type": "x", "metadata": {}}],
    }
    body.update(manifest)
    (root / MANIFEST).write_text(json.dumps(body))
    return root


def test_a_complete_backup_passes(tmp_path: Path) -> None:
    check_backup(make_backup(tmp_path))


def test_a_directory_without_a_manifest_is_refused(tmp_path: Path) -> None:
    (make_backup(tmp_path) / MANIFEST).unlink()
    with pytest.raises(RestoreRefused, match=r"no manifest\.json"):
        check_backup(tmp_path)


def test_a_truncated_manifest_is_refused(tmp_path: Path) -> None:
    manifest = make_backup(tmp_path) / MANIFEST
    manifest.write_text(manifest.read_text()[:40])
    with pytest.raises(RestoreRefused, match="not valid JSON"):
        check_backup(tmp_path)


def test_another_format_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RestoreRefused, match="format 99"):
        check_backup(make_backup(tmp_path, format=99))


def test_another_migration_head_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RestoreRefused, match=r"migration 0001.*this checkout's .* at "):
        check_backup(make_backup(tmp_path, migration="0001"))


def test_a_truncated_dump_is_refused(tmp_path: Path) -> None:
    dump = make_backup(tmp_path) / "temporal.dump"
    dump.write_bytes(dump.read_bytes()[:3])
    with pytest.raises(RestoreRefused, match=r"temporal\.dump is 3 bytes"):
        check_backup(tmp_path)


def test_a_missing_dump_is_refused(tmp_path: Path) -> None:
    (make_backup(tmp_path) / "praxismesh.dump").unlink()
    with pytest.raises(RestoreRefused, match=r"praxismesh\.dump is missing"):
        check_backup(tmp_path)


def test_a_missing_object_is_refused(tmp_path: Path) -> None:
    (make_backup(tmp_path) / "blobs" / "sha256" / "ab").unlink()
    with pytest.raises(RestoreRefused, match="sha256/ab is missing"):
        check_backup(tmp_path)

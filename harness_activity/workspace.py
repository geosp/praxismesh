"""Workspace snapshots (RFC Phase 1: run_harness_turn, checkpoint).

Snapshots are deterministic tar.gz archives: sorted entries, zero mtime, uid and
gid, and gzip mtime 0. The same files always give the same bytes, so an unchanged
workspace adds no new blob (keys are content-addressed). `.skills/` is excluded;
it is mounted from the template on every restore.
"""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

EXCLUDED = (".skills",)


def _members(root: Path) -> list[Path]:
    paths = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in EXCLUDED:
            continue
        if path.is_symlink():
            continue  # never follow or archive links out of the workspace
        paths.append(path)
    return paths


def pack(root: Path) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in _members(root):
            info = tar.gettarinfo(str(path), arcname=str(path.relative_to(root)))
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if path.is_dir() or info.mode & 0o100 else 0o644
            if path.is_file():
                with path.open("rb") as f:
                    tar.addfile(info, f)
            else:
                tar.addfile(info)
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def unpack(data: bytes, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(root, filter="data")

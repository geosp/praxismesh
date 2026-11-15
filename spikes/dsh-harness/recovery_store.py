"""Trusted spike-only checkpoint/effect authority, never mounted into DSH.

SQLite transactions serialize attempt ownership and authoritative publications.
The controller, not the candidate, establishes quiescence before supplying bytes.
This is an isolated contract fixture, not a production persistence adapter.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Superseded(RuntimeError):
    pass


class CheckpointLimit(ValueError):
    """A checkpoint breached a fixed spike limit; retrying cannot change that."""


class FlushMissing(ValueError):
    """The required session marker is absent: the barrier was not reached."""


class Authority:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS owner (id INTEGER PRIMARY KEY, attempt INTEGER);"
                "INSERT OR IGNORE INTO owner VALUES (1, 0);"
                "CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY, "
                "attempt INTEGER, digest TEXT, payload BLOB);"
                "CREATE TABLE IF NOT EXISTS outcome (id INTEGER PRIMARY KEY, "
                "attempt INTEGER, payload TEXT);"
                "CREATE TABLE IF NOT EXISTS effect (operation TEXT PRIMARY KEY, value INTEGER);"
                "CREATE TABLE IF NOT EXISTS entry (sequence INTEGER PRIMARY KEY, "
                "attempt INTEGER, operation TEXT, admitted INTEGER);"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def require_owner(db, attempt: int):
        if db.execute("SELECT attempt FROM owner WHERE id=1").fetchone()[0] != attempt:
            raise Superseded("attempt no longer owns publication")

    def claim(self, order: int | None = None) -> int:
        """Take ownership. With an order (Temporal turn/attempt), an older or equal
        order is refused, so a stale attempt resuming late cannot take it back."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT attempt FROM owner WHERE id=1").fetchone()[0]
            if order is None:
                attempt = current + 1
            elif order <= current:
                raise Superseded("a newer attempt already owns this task")
            else:
                attempt = order
            db.execute("UPDATE owner SET attempt=? WHERE id=1", (attempt,))
            return attempt

    def owns(self, attempt: int) -> bool:
        with self.connect() as db:
            return db.execute("SELECT attempt FROM owner WHERE id=1").fetchone()[0] == attempt

    def checkpoint(self, attempt: int, payload: bytes) -> str:
        digest = hashlib.sha256(payload).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_owner(db, attempt)
            db.execute(
                "INSERT OR REPLACE INTO checkpoint VALUES (1, ?, ?, ?)", (attempt, digest, payload)
            )
        return digest

    def acknowledge(self, attempt: int, payload: bytes, publication: dict) -> str:
        """Commit a consistent pair and its finish metadata under one fence."""
        digest = hashlib.sha256(payload).hexdigest()
        encoded = json.dumps(publication, sort_keys=True)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_owner(db, attempt)
            db.execute(
                "INSERT OR REPLACE INTO checkpoint VALUES (1, ?, ?, ?)", (attempt, digest, payload)
            )
            db.execute("INSERT OR REPLACE INTO outcome VALUES (1, ?, ?)", (attempt, encoded))
        return digest

    def publication(self) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM outcome WHERE id=1").fetchone()
        return json.loads(row[0]) if row is not None else None

    def restore(self) -> tuple[str, bytes]:
        with self.connect() as db:
            row = db.execute("SELECT digest, payload FROM checkpoint WHERE id=1").fetchone()
        if row is None or hashlib.sha256(row[1]).hexdigest() != row[0]:
            raise ValueError("missing or corrupt acknowledged checkpoint")
        return row[0], row[1]

    def publish(self, attempt: int, payload: dict):
        encoded = json.dumps(payload, sort_keys=True)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_owner(db, attempt)
            db.execute("INSERT OR REPLACE INTO outcome VALUES (1, ?, ?)", (attempt, encoded))

    def effect(self, attempt: int, operation: str) -> dict:
        # Both operation and attempt come from the host-created fixture endpoint.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            owned = db.execute("SELECT attempt FROM owner WHERE id=1").fetchone()[0] == attempt
            db.execute("INSERT INTO entry VALUES (NULL, ?, ?, ?)", (attempt, operation, int(owned)))
            if owned:
                db.execute("INSERT OR IGNORE INTO effect VALUES (?, 1)", (operation,))
        if not owned:
            raise Superseded("attempt no longer owns effects")
        return {"operation": operation, "committed": True}

    def counts(self) -> dict:
        with self.connect() as db:
            return {
                "business_effects": db.execute("SELECT COUNT(*) FROM effect").fetchone()[0],
                "admitted_entries": db.execute(
                    "SELECT COUNT(*) FROM entry WHERE admitted=1"
                ).fetchone()[0],
                "denied_entries": db.execute(
                    "SELECT COUNT(*) FROM entry WHERE admitted=0"
                ).fetchone()[0],
            }


def capture_pair(
    state: Path,
    marker: str | None,
    *,
    session_marker: str | None = None,
    workspace_policy: str = "strict",
) -> bytes:
    """Capture only an externally quiesced session/workspace, excluding home config.

    workspace_policy "production" matches harness_activity/workspace.py: links and
    the read-only .skills mount are skipped instead of failing the checkpoint.
    """
    files = {}
    total_bytes = 0
    for prefix in ("home/sessions", "workspace"):
        root = state / prefix
        if any((state / parent).is_symlink() for parent in ("home", prefix)) or not root.is_dir():
            raise ValueError("missing or symlinked checkpoint root")
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if workspace_policy == "production" and prefix == "workspace":
                if relative.parts[:1] == (".skills",) or path.is_symlink():
                    continue
                if any(parent.is_symlink() for parent in path.parents if root in parent.parents):
                    continue
            if path.is_symlink() or (not path.is_file() and not path.is_dir()):
                raise CheckpointLimit("checkpoint contains nonregular state")
            if path.is_file():
                data = path.read_bytes()
                total_bytes += len(data)
                if (
                    len(data) > 4 * 1024 * 1024
                    or total_bytes > 16 * 1024 * 1024
                    or len(files) >= 1000
                ):
                    raise CheckpointLimit("checkpoint exceeds 4 MiB/file, 16 MiB or 1000 files")
                files[path.relative_to(state).as_posix()] = data.hex()
    sessions = [bytes.fromhex(v) for k, v in files.items() if k.startswith("home/sessions/")]
    if session_marker is not None and not any(session_marker.encode() in s for s in sessions):
        raise FlushMissing("latest tool result not yet in durable session state")
    if not sessions or (
        marker is not None and not any(marker.encode() in value for value in sessions)
    ):
        raise ValueError("acknowledged conversation marker absent from durable state")
    if marker is not None and files.get("workspace/recovery-note.txt") != marker.encode().hex():
        raise ValueError("acknowledged edit absent")
    return json.dumps(files, sort_keys=True).encode()


def restore_pair(payload: bytes, state: Path):
    files = json.loads(payload)
    if not isinstance(files, dict) or len(files) > 1000:
        raise ValueError("invalid checkpoint inventory")
    decoded = []
    for name, value in files.items():
        relative = Path(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not (name.startswith("home/sessions/") or name.startswith("workspace/"))
        ):
            raise ValueError("checkpoint path outside granted roots")
        decoded.append((relative, bytes.fromhex(value)))
    # Restore only into a newly created destination, never overlay old worker disk.
    state.mkdir(exist_ok=False)
    for relative, data in decoded:
        path = state / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

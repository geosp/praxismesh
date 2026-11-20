"""Session store for DSH attempts (DSH migration plan D1).

DSH keeps its conversation in files under its home directory. A checkpoint
records them as a separate session blob (`session_ref`, `session_digest`), never
inside the workspace tarball, where tools and commands would see them;
`session_position` stays 0.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from common.blob_store import BlobCorrupt, BlobStore
from common.persistence.repositories import Checkpoint
from harness_activity import workspace as ws
from harness_activity.dsh.barrier import pack_session
from harness_activity.session_store import SessionSnapshot


class DshSession:
    """What the seam hands a runner as "the session". DSH reads and writes its own
    session files in `home`, so this holds no items."""

    session_settings: Any = None

    def __init__(self, session_id: str, home: Path) -> None:
        self.session_id, self.home = session_id, home

    async def get_items(self, limit: int | None = None) -> list[Any]:
        return []

    async def add_items(self, items: list[Any]) -> None:
        return None

    async def pop_item(self) -> Any | None:
        return None

    async def clear_session(self) -> None:
        return None


def clear(directory: Path) -> None:
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


class DshSessionStore:
    def __init__(
        self,
        task_id: str,
        home: Path,
        blobs: BlobStore,
        share: Callable[[Path], None] = lambda path: None,
    ) -> None:
        self.home, self.blobs, self.share = home, blobs, share
        self.task_id = task_id
        self._session = DshSession(task_id, home)

    @property
    def session(self) -> DshSession:
        return self._session

    async def load(self, checkpoint: Checkpoint | None) -> None:
        """Replace the home directory with the checkpoint's session files, or empty it."""
        self.home.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(clear, self.home)
        if checkpoint is None or checkpoint.session_ref is None:
            return
        data = await self.blobs.get(checkpoint.session_ref)
        if pack_digest(data) != checkpoint.session_digest:
            raise BlobCorrupt("the session blob does not match its checkpoint's digest")
        await asyncio.to_thread(ws.unpack, data, self.home)
        await asyncio.to_thread(self.share, self.home)

    async def capture(self) -> SessionSnapshot:
        data, digest = await asyncio.to_thread(pack_session, self.home)
        ref = await self.blobs.put(
            data, content_type="application/gzip", retention="checkpoint", task_id=self.task_id
        )
        return SessionSnapshot(position=0, session_ref=ref, session_digest=digest)


def pack_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

"""The checkpoint barrier for a DSH attempt (DSH migration plan D6, R5).

Runs while the gateway holds a model request. DSH's checkpoint policy has flushed
the earlier tool results to session files before sending that request, so the
newest tool-call ID in it must already be in those files. The attempt is then
frozen, so nothing writes while the session and workspace are captured and
committed through the fence, and thawed again.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from harness_activity import workspace as ws


class BarrierFailed(Exception):
    """No checkpoint was committed; a retryable infrastructure failure (D6)."""


def latest_tool_call_id(request: dict[str, Any]) -> str | None:
    ids = [
        m.get("tool_call_id")
        for m in request.get("messages", [])
        if isinstance(m, dict)
        and m.get("role") == "tool"
        and isinstance(m.get("tool_call_id"), str)
    ]
    return ids[-1] if ids else None


def session_contains(session_dir: Path, marker: str) -> bool:
    needle = marker.encode()
    return any(
        needle in path.read_bytes()
        for path in sorted(session_dir.rglob("*"))
        if path.is_file() and not path.is_symlink()
    )


def pack_session(session_dir: Path) -> tuple[bytes, str]:
    """A deterministic archive of the session files, and its digest."""
    data = ws.pack(session_dir)
    return data, "sha256:" + hashlib.sha256(data).hexdigest()


async def run_barrier(
    *,
    request: dict[str, Any],
    session_dir: Path,
    freeze: Callable[[], Awaitable[bool]],
    thaw: Callable[[], Awaitable[bool]],
    capture_and_commit: Callable[[], Awaitable[None]],
) -> None:
    """Check the flush marker, freeze, capture and commit, thaw. Any failure raises
    `BarrierFailed`; a failed thaw is raised even when the commit succeeded, because
    the attempt cannot continue frozen."""
    marker = latest_tool_call_id(request)
    if marker is not None and not session_contains(session_dir, marker):
        raise BarrierFailed("the newest tool result is not in the session files yet")
    if not await freeze():
        await thaw()
        raise BarrierFailed("the attempt could not be frozen")
    failure: BaseException | None = None
    try:
        await capture_and_commit()
    except BaseException as error:  # thaw before anything propagates
        failure = error
    thawed = await thaw()
    if failure is not None:
        raise failure
    if not thawed:
        raise BarrierFailed("the attempt could not be thawed")

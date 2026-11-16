"""Worker-side client of the DSH launcher's control socket (DSH migration plan D3).

One connection is one attempt: when it closes, for any reason, the launcher kills
the attempt's processes and removes its tree (R10). Requests carry an id, so a
long `exec` does not delay a freeze or a stop.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
from pathlib import Path
from typing import Any


class LauncherError(RuntimeError):
    """The launcher refused a request or the connection was lost."""


class LauncherClient:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader, self._writer = reader, writer
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._task = asyncio.create_task(self._read())

    @classmethod
    async def connect(cls, control: Path) -> LauncherClient:
        try:
            reader, writer = await asyncio.open_unix_connection(str(control), limit=2**22)
        except OSError as error:
            raise LauncherError(f"cannot reach the DSH launcher at {control}: {error}") from error
        return cls(reader, writer)

    async def _read(self) -> None:
        error: BaseException = LauncherError("the launcher closed the connection")
        try:
            while line := await self._reader.readline():
                reply = json.loads(line)
                future = self._pending.pop(reply.pop("id", 0), None)
                if future is not None and not future.done():
                    future.set_result(reply)
        except (OSError, ValueError) as e:
            error = LauncherError(f"launcher connection failed: {e}")
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    async def request(self, op: str, **fields: Any) -> dict[str, Any]:
        if self._task.done():
            raise LauncherError("the launcher connection is closed")
        number = next(self._ids)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[number] = future
        self._writer.write((json.dumps({"op": op, "id": number, **fields}) + "\n").encode())
        await self._writer.drain()
        reply = await future
        if "error" in reply:
            raise LauncherError(f"launcher {op}: {reply['error']}: {reply.get('detail', '')}")
        return reply

    async def close(self) -> None:
        self._writer.close()
        with contextlib.suppress(OSError, asyncio.CancelledError):
            await self._writer.wait_closed()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

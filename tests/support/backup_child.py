"""A backup whose `temporal` dump hangs, so a test can send this process a
signal during the dumps (Phase 3A persistence plan D8; impl-review F199). The
Compose calls are recorded to CALLS, one per line, and never run. Run as a
child process by tests/integration/test_backup.py:

    python -m tests.support.backup_child BUCKET TARGET CALLS

Exits 2 with the error on stderr when the backup fails, as the CLI does.
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import IO

from common.blob_store.s3 import S3BlobStore
from common.errors import PraxisError
from common.persistence.repositories import make_engine
from orchestrator.backup import backup


class HangingCompose:
    def __init__(self, calls: Path) -> None:
        self.calls = calls

    def record(self, line: str) -> None:
        with self.calls.open("a") as f:
            f.write(line + "\n")

    def run(self, args: Sequence[str], *, stdout: IO[bytes] | None = None) -> str:
        if args[0] == "config":
            return "paradedb/paradedb:test\n"
        if args[0] == "ps":
            return "worker-a\n" if "running" in args else ""
        if args[0] in ("stop", "start"):
            self.record(" ".join(args))
            return ""
        if args[0] == "exec":
            self.record(f"dump {args[-1]}")
            if args[-1] == "temporal":
                time.sleep(60)  # the signal arrives here
            if stdout is not None:
                stdout.write(b"PGDMP")
            return ""
        raise AssertionError(f"unexpected compose {args}")


async def main(bucket: str, target: str, calls: str) -> None:
    store = S3BlobStore.from_env()
    store.bucket = bucket
    engine = make_engine()
    try:
        await backup(engine, store, HangingCompose(Path(calls)), to=Path(target))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main(*sys.argv[1:4]))
    except PraxisError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    sys.exit("the backup finished: the signal never came")

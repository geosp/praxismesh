"""A `request delete` that SIGKILLs its own process after its `at`-th committed
batch, before that batch's bucket step (Phase 3A persistence plan R13, R15;
impl-review F164). Run as a child process by tests/integration/test_removal_kills.py:

    python -m tests.support.removal_child DATABASE BUCKET REQUEST AT
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import create_async_engine

from common.blob_store.s3 import S3BlobStore
from common.persistence.removal import RemovalEngine
from common.persistence.settings import app_database_url
from orchestrator.lifecycle import delete_request
from tests.support.lifecycle import FakeTemporal


async def main(database: str, bucket: str, request: str, at: int) -> None:
    real_finish = RemovalEngine.finish
    committed = 0

    async def finish(self: RemovalEngine, keys: Iterable[str]) -> int:
        nonlocal committed
        # A committed batch's bucket step gets its marked keys as a tuple.
        if isinstance(keys, tuple) and keys:
            committed += 1
            if committed == at:
                os.kill(os.getpid(), signal.SIGKILL)  # no cleanup, no unlock
        return await real_finish(self, keys)

    RemovalEngine.finish = finish  # type: ignore[method-assign]
    store = S3BlobStore.from_env()
    store.bucket = bucket
    engine = create_async_engine(app_database_url(database=database))
    await delete_request(engine, store, FakeTemporal(), request)
    sys.exit("the delete finished: the kill never happened")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])))

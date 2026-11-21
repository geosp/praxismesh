"""`agentctl backup` against the stack (Phase 3A persistence plan phase 03 task
2.1; R16, D4, D8; notes.md#d8): three dumps, every object of the bucket and a
manifest; the workers stopped during the dumps and started again, even when a
dump fails; a removal started during the backup fails on D4's lock.

The dumps and the bucket copy are real (`docker compose exec db pg_dump`, the
stack's SeaweedFS, a bucket of the test's own). The worker services are
simulated: the recording Compose reports `worker-a` running and records `stop`
and `start` instead of running them, so the test never stops a developer's
workers. The drill (`make drill`) stops and starts real ones.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import IO

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store.s3 import S3BlobStore
from common.persistence.removal import RemovalBusy, run_lock
from common.persistence.repositories import RecordingBlobStore, make_engine
from orchestrator.backup import MANIFEST, BackupFailed, DockerCompose, backup
from orchestrator.lifecycle import gc
from tests.support.lifecycle import FakeTemporal, end_task, record_task
from tests.support.stack import scratch_bucket

pytestmark = pytest.mark.integration


class RecordingCompose:
    """The real Compose, except that `worker-a` is reported running and its
    `stop` and `start` are recorded, not run. `fail` makes that dump fail."""

    def __init__(self, fail: str | None = None) -> None:
        self.real = DockerCompose.from_env()
        self.calls: list[str] = []
        self.fail = fail

    def run(self, args: Sequence[str], *, stdout: IO[bytes] | None = None) -> str:
        if args[0] == "ps":
            return "db\ntemporal\nworker-a\n"
        if args[0] in ("stop", "start"):
            self.calls.append(" ".join(args))
            return ""
        if args[0] == "exec":
            self.calls.append(f"dump {args[-1]}")
            if args[-1] == self.fail:
                raise BackupFailed(f"dump of {self.fail} failed (test)")
        return self.real.run(args, stdout=stdout)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = make_engine()
    yield eng
    await eng.dispose()


@pytest.fixture
async def bucket() -> AsyncIterator[S3BlobStore]:
    async with scratch_bucket("backup") as s3:
        yield s3


async def test_a_backup_has_three_dumps_every_object_and_a_manifest(
    engine: AsyncEngine, bucket: S3BlobStore, tmp_path: Path
) -> None:
    store = RecordingBlobStore(bucket, engine)
    stored = await record_task(engine, store, inputs={"orders.csv": b"sku,qty\nSKU-1,3\n"})
    await end_task(engine, store, stored, artifacts={"order-summary.md": b"# 3 units\n"})
    compose = RecordingCompose()
    refused: list[str] = []

    async def removal_during_backup() -> None:
        try:
            await gc(engine, bucket, FakeTemporal(), dry_run=True)
        except RemovalBusy as e:
            refused.append(str(e))

    target = await backup(
        engine, bucket, compose, to=tmp_path / "b", after_dumps=removal_during_backup
    )

    assert compose.calls == [
        "stop worker-a",
        "dump praxismesh",
        "dump temporal",
        "dump temporal_visibility",
        "start worker-a",
    ]
    assert refused and "another gc" in refused[0]
    for db in ("praxismesh", "temporal", "temporal_visibility"):
        assert (target / f"{db}.dump").read_bytes()[:5] == b"PGDMP"  # pg_dump -Fc
    manifest = json.loads((target / MANIFEST).read_text())
    keys = {stored.instructions.key, *(r.key for r in stored.inputs.values())}
    keys |= {r.key for r in stored.artifacts.values()}
    assert {o["key"] for o in manifest["objects"]} == keys
    for obj in manifest["objects"]:
        assert (target / "blobs" / obj["key"]).read_bytes() == bucket.client.get_object(
            Bucket=bucket.bucket, Key=obj["key"]
        )["Body"].read()
        assert obj["metadata"].get("retention") in {"transcript", "artifact"}
    assert manifest["migration"] and manifest["rows"]["tasks"] >= 1
    assert manifest["workers_stopped"] == ["worker-a"]
    assert any(i.startswith("paradedb/paradedb:") for i in manifest["images"])


async def test_the_workers_start_again_when_a_dump_fails(
    engine: AsyncEngine, bucket: S3BlobStore, tmp_path: Path
) -> None:
    compose = RecordingCompose(fail="temporal")
    with pytest.raises(BackupFailed):
        await backup(engine, bucket, compose, to=tmp_path / "b")
    assert compose.calls[0] == "stop worker-a" and compose.calls[-1] == "start worker-a"
    assert not (tmp_path / "b" / MANIFEST).exists()  # incomplete: restore refuses it
    async with run_lock(engine):
        pass  # released: a removal can run now

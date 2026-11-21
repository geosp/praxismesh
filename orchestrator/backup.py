"""`agentctl backup` and the Python half of `make restore` (Phase 3A persistence
plan R16, R23, D4, D8; notes.md#d8).

Backup holds D4's run lock for its whole run, so no gc, request delete or events
prune changes rows or the bucket between the dumps and the bucket copy. It stops
the worker services while it dumps `praxismesh`, `temporal` and
`temporal_visibility` (`pg_dump -Fc` in the `db` container), so no Workflow gets
ahead of its rows, and starts them again even if a dump fails. It then copies
every bucket object, and writes `manifest.json` last: a directory without one
is an incomplete backup, which restore refuses.

    backups/<UTC time>/
        manifest.json
        praxismesh.dump  temporal.dump  temporal_visibility.dump
        blobs/<key>                     every bucket object, as stored

`python -m orchestrator.backup check-backup DIR | check-empty | load-blobs DIR`
are the steps `infra/restore.sh` runs: refuse a backup this checkout cannot
restore whole, refuse a stack that holds data (R23), and load a backup's
objects with their content type and metadata.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO, Any, Protocol

from alembic.config import Config
from alembic.script import ScriptDirectory
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store.base import BlobError
from common.blob_store.s3 import S3BlobStore
from common.errors import PraxisError
from common.persistence.removal import run_lock
from common.persistence.repositories import make_engine
from common.persistence.retention import APP_TABLES

ROOT = Path(__file__).resolve().parents[1]
DATABASES = ("praxismesh", "temporal", "temporal_visibility")
# Services that write rows, blobs or Workflow state (infra/docker-compose.yml).
WORKERS = ("orchestrator", "worker-a", "worker-b", "worker-dsh-a", "worker-dsh-b")
MANIFEST = "manifest.json"
FORMAT = 1


class BackupFailed(PraxisError):
    pass


class RestoreRefused(PraxisError):
    pass


class Compose(Protocol):
    """`docker compose` for this checkout's project."""

    def run(self, args: Sequence[str], *, stdout: IO[bytes] | None = None) -> str: ...


@dataclass(frozen=True)
class DockerCompose:
    project: str
    env_file: str

    @classmethod
    def from_env(cls) -> DockerCompose:
        """The project named in the env file (ENV_FILE, default infra/.env), read
        as the Makefile reads it: a COMPOSE_PROJECT_NAME in the shell never
        counts, so a backup cannot act on another checkout's stack."""
        env_file = str(Path(os.environ.get("ENV_FILE") or ROOT / "infra" / ".env").resolve())
        found = subprocess.run(
            ["sh", str(ROOT / "infra" / "check-prereqs.sh"), "--project-only", env_file],
            capture_output=True,
            text=True,
        )
        project = found.stdout.strip()
        if found.returncode != 0 or not project:
            raise BackupFailed(f"no Compose project name in {env_file}: {found.stderr.strip()}")
        return cls(project, env_file)

    def run(self, args: Sequence[str], *, stdout: IO[bytes] | None = None) -> str:
        command = [
            "docker",
            "compose",
            "-p",
            self.project,
            "--env-file",
            self.env_file,
            "-f",
            str(ROOT / "infra" / "docker-compose.yml"),
            *args,
        ]
        out = stdout if stdout is not None else subprocess.PIPE
        done = subprocess.run(command, stdout=out, stderr=subprocess.PIPE)
        if done.returncode != 0:
            tail = done.stderr.decode(errors="replace").strip().splitlines()[-5:]
            raise BackupFailed(f"'docker compose {' '.join(args)}' failed: {' | '.join(tail)}")
        return "" if stdout is not None else done.stdout.decode()


def running_workers(compose: Compose) -> list[str]:
    up = set(compose.run(["ps", "--services", "--status", "running"]).split())
    return [w for w in WORKERS if w in up]


def _safe_path(root: Path, key: str) -> Path:
    """`root/<key>`, refusing keys that would leave `root`."""
    parts = PurePosixPath(key).parts
    if not parts or key.startswith("/") or any(p in ("..", ".") for p in parts):
        raise BackupFailed(f"bucket key {key!r} cannot be stored as a file")
    return root.joinpath(*parts)


def _copy_bucket(store: S3BlobStore, keys: Sequence[str], to: Path) -> list[dict[str, Any]]:
    """Every listed object, with what `load_blobs` needs to put it back as it was."""
    objects: list[dict[str, Any]] = []
    for key in keys:
        try:
            obj = store.client.get_object(Bucket=store.bucket, Key=key)
            body = obj["Body"].read()
        except (ClientError, BotoCoreError) as e:
            raise BackupFailed(f"cannot copy {key} from bucket {store.bucket}: {e}") from e
        path = _safe_path(to, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        objects.append(
            {
                "key": key,
                "bytes": len(body),
                "content_type": obj.get("ContentType", "application/octet-stream"),
                "metadata": obj.get("Metadata", {}),
            }
        )
    return objects


async def _list_bucket(store: S3BlobStore) -> list[str]:
    """The bucket's keys. Only a bucket not created yet (it is created on first
    use) is empty; a refused or failing listing fails the backup (F165)."""
    try:
        return sorted(await store.list_objects())
    except BlobError as e:
        raise BackupFailed(f"cannot list bucket {store.bucket}: {e}") from e


def _write_atomic(path: Path, content: str) -> None:
    """Write `path` whole or not at all: through a temporary file and a rename."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content)
    try:
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


async def _rows(engine: AsyncEngine) -> tuple[dict[str, int], str | None]:
    async with engine.connect() as conn:
        counts = {
            t: int(await conn.scalar(text(f"SELECT count(*) FROM {t}")) or 0) for t in APP_TABLES
        }
        head = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        return counts, head


async def backup(
    engine: AsyncEngine,
    store: S3BlobStore,
    compose: Compose,
    *,
    to: Path | None = None,
    after_dumps: Callable[[], Awaitable[None]] | None = None,
) -> Path:
    """Back the stack up into `to` (default `backups/<UTC time>/`); returns it."""
    started = datetime.now(UTC)
    target = to or ROOT / "backups" / started.strftime("%Y%m%dT%H%M%SZ")
    async with run_lock(engine):
        # Made under the lock, so a refused backup leaves nothing behind; only
        # operators may read it: it holds prompts and outputs in clear text.
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.mkdir(mode=0o700)
        except FileExistsError:
            raise BackupFailed(f"{target} already exists: back up into a new directory") from None
        # Before anything stops: a failure here changes nothing.
        images = compose.run(["config", "--images"]).split()
        stopped = running_workers(compose)
        try:
            if stopped:
                # Inside the `try`: a stop that fails partway may have stopped some.
                compose.run(["stop", *stopped])
            rows, head = await _rows(engine)
            dumps: dict[str, int] = {}
            # The application database first: no restored row names a blob newer
            # than the bucket copy (notes.md#d8).
            for db in DATABASES:
                path = target / f"{db}.dump"
                with path.open("wb") as out:
                    compose.run(
                        ["exec", "-T", "-u", "postgres", "db", "pg_dump", "-Fc", "-d", db],
                        stdout=out,
                    )
                dumps[db] = path.stat().st_size
        finally:
            if stopped:
                compose.run(["start", *stopped])
        if after_dumps is not None:
            await after_dumps()
        keys = await _list_bucket(store)
        objects = await asyncio.to_thread(_copy_bucket, store, keys, target / "blobs")
    manifest = {
        "format": FORMAT,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "migration": head,
        "databases": {db: {"file": f"{db}.dump", "bytes": n} for db, n in dumps.items()},
        "rows": rows,
        "bucket": store.bucket,
        "objects": objects,
        "workers_stopped": stopped,
        "images": sorted(set(images)),
    }
    _write_atomic(target / MANIFEST, json.dumps(manifest, indent=2) + "\n")
    return target


# ---- restore's steps (infra/restore.sh) ----


def checkout_head() -> str | None:
    """This checkout's Alembic head: the schema its code expects."""
    config = Config(str(ROOT / "common" / "persistence" / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


def check_backup(backup_dir: Path) -> None:
    """Refuse a backup this checkout cannot restore whole (impl-review F179),
    before restore changes anything: its manifest is missing or not valid,
    it has another format or migration head, or a dump or object is missing
    or not the size the manifest gives."""
    path = backup_dir / MANIFEST
    if not path.is_file():
        raise RestoreRefused(f"{backup_dir} has no {MANIFEST}: not a complete backup")
    try:
        manifest = json.loads(path.read_text())
    except (ValueError, UnicodeDecodeError) as e:
        raise RestoreRefused(f"{path} is not valid JSON: {e}") from e
    if manifest.get("format") != FORMAT:
        raise RestoreRefused(
            f"the backup has format {manifest.get('format')}; this checkout reads format {FORMAT}"
        )
    head = checkout_head()
    if manifest.get("migration") != head:
        raise RestoreRefused(
            f"the backup is at migration {manifest.get('migration')}; this checkout's "
            f"migrations are at {head}: restore with a checkout whose head is "
            f"{manifest.get('migration')}, then migrate"
        )
    files = [
        (f"{db}.dump", backup_dir / manifest["databases"][db]["file"], manifest["databases"][db])
        for db in DATABASES
    ] + [(o["key"], _safe_path(backup_dir / "blobs", o["key"]), o) for o in manifest["objects"]]
    for name, file, entry in files:
        if not file.is_file():
            raise RestoreRefused(f"{name} is missing from {backup_dir}")
        if (size := file.stat().st_size) != entry["bytes"]:
            raise RestoreRefused(f"{name} is {size} bytes; the manifest says {entry['bytes']}")


async def check_empty(engine: AsyncEngine, store: S3BlobStore, workflows: int) -> None:
    """Refuse a stack whose application database, Temporal namespace or bucket
    holds data (R23): a row in any application table, not only `tasks` (F171).
    `workflows` is how many Workflows Temporal lists in the app's namespace,
    which the caller asks through Temporal's API."""
    problems: list[str] = []
    try:
        async with engine.connect() as conn:
            held = []
            for table in APP_TABLES:
                exists = text(f"SELECT to_regclass('public.{table}') IS NOT NULL")
                if not await conn.scalar(exists):
                    continue  # a database restore has not migrated yet
                if n := int(await conn.scalar(text(f"SELECT count(*) FROM {table}")) or 0):
                    held.append(f"{table} {n}")
            if held:
                problems.append(f"the application database has rows: {', '.join(held)}")
    except DBAPIError as e:
        raise RestoreRefused(f"cannot read the application database: {e.orig}") from e
    if workflows:
        problems.append(f"Temporal lists {workflows} Workflow(s) in the app's namespace")
    if await store.list_objects():
        problems.append(f"bucket {store.bucket} holds objects")
    if problems:
        raise RestoreRefused(
            "refusing to restore into a stack that holds data: "
            + "; ".join(problems)
            + ". Run 'make reset' and 'make up' first (this deletes the stack's data)"
        )


async def workflow_count() -> int:
    """Workflows Temporal lists in the app's namespace (TEMPORAL_NAMESPACE), open
    or closed, through its API: no SQL on Temporal's databases (ADR-0002)."""
    from orchestrator.cli import connect  # the CLI's client settings

    client = await connect()
    return (await client.count_workflows()).count


async def load_blobs(store: S3BlobStore, backup_dir: Path) -> int:
    manifest = json.loads((backup_dir / MANIFEST).read_text())
    await store.ensure_bucket()

    def load() -> int:
        for obj in manifest["objects"]:
            body = _safe_path(backup_dir / "blobs", obj["key"]).read_bytes()
            store.client.put_object(
                Bucket=store.bucket,
                Key=obj["key"],
                Body=body,
                ContentType=obj["content_type"],
                Metadata=obj["metadata"],
            )
        return len(manifest["objects"])

    return await asyncio.to_thread(load)


async def _main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="python -m orchestrator.backup")
    steps = p.add_subparsers(dest="step", required=True)
    check = steps.add_parser("check-backup", help="refuse a backup this checkout cannot restore")
    check.add_argument("backup_dir", type=Path)
    steps.add_parser("check-empty", help="refuse a stack that holds data (R23)")
    load = steps.add_parser("load-blobs", help="load a backup's objects into the bucket")
    load.add_argument("backup_dir", type=Path)
    args = p.parse_args(argv)
    if args.step == "check-backup":
        check_backup(args.backup_dir)
        print(f"{args.backup_dir} is a complete backup this checkout can restore")
        return 0
    engine = make_engine()
    try:
        store = S3BlobStore.from_env()
        if args.step == "check-empty":
            await check_empty(engine, store, await workflow_count())
            print("the stack holds no data")
        else:
            print(f"loaded {await load_blobs(store, args.backup_dir)} object(s)")
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main(sys.argv[1:])))
    except PraxisError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)

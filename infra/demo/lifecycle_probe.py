"""Probes for the Phase 3A lifecycle demo (infra/demo/phase-3a-lifecycle.sh):

    PYTHONPATH=. uv run --env-file infra/.env python infra/demo/lifecycle_probe.py age TASK DAYS
    PYTHONPATH=. uv run --env-file infra/.env python infra/demo/lifecycle_probe.py tombstones OP
    PYTHONPATH=. uv run --env-file infra/.env python infra/demo/lifecycle_probe.py live KEY

`age` sets the task's `ended_at` DAYS days back, so the demo can show an expiry
without waiting for it: the one change the demo makes outside `agentctl`.
`tombstones` prints the `audit_log` rows of one operation, in order. `live`
prints a blob's `blob_objects` row and whether the bucket holds it, and exits
1 unless the row is not marked removed and the object is there.
"""

from __future__ import annotations

import asyncio
import json
import sys

from sqlalchemy import text

from common.blob_store.s3 import S3BlobStore
from common.persistence.repositories import make_engine


async def age(task_id: str, days: float) -> None:
    engine = make_engine()
    try:
        async with engine.begin() as conn:
            done = await conn.execute(
                text(
                    "UPDATE tasks SET ended_at = now() - make_interval(secs => :s) "
                    "WHERE task_id = :t AND ended_at IS NOT NULL RETURNING ended_at"
                ),
                {"s": days * 86400, "t": task_id},
            )
            ended = done.scalar_one()
        print(f"{task_id}: ended_at set to {ended:%Y-%m-%d %H:%M} UTC ({days:g} days ago)")
    finally:
        await engine.dispose()


async def tombstones(operation: str) -> None:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT created_at, actor, action, subject, details FROM audit_log "
                    "WHERE operation_id = :o ORDER BY id"
                ),
                {"o": operation},
            )
            for at, actor, action, subject, details in rows:
                body = details if isinstance(details, dict) else json.loads(details)
                print(f"{at:%H:%M:%S} {actor} {action} {subject} {json.dumps(body)}")
    finally:
        await engine.dispose()


async def live(key: str) -> bool:
    engine = make_engine()
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT removed_at, removed_by, bucket_deleted_at FROM blob_objects "
                        "WHERE key = :k"
                    ),
                    {"k": key},
                )
            ).one_or_none()
    finally:
        await engine.dispose()
    store = S3BlobStore.from_env()
    in_bucket = key in await store.list_objects()
    if row is None:
        print(f"{key}: no blob_objects row; in the bucket: {in_bucket}")
        return False
    removed_at, removed_by, bucket_deleted_at = row
    print(
        f"{key}: removed_at {removed_at}, removed_by {removed_by}, "
        f"bucket_deleted_at {bucket_deleted_at}; in the bucket: {in_bucket}"
    )
    return removed_at is None and in_bucket


if __name__ == "__main__":
    what, *args = sys.argv[1:]
    if what == "age":
        asyncio.run(age(args[0], float(args[1])))
    elif what == "live":
        sys.exit(0 if asyncio.run(live(args[0])) else 1)
    else:
        asyncio.run(tombstones(args[0]))

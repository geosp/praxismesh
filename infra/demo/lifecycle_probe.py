"""Probes for the Phase 3A lifecycle demo (infra/demo/phase-3a-lifecycle.sh):

    PYTHONPATH=. uv run --env-file infra/.env python infra/demo/lifecycle_probe.py age TASK DAYS
    PYTHONPATH=. uv run --env-file infra/.env python infra/demo/lifecycle_probe.py tombstones OP

`age` sets the task's `ended_at` DAYS days back, so the demo can show an expiry
without waiting for it: the one change the demo makes outside `agentctl`.
`tombstones` prints the `audit_log` rows of one operation, in order.
"""

from __future__ import annotations

import asyncio
import json
import sys

from sqlalchemy import text

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


if __name__ == "__main__":
    what, *args = sys.argv[1:]
    if what == "age":
        asyncio.run(age(args[0], float(args[1])))
    else:
        asyncio.run(tombstones(args[0]))

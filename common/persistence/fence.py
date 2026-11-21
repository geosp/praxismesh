"""ADR-0007's fence, shared by every write an attempt makes (Phase 2 events plan D2).

A write by an attempt is valid only while no newer turn or attempt of the same
task has started. `AttemptRepository.start` and every fenced write take the
per-task transaction lock first, so under READ COMMITTED the check sees any start
that committed before it (DSH migration plan D10, review F1). A fenced write never
takes the task lock while holding another row lock, so lock order cannot invert.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


class FenceRejected(RuntimeError):
    """A newer (turn, attempt) exists for the task, so the fenced write was not made."""


# Bind `:t` (task ID).
TASK_LOCK = text("SELECT pg_advisory_xact_lock(hashtext(:t))")
# The same lock without waiting; returns whether it was taken.
TRY_TASK_LOCK = text("SELECT pg_try_advisory_xact_lock(hashtext(:t))")

# The per-request lock (Phase 2 messaging plan; bind `:r`, the request ID): taken
# by messaging, `end_task` and a task's `record_task`. `request delete` holds the
# session form, `pg_advisory_lock(2, hashtext(:r))`, for its whole run, and the
# two forms conflict (Phase 3A persistence plan D12).
REQUEST_LOCK_KEY = 2
REQUEST_LOCK_ARGS = f"{REQUEST_LOCK_KEY}, hashtext(:r)"  # also the session form's
REQUEST_LOCK = text(f"SELECT pg_advisory_xact_lock({REQUEST_LOCK_ARGS})")

# A SQL condition; bind `:t`, `:turn` and `:a` (the writer's task, turn and attempt).
# A `deleted` row (the fencing row of `request delete`) refuses every later write
# of the task, whatever its turn (Phase 3A persistence plan R25, review F118).
NO_NEWER_ATTEMPT = (
    "NOT EXISTS (SELECT 1 FROM task_attempts n WHERE n.task_id = :t "
    "AND (n.turn > :turn OR (n.turn = :turn AND n.attempt > :a) OR n.outcome = 'deleted'))"
)


# A SQL condition; bind `:t`: the task's request was deleted (its fencing row).
DELETED = "EXISTS (SELECT 1 FROM task_attempts d WHERE d.task_id = :t AND d.outcome = 'deleted')"


async def refuse_if_deleted(conn: AsyncConnection, task_id: str) -> None:
    """For a write that has no attempt identity (an SDK session item, a tool's
    row): take the task lock, then refuse if the task was deleted (Phase 3A
    persistence plan R25, review F117). The write must follow in `conn`'s
    transaction, so a delete either commits first or waits for it."""
    await conn.execute(TASK_LOCK, {"t": task_id})
    if (await conn.execute(text(f"SELECT 1 WHERE {DELETED}"), {"t": task_id})).first():
        raise FenceRejected(f"task {task_id} was deleted")

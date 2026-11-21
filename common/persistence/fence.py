"""ADR-0007's fence, shared by every write an attempt makes (Phase 2 events plan D2).

A write by an attempt is valid only while no newer turn or attempt of the same
task has started. `AttemptRepository.start` and every fenced write take the
per-task transaction lock first, so under READ COMMITTED the check sees any start
that committed before it (DSH migration plan D10, review F1). A fenced write never
takes the task lock while holding another row lock, so lock order cannot invert.
"""

from __future__ import annotations

from sqlalchemy import text


class FenceRejected(RuntimeError):
    """A newer (turn, attempt) exists for the task, so the fenced write was not made."""


# Bind `:t` (task ID).
TASK_LOCK = text("SELECT pg_advisory_xact_lock(hashtext(:t))")

# The per-request lock (Phase 2 messaging plan; bind `:r`, the request ID): taken
# by messaging, `end_task` and a task's `record_task`. `request delete` holds the
# session form, `pg_advisory_lock(2, hashtext(:r))`, for its whole run, and the
# two forms conflict (Phase 3A persistence plan D12).
REQUEST_LOCK_KEY = 2
REQUEST_LOCK = text("SELECT pg_advisory_xact_lock(2, hashtext(:r))")

# A SQL condition; bind `:t`, `:turn` and `:a` (the writer's task, turn and attempt).
NO_NEWER_ATTEMPT = (
    "NOT EXISTS (SELECT 1 FROM task_attempts n WHERE n.task_id = :t "
    "AND (n.turn > :turn OR (n.turn = :turn AND n.attempt > :a)))"
)

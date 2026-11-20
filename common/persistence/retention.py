"""Retention classes and lifetimes (plan §4.13; Phase 3A persistence plan D3,
notes.md#d3). Every blob and stored row carries a class from its first write.

Lifetimes count from the task's `ended_at`, except `ephemeral`, which counts
from the write; `audit` is kept. A row of a task that never ended never expires.
GC computes expiry when it runs; nothing stores an expiry time.
"""

from __future__ import annotations

from datetime import timedelta
from typing import get_args

from common.schemas import RetentionClass

RETENTION_CLASSES: tuple[str, ...] = get_args(RetentionClass)

DEFAULT_LIFETIME: dict[RetentionClass, timedelta | None] = {
    "ephemeral": timedelta(days=1),
    "checkpoint": timedelta(days=7),
    "transcript": timedelta(days=30),
    "artifact": timedelta(days=90),
    "audit": None,  # kept; Phase 3A has no purge
    "task": timedelta(days=30),  # the Phase 1-2 class, read as transcript
}

# How long a blob with no live holder is kept after its last upload (D5).
SAFETY_WINDOW = timedelta(hours=24)

# Each application table's class (notes.md#d3, the one source; a unit test
# compares the two). None: the row takes its blob's or reference's class.
TABLE_CLASS: dict[str, RetentionClass | None] = {
    "tasks": "audit",
    "task_attempts": "audit",
    "usage_ledger": "audit",
    "audit_log": "audit",
    "checkpoints": "checkpoint",
    "agent_sessions": "transcript",
    "agent_messages": "transcript",
    "event_logs": "transcript",
    "agent_events": "transcript",
    "task_messages": "transcript",
    "task_inbox": "transcript",
    "idempotency_keys": "transcript",
    "sample_orders": "artifact",
    "message_wakes": "ephemeral",
    "event_batches": "ephemeral",
    "blob_objects": None,
    "blob_refs": None,
}

# Application tables, all with `retention_class NOT NULL` (migrations 0003-0007).
APP_TABLES = tuple(TABLE_CLASS)

# The class of a blob by where it is named (notes.md#d3's blob table): holder
# table and column. Uploads take the class `put` was given.
REFERENCE_CLASS: dict[tuple[str, str], RetentionClass] = {
    ("tasks", "instructions_ref"): "transcript",
    ("tasks", "input_refs"): "transcript",
    ("tasks", "result"): "artifact",
    ("checkpoints", "workspace_ref"): "checkpoint",
    ("checkpoints", "session_ref"): "checkpoint",
    ("agent_events", "blob_ref"): "transcript",
}

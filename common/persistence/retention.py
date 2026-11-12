"""Retention classes (plan §4.13). Every blob and stored row carries one from its
first write. Phase 1 records them only; deletion and garbage collection arrive in
Phase 3A, which enforces these default lifetimes."""

from __future__ import annotations

from datetime import timedelta
from typing import get_args

from common.schemas import RetentionClass

RETENTION_CLASSES: tuple[str, ...] = get_args(RetentionClass)

DEFAULT_LIFETIME: dict[str, timedelta | None] = {
    "ephemeral": timedelta(days=1),
    "task": timedelta(days=30),
    "audit": None,  # kept until an operator policy says otherwise
}

# Phase 1 tables, all with `retention_class NOT NULL` (migration 0003).
PHASE1_TABLES = (
    "tasks",
    "task_attempts",
    "checkpoints",
    "idempotency_keys",
    "blob_objects",
    "sample_orders",
    "agent_sessions",
    "agent_messages",
)

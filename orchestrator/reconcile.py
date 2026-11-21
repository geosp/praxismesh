"""`agentctl reconcile [--reindex]`: compare the rows, the reference index and the
bucket, and list what is inconsistent (Phase 3A persistence plan R17, D4).

It lists dangling references (live, but the blob is marked removed or missing
from the bucket), orphaned bucket objects with their age, unindexed references,
and tasks that never ended although Temporal reports their Workflow closed (or
no longer knows it). Without `--reindex` it changes nothing. With it, it first
indexes the unindexed references (`refs.reindex`, as migration 0007 does) under
D4's run lock, then reports what is left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from common.blob_store.base import Bucket
from common.persistence import refs
from common.persistence.refs import Orphan, Reference, Reindexed
from common.persistence.removal import run_lock
from orchestrator.workflow_status import StatusOf, WorkflowStatus


@dataclass
class Report:
    dangling: list[Reference] = field(default_factory=list)
    orphaned: list[Orphan] = field(default_factory=list)
    unindexed: list[Reference] = field(default_factory=list)
    # Tasks with no `ended_at` whose Workflow is closed or missing, by task ID.
    never_ended: dict[str, WorkflowStatus] = field(default_factory=dict)
    reindexed: Reindexed | None = None
    now: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def clean(self) -> bool:
        return not (self.dangling or self.orphaned or self.unindexed or self.never_ended)

    def as_json(self) -> dict[str, object]:
        def ref(r: Reference) -> dict[str, object]:
            return {
                "blob_key": r.blob_key,
                "holder": f"{r.holder_table}/{r.holder_key}/{r.holder_column}".rstrip("/"),
                "task_id": r.task_id,
                "request_id": r.request_id,
            }

        return {
            "clean": self.clean,
            "dangling": [ref(r) for r in self.dangling],
            "orphaned": [
                {
                    "key": o.key,
                    "last_put_at": o.last_put_at.isoformat(),
                    "age_hours": round((self.now - o.last_put_at).total_seconds() / 3600, 1),
                    # Not `sha256/<hex>`: never recorded, so gc never removes it.
                    "content_key": refs.is_content_key(o.key),
                }
                for o in self.orphaned
            ],
            "unindexed": [ref(r) for r in self.unindexed],
            "never_ended": [
                {"task_id": t, "workflow": status} for t, status in self.never_ended.items()
            ],
            "reindexed": (
                None
                if self.reindexed is None
                else {"references": self.reindexed.references, "blobs": self.reindexed.blobs}
            ),
        }


async def reconcile(
    engine: AsyncEngine,
    bucket: Bucket,
    status_of: StatusOf,
    *,
    reindex: bool = False,
    now: datetime | None = None,
) -> Report:
    report = Report(now=now or datetime.now(UTC))
    if reindex:
        async with run_lock(engine), engine.begin() as conn:
            report.reindexed = await refs.reindex(conn, await bucket.list_objects())
    async with engine.connect() as conn:
        # One snapshot, taken before the listing: every reference it holds had
        # its bytes uploaded before it committed, so it is in the listing unless
        # it is missing, or a gc or request delete committed and removed it
        # after the snapshot (no lock is taken: rerun once the removal is done).
        # An upload after the snapshot can only show as a young orphan.
        conn = await conn.execution_options(isolation_level="REPEATABLE READ")
        await conn.execute(text("SELECT 1"))
        listing = await bucket.list_objects()
        report.dangling = await refs.dangling(conn, listing)
        report.orphaned = await refs.orphaned(conn, listing)
        report.unindexed = await refs.unindexed(conn)
        unended = await conn.execute(
            text("SELECT task_id FROM tasks WHERE ended_at IS NULL ORDER BY task_id")
        )
        candidates = list(unended.scalars())
    for task_id in candidates:
        status = await status_of(task_id)
        if status != "running" and not await _ended(engine, task_id):
            report.never_ended[task_id] = status
    return report


async def _ended(engine: AsyncEngine, task_id: str) -> bool:
    """Whether the task has ended by now: the unended list comes from the
    snapshot, and a task can end and its Workflow close before Temporal is
    asked (impl-review F201)."""
    async with engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT ended_at IS NOT NULL FROM tasks WHERE task_id = :t"), {"t": task_id}
        )
    return bool(found)

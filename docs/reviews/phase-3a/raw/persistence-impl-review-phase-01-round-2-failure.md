Phase 01 impl-review (failure lens), round 2. Diff 8cc4355..dccc8ff, frozen commit dccc8ff.

I found no Blockers and no Majors. I traced every long-running unit in the diff. The round-1 Majors (F80, F81, F82) hold up when a run stops partway, is retried or overlaps another, as far as this phase's code can show. Phase 02's removal engine doesn't exist yet, so the concurrent-removal paths can only be checked then.

## How each unit behaves when it stops and runs again

**`RecordingBlobStore.put`** (common/persistence/repositories.py:658-732). It collects the bytes, then in one transaction: `TASK_LOCK` (a transaction-scoped advisory lock, common/persistence/fence.py:20), `delete_mark`, the `blob_objects` upsert, the upload reference through `index_keys`, commit. Only then does it call `inner.put`.
- **Before the transaction commits:** nothing persists.
- **After the commit, before or during `inner.put`:** a live reference and a `blob_objects` row name a missing object. This is F86, already accepted. A retried Activity or submit puts the same bytes again and heals it.
- **Lock order:** task lock, then the `blob_objects` row, then `blob_refs`. Nothing else in the diff takes the `blob_objects` row lock:
  - `end_task` takes the request lock, then `tasks` and `blob_refs`.
  - `insert_fenced` and `publish` take `TASK_LOCK`, then their own row and `blob_refs`.
  So I found no lock-order inversion.
- **No self-deadlock:** no caller holds a `TASK_LOCK` transaction while calling `put`. The callers are activity.py:536 and 693, dsh/session.py:85, and submit.py:37 and 48. Each `put` runs between fenced writes, never inside one.
- **Overlapping puts of the same key:** the upsert's row lock serialises them. For the same task they are also serialised by `TASK_LOCK`.

**`TaskRepository.record_task`** (repositories.py:60-115). The index rows commit with the row and are written only when the row is inserted. A retry after the commit finds the row and returns. Two overlapping attempts: the second insert waits on the first's uncommitted row, then sees the conflict.

**`insert_fenced` and `insert`** (repositories.py:402-453, 500-510). A refused fence raises before any index write, so the transaction rolls back clean. A retry after the commit hits the primary-key violation, as before this diff.

**`TableTransport.publish`** (common/events/table.py:59-112). The index rows are written in the same transaction as the event rows. A re-sent batch within the horizon returns at line 95, and its index rows were already committed.

**`MessageRepository.end_task`** (common/persistence/messages.py:292-330) is called by `complete_task` (orchestrator/activities.py:123-165). The sequence is: `close_unfinished` (its own transaction), `_with_ledger_usage` (a read), `end_task` (one transaction: request lock, `UPDATE ... AND ended_at IS NULL`, index, close messages), then `tasks.get`.
- If the worker dies after `end_task` commits, the retry is a no-op, and the messages were already closed in the committed transaction.
- The v2 loop at orchestrator/workflow.py:431-447 can re-run `complete_task` after a cancel. That path is safe for the same reason.

**Migration 0007** runs in a single Alembic transaction (env.py:46-48, transactional DDL on PostgreSQL). A failure partway rolls everything back. The backfill uses `UNION` plus `ON CONFLICT DO NOTHING`, so it is idempotent.

**`reindex`** (common/persistence/refs.py:962-1003). Every write is `ON CONFLICT DO NOTHING` and runs in the caller's transaction. A rerun adds nothing. A concurrent `record_task` on the same primary key serialises on the insert.

**History guard** (tests/support/history_guard.py, tests/integration/conftest.py). Every file in tests/integration carries `pytestmark = integration`, so a unit-only `uv run pytest` never activates the session fixture. An unreachable Temporal is reported as a failure.

## Findings

No Blockers. No Majors.

## Nits

1. **common/persistence/refs.py:962 (`reindex`), migration 0007:211, plan Rollout · R2, R20.** A worker started too early, which Rollout explicitly anticipates, runs the old `end_task`. It writes a terminal status with `ended_at` NULL. `reindex` repairs unindexed references but not `ended_at`. Reconcile's "never ended" check covers only tasks left `running`. So that task's rows and blobs never expire, and `gc` doesn't refuse. Scenario: migrate, start an old worker, finish one task, start new workers, run `reconcile --reindex`, then `gc` after 8 days: the checkpoints are kept forever. This errs towards keeping data, which is why it is a Nit. Possible fixes: have `reindex` (and the unindexed check) also run `UPDATE tasks SET ended_at = updated_at WHERE status IN ENDED AND ended_at IS NULL`, or list such tasks. Test: seed a `succeeded` task with NULL `ended_at` and run `reindex`.

2. **orchestrator/activities.py:125-153 with messages.py:306-309 · F82 side effect.** On a `complete_task` retry, `_with_ledger_usage` re-reads the ledger. The retry then returns a `TaskResult` built from that fresh read, while the stored row keeps the first call's values. If a stale attempt settled usage in between, the Workflow's result has larger token counts than `tasks.result`. Before this diff, the retry overwrote the row, so the two matched. Nit: it only affects reporting. One fix is to return the stored result when `end_task` changes nothing.

3. **repositories.py:1219-1229 vs notes#revive step 2 and the `put` docstring (D10).** A deleted task's `put` decides whether to upload from `removed_at IS NULL` on the `blob_objects` row. The docstring and notes say "unless the blob is live for another holder". A row that is unmarked but has no live reference (a cleared-mark orphan) counts as live, so the bytes are uploaded again. `last_put_at` is not refreshed, so the orphan check still ages it from its old time. Nit: nothing is revived, and `orphaned()` reaches it. Either align the wording or check for a live `blob_refs` row.

4. **tests/support/history_guard.py:96-101, tests/integration/test_task_e2e.py:179 · R18.** Runs deleted by a test are skipped. `test_duplicate_task_id_rejected` deletes its run, so that history is never checked. The fixed 2 s `settle` can also miss a run started in the suite's last moments, before visibility indexes it. Nit: both are small coverage gaps in the guard, not in the product.

5. **tests/support/scratch_db.py:41-47.** The database is created before the `try`. If `CREATE EXTENSION pg_search` or the `db_admin` step fails, the scratch database is never dropped. Nit: like F95, the UUID names avoid collisions.

6. **repositories.py:1239-1241 · D10, R9.** The database commits before `inner.put`, so a failed upload leaves a live reference to a missing object until a retry. Listed for completeness: this is F86, already accepted as the order notes#revive prescribes.

## Helper behaviour relied on
- common/persistence/fence.py:20: `TASK_LOCK` is `pg_advisory_xact_lock(hashtext(:t))`, released at commit.
- common/events/table.py:94-95: a re-sent batch within the horizon returns before inserting events or index rows.
- orchestrator/workflow.py:431-447: `complete_task` is re-run after a cancel, with an identical payload.
- common/persistence/migrations/env.py:46-48: one `begin_transaction` around all migrations.
- tests/support/stack.py:37-44: `temporal_client` wraps every connect error as `RuntimeError`, which `guard_failure` catches.
- orchestrator/cli.py:95 and workers/main.py:162: both production paths use `RecordingBlobStore`, so the upload references are actually written.
- pyproject.toml:50 and every file in tests/integration: the integration marker keeps the session guard out of unit runs.

Relevant files:
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/persistence/refs.py
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/orchestrator/activities.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0007_blob_refs_and_classes.py
- /home/geo/develop/praxismesh/tests/support/history_guard.py
- /home/geo/develop/praxismesh/tests/support/scratch_db.py

Phase 01 review, failure lens. Plan: /home/geo/develop/praxismesh/docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle. Diff: 8cc4355..a50c358.

## Verdict
I found nothing in phase 01 that breaks one of its own requirements (R1, R2, R4, R5, R14, R18, R19, R20) when a run stops partway. Two Major findings are failure paths that come from phase-01 code and break phase-02 requirements (R11, R25, R10/R9). They are cheapest to fix while this code is still under review. Six Nits follow.

## What I traced (order of awaits and side effects)
- **`RecordingBlobStore.put`** (`common/persistence/repositories.py:656-695`):
  1. Collect the bytes.
  2. Transaction A: upsert `blob_objects`, which clears `removed_at`, `removed_by` and `bucket_deleted_at` and sets `last_put_at` (`:685`); then `index_keys(upload)` (`:692`). Commit.
  3. `inner.put` (`:695`), which is S3 `head`, then `put_object` or `copy_object` (`common/blob_store/s3.py:84-130`).
- **`prepare_task`** (`orchestrator/submit.py:33-52`): mint the task ID, then one `put` per blob (steps 2-3 above each time), then return. No row is written.
- **`record_task`**: insert the row; only if it inserted, index the instructions and inputs in the same transaction. A retry finds the row and skips the index, which the first run already committed.
- **`insert_fenced` / `insert`**: `TASK_LOCK`, the fenced insert, raise `FenceRejected` before `_index_checkpoint`, all in one transaction. A refusal rolls everything back (R1 holds).
- **`TableTransport.publish`** (`common/events/table.py:60-110`):
  1. Lock and fence.
  2. Batch dedup.
  3. Insert the events, then `index_refs` per attachment.
  4. Advance `next_offset`.
  5. `NOTIFY`.
  All in one transaction. A re-send inside the horizon returns before indexing.
- **`end_task`** (`common/persistence/messages.py:299-315`): `_request_of`, `_REQUEST_LOCK` (xact), `UPDATE tasks` (`ended_at = coalesce(...)`), `index_keys(result)`, then close messages. All in one transaction. `complete_task` retries it without limit (`orchestrator/workflow.py` comment at `_complete`).
- **Migration 0007**: runs inside one `context.begin_transaction()` (`common/persistence/migrations/env.py` `do_run_migrations`), so a death partway rolls everything back and a rerun starts clean. The backfill uses `ON CONFLICT DO NOTHING`.
- **`refs.reindex`**: runs on the caller's connection. `INSERT ... ON CONFLICT DO NOTHING` plus a per-object `blob_objects` insert `ON CONFLICT DO NOTHING`. Idempotent; a concurrent `put` serializes on the same primary key.
- **Session payload guard** (`tests/integration/conftest.py`): yield, then list runs since the start and fetch each history.

Overlaps: two `put`s of the same key serialize on the `blob_objects` row. Index keys are sorted (`refs.py` `index_keys`: `sorted(set(...))`). Writers never lock `blob_objects` after `blob_refs`, so I found no lock cycle with the D6 order.

## Major

**M1 · A deleted task's late upload brings the bytes back, and nothing will ever collect them** (R25, R10, R9, D10; phase 02 impact)
- **Location:** `common/persistence/repositories.py:685` (unconditional `removed_at = NULL, removed_by = NULL, bucket_deleted_at = NULL`) together with `common/persistence/refs.py:165-174` (a delete's mark on the reference stays).
- **Scenario:** this is R25's own case.
  1. `request delete --force` marks task T's references `delete:...` and marks blob X; the bucket step deletes X.
  2. T's still-running attempt uploads its workspace, which has the same bytes X.
  3. `put` clears X's mark and `bucket_deleted_at`. The upload reference stays marked (correct for R25). `inner.put` sees the object missing and uploads it again.
- **Result:**
  - X is back in the bucket, `blob_objects` is unmarked, and X has no live reference.
  - Phase 02's planned GC never selects it. `expired()` scans only live references (`refs.py:268-289`, `r.removed_at IS NULL`). The orphan check needs "no `blob_refs` row" (`refs.py:264`), but X has marked rows. notes.md#d6 marks a blob free only for keys that the batch's own references name.
  - Any `BlobRef` to X (in Temporal history for 72 h, or in a backup) reads the deleted content and does not raise `BlobExpired`. This contradicts R10 ("none of its artifacts, checkpoints or inputs can be read").
- **Evidence:** notes.md#revive step 2 says to clear the mark unconditionally. The plan's own mechanism therefore produces this, so it is a design gap that the code faithfully implements.
- **Fix direction:** clear the `blob_objects` mark only when the `put` leaves a live reference, or skip the bucket upload when the upload reference stays delete-marked.
- **Test:** delete-mark task T's upload reference and blob X with `bucket_deleted_at` set. `put` X with `task_id=T`. Assert that X is either still marked or absent from the bucket, and that `reconcile`/`gc` can reach it.

**M2 · A retried `end_task` overwrites a redacted result** (R11, R25; phase 02 impact; code changed in this diff for R20)
- **Location:** `common/persistence/messages.py:301-306`. The `UPDATE tasks SET status, result ...` has no guard; only `ended_at` is coalesced.
- **Scenario:**
  1. `complete_task` commits `end_task`, but the worker dies before Temporal records the completion.
  2. The task now has `ended_at`, so phase 02's `request delete` accepts it, redacts `result` and marks its references.
  3. Temporal retries `complete_task` with the same `CompleteTaskInput`, and `end_task` rewrites `result` with the original summary, questions and artifact refs.
- **Result:**
  - The redacted content returns to `tasks.result`.
  - `index_keys` keeps the delete marks, so the restored artifact refs show as references that look live in the row but are marked in the index. Reconcile shows them as neither dangling nor unindexed, so it misses the problem.
- **Evidence:** the `_complete` comment says it is "Idempotent, so retried without limit". D12's fencing row (`task_attempts`) does not fence `end_task`.
- **Fix direction:** make `end_task` a no-op when `ended_at` is already set (it already takes the request lock that phase 02's delete holds).
- **Test:** call `end_task`, simulate redaction of `result`, call `end_task` again with the original result, and assert that the redaction stands.

## Nits
1. **`repositories.py:680-695`:** the database commits before `inner.put`. If S3 fails at step 3, `blob_objects` loses its `removed_at` and `bucket_deleted_at` and a live upload reference names an object that is not in the bucket. A later read then raises `BlobNotFound` instead of R9's `BlobExpired`, and reconcile reports it as dangling. This persists until the task expires, or for 24 h plus a closed Workflow if there is no row. The order is prescribed by notes.md#revive and a retry heals it, so I rate it Nit. No test covers a failing inner `put`.
2. **`repositories.py:695`:** the returned `BlobRef.retention_class` comes from the S3 metadata via `stronger` (`s3.py:117-130`). Bytes first stored as an old `audit` artifact and reused as a workspace come back as `audit` and are stored in `checkpoints.workspace_ref`. R4 says "every blob ... written after the change must carry its D3 class". The index uses the holder class, so lifetimes are unaffected (D3: metadata is never read), hence Nit.
3. **`tests/integration/conftest.py:28-30`:** the R18 guard passes silently (only a warning) when Temporal is unreachable at teardown. The fixed 2 s visibility wait can also miss the last runs. Either way the guard can pass without checking anything.
4. **`harness_activity/activity.py:511,724`:** the resume path copies `latest.finish["questions"]` into `TurnOutcome` without truncating. A checkpoint finish written before this change (an open turn that was not drained) would put untruncated questions into history. The rollout drains Workflows, so this is defense in depth only (D9).
5. **Migration 0007 downgrade:** it is lossy. `event_batches` rows that were `task` and orphan `blob_objects` that were `task` or `audit` stay `ephemeral` after a downgrade. Old code accepts `ephemeral`, and the plan documents the downgrade's limits, hence Nit.
6. **`tests/support/scratch_db.py`:** if the test process is killed, `praxis_scratch_*` databases are left on the stack server. The UUID names prevent collisions, but they accumulate until `make reset`.

## Not findings (checked)
- A refused fenced checkpoint leaves no index row.
- `record_task` retries leave no gap in the index.
- Retrying `end_task` with the same result does not change `ended_at` (coalesce) and does not duplicate index rows.
- Rerunning the migration after a crash is clean because it is all one transaction.
- `reindex` reruns are no-ops.
- Concurrent `put`s of the same key serialize.
- Event re-sends inside the horizon skip indexing.
- `agent_events.task_id` is NOT NULL (`0005_agent_events.py:52`), so `blob_refs.task_id` NOT NULL cannot fail the backfill.

Key files:
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/persistence/refs.py
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0007_blob_refs_and_classes.py
- /home/geo/develop/praxismesh/tests/integration/conftest.py
- /home/geo/develop/praxismesh/harness_activity/activity.py

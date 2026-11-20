<!-- Verbatim subagent report (Phase 3A persistence plan design-review round 2, zoom out, at c6efe44; plan files unchanged at eadd5ad); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged with save-report). -->

## Review: Phase 3A persistence and data lifecycle plan (round 2 inputs at eadd5ad)

I found six Major problems and six Nits, and no Blockers. The plan does go after the real cause: there is no queryable reference index and no lifecycle. But the expiry design misses issue #74's own timing, and the rollback, event-pruning and request-delete sections conflict with the code as it stands.

### Major

**M1. Root cause: stale-attempt uploads made after the task ends never expire, which is issue #74's main case**
- Where: notes.md#d2 "Expiry"; plan R20 and D2; phase 01 task 2.3.
- What is wrong: expiry is written once. notes#d2 says "`end_task` sets `tasks.ended_at` and `expires_at = ended_at + lifetime` for every reference the task holds, in its own transaction", and notes#d3 says "A row of a task that never ended never expires".
- Why it happens: a stale attempt keeps running after its heartbeat times out, up to `start_to_close_timeout=resolved.turn_timeout` (/home/geo/develop/praxismesh/orchestrator/workflow.py:149-151). Its `put` calls are not fenced (ADR-0007:80-82). So it can upload after a newer attempt finished and `end_task` committed. The upload reference it then inserts (notes#revive step 2) has `expires_at` NULL forever, and nothing ever sets it.
- Test gap: R6's scenario ("a task that ended 8 days ago with a stale attempt's workspace upload") would pass with the upload seeded before the end, so the bug would not show.
- Fix (simpler): drop the stored `expires_at` and the stamping in R20. GC can compute expiry as `tasks.ended_at + lifetime(class)` with a join; the D5 rule for tasks with no row is already computed at GC time. The other option is for `index_refs` to set expiry from `tasks.ended_at` under the task lock, but that adds another place where a race can happen.

**M2. Failure mode: request delete is not protected by the request lock, and marking by `request_id` removes a joining task's inputs**
- Where: D12; notes.md#redact; notes.md#d2 ("a delete marks its request's references removed"); D4 (batches of 500).
- Lock: `_REQUEST_LOCK = text("SELECT pg_advisory_xact_lock(2, hashtext(:r))")` (/home/geo/develop/praxismesh/common/persistence/messages.py:32) is held only for one transaction. The delete commits up to 500 rows per transaction (D4, D6), so the lock is released between batches. D12's "no task joins or ends mid-delete" does not hold.
- Joining task: a `--join REQ` submit runs `prepare_task`, which uploads and writes upload references carrying `request_id = REQ` before `record_task` exists, without taking any lock. A delete that marks references by request ID will mark them, and then remove those inputs from the bucket under a task that is about to run. R12's ended-check cannot see this task, because it has no `tasks` row yet.
- Fix:
  - Fix the set of task IDs under the lock at the start, and record it in the first tombstone.
  - Mark only references whose `task_id` is in that set.
  - Either hold a session-level `pg_advisory_lock(2, hashtext(REQ))` on a dedicated connection for the whole run, or state plainly that joins are allowed during a delete.

**M3. D11 contradicts D6 and R13: `TableTransport.prune` cannot join the batch transaction**
- Where: D11; notes.md#redact (events row); phase 02 task 1.4; R13 ("in the same transaction, a tombstone").
- What `prune` does today (/home/geo/develop/praxismesh/common/events/table.py:170-209):
  - It opens its own transaction (`async with self.engine.begin() as conn`).
  - It deletes every row below the cutoff for one log in one statement, with no 500-row limit.
  - It does not mark the references in `agent_events.blob_ref`.
- Consequence: an event removal cannot share a transaction with its tombstone. A crash between the two loses the tombstone, which is exactly what D6 rejects ("tombstone last (a crash loses it)").
- Fix: give `prune` an optional `conn` argument and use the `below=` cutoff to keep each batch to 500 rows, or say that events get their own transaction and tombstone per log.

**M4. Rollout and rollback: a downgrade cannot work once new code has written anything**
- Where: Rollout & rollback ("Downgrade ... maps classes back to `task` and `audit`"); notes.md#d3 ("Stored JSON `BlobRef`s and S3 object metadata keep their recorded class").
- Why old code fails:
  - It has `RetentionClass = Literal["ephemeral", "task", "audit"]` (/home/geo/develop/praxismesh/common/schemas/base.py:11).
  - `BlobRef` is `Strict` with `retention_class: RetentionClass` (/home/geo/develop/praxismesh/common/schemas/blob.py:13-20).
  - `RETENTION_ORDER` has only the old three keys (/home/geo/develop/praxismesh/common/blob_store/base.py:20).
- Where it breaks after a downgrade:
  - Checkpoint JSON written by new code fails `BlobRef.model_validate` in `CheckpointRepository.latest` (/home/geo/develop/praxismesh/common/persistence/repositories.py:475).
  - In-flight Temporal histories carry `BlobRef`s with `checkpoint`, `transcript` or `artifact`, and fail to decode.
  - `S3BlobStore.put` raises `KeyError` in `stronger()` on object metadata that says `checkpoint`.
  - The migration's downgrade only rewrites columns, so none of this is repaired.
- Also missing: Rollout does not mention the `agentctl` CLI version, although it uploads too.
- Fix: either ship a compatibility step first (old code accepts the new classes before any new code writes them), or state that rollback is only possible before the first write after the upgrade, with no in-flight Workflows.

**M5. Failure mode: the 24-hour window can remove blobs still in use**
- Where: D5; notes.md#d2 ("An upload reference whose task has no `tasks` row 24 hours after upload expires then"); notes.md#revive ("`last_put_at` is backfilled from `created_at`").
- Queued tasks lose inputs: notes#refs itself says the gap before `record_task` is "Unbounded if no orchestrator worker runs". If a submitted Workflow waits more than 24 hours for an orchestrator worker (workers stopped, including the rollout's own "Stop the workers" window), `gc` removes its inputs. D5's wording, "a submit whose Workflow never started", cannot be told apart from "not started yet". Fix: before expiring a reference with no row, ask Temporal to describe the Workflow (its ID is the task ID; `--force` already uses this call), and expire only if it is missing or closed.
- Old blobs re-uploaded before the migration look old: blobs are content-addressed, and the old `put` never updates any timestamp (repositories.py:636-645). A blob first stored long ago but uploaded again recently by a running task gets an old `last_put_at` from the backfill. If it lives only in Workflow state (artifacts waiting for `complete_task`, notes#refs), the first `gc` after the migration removes it. Fix: backfill `last_put_at = now()` at migration time. R8's pre-0007 orphan test then has to set the time explicitly.

**M6. Objects in the bucket with no `blob_objects` row are invisible to GC and reconcile, though D8 counts on GC removing them**
- Where: notes.md#d8 ("a blob uploaded after its dump is an orphan (harmless; GC removes it)"); notes.md#d2 ("*orphaned*: a `blob_objects` row with no `blob_refs` row"); R17.
- What is wrong: after a restore, a blob uploaded between the app-database dump and the bucket copy exists only in the bucket. GC's orphan rule depends on `blob_objects.last_put_at`, and the orphan check depends on a `blob_objects` row, so neither ever sees it. The same leak exists today because `put` uploads before writing the row (repositories.py:634, then 636).
- Fix: reconcile already lists the bucket for the dangling check, so define orphans from the bucket listing and use the object's LastModified for the window. Alternatively, restore and `--reindex` can insert `blob_objects` rows for bucket-only objects with `last_put_at = now()`.

### Nits

- notes.md#d3, last table row: it says `blob_objects` and `blob_refs` expire "with its references", but notes#d2 says "Marked rows stay", and R9 needs `removed_at` to persist. If these rows are deleted, round 1's F2 comes back (permanent unindexed) and R9 fails.
- D3, "S3 object metadata is left as written": not true. `S3BlobStore.put` rewrites metadata with `copy_object` when `stronger(current, retention) != current` (/home/geo/develop/praxismesh/common/blob_store/s3.py:106-118), and `task` becomes `transcript` on the next upload of the same bytes.
- D10 / notes#revive step 3 ("always if the key was marked or new"): this needs a forced upload in the inner store. `S3BlobStore.put` always checks `head_object` and skips (s3.py:91-93). "What changes" does not list the `BlobStore` protocol change or the `MemoryBlobStore` change.
- notes#d2, upload reference primary key "rewriting the same reference is a no-op": when one task uploads the same bytes under two classes, the first class is kept. It should say the stronger class wins, as `blob_objects` already does.
- D4 / D8, `backup.sh` "holding the D4 lock": a shell script running `pg_dump` cannot hold a session advisory lock unless something keeps a database session open. Say how (for example a Python wrapper that holds the connection).
- R23 / notes#d8 step 1: the refusal checks only `tasks` and the bucket, not the `temporal` database, so a stack with Workflows but no `tasks` rows yet passes and gets dropped.

### Checked and not raised

- Every write goes through `RecordingBlobStore` (/home/geo/develop/praxismesh/workers/main.py:162, /home/geo/develop/praxismesh/orchestrator/cli.py:95). Only `task output` reads directly from S3 (cli.py:133), which phase 02 task 1.1 already handles.
- `needs_input` is terminal in the Workflow (/home/geo/develop/praxismesh/orchestrator/workflow.py:178-179).
- D9 matches the existing truncation at /home/geo/develop/praxismesh/harness_activity/tools.py:222.
- The task counts in the Phases table match the phase files.
- Simplicity: I considered dropping the row-level index in favour of upload references alone. I did not raise it, because plan D's DAG hand-offs will put references in rows of tasks that never uploaded those blobs.

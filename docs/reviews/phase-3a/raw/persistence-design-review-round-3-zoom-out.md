<!-- Verbatim subagent report (Phase 3A persistence plan design-review round 3, zoom out, at f3453cd; plan files unchanged at b1ef5de); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged with save-report). -->

I reviewed plan.md, the three phase files, notes.md and ADR-0001 to 0011 against the code at HEAD (b1ef5de). The plan does fix the root cause: an explicit index plus upload references is what makes deletion safe when identical bytes share one object. I found 4 Majors and 5 Nits, and no Blockers.

## Majors

**M1. An attempt that is still running can write content back after `request delete`**
- **Where:** plan.md › Decisions › D12 and D10; notes.md#d2; notes.md#redact (`--force`); R11 and R21.
- **What is wrong:** A task can end while an attempt is still running. This happens when a turn passes `turn_timeout` and is failed for good, or when `--force` deletes a task whose Workflow was terminated while its Activity keeps going.
  - ADR-0007's fence only checks for a *newer* attempt (`common/persistence/fence.py:23-26`). `insert_fenced` (`common/persistence/repositories.py:387-417`) and event publish (`common/events/table.py:62-67`) therefore still commit for that last attempt after the delete. New checkpoint rows, events and session rows with content appear after the tombstone says the request was deleted.
  - The attempt's unfenced uploads go further. notes.md#d2 says of `blob_refs` upserts: "On conflict the stronger class wins and any removal mark is cleared". The deleted task's upload reference becomes live again, `put` clears `blob_objects.removed_at` (notes.md#revive step 2), and the bytes are readable for up to the class lifetime (90 days for artifacts).
  - notes.md#refs already says such uploads arrive "possibly after the task has ended".
- **Fix:** Stop those writes, for example:
  - The delete inserts a fencing `task_attempts` row, or the fence also checks the task's status, so ADR-0007's fence refuses later writes.
  - An upload-reference upsert never clears a mark set by a delete. The blob can still be revived, and is then free and collected.
  - Add a test: a `--force` delete while the Activity is still running.

**M2. Rollout: in-flight uploads from before 0007 have no index row and look like orphans to `gc`**
- **Where:** plan.md › Rollout & rollback; notes.md#d2 (backfill); D5; R7.
- **What is wrong:** The backfill only reads JSON columns. Two kinds of blob are named only in Temporal state when the migration runs:
  - the instructions and inputs of a queued task with no `tasks` row yet (`orchestrator/submit.py:34-42` uploads them before `start_task`);
  - artifacts carried in Workflow state until `complete_task` (`harness_activity/activity.py:691`).
  
  The old `put` wrote no upload reference, so these blobs have no `blob_refs` row. Their `last_put_at` is the migration time. The "unindexed" check only scans rows, so `gc` does not refuse. A Workflow still queued 24 hours after the migration loses its inputs, which R7 ("a submitted task whose Workflow has waited 30 hours … its inputs are kept") says must not happen.
- **Fix:** Require no open Workflows before migrating; the rollback paragraph already needs that condition. Alternatively, have `reconcile --reindex` or the first `gc` index the BlobRefs of open Workflows.

**M3. A backup taken while workers run can restore Workflows that are ahead of their rows**
- **Where:** plan.md › Decisions › D8; notes.md#d8; R16.
- **What is wrong:** notes.md#d8 says: "Temporal's dumps come next, so a Workflow may be newer than the restored rows … comparing Workflows with rows is Phase 9 hardening." Nothing handles the result.
  - Say a Workflow's `record_task` (or a turn's attempt start) completes between the two dumps. After a restore, Temporal believes it is done, but there is no row. Later Activities fail permanently, for example `_request_of` raises "task … is not recorded" (`common/persistence/messages.py:362-370`).
  - Reconcile does not list this case; it only lists unended tasks whose Workflow is closed.
  - The drill (R16, phase 03 task 2.3) uses only finished tasks, so it cannot catch it.
- **Fix:** Have `agentctl backup` refuse while workers are up or Workflows are open, or stop the workers itself. On one machine this costs little, and the Rollout section already stops workers.

**M4. The plan does not say which class the backfilled `blob_refs` rows get**
- **Where:** notes.md#d2 (backfill) and notes.md#d3 ("Old values"); R19; plan.md › D3.
- **What is wrong:** notes.md#d3 says "Stored JSON `BlobRef`s keep their recorded class", and that each `blob_objects` row "gets the longest-lived class of its index rows". It never says where the class of a backfilled index row comes from.
  - Artifacts written before 0007 are recorded as `audit` (`harness_activity/activity.py:691`, `retention="audit"`).
  - If the backfill copies the class from the JSON, those artifacts and their `blob_objects` rows rank `audit` and never expire. D3 explicitly rejects that ("artifacts never expire"). `task` values would also end up in `blob_refs`, which phase 01 task 1.3 says is never written.
  - R19 only tests table rows, not index rows.
- **Fix:** State that the backfill takes each index row's class from notes.md#d3's blob table (by table and column), never from the JSON. Add an R19 scenario for an artifact written before 0007.

## Nits

- **notes.md#d6 step 1 vs task 1.2, lock order:** the step list marks references and then locks `blob_objects`, yet both say "`blob_objects` locked first". The step list's order inverts the order `put` uses, so a stale-attempt `put` racing `gc` can deadlock. Lock the candidate keys' `blob_objects` rows, in key order, before marking.
- **D10 / phase 01 task 2.2, the `force` flag:** it adds nothing. Under the row lock, either the bucket delete already ran, so `head_object` misses and `S3BlobStore.put` uploads anyway (`common/blob_store/s3.py:89-104`), or the bucket step will see the cleared mark and skip. Dropping it avoids a protocol change in three stores.
- **notes.md#revive, bucket step condition "`last_put_at` is older than `removed_at`":** both values come from transaction-start `now()`. A `put` that commits first, inside a removal transaction that started earlier, gives `removed_at < last_put_at`. That blob is then skipped on every rerun and never deleted. The mark check under the lock is enough on its own; otherwise use `clock_timestamp()`.
- **D4 and phase 02 task 1.5, `events prune` not locked:** it now runs the removal engine but is not listed under the `pg_advisory_lock(3, 0)` lock. It can overlap `gc` or a backup, which D8 relies on the lock to prevent ("The lock keeps removals out between the dump and the copy").
- **notes.md#d8 restore step 1, "`temporal` holds no Workflow execution":** I did not check this, but Temporal 1.32 (`infra/docker-compose.yml:54`) normally runs its own system Workflows in the `temporal-system` namespace. A raw check of executions would then refuse every started stack. Scope the check to the app namespace.

The files that matter most are:
- `/home/geo/develop/praxismesh/docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/notes.md`
- `/home/geo/develop/praxismesh/common/persistence/fence.py`
- `/home/geo/develop/praxismesh/common/persistence/repositories.py`
- `/home/geo/develop/praxismesh/harness_activity/activity.py`
- `/home/geo/develop/praxismesh/orchestrator/submit.py`
- `/home/geo/develop/praxismesh/common/blob_store/s3.py`
- `/home/geo/develop/praxismesh/common/events/table.py`
- `/home/geo/develop/praxismesh/common/persistence/messages.py`

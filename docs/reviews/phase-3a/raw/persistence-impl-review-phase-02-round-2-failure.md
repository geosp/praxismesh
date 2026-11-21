Phase 02 impl-review, failure lens. Diff 9a81933..dd999f3 in /home/geo/develop/praxismesh.

## Verdict
I found one Major finding and seven Nits. For every unit I traced, a run that stops partway finishes correctly when run again, with one exception: a narrow upload-and-crash case leaks a bucket object permanently.

## How I traced it
I listed every await and side effect, in order, for these units:
- `RemovalEngine.run`, `_batch` and `_bucket_step` (`/home/geo/develop/praxismesh/common/persistence/removal.py`)
- `gc`, `_gc` steps 1-5, `prune_events`/`_prune_events`, `delete_request` with its retry loop, `_delete`, `_redactions` and `unfinished_delete` (`/home/geo/develop/praxismesh/orchestrator/lifecycle.py`)
- `RecordingBlobStore.put`, `check_live`, `get` and `stream` (`/home/geo/develop/praxismesh/common/persistence/repositories.py:662-766`)
- `TableTransport._prune` (`/home/geo/develop/praxismesh/common/events/table.py`)
- `FencedSQLAlchemySession.add_items` (`/home/geo/develop/praxismesh/harness_activity/session_store.py`)
- `refuse_if_deleted` and `NO_NEWER_ATTEMPT` (`/home/geo/develop/praxismesh/common/persistence/fence.py`)
- `delete_mark`, `index_keys`, `orphaned`, `expired` and `rowless_uploads` (`/home/geo/develop/praxismesh/common/persistence/refs.py`)
- `S3BlobStore.put` and `delete` (`/home/geo/develop/praxismesh/common/blob_store/s3.py:84-157`)

These cases hold:
- **Failure before the first save.** A refused delete changes nothing: R12 and R21 are checked before `finish_pending` (lifecycle.py:653-670). `GcRefused` is raised before any batch.
- **Crash inside a batch.** The transaction rolls back, including the task locks taken with try-lock (removal.py:231-237).
- **Crash after a commit, before the bucket step.** The blob keeps `removed_at` with `bucket_deleted_at` null. `pending()` picks it up (removal.py:366-375) and `finish_pending` runs before any new batch (lifecycle.py:412, 670).
- **Crash after the S3 delete, before `bucket_deleted_at`.** The rerun deletes again, and a missing object is not an error. A `put` that waited for the row lock clears the mark, and `S3BlobStore.put` re-uploads because `head_object` misses (s3.py:95-109).
- **A delete killed after its first batch.** `unfinished_delete` (lifecycle.py:547-568) resumes with the task list from that batch's tombstone. A forced task already has `ended_at`, so the resumed run needs no `--force`. Inserting the fencing row is idempotent (`NOT EXISTS ... 'deleted'`, lifecycle.py:681). Redactions skip rows that already hold the marker. References and blobs are marked only while `removed_at IS NULL`. So nothing is counted twice (R15), and the tests at test_removal_kills.py:154-208 and test_request_delete.py:580 cover this.
- **Two runs overlapping.** `run_lock` uses `pg_try_advisory_lock(3,0)` (removal.py:92-101). A delete also holds the session form of the request lock; `record_task`, `end_task` and messaging wait on its transaction form (fence.py, repositories.py `record_task`).
- **The R25 fence.** The `deleted` outcome row refuses every fenced writer: `publish` (table.py:64-68), checkpoints, attempts and messages. SDK session items and tool rows get `refuse_if_deleted`. A deleted task's `put` writes its reference already marked, and a new key is recorded as marked with `bucket_deleted_at` set (repositories.py:712-738).

## Findings

**F1 · Major · R6, R15, D6, D10 · An object uploaded by a `put` whose transaction never commits leaks forever, and no check reports it.**
- **Where:** `/home/geo/develop/praxismesh/common/persistence/repositories.py:693-742`, together with refs.py:312-316 and removal.py:366-375.
- **What `put` does:** since F124, it clears the mark (`removed_at`, `removed_by` and `bucket_deleted_at` set to NULL, lines 704-708) and then calls `self.inner.put`, all inside the open transaction (line 742).
- **Scenario:**
  1. GC removes blob K: the row is marked, the bucket step deletes the object, and `bucket_deleted_at` is set.
  2. `agentctl task submit` uploads the same file again. `put` clears the mark in its transaction, and `S3BlobStore.put` sees `head_object` miss, uploads the bytes and calls `stat`.
  3. The CLI process is killed (Ctrl-C) or the database connection drops before COMMIT.
- **Wrong outcome:** the row rolls back to "removed, bucket deleted", but the object is back in the bucket. Nothing ever removes it:
  - `pending()` selects only rows with `bucket_deleted_at IS NULL`.
  - `orphaned()` skips every key whose row is marked (`not (key in recorded and recorded[key][1])`, refs.py:315).
  - `reconcile`'s orphan and dangling checks skip it for the same reason.

  An Activity retry of `put` would heal it, but a dead CLI submit never retries. This is the class of unreferenced blob that issue #74 and R6 set out to remove.
- **Rating:** Major rather than Nit because the leak is permanent and invisible to every check. The window is narrow, between `put_object` returning and COMMIT, so you may downgrade it.
- **Possible fix:** treat a bucket object whose row has `bucket_deleted_at` set as an orphan again, or as pending again.
- **Test that exposes it:** wrap the inner store so `put` succeeds and then raises, against a row already marked with `bucket_deleted_at` set. Then assert that the next `gc`, past the safety window, deletes the object, or that `reconcile` lists it.

**Nits** (location · what · why):
- N1 · lifecycle.py:615-627 (R24) · After `TaskBusy`, the request lock is released while the retry sleeps. A task can join then, and the retry re-reads the task list by `request_id` (line 647), so a running joiner makes the delete fail with `DeleteRefused`. It refuses rather than corrupting anything, but R24's "a task joining while it is being deleted" turns into a refusal in this window.
- N2 · lifecycle.py:699-714 (D4) · The delete's first batch marks every upload reference of every task in the list, and fences every task, in one transaction with no cap. A large request can go over D4's "batches of at most 500 rows".
- N3 · lifecycle.py:310-330 (D4) · A checkpoint batch deletes up to 500 rows but can mark up to 1,000 references (workspace and session). Whether 500 "rows" includes reference marks is ambiguous.
- N4 · repositories.py:744-757 (R9) · `check_live` reads `removed_at` on its own connection before `inner.get`. A bucket step that runs between the two makes a removed blob read as `BlobNotFound`, not expired. The window is tiny.
- N5 · repositories.py:693-742 with removal.py:255-261 (D12) · `put` now holds the task lock and a database transaction for the whole S3 upload. A large workspace upload that lasts longer than the delete's retry budget (about 10 s, `DELETE_RETRY_S`) makes `request delete` fail with `RemovalBusy`. The operator only has to rerun it, but the delete fails while an upload is in progress.
- N6 · removal.py:85-89 · If the unlock is cancelled or fails while the connection stays healthy, the connection goes back to the pool still holding the session lock: the pool's reset on return is a rollback, not `pg_advisory_unlock_all`. The CLI disposes its engine afterwards, so only a long-lived caller of `gc` or `delete_request` would keep the lock. I could not confirm a long-lived caller exists.
- N7 · removal.py:247-252 · A dry run skips `finish_pending`, so its plan never shows the bucket objects the real run would delete for blobs an earlier run left marked. A dry run should touch no bucket, but its report then differs from the real run's `finished_from_earlier_runs`.

I found no deadlock under the lock orders I checked: task lock, then `blob_objects` in key order, then `blob_refs`/`event_logs`; and publish's task lock, then `event_logs`.

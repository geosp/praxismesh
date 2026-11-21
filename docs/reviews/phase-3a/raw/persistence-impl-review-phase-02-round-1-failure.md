## Phase 02 implementation review (failure lens): 9a81933..8012f6b

I found 2 Majors and no Blockers, plus Nits. I traced every await and side effect in `run_lock`, `request_lock`, `RemovalEngine.run`, `_batch`, `_bucket_step`, `finish_pending`, `gc`, `_gc`, `delete_request`, `_delete`, `prune_events`, `event_batch`, `row_batch`, `_redactions`, `RecordingBlobStore.put`/`get`/`stream`/`stat`, `TableTransport._prune`, `end_task` and `MessageRepository._enter`.

### What holds up (helper behaviour I relied on)
- **A batch is all or nothing.** The tombstone goes through `AuditRepository.append` on the caller's connection (`common/persistence/audit.py:38`). `run()` rolls back on any `BaseException` (`common/persistence/removal.py:215-217`). The bucket step runs only after commit (`removal.py:224`).
- **Bucket step is safe to repeat.** S3 `delete_object` and `MemoryBlobStore.delete` don't fail on a missing object (`common/blob_store/s3.py:156`, `memory.py:80`). The step runs under the row lock and checks `removed_at`; a crash before `bucket_deleted_at` is set is redone by `pending()` (`removal.py:365-402`).
- **Revive ordering is sound.** `put` takes the task lock, then `blob_objects`, then `blob_refs` (`common/persistence/repositories.py:692-733`). That is the batch order (`removal.py:235-251`). A delete-kept mark is never cleared (`common/persistence/refs.py:183-195`).
- **Task-lock retry works.** `_enter` takes the task lock before the request lock (`common/persistence/messages.py:374-379`), so `pg_try_advisory_xact_lock` plus a retry that releases the request lock avoids the undetectable wait. `end_task` does nothing once `ended_at` is set (`messages.py:303-310`).
- **Reruns don't double-count.** Each run gets a fresh operation ID. References are counted by `removed_by = op AND removed_at = now()`, blobs only from `removed_at IS NULL`, and redactions skip marked rows. Every collect reads only live references, including in the single dry-run transaction.

### Major 1: a delete rerun rebuilds the task list from `request_id` (R24, R15, D12)
- **Location:** `orchestrator/lifecycle.py:584-602`. `_delete` always runs `SELECT task_id ... FROM tasks WHERE request_id = :r`. It never reads the list fixed in an earlier run's first tombstone.
- **Scenario:**
  1. `request delete REQ` (tasks T1, T2) commits its first batch, which fences T1 and T2 and records `tasks: [T1, T2]`. It is then killed during the checkpoint batches.
  2. The session request lock goes with the connection. `task submit --join REQ` records T3, since `record_task` now gets the lock (`common/persistence/repositories.py:60-62`).
  3. The operator reruns the delete. If T3 is still running, the rerun is refused naming T3 (`lifecycle.py:597-601`), so the half-done delete cannot finish (R15). If T3 has ended, the rerun fences, redacts and removes T3 too: a task that joined mid-delete is changed (R24).
- **Evidence:** notes.md#redact: "writes the list into its first tombstone. Every batch selects by that list, never by `request_id`". The kill tests (`tests/integration/test_removal_kills.py:157-182`) and the join test (`tests/integration/test_request_delete.py:338`) each cover one run only.
- **Exposing test:** kill a delete after batch 1, `record_task` a joiner (running, then ended), rerun. Assert the rerun completes and the joiner is untouched.
- **Possible fix:** a rerun takes the union of earlier delete-tombstone lists for the request (or the tasks with a `deleted` fencing row), not `request_id`.

### Major 2: redaction skips content that merely starts with "[deleted " (R11)
- **Location:**
  - `orchestrator/lifecycle.py:516`: `_MARKED = "[deleted %"`
  - `lifecycle.py:734`: `startswith("[deleted ")` on `result.summary`
  - `lifecycle.py:755`, `:763`, `:771`: `NOT LIKE` on `agent_messages`, `task_messages` and `idempotency_keys`
- **Scenario:** a model writes a summary such as `"[deleted draft] the key is ..."`, or an agent sends a message body starting `[deleted `. `request delete` treats the value as already redacted. The questions, failure reason and artifacts list stay, and so does the message or tool-result body. R11 fails, and model output (untrusted, §9.5) decides whether redaction happens.
- **Exposing test:** in a finished request, set a summary and a `task_messages.body` to `"[deleted x] secret"` with questions present. Delete, then assert each value equals `marker(now)` and questions equal `[marker]`.
- **Possible fix:** match the exact marker form, `^\[deleted \d{4}-\d{2}-\d{2}\]$`, and its JSON-string form.

### Nits
1. `common/persistence/refs.py:123-133` (R25): `delete_mark` only sees a deleted task if some reference carries a `delete:` mark. If the first batch marked no upload reference (a backfilled pre-0007 task, or uploads already expired by GC), a late `put` before step 5 writes a live upload reference and clears the blob's mark. This also happens after a kill between the first batch and step 5. Checking `task_attempts.outcome = 'deleted'` would close it.
2. `removal.py:309-335`: the free check and the mark are separate statements. A key with no `blob_objects` row has no row for `FOR UPDATE` to lock, so a `put` that commits between them gets marked even though its upload reference is live. The bucket step then deletes a live blob. This needs a reference to a key with no `blob_objects` row, so it is narrow. Fold the `NOT EXISTS` into the `UPDATE`, as `_mark_orphans` does.
3. `repositories.py:734-736`: `put` uploads after its commit, outside the lock. If the row is re-marked and bucket-deleted in that gap (a deleted task's `put` with `live=True` while the other holder is removed, or an upload reference already expired), the object comes back under a row with `removed_at` and `bucket_deleted_at` both set. `pending()` never lists it and `refs.orphaned` excludes it (`refs.py:268-296`), so it leaks for good. The race window is narrow.
4. `removal.py:183-190`, `:204`: a dry run keeps its `blob_objects FOR UPDATE` locks, row locks and the delete's `TASK_LOCK`s until the final rollback. Live `put`s and checkpoint writes on those keys or tasks block for the whole dry run. This follows from the recorded design, but the consequence isn't documented.
5. `removal.py:230-231`: a dry run skips `finish_pending`, so a killed run's pending bucket deletes don't appear in the plan.
6. `removal.py:206-207`: a dry run rolls back a zero-count savepoint even when `record_empty` is set. The dry first batch's fence and forced end then vanish when no upload reference was marked, while the real run commits them. The plans diverge, harmlessly today.
7. `repositories.py:738-751` (R9): `check_live` and then `inner.get` leave a gap. A bucket step between them gives `BlobNotFound` instead of `BlobExpired`. Tiny race.
8. `removal.py:320-327`, `:345-351`: placeholder `blob_objects` rows are written with 0 bytes and `application/octet-stream`. A later revive's upsert (`repositories.py:702-708`) never corrects them.
9. `refs.py:268-296` with `removal.py:347-349`: the orphan path doesn't filter out keys that aren't content keys. A non-`sha256/` object is removed after the window with a made-up checksum. Reindex does filter, with `_CONTENT_KEY` (`refs.py:76`).
10. `removal.py:82-85`, `lifecycle.py:538-539`: if the lock connection broke, the unlock in `finally` raises and hides the original error.
11. `lifecycle.py:383-389`, `:593-608`: refusals (unindexed references, unended tasks) come before `finish_pending`, so a killed run's pending bucket deletes wait until the refusal clears. Acceptable.
12. `lifecycle.py:631-638`: the forced end sets `failed`/`ended_at` directly and skips `end_task`'s message closing. Open questions to and from a forced task stay open. Harmless while every task in the request has ended.
13. Tests, task 1.5: "two concurrent runs across several batches" is covered only for `events prune` (`tests/integration/test_event_prune.py:184`). The gc test only holds the lock directly (`tests/integration/test_gc.py:284`), and no test runs two deletes at once.
14. Tests, task 3.3: `tests/integration/test_removal_kills.py` kills by raising inside the process, so `finally` blocks and rollbacks still run. It has no forced-delete case and no join between the killed run and the rerun, which is why Major 1 isn't caught.

Files: `/home/geo/develop/praxismesh/orchestrator/lifecycle.py`, `/home/geo/develop/praxismesh/common/persistence/removal.py`, `/home/geo/develop/praxismesh/common/persistence/repositories.py`, `/home/geo/develop/praxismesh/common/persistence/refs.py`, `/home/geo/develop/praxismesh/tests/integration/test_removal_kills.py`, `/home/geo/develop/praxismesh/tests/integration/test_request_delete.py`

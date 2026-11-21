## Scope review: phase 02 (GC and delete-by-request), diff 9a81933..8012f6b

I found 1 Major and 13 Nits. All files are under /home/geo/develop/praxismesh. I read the code only; I ran no tests.

### Major

**M1. A `put` that commits its transaction before a removal marks the blob, and uploads after the bucket delete, leaves an object nothing will ever remove.** (R6, R10, D6, D10)

- **Where:**
  - `common/persistence/repositories.py:692-736` (`RecordingBlobStore.put`)
  - `common/persistence/removal.py:383-402` (`_bucket_step`)
  - `common/persistence/refs.py:268-295` (`orphaned`) and `removal.py:365-374` (`pending`)
- **Why the lock is not enough:** `put` holds the `blob_objects` row lock and `TASK_LOCK` only for its transaction (step 2). The inner upload (step 3, line 736) runs after that commit with no lock held. notes.md#revive covers two orders:
  - the `put` commits before the bucket step, which then sees the mark cleared;
  - the bucket delete comes first, and the `put`'s step 2 then clears the mark.

  It does not cover this order: the `put`'s step 2 commits, then the removal marks, then the bucket delete runs, then the `put`'s step 3 uploads.
- **Scenario (delete):**
  1. A `--force` delete runs while the task's Activity still runs (R25).
  2. The Activity's `put(ws, task_id=T)` commits a live upload reference (no delete mark yet) and releases its locks.
  3. The delete's first batch gets `TRY_TASK_LOCK`, marks that upload reference and the blob (no other live holder), and commits.
  4. The bucket step deletes the object, which may not exist yet, and sets `bucket_deleted_at`.
  5. The `put`'s `inner.put` runs: `head_object` misses, so the bytes are uploaded.
- **Scenario (gc):** the same happens to a stale attempt of a task that ended 8 days ago (the issue #74 case). Its upload reference is expired, so gc step 3 marks it between the `put`'s steps 2 and 3.
- **Wrong outcome:**
  - The object is in the bucket while `blob_objects` has `removed_at` and `bucket_deleted_at` set.
  - `pending()` skips it because `bucket_deleted_at` is set.
  - `orphaned()` skips it because it is marked ("no removal mark").
  - So no later `gc` removes it, and phase 03's `reconcile` will not list it.
  - For a delete, the deleted request's bytes stay in SeaweedFS for good. This breaks R10's "every blob left with no live reference" is removed.
- **Test that would expose it:** wrap the inner store's `put` so it blocks until released, after `RecordingBlobStore.put`'s transaction has committed. Start `delete_request(..., force=True)`, or `gc` on an ended task. Let it finish, then release the upload. Assert that the key is not in `inner.objects`, or that the next `gc` removes it. The existing race tests pause either before batch 2 (`test_request_delete.py:431`) or before the bucket step (`test_revive.py:85`, `test_removal_engine.py:183`). Neither pauses inside `put` between its commit and its upload.

### Nits

- **N1.** `orchestrator/lifecycle.py:620-629` with `repositories.py:167-200` (R25, D12): the fencing row is `(max turn + 1, attempt 1)`. `AttemptRepository.start` for that same (turn, attempt) passes `NO_NEWER_ATTEMPT` and upserts over the fencing row, so its later writes are accepted. It can't be reached today because the Workflow is ended or closed, so I rated it a Nit.
- **N2.** `common/persistence/refs.py:123-133` with `lifecycle.py:641-654` (R25): a `put` detects a deleted task only by a `delete:` mark on one of the task's references. If the task has no live upload reference at batch 1 (a pre-0007 task, or uploads already marked by gc), batch 1 marks nothing. A `put` that commits after step 5's `live_references` read (`lifecycle.py:695-696`) then leaves a live reference after the delete commits. It needs an unusual task, so Nit.
- **N3.** `lifecycle.py:559-571` (R24): after `TaskBusy` the request lock is released and `_delete` reads the task list again. A rerun after a kill (R15) does the same. A task that joined in that gap is included, which goes beyond "the tasks of the request when it began". It is logged as mechanics in the decision log, so Nit.
- **N4.** `lifecycle.py:644-654` (D4): the delete's first batch marks every live upload reference of every task in one transaction, with no 500 cap. A cap here would break F81's guarantee, so the bound mismatch is probably deliberate, but D4 says "at most 500 rows".
- **N5.** `removal.py:175-190`, `204-210` (D4): a dry run is one transaction. It holds the task transaction locks, `blob_objects` `FOR UPDATE` locks, `event_logs` locks and the deleted rows' locks until the end of the run, so live `put`s and fenced writes for those keys and tasks block meanwhile. At one machine's volumes this is low impact.
- **N6.** `removal.py:244-249`, `303-335` (R3): `FOR UPDATE` locks nothing for a key that has no `blob_objects` row. A `put` that inserts the row and a live reference after the `NOT EXISTS` check but before the `INSERT ... DO NOTHING` gets marked removed: the `UPDATE` checks only `removed_at IS NULL`, unlike `_mark_orphans`, which re-checks `last_put_at`. It needs an indexed key with no `blob_objects` row, which is rare.
- **N7.** `lifecycle.py:448-489` (R13): gc steps 3-5 call `totals.add` even when a batch commits nothing (rolled back, no tombstone). `totals.batches` can then exceed the tombstone count that `test_gc.py:142` asserts is equal. Also, deletions done by `finish_pending` are never reported in `Totals`.
- **N8.** Tests, D4: the 500-row cap is tested across several batches only for events (`test_event_prune.py:120`). Nothing tests gc row rules, reference chunks or orphans, or a delete, past 500 rows. The code is simple, so Nit.
- **N9.** `test_removal_kills.py:176-181` (R15): the final `live == 0` check filters on `request_id`, but upload references have a null `request_id`, so it never covers them.
- **N10.** `test_blob_expired.py:55-70` (R9): the CLI test marks the removal by hand instead of running `gc`. The gc-to-`BlobExpired` path is covered only through the store, by `readable()` in `test_gc.py:96`.
- **N11.** `lifecycle.py:734-735`, `755`, `763`, `771` (R11): a redaction skips any value that already starts with `[deleted `. Genuine content with that prefix is never redacted, and for `result` the whole redaction is skipped, so `artifacts` is not emptied either.
- **N12.** Tests, R7: no test checks that an `audit_log` row of any age survives `gc`. It holds trivially (no rule touches the table), but the given has no test.
- **N13.** `removal.py:337-351`, `410-419` (R8): `_mark_orphans` and `_ref` assume every bucket key is `sha256/<hex>`, since they build the checksum with `substr(key, 8)`. A non-content key in the bucket would produce a bogus row, and `BlobRef` validation may fail in the bucket step. I couldn't confirm the `BlobRef` validation.

### Checked, no finding

- The run lock (D4): taken per run without waiting, and tested concurrently across several batches.
- The request lock: held for the session and conflicts with the transaction form, which `record_task` now takes.
- Task locks only in the first batch: the `delete:` marks then persist the effect.
- Tombstones written in the batch's transaction.
- Re-mark counting through `removed_at = now()`: no double count in a real run or a dry run, because the lists are read through the dry run's connection.
- Prune range fixed in `collect`.
- `end_task` is a no-op once `ended_at` is set.
- Gc's row rules for wakes and messages.
- Row-less uploads gated by Temporal status.
- The orphan race guarded by `last_put_at <= seen`.

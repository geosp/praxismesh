Scope review of phase 01 (diff 8cc4355..dccc8ff, frozen at dccc8ff)

I found no Blockers or Majors. Each mechanism holds at the scope the plan promises:
- **Index transactions.** `record_task`, both checkpoint inserts, `publish` and `end_task` write their index rows in the holder row's transaction.
- **Upload references.** One row per task and key. The stronger class wins, a GC mark is cleared and a delete mark is kept.
- **Lock order.** `put` takes the task lock, then the `blob_objects` row, then `blob_refs`. That matches `publish` and `insert_fenced` (task lock, then their own rows, then `blob_refs`) and notes.md#revive. No path takes these locks in the opposite order.
- **Advisory key spaces.** `TASK_LOCK` uses the single-bigint key space and the request and D4 locks use the two-int space, which PostgreSQL keeps separate.
- **Questions cap.** `finish_task_body` and `TurnOutcome` apply the same 20 x 500 bound, so every runner path is covered.
- **Migration.** The remap and backfill are checked through upgrade, downgrade and upgrade again.

Everything below is a Nit: a scope mismatch I judged acceptable or could not fully verify.

**Nits**

1. `Makefile:111-112`, `:132-136`; `tests/integration/conftest.py:15-25` (R18). The payload guard only covers pytest sessions. `make restart-check` (`python -m tests.integration.restart_check`, which starts Workflows) and `make workers-check` run in the same CI stack job (`ci.yml:120,122`), and their histories are never checked. R18 says "no Workflow history of the integration suite". A test that would expose it: run the guard as a step after the whole stack job.
2. `tests/support/history_guard.py:103` (R18). After a fixed 2 s `settle`, the guard trusts whatever the visibility listing returns. A run whose visibility record lags more than 2 s is silently left out, and nothing checks the listing is complete (for example against the number of runs the suite started). Not verified; with SQL visibility the lag is usually well under a second.
3. `tests/support/history_guard.py:56-58` (R18, D9). Size is measured per `Payload`. Temporal's blob limit applies to an event's whole `Payloads` (all arguments together). Every Activity here takes one argument, so today the two are the same.
4. `tests/integration/test_history_payloads.py:25` (R18). The 20-questions test uses ASCII only, where one character is one byte. The cap is in characters: 4-byte UTF-8 text gives about 40 KB of questions plus 8 KB of summary in one `CompleteTaskInput`. That still fits under 64 KiB, so the property holds, but only the 1x case is tested. Only the `openai` profile is exercised, not DSH.
5. `tests/integration/test_task_e2e.py:75-76` (R4). The JSON `BlobRef` stored in `tasks.result` can carry `audit` for an artifact written after the change. `RecordingBlobStore.put` returns the inner S3 ref, whose class is the stronger of the object metadata and the request. The test now accepts `("artifact", "audit")`. R4's "every blob ... carries its D3 class" holds for `blob_objects` and `blob_refs` but not for the JSON. This is acceptable under D3, which says metadata is never read.
6. `common/persistence/refs.py:302-322` `rowless_uploads` (D5). It ages a rowless task's upload by the blob's `last_put_at`, which any task's upload of the same bytes resets, not by that task's own upload time. This only errs toward keeping data longer.
7. `common/persistence/refs.py:358-370` `reindex` (R8, D5). A bucket-only object gets `last_put_at = now()`. An orphan that `orphaned()` reports as 25 h old therefore restarts its 24 h window after `reconcile --reindex`, and its real age is lost. notes.md#d2 specifies this, so it is by design, but R8's "last uploaded 25 hours ago" is no longer observable after a reindex.
8. `common/persistence/repositories.py:701-732` (R1, D10). The upload reference and the cleared removal mark commit before `inner.put`. If the S3 upload then fails:
   - for an ordinary put, the result is a live reference and an unmarked `blob_objects` row with no object (dangling);
   - for a blob whose bucket step already ran, `bucket_deleted_at` is also cleared, so a later read reports "not found" rather than R9's "expired".
   Reconcile lists the dangling reference, and an Activity retry heals it.
9. `common/events/table.py` prune (unchanged here; D2, D11). The existing `TableTransport.prune` and `agentctl events prune` still delete `agent_events` rows without marking their `blob_refs`. Until phase 02 lands, a pruned event's attachment keeps a live reference with no holder row. Planned for phase 02, but it is a gap in phase 01.
10. `tests/integration/test_audit_log.py:24-35`, `test_index_writers.py`, `test_upload_refs.py:31-76` (cross-phase R17 and the drill). These tests run against the stack's own `praxismesh` database and leave:
    - `audit_log` rows the app role cannot delete;
    - `blob_refs` rows naming blobs that are not in the bucket (fake refs, and a `MemoryBlobStore` inner store);
    - row-less upload references.

    The phase 03 drill runs after `make smoke` in the same CI job, and its reconcile will report these as dangling or never-ended unless it filters them out.
11. `tests/integration/test_migration_0007.py:57-67` (R2). The seed has only a `succeeded` ended task. The `ended_at` backfill for `failed` and `needs_input` (`ENDED` in migration 0007) is never exercised, although R2 says "every ended task".
12. Migration 0007's `audit_log_append_only` trigger (R14) is `FOR EACH ROW`. An `UPDATE` or `DELETE` that matches no rows succeeds instead of being refused (for example `DELETE FROM audit_log` on an empty table). No data can be lost this way.
13. `tests/integration/test_dsh_activity.py:130`, `test_harness_activity.py:167` and others (R4, "never written"). Tests still call `put(..., retention="task")`. `current_class` maps it to `transcript`, so nothing stores `task`, but the convention is not enforced in tests.

No other mismatches found. The diff was read at dccc8ff via `git show` only; the main files are `/home/geo/develop/praxismesh/common/persistence/refs.py`, `/home/geo/develop/praxismesh/common/persistence/repositories.py`, `/home/geo/develop/praxismesh/common/persistence/messages.py`, `/home/geo/develop/praxismesh/common/persistence/migrations/versions/0007_blob_refs_and_classes.py`, `/home/geo/develop/praxismesh/tests/support/history_guard.py` and `/home/geo/develop/praxismesh/tests/integration/conftest.py`.

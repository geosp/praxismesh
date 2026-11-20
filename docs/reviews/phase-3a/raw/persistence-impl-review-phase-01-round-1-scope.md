Scope-lens review of phase 01 (diff 8cc4355f..a50c3585)

I found one Major finding and a list of Nits. Each mechanism holds at the scope phase 01 promises: the per-transaction indexing in record_task, both checkpoint inserts, publish and end_task; the per-row class remap; the per-task `ended_at`; and the per-session history guard. The problems appear when the phase 01 pieces are combined with the semantics phase 02 relies on. I only read code and ran no tests.

## Major

**M1. A blob can end up live in `blob_objects`, with only removed references and not counted as an orphan. Nothing can then ever remove it (D2, D10, D5; leads to R25 and R6 in phase 02).**

- **Location:**
  - `common/persistence/repositories.py` `RecordingBlobStore.put`: the upsert always sets `removed_at = NULL, removed_by = NULL, bucket_deleted_at = NULL`.
  - `common/persistence/refs.py` `index_keys`: on conflict, a mark whose `removed_by` starts with `delete:` is kept.
  - `common/persistence/refs.py` `orphaned()`: `SELECT DISTINCT blob_key FROM blob_refs WHERE blob_key = ANY(:k)` has no `removed_at IS NULL` filter.
- **Scenario A:**
  1. Task T's request is deleted, so its upload reference `(upload, T, '', K)` is marked `delete:op`, and so is the blob K.
  2. A still-running stale attempt of T then calls `put` of the same bytes K, with `task_id=T`.
  3. The `blob_objects` mark is cleared and the bytes are uploaded again, but the reference stays marked, as intended.
  4. K is now in the bucket, unmarked, with every `blob_refs` row removed. `orphaned()` skips it because index rows exist. `expired()` skips it because no reference is live. `rowless_uploads()` skips it for the same reason.
  5. No check in phase 01, and no step in phase 02's described GC (d6 marks only blobs touched by a batch, or orphans), ever reaches it. The bytes of a deleted request stay in the bucket indefinitely.
- **Scenario B:** the same happens with `put(..., task_id=None)` after GC has marked K. `test_upload_refs.py::test_repeat_put_clears_a_removal_and_keeps_the_stronger_class` builds almost exactly this state, except that its reference is live.
- **Second mismatch inside the same mechanism:** the "delete's mark stays" protection works per (task, blob) row, not per task. A deleted task's stale attempt that uploads new bytes (a later workspace snapshot always differs) has no conflicting row. It inserts a fresh live upload reference. R25 requires "the upload leaves no live reference". Today that reference only expires with the task's `ended_at` plus the class lifetime (7 days for `checkpoint`). The notes say "a late upload by a deleted task never makes its reference live again", but that holds only for keys it uploaded before.
- **Evidence:**
  - notes.md#d2: "*orphaned*: a bucket object ... with no `blob_refs` row"
  - notes.md#d2: "a mark set by a delete ... stays, so a late upload by a deleted task never makes its reference live again (R25)"
  - notes.md#revive step 2: clear `removed_at` unconditionally.
- **This follows the plan as written; it is a plan gap.** Possible fixes:
  - (a) Count a blob as orphaned when it has no *live* reference, aged by `last_put_at`.
  - (b) Don't clear the `blob_objects` mark when the upload reference stays delete-marked.
  - (c) Refuse or pre-mark upload references for tasks that have a delete fence row.
- **Tests that would expose it:**
  - Mark a ref and its blob `delete:`, `put` the same bytes with that `task_id`, then assert some check (`orphaned`, `expired`, or a no-live-ref sweep) reports K.
  - Insert a `delete:`-marked upload ref for T, `put` new bytes with `task_id=T`, and assert no live ref exists for T.

## Nits

- **N1.** `common/persistence/repositories.py` `RecordingBlobStore.put`: the row and the reference now commit before `inner.put`. A failed upload (S3 unavailable) leaves a `blob_objects` row and a live upload ref with no object, which reads as dangling until a retry succeeds. This matches notes.md#revive's order, so it is a Nit (D10).
- **N2.** `orchestrator/submit.py:36` and `repositories.py` `record_task`: when a user-supplied `task_id` collides with an existing task, the uploads are held by the *existing* task before `TaskAlreadyExists` is raised. The upload refs then expire with the other task's lifetime. This is harmless but mis-attributed (R1).
- **N3.** `refs.py` `index_keys`: on conflict, `created_at` is never refreshed. A re-uploaded `ephemeral` blob expires 1 day after its *first* write rather than its last (D3, "1 day after write"). Nothing writes `ephemeral` today.
- **N4.** `messages.py` `end_task`: if a retried `end_task` carries a different artifact list, the earlier artifact refs stay live under `(tasks, T, result)`. In practice the result is deterministic per Activity retry (R1).
- **N5.** `common/events/table.py` `prune`, unchanged in this phase: `agentctl events prune` deletes `agent_events` rows and leaves their `blob_refs` live, with no holder row, until phase 02 rewires it (D11). The impact is low because event attachments are unused.
- **N6.** An upload ref takes its class from `put`. A stale attempt's artifact upload, which is never named in a row, is therefore kept 90 days after the task ends, not with the checkpoint data. Issue #74 intends such blobs to go. This is consistent with "expires with its task", so it is a Nit (D2, D3).
- **N7.** `tests/integration/test_upload_refs.py::test_submit_uploads_are_held_by_their_task_before_record_task` submits one input file, while R1's scenario names "two input files". The property is not exercised for several inputs, or for two inputs with identical bytes (one upload ref) (R1).
- **N8.** R4's "an event inserted without naming a class carries transcript" is tested on `event_logs` in `test_migration_0007.py::test_new_defaults_and_checks`. It is tested on `agent_events` only indirectly, through the e2e row check (R4).
- **N9.** `tests/test_retention.py::test_repeat_put_over_task_metadata` exercises only `MemoryBlobStore`. The S3 path in `s3.py` (`current='task'`, then `stronger` gives `transcript`, then `copy_object`) is not tested, although task 1.3 asks for "a repeat `put` over `task` metadata". Pre-0007 S3 objects with `audit` metadata will also keep returning `retention_class: audit` in new `BlobRef`s. The index decides lifetimes, so this is a Nit (R4, D3).
- **N10.** `tests/integration/conftest.py` `history_payload_guard`:
  - It downgrades to a warning when Temporal is unreachable at teardown.
  - `check_since` skips runs that tests deleted.
  - It waits a fixed 2 s for visibility lag.

  Any of these lets a Workflow escape the R18 check silently (R18, D9).
- **N11.** `harness_activity/activity.py:506-512`: a turn resumed from a checkpoint written before this change replays `latest.finish["questions"]` untruncated into the Workflow result. Rollout drains Workflows first, so this is a Nit (D9).
- **N12.** `refs.py` `rowless_uploads`: ages by `blob_objects.last_put_at`, which is per blob, not per task's upload. Another task's re-put of shared bytes restarts the window for every row-less task holding them. This is conservative, so it is a Nit (D5).

Key files reviewed:
- /home/geo/develop/praxismesh/common/persistence/refs.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0007_blob_refs_and_classes.py
- /home/geo/develop/praxismesh/common/events/table.py
- /home/geo/develop/praxismesh/common/blob_store/s3.py
- /home/geo/develop/praxismesh/orchestrator/submit.py
- /home/geo/develop/praxismesh/harness_activity/tools.py
- /home/geo/develop/praxismesh/tests/integration/conftest.py
- /home/geo/develop/praxismesh/tests/integration/test_upload_refs.py
- /home/geo/develop/praxismesh/tests/integration/test_index_writers.py
- /home/geo/develop/praxismesh/tests/integration/test_refs.py
- /home/geo/develop/praxismesh/tests/integration/test_migration_0007.py
- /home/geo/develop/praxismesh/tests/test_retention.py

Scope review: phase 02 (GC and delete-by-request), diff 9a81933..dd999f3

I found no Blockers and one Major. Each mechanism holds at the scope the plan promises, with these exceptions:

- the run lock is held per run;
- task locks are held per first batch;
- the request lock is held per delete;
- the fence row covers every later turn;
- revive takes its lock per key;
- tombstones are per batch;
- `finish_pending` runs per run.

The mechanisms that interact also stay correct together:

- `put` and the bucket step;
- message `_enter` and the delete's try-lock and retry;
- `record_task` and the request lock;
- prune marking and the engine's marking;
- dry-run savepoints and `_drain`.

### Major

**M1. The delete's first batch has no 500-row cap (D4; R13 tombstone scope).**
- **Location:** `/home/geo/develop/praxismesh/orchestrator/lifecycle.py:696-714`, through `/home/geo/develop/praxismesh/common/persistence/removal.py:262-278`.
- **What happens:** the `uploads` collect returns every live upload reference of every task in the request, and nothing chunks it. One transaction then does all of the following:
  - runs `_ensure_rows` on every key;
  - takes `FOR UPDATE` on every key;
  - marks them all;
  - writes one tombstone.
- **Contract:** D4 says "Removals commit in batches of at most 500 rows". Step 5 of the same delete does chunk (`_chunks(held)`, line 763), so only the first batch escapes the cap.
- **Failure scenario:** a request of 10 tasks, each with 100 turns. The openai and DSH runners `put` a workspace snapshot and a session archive per turn, so that is about 2,000 upload references.
  - Wrong outcome: the first batch marks about 2,000 references and up to about 2,000 blobs in one transaction, and its tombstone reports `references` well above 500.
  - Side effect: it holds about 2,000 `blob_objects` row locks plus every task lock for the whole statement. Any live task re-putting a shared blob blocks behind it.
- **Why it can be split:** since F125, `delete_mark` also treats the `deleted` attempt row as the delete mark (`/home/geo/develop/praxismesh/common/persistence/refs.py:150-154`). So the guarantee that a later `put` revives nothing already comes from the fence row in the first batch. Marking the upload references there is not needed for that, and they could be chunked into later batches.
- **Test that would expose it:** a delete of a request with more than 500 upload references, asserting every `request.delete` tombstone has `references <= 500`.
- **Related test gap:** the 500 bound is tested only for events (`/home/geo/develop/praxismesh/tests/integration/test_event_prune.py:93`). No test pushes more than 500 checkpoints, content rows, redactions or references through `gc` or `delete`. So the multi-batch paths of `_drain`/`row_batch` (closure `chosen`, `ctid ... LIMIT`) and `_chunks` are never exercised at the scope D4 promises.

### Nits

- **N1.** `/home/geo/develop/praxismesh/orchestrator/lifecycle.py:310-330` (`row_batch` for checkpoints), D4: the batch is capped at 500 checkpoint rows, but each row holds up to two references, so up to 1,000 references and blobs are marked per batch. Whether D4's "500 rows" covers `blob_refs`/`blob_objects` marks is ambiguous, so I report it rather than judge it.
- **N2.** Upload inside the `put` transaction, R8/D6, a combination of two mechanisms.
  - The mechanisms: `RecordingBlobStore.put` now uploads inside its transaction (`/home/geo/develop/praxismesh/common/persistence/repositories.py:739-742`, F124). `refs.orphaned` skips every row with `removed_at` set, whatever its `bucket_deleted_at` (`/home/geo/develop/praxismesh/common/persistence/refs.py:278-283`). `pending()` skips rows whose `bucket_deleted_at` is set (`/home/geo/develop/praxismesh/common/persistence/removal.py:369-373`).
  - Scenario: a blob is removed and its bucket step is done. A later `put` uploads the bytes, then its commit fails (for example, the connection drops).
  - Wrong outcome: the object sits in the bucket marked, with `bucket_deleted_at` set. It is neither an orphan nor pending, so no `gc` ever removes it.
  - Test: fail the commit after `inner.put`, run `gc` past the window, and assert the object is gone.
- **N3.** `/home/geo/develop/praxismesh/common/persistence/removal.py:194-209`, D4/D6: a dry run holds, for its whole duration:
  - its `FOR UPDATE` locks on `blob_objects`, `tasks` and `event_logs`;
  - its transaction-level `TRY_TASK_LOCK`s.

  A real run holds them per batch. So `gc --dry-run` blocks live `put`s of any key it would mark until it ends, and `request delete --dry-run` blocks a forced task's still-running attempt (`put`, session items, tool writes). "Changes nothing" holds; "harmless to run" does not.
- **N4.** `/home/geo/develop/praxismesh/common/persistence/refs.py:154` and `/home/geo/develop/praxismesh/common/persistence/repositories.py:710-731`, R13: a deleted task's late `put` writes references, and for a new key a `blob_objects` row, already marked. The marker is either the delete's operation ID or a synthetic `delete:<task_id>` that no tombstone carries. These marks are never counted in any tombstone, so a "tombstone sums equal marks by operation" check (as `check_consistent` in `test_removal_kills.py` does) would fail after an R25 late upload. Arguably these are not "removals", hence Nit.
- **N5.** `/home/geo/develop/praxismesh/orchestrator/lifecycle.py:615-627` with `/home/geo/develop/praxismesh/common/persistence/repositories.py:739-742`, D12 retry together with F124: `put` holds `TASK_LOCK` for its whole S3 upload. A `--force` delete while an Activity uploads a workspace that takes more than 9.8 s (the sum of `DELETE_RETRY_S`) always ends `RemovalBusy`. This is correct, but the busy window now scales with upload size, not just message writes as the decision log describes.
- **N6.** `/home/geo/develop/praxismesh/harness_activity/session_store.py:60-63`: `FencedSQLAlchemySession.add_items` holds one pooled connection (the task lock) while the SDK takes a second one from the same engine (default pool 5+10, `/home/geo/develop/praxismesh/common/persistence/repositories.py:36`). With enough concurrent `add_items` calls on one worker, the pool runs out and they time out. Unlikely at the current `concurrency_per_pod`, so Nit.
- **N7.** `/home/geo/develop/praxismesh/common/persistence/removal.py:411-425`, D3: `_ensure_rows` gives a referenced key that has no `blob_objects` row a placeholder (`bytes` 0, class `ephemeral`, `application/octet-stream`). If the blob stays live, the placeholder persists, and a later `put` upsert does not correct `bytes` or `content_type`. Nothing reads lifetimes from it today, hence Nit.
- **N8.** `/home/geo/develop/praxismesh/tests/integration/test_event_prune.py:107`, task 1.4: the verify step is "a GC killed after a prune batch leaves the prune and its tombstone both committed or both absent". The test drives a hand-built `event_batch` through the engine, not a `gc` run that is killed. The property is tested one level below its promised scope.
- **N9.** `/home/geo/develop/praxismesh/common/persistence/removal.py:77-89` (`session_lock` with `wait=True` for the request lock): `pg_advisory_lock` has no timeout. A transaction stuck holding the request lock makes `request delete` hang rather than report busy. Minor, because transaction-level holders are short.

### Checked and found consistent

- R3: shared blobs are kept by `_mark_free_blobs`' NOT EXISTS over all holders.
- R7/D5: row-less uploads ask Temporal per task. Wakes for running recipients are kept.
- R8: an orphan's `seen` time compared with `last_put_at`, together with `_ensure_rows`, keeps an orphan that is re-uploaded after the listing.
- R15: resume by its own task list (`unfinished_delete`) and `finish_pending`.
- R21: refusal happens before any change.
- R22: revive under the row lock.
- R24: `record_task` takes the request lock; batches select by the fixed list.
- R25: the `deleted` row in `NO_NEWER_ATTEMPT` covers every turn; session and tool writes go through `refuse_if_deleted`.
- D4: the run lock across batches is tested in `test_gc.py:397`.

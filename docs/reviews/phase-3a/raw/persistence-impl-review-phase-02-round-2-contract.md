Review of phase 02 (GC and delete-by-request), diff 9a81933..dd999f3, against the contract

Verdict: the engine, GC, delete, revive and fencing paths keep nearly every promise, and most promises have a test that would fail without them. Two Major findings: `request delete` silently skips unindexed references (R10), and the Temporal status mapping that R7, R21 and D5 depend on has no test. The rest are Nits.

## Promise map (enforcing code / test that would fail)

All code citations are at dd999f3.

- **R3** (shared blob kept): `removal.py:756-770` (`_mark_free_blobs`, NOT EXISTS live ref, under the row locks from :692-702). Tests: `test_removal_engine.py:55` and `test_request_delete.py:223`.
- **R6** (expired removed, including the #74 late upload): `lifecycle.py:414-493` (row rules, events, `refs.expired`). Test: `test_gc.py:89`.
- **R7** (nothing removed before expiry):
  - running task, 6-day-old task and audit rows: `test_gc.py:89`;
  - queued row-less task: `lifecycle.py:482` and `test_gc.py:246`;
  - undelivered wake row: `test_gc.py:189`.
- **R8** (orphan safety window): `lifecycle.py:496-511` and `removal.py:772-792`. Tests: `test_gc.py:231` and `:302`.
- **R9** (removed blob reads as expired): `repositories.py:744-765` and `cli.py:135`. Tests: `test_blob_expired.py:43` and `:57`.
- **R10** (delete removes the request's blobs): `lifecycle.py:699-772`. Test: `test_request_delete.py:85`. Gap: see Major 1.
- **R11** (content redacted): `lifecycle.py:786-857`. Tests: `test_request_delete.py:85` and `:528`. Gap: `failure_reason` (Nit).
- **R12** (refuse an unended task): `lifecycle.py:657-661`. Test: `test_request_delete.py:184`.
- **R13** (tombstone in the batch's transaction): `removal.py:708-715` (same transaction). Tests: `test_request_delete.py:85`, `test_gc.py:152`, `test_removal_kills.py`.
- **R15** (safe rerun): `removal.py:675-680`, `lifecycle.py:547-568` and :643-651. Tests: `test_removal_kills.py:154` and `:189`; `test_request_delete.py:580`.
- **R21** (`--force` for closed Workflows): `lifecycle.py:662-668` and :686-693. Tests: `test_request_delete.py:201` and `:618`, through FakeTemporal only (Major 2).
- **R22** (re-upload revives): `repositories.py:697-742`. Tests: `test_revive.py:68`, `:86`, `:112`, `:127`, `:150`.
- **R24** (joining task untouched): `repositories.py:887-889` (`record_task` takes the request lock) and the fixed list at `lifecycle.py:655`. Test: `test_request_delete.py:266`.
- **R25** (no writes after delete):
  - fencing row: `lifecycle.py:675-694`;
  - fence condition: `fence.py:292-310`;
  - upload path: `refs.py` `delete_mark`;
  - session items: `session_store.py:981-994`;
  - sample MCP orders: `sample_mcp/server.py:1022`;
  - tests: `test_request_delete.py:234`, `:395`, `:433`, `:459`.
- **D4** (one run lock, fail at once): `removal.py:520-529`. Tests: `test_gc.py:275` and `:397`; `test_event_prune.py:157`.
- **D6** (rows first, then bucket): `removal.py:812-831`. Tests: `test_removal_engine.py:114`, `:144`, `:167`.
- **D11** (events only through prune): `table.py:179-218` and `lifecycle.py:98-154`. Tests: `test_event_prune.py`. grep finds no other `DELETE FROM agent_events`.
- **D12**: as R24 and R25; the task locks are taken without waiting and retried (`lifecycle.py:615-627`). Test: `test_request_delete.py:334`.

## Major

**M1 · R10 (and D4's index rule): `request delete` never checks for unindexed references, so it silently leaves their blobs live.**
- Location: `orchestrator/lifecycle.py:630-783`. Only `gc` checks, at `lifecycle.py:405-411`.
- Scenario:
  1. A worker started before migration 0007, or before `reconcile --reindex` (the Rollout section says this can happen), writes `tasks.input_refs` or a checkpoint `workspace_ref` with no `blob_refs` row.
  2. `agentctl request delete REQ` deletes the checkpoint rows and marks every indexed reference.
  3. The unindexed key has no reference to mark, so `_mark_free_blobs` never sees it. The blob keeps `removed_at` NULL and stays readable through `RecordingBlobStore`.
  4. For `tasks.*` refs it is worse: `reconcile --reindex` later indexes it as a live `transcript` reference.
- Wrong outcome: R10 says "none of its artifacts, checkpoints or inputs can be read", yet a deleted request's input stays readable.
- Evidence: R10 says "must remove every reference its tasks hold". `test_request_delete.py:433` already builds this state (it deletes the task's `blob_refs`) but only checks the late upload, never `task.instructions`.
- Exposing test: in that test, assert `await expired(store, task.instructions)` after the delete; it fails. Fix: refuse when `refs.unindexed` finds references for the task list, or index them first.

**M2 · Observability, R7, R21, D5: the Temporal status mapping that decides "queued: keep" and "running: refuse" is never tested.**
- Location: `orchestrator/cli.py:281-291` (`workflow_status`). Every gc and delete test injects `FakeTemporal` (`tests/support/lifecycle.py:205-215`).
- `test_cli.py:202-251` monkeypatches `gc` and `delete_request` and never calls `workflow_status`. `grep workflow_status tests/` finds nothing.
- Scenario: suppose the mapping is wrong. For example, a queued (not yet picked up) Workflow's status, or a namespace error that comes back as NOT_FOUND, maps to `missing`.
  - `gc` then expires a queued task's inputs (breaks R7: "a submitted task whose Workflow has waited 30 hours ... inputs are kept").
  - `--force` then deletes a live task (breaks R21: "still running ... refuses").
  - No test fails.
- Setup that would observe it: an integration test against the Compose Temporal. Start a Workflow on a task queue with no worker and assert `running`; terminate one and assert `closed`; use an unknown ID and assert `missing`. Or at least a unit test with a fake client raising `RPCError(NOT_FOUND)` and another status code.

## Nits

- `lifecycle.py:615-627, 644-651` · R24/D12: on `TaskBusy` the delete releases the request lock, sleeps, and re-reads `request_id = :r`, so a task that joined during the sleep enters the list. Today an unended joiner makes the delete refuse rather than changing the joiner, but D12 says the lock is held "for its whole run". The decision log records the retry.
- `lifecycle.py:843-847` · R24: on a resumed rerun, a joiner that joined after the killed run can have message rows to or from the deleted tasks; the redaction (`sender_task = :t OR recipient_task = :t`) rewrites the joiner's rows.
- `lifecycle.py:663` · R21: `missing` counts as ended, while R21 says "when Temporal reports its Workflow closed". The plan's decision log calls this "no requirement changed". A wrong `TEMPORAL_NAMESPACE` could make every task `missing`; the runbook warns about it, nothing in code does.
- `lifecycle.py:822-823` · R11: the `failure_reason` redaction has no test; every test task ends `succeeded` (`test_request_delete.py:61-82`).
- `tests/support/lifecycle.py:110-130` · task 3.1: `session_ids` finds `agent_sessions` and `agent_messages` only through `checkpoints.session_id`. A session written under another ID would not be seen, so the assumption is only partly checked.
- `repositories.py:541` (`settle`) and `AttemptRepository.finish(fenced=False)` · R25: after a delete, an attempt can still update its `usage_ledger` and `task_attempts` rows. These are audit rows with no content, but R25 says "no attempt ... may write a row".
- `lifecycle.py:686-693` · D12: a forced end sets `failed` and `ended_at` but skips `end_task`'s message closing (cancel open asks, wake askers). A joiner waiting on a deleted task's reply is not woken.
- `test_removal_kills.py:70-95` · R13/R15: the "kill" is an in-process exception, so the `finally` unlock (`removal.py:513-517`) always runs. Release of the session lock when a process really dies is never observed; a subprocess SIGKILL test would.
- All removal tests (`test_gc`, `test_request_delete`, `test_revive`, `test_removal_*`) · D10/R22: the bucket is `MemoryBlobStore`. D10's "a removed object is simply missing, so the upload goes through" is never run on SeaweedFS (`s3.py:96-108`). Partly covered by `tests/support/blob_contract.py`.
- `lifecycle.py:498` and `refs.rowless_uploads` · R8/D5: the DB's `last_put_at` (DB `now()`) is compared with the CLI host's `datetime.now(UTC)`, so clock skew shifts the 24-hour window.
- `removal.py:567-569` vs `:683-690`: the `Collect` comment says "before any lock", but task locks are taken first (correctly, per F81). The comment is wrong.
- `lifecycle.py:675-693` · D4: the first delete batch inserts one fencing row per task with no 500-row cap.
- `removal.py:839-853` · D3: placeholder `blob_objects` rows created for live referenced keys get class `ephemeral` and `bytes` 0 and keep them.
- `removal.py:780-781, 843` · R10: a reference to a non-content key is never marked or removed (F119 choice), so it stays readable after a delete.
- `docs/architecture/overview.md` (Tests bullet) says `test_blob_expired.py` runs "on the stack database". It uses `scratch_database` (`test_blob_expired.py:28-32`).
- `docs/operations/runbook.md` ("the delete stops having changed nothing"): every try first runs `finish_pending` (`lifecycle.py:670`), which deletes objects left by earlier runs.

## Reuse and placement

All Nits. If the two copies drift, the engine and its counterpart disagree.

- `removal.py:856-865` `_ref` duplicates `make_ref` (`common/blob_store/base.py:86`), including the `blob:` ID format.
- `removal.py:839-853` `_ensure_rows` duplicates the placeholder `blob_objects` insert in `refs.reindex` (`refs.py:391-400`): checksum taken from the key, with a different class rule.
- `lifecycle.py:116-139` (`event_batch.collect`) repeats `TableTransport._prune`'s range arithmetic and its event-reference query (`common/events/table.py:166-186`). If they drift, the engine locks and counts a different range from the one pruned.
- `removal.py:538-545` `RefKey` re-declares the key fields of `refs.Reference` and `refs.Holder` (`refs.py:236`, `:113`), with a converter at `lifecycle.py:360-366`.
- `fence.py:300` `DELETED` repeats the `outcome = 'deleted'` clause inside `NO_NEWER_ATTEMPT` (`fence.py:292-295`).
- `refs.py:93` adds `is_content_key`, but `refs.reindex` (`refs.py:391`) still calls `_CONTENT_KEY.match` directly.
- The empty-batch test is written four times: `removal.py:653`, `:666`; `lifecycle.py:593`, `:209` (the last checks only `rows`).
- Placement: `workflow_status` sits in `orchestrator/cli.py:281` while its type is in `orchestrator/lifecycle.py:217`, and `cli.status` (`cli.py:156-160`) does its own `describe`. Phase 03's reconcile will need the same mapping. Similarly, the `Bucket` protocol (`lifecycle.py:222-225`) could sit next to `BucketObject` in `common/blob_store/base.py`.
- Test fixtures: three near-identical "task with checkpoint and artifact" builders (`test_gc.py:49-70`, `test_request_delete.py:61-82`, `test_removal_kills.py:46-63`) despite the shared `tests/support/lifecycle.py`. `set_last_put` (`test_gc.py:73-77`) is copied inline in `test_revive.py:133-137`. The `pausing_run` monkeypatch appears twice in `test_request_delete.py` (:274-285, :371-381).
- Good reuse: `REQUEST_LOCK` moved into `fence.py` and is shared by messages, `record_task` and delete. `tail` uses `workflow_status`. `checkpoint_holder_sql` is shared by `REFERENCES` and `row_batch`. Row-rule classes come from `TABLE_CLASS`, with a unit test.

Files: /home/geo/develop/praxismesh/common/persistence/removal.py, /home/geo/develop/praxismesh/orchestrator/lifecycle.py, /home/geo/develop/praxismesh/orchestrator/cli.py, /home/geo/develop/praxismesh/common/persistence/repositories.py, /home/geo/develop/praxismesh/common/persistence/fence.py, /home/geo/develop/praxismesh/common/persistence/refs.py, /home/geo/develop/praxismesh/common/events/table.py, /home/geo/develop/praxismesh/harness_activity/session_store.py, /home/geo/develop/praxismesh/tests/support/lifecycle.py, /home/geo/develop/praxismesh/tests/integration/test_request_delete.py, /home/geo/develop/praxismesh/tests/integration/test_gc.py, /home/geo/develop/praxismesh/tests/integration/test_removal_kills.py

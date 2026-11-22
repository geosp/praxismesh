## Contract review: Phase 3A persistence plan, phase 03 (R16, R17, R23), diff 9920f36..d4e32c4

Phase 03 keeps its promises, but there is one real defect. Backup can write an empty bucket copy that looks complete. One Verify item is also not observed end to end. The rest are Nits.

### Promise map (enforcing code and the test that would fail without it)
- **R16 (restore reproduces the stack).** Enforced by `infra/restore.sh:44-84` and `orchestrator/backup.py` (`backup`, `load_blobs`). Shown by `infra/drill.sh` step 5 (`task status`, `task output`, the `praxis_comms` login) and `tests/integration/test_backup.py::test_a_backup_has_three_dumps_every_object_and_a_manifest`.
- **R17 (reconcile).** Enforced by `orchestrator/reconcile.py:84-106`, which reuses `refs.dangling`, `refs.orphaned`, `refs.unindexed` and `refs.reindex`, and by `cli.reconcile_command`, which exits 1 when anything is listed. Shown by `tests/integration/test_reconcile.py` (each case seeded; the snapshot asserts read-only), `tests/test_cli.py::test_reconcile_exits_1_when_anything_is_listed` and drill step 6.
- **R23 (restore refuses a stack with data).** Enforced by `backup.py:214` `check_empty`, `backup.py:239` `workflow_count`, the mark check at `restore.sh:42-47`, and the refusals placed before any state change. Shown by `tests/integration/test_restore_refusals.py` and drill step 3.
- **D4 (lock held for the whole backup).** Enforced at `backup.py:171`, which wraps the dumps and the bucket copy. Shown by `test_backup.py`: `gc` gets `RemovalBusy` in `after_dumps`, and the second test checks the lock is released.
- **D8 order (app database, then Temporal databases, then the bucket; workers stopped during the dumps and restarted in `finally`).** Enforced at `backup.py:172-193`. Shown by the `compose.calls` order assertion and `test_the_workers_start_again_when_a_dump_fails`.
- **Restore steps.**
  - Databases dropped and recreated: `restore.sh:61-64`, through `databases.sh`.
  - `roles.sh` rerun: lines 64 and 72.
  - Temporal started: line 76.
  - Reconcile run without failing the restore: lines 83-84.
  - The killed-restore mark survives the database drops because it is a comment on the `postgres` role.
  - Shown by drill steps 4-5.
- **`init.sh` goes through `databases.sh`.** Enforced at `infra/db/init.sh:24` and the Compose mount. Shown by the drill's `make reset` and `make up`.
- **Reuse is good in two places.** `workflow_status`, `StatusOf` and `Bucket` were moved, not copied: `orchestrator/workflow_status.py` and `common/blob_store/base.py:136`, with the duplicates removed from `cli.py` and `lifecycle.py`. Backup reuses `run_lock` and `APP_TABLES`.

### Findings

**Major 1. A failed bucket check writes a "complete" backup with no objects (R16, D8).**
- **Where:** `orchestrator/backup.py:126-129`:
  ```python
  try:
      store.client.head_bucket(Bucket=store.bucket)
  except ClientError:
      return objects  # not created yet ...
  ```
- **Failure scenario:**
  1. `head_bucket` raises any `ClientError`: a 403 from a rotated or wrong `S3_SECRET_KEY` in the CLI's env file, or a transient 5xx from SeaweedFS.
  2. Backup treats this as "bucket not created", copies nothing and writes `manifest.json` with `"objects": []`. The backup looks complete and the exit status is 0.
  3. The operator runs `make reset` and then `make restore`.
  4. The restore succeeds, but every reference is dangling. The stack's blobs are gone; the only sign is reconcile's report, which restore treats as information.
- **Inconsistent with existing code:** `common/blob_store/s3.py:172-180` (`list_objects`) was changed in this same diff to treat only `NoSuchBucket` as empty and to raise everything else. `_copy_bucket` lists the bucket a second time with its own, broader rule instead of reusing that.
- **Fix:** treat only 404 / `NoSuchBucket` / `NotFound` as empty, or build the copy from `await store.list_objects()`. Optionally, cross-check the object count against the `blob_objects` rows that are not removed.
- **Test that would expose it:** a `test_backup.py` case whose store's `head_bucket` raises a 403 `ClientError`, expecting `BackupFailed` and no manifest.

**Major 2. The R23 case "a Workflow and no task" is never run through restore (R23, task 2.2 Verify).**
- **Where:** `backup.py:278`, `await check_empty(engine, store, await workflow_count())`.
- **What the tests cover:** `test_a_workflow_without_a_task_row_is_refused` (`test_restore_refusals.py`) passes `workflows=1` as a literal. `test_workflow_count_asks_the_app_namespace` tests the count on its own. Drill step 3 refuses a stack that has a task row, a Workflow and objects all at once, so it cannot show which check fired.
- **Failure scenario:** a stack with one Workflow in the app namespace, no `tasks` row and an empty bucket. If the wiring at `backup.py:278` passed 0, or `count_workflows` counted another namespace, `make restore` would drop the Temporal databases holding that Workflow, and no test would fail.
- **The Verify line asks for exactly this case:** "restore into a stack with a task, or a Workflow and no task, changes nothing".
- **Setup that would observe it:** run `python -m orchestrator.backup check-empty` (or `restore.sh`) against the stack's real Temporal with a started, workerless Workflow, a scratch database with no tasks and an empty bucket. Assert exit 2 and the Workflow still there.
- **Severity:** the wiring is one line, so you may judge this a Nit. I rated it Major because a stated Verify item is not observed.

### Nits
- **`infra/restore.sh:42-58`, R23:** the refusal check and the worker stop are not atomic. A worker that is running, or a `task submit` that lands between `check-empty` and line 58, writes data that the drop then destroys. "Changes nothing" holds only if nothing else is writing.
- **`tests/integration/test_restore_refusals.py` (`test_a_task_row_is_refused`):** `assert stored.task_id` is a tautology. It does not check that nothing changed. `check_empty` is read-only by inspection only.
- **`check_empty` (`backup.py:214`), R23:** the only database check is the `tasks` row count. A stack with `blob_objects`, `agent_events` or `audit_log` rows but no task row is accepted and then dropped. This matches notes.md#d8 ("`tasks` is missing or empty"), but R23 says the "application database ... holds data".
- **`orchestrator/reconcile.py:104`, R17 / task 1.1:** reconcile lists `missing` Workflows as never ended, as well as `closed` ones. The task says "whose Workflow Temporal reports closed". The behaviour is documented in the runbook and overview, so this is a scope mismatch, not a bug.
- **`orchestrator/reconcile.py:84-99`, R17:** a read-only reconcile does not take the D4 lock. Suppose a `gc` or delete commits its mark after reconcile's snapshot and deletes the object before reconcile lists the bucket. Reconcile then reports a false dangling reference and exits 1. No test covers this.
- **`infra/drill.sh:132`, task 2.3:** the task says "reconcile lists one dangling reference". The drill asserts two (the `tasks/.../input_refs` holder and the `upload/...` holder). The test is right; the task's wording is loose.
- **`infra/drill.sh:105`, R16:** the comms check is a raw SQLAlchemy login as `praxis_comms` reading `tasks`, not `comms_mcp` itself connecting. It is a weaker check than the task text ("`comms_mcp` works").
- **`orchestrator/backup.py:170`, task 2.1:** `target.mkdir` runs before `run_lock`. A backup refused with `RemovalBusy` leaves an empty directory, and retrying with the same `--to` then fails on `exist_ok=False`.
- **`orchestrator/backup.py:172-193`, D8 / task 2.1 observability:** the worker stop and start are simulated in `test_backup.py`. The drill only checks that the workers run after the backup, never that they were stopped during the dumps. Temporal's server also keeps running between the `temporal` and `temporal_visibility` dumps, and timers and timeouts can advance a history there.
- **`infra/restore.sh:64`, D8:** `--no-extensions` departs from D8's "recreates them with init.sh's database statements". The extensions come from the dump instead. This is documented in the overview; I noted it only because it differs from the plan text.
- **Restore checks no migration version (runbook "Use ... this checkout's migrations"):** `restore.sh` never compares the manifest's `migration` head with the checkout's head. An older backup restored under newer code runs workers against an old schema.
- **Duplicated worker-service lists:** `backup.py:50` and `restore.sh:25` (plus `drill.sh:23` and `infra/demo/phase-3a-lifecycle.sh:33`). If a later plan adds a writing service to Compose and only one list is updated, backup no longer stops it during the dumps (D8). The lists could be derived from the Compose profiles (`docker compose --profile workers --profile dsh config --services`).
- **Duplicated database lists:** `backup.py:48`, `restore.sh:24` and `infra/db/databases.sh:154-156`. If they drift, a database is dumped but never recreated, or the reverse.
- **Duplicated bucket fixtures:** `tests/integration/test_backup.py` (`bucket`) and `test_restore_refusals.py` (`bucket`) repeat `test_blob_store_s3.py:18-27` (`store`), and `test_removal_kills.py:220-258` repeats it inline. `tests/support/stack.py` has no shared S3 bucket fixture to reuse. A shared one there would keep the cleanup and the `NoSuchBucket` handling consistent.
- **Duplicated `compose()` shell helper:** it is defined in `infra/restore.sh:29`, `infra/drill.sh:26` and `infra/demo/phase-3a-lifecycle.sh:36`, next to the Makefile's `COMPOSE` and `DockerCompose.run` (`backup.py:63`). If the project or env-file rule changes in one copy, the scripts act on different stacks.
- **No unit test for `backup_command`:** `tests/test_cli.py` covers `reconcile` but not the `backup` command's wiring (`--to`, JSON output). The drill exercises it only end to end.

### Files reviewed
- /home/geo/develop/praxismesh/orchestrator/backup.py
- /home/geo/develop/praxismesh/orchestrator/reconcile.py
- /home/geo/develop/praxismesh/orchestrator/workflow_status.py
- /home/geo/develop/praxismesh/orchestrator/cli.py
- /home/geo/develop/praxismesh/infra/restore.sh
- /home/geo/develop/praxismesh/infra/drill.sh
- /home/geo/develop/praxismesh/infra/db/databases.sh
- /home/geo/develop/praxismesh/infra/db/init.sh
- /home/geo/develop/praxismesh/common/blob_store/s3.py
- /home/geo/develop/praxismesh/common/blob_store/base.py
- /home/geo/develop/praxismesh/tests/integration/test_backup.py
- /home/geo/develop/praxismesh/tests/integration/test_restore_refusals.py
- /home/geo/develop/praxismesh/tests/integration/test_reconcile.py
- /home/geo/develop/praxismesh/tests/integration/test_removal_kills.py
- /home/geo/develop/praxismesh/tests/test_cli.py

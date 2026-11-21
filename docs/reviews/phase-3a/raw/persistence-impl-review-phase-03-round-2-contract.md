## Contract review: Phase 3A persistence plan, phase 03 (diff 9920f36..72bf8d6)

I found no Blockers, two Majors and a list of Nits. Every test the phase file's verification table cites for R16, R17 and R23 exists. All three requirements and D4, D8 have enforcing code and tests. The drill (`make drill`, run in CI) is where R16 and the real worker stop and start can be observed.

### Promises and where they are enforced

- **R16: restore reproduces a backup.**
  - Code: `/home/geo/develop/praxismesh/orchestrator/backup.py:181-243` (backup) and `/home/geo/develop/praxismesh/infra/restore.sh` steps 1-4.
  - Tests: `/home/geo/develop/praxismesh/tests/integration/test_backup.py` (real pg_dump and bucket copy; the worker stop and start are simulated), `/home/geo/develop/praxismesh/tests/test_backup_check.py`, and `/home/geo/develop/praxismesh/infra/drill.sh` step 5 (the real round trip, in CI).
- **R17: reconcile lists what is inconsistent and changes nothing.**
  - Code: `/home/geo/develop/praxismesh/orchestrator/reconcile.py:72-104`.
  - Tests: `/home/geo/develop/praxismesh/tests/integration/test_reconcile.py`. It covers every case, uses snapshot checks for read-only, and checks the lock behaviour of `--reindex`. Drill step 6 covers one missing object listed under both holders.
- **R23: restore refuses a stack with data and changes nothing.**
  - Code: `check_empty` at `orchestrator/backup.py:285-320` runs before any write in `restore.sh`. The unfinished-restore mark is checked first.
  - Tests: `/home/geo/develop/praxismesh/tests/integration/test_restore_refusals.py` (real Temporal and SeaweedFS) and drill step 3.
- **D4 (the run lock is held by every removal command and by backup):**
  - Code: `backup.py:192` (`async with run_lock`); `--reindex` takes it at `reconcile.py:82`.
  - Tests: `test_backup.py` (a gc started during the backup fails on the lock; a backup refused on the lock creates nothing) and `test_reconcile.py::test_reindex_waits_for_no_one_and_fails_on_the_run_lock`.
- **D8:**
  - Promise: the workers stop during the dumps, the application database is dumped first, and they start again even on failure. Code: `backup.py:203-221`. Test: `test_backup.py` checks the call order.
  - Promise: the database statements moved out of `init.sh` into a script both use. Code: `/home/geo/develop/praxismesh/infra/db/databases.sh` and `infra/db/init.sh:26`. `make up` inside the drill exercises it.
  - Promise: `roles.sh` reruns, the dumps load, and reconcile's report is printed without failing restore. Code: `restore.sh` steps 3-4 and the final block.
  - Promise: a partial failure means `make reset`, then restore again. Code: the mark on the `postgres` role. Test: drill step 4 kills a restore with SIGKILL.
  - `backups/` was already git-ignored (`.gitignore:40`).

### Majors

**M1 · `agentctl reconcile` exits 1, the "findings" code, when Temporal or the database is unreachable (R17, task 1.1; contradicts the runbook and overview).**
- **Location:** `/home/geo/develop/praxismesh/orchestrator/cli.py:355-367`.
- **What happens:** `reconcile_command` calls `connect()` (`cli.py:66-73`, `Client.connect`) and `make_engine()` with no translation. A Temporal server that is down fails inside `Client.connect` with a temporalio `RuntimeError` ("Failed client connect"). A database that is down raises asyncpg or SQLAlchemy errors. None of these is a `PraxisError`, so `main` (`cli.py:457-461`) does not catch them. Python prints a traceback and exits 1.
- **Failure scenario:** with Temporal stopped, `./agentctl reconcile` exits 1, which task 1.1 defines as "anything is listed". The runbook says the opposite at `/home/geo/develop/praxismesh/docs/operations/runbook.md:304-305`: "2 with an `error:` line when it cannot finish (Temporal unreachable, for example)". The overview's Reconcile row makes the same claim.
- **Why the fix does not cover it:** F186's fix covers only `describe()` errors (`/home/geo/develop/praxismesh/orchestrator/workflow_status.py:29-35`). `restore.sh` only avoids the problem by grepping for `"clean": false`. Anything else that reads the exit status, such as a later CronJob or an operator script, will read an outage as findings.
- **Test that would expose it:** in `tests/test_cli.py`, make `connect` raise `RuntimeError("Failed client connect")` and assert that `cli.main(["reconcile"]) == 2`. Today it propagates or exits 1.

**M2 · A backup of a bucket that does not exist succeeds with zero objects, even when rows name blobs (R16, D8).**
- **Location:** `/home/geo/develop/praxismesh/common/blob_store/s3.py:175-177` (`NoSuchBucket` now returns `{}`), used by `_list_bucket` at `orchestrator/backup.py:152-157`.
- **Failure scenario:** the stack has finished tasks, so `blob_objects` has rows. `S3_BUCKET` in the env file the CLI reads names a bucket that does not exist, for example a mistyped or mismatched `ENV_FILE`. `agentctl backup` dumps the databases, lists `{}`, copies nothing, writes a valid `manifest.json` and exits 0. `check-backup` accepts it. Restore then loads rows whose every blob is missing, which reconcile reports as dangling only after the stack has been reset.
- **Why the fix does not cover it:** F165 fixed only listings that are refused, not a missing bucket.
- **Suggested fix:** `backup` already reads `rows["blob_objects"]` at `backup.py:212`. Fail when that count is above 0 and the listing is empty because the bucket is missing.
- **Test that would expose it:** in `test_backup.py`, record a task, then point the store at an absent bucket (`scratch_bucket(..., create=False)`) and expect `BackupFailed`.

### Nits

- `/home/geo/develop/praxismesh/orchestrator/reconcile.py:80-100`: it takes no run lock, so a gc or delete committing between its snapshot and its bucket listing makes it list a reference as dangling that is not (R17). This is documented at `runbook.md:305-307`, so it is accepted, but it is still a wrong output with exit 1.
- `orchestrator/cli.py:420-425`: D4 lists `reconcile` among the commands that "print their plan with `--dry-run`", but `reconcile --reindex` has no dry run. The default run is read-only, so this is arguably satisfied.
- `orchestrator/backup.py:274-276`: a manifest without `databases` or `objects` raises `KeyError`, a traceback, instead of `RestoreRefused`. Restore still refuses (`|| exit 1`), but without a clear message.
- `infra/restore.sh` (the `pg_restore ... <"$backup/$db.dump"` loop): it loads fixed file names, while `check_backup` (`backup.py:275`) checks the manifest's `file` field. The two can drift if the file name ever changes.
- `orchestrator/backup.py:219-221`: if `compose start` fails inside the `finally`, its `BackupFailed` replaces the dump error that caused it, so the operator sees only "start failed".
- `orchestrator/backup.py:187`: the test-only hook `after_dumps` is part of the production `backup()` signature.
- `orchestrator/backup.py:121-127`: keys `a` and `a/b` collide as file and directory. The resulting `OSError` is not a `BackupFailed`. Content keys cannot collide, but non-content ("unrecognised") keys can.
- `/home/geo/develop/praxismesh/docs/operations/runbook.md:335`: "start them with `make workers-up`" after a killed backup starts every worker (DSH pairs too, on `VLLM_BASE_URL`, with a rebuild), not just the ones the backup stopped. That list is in the manifest only if the backup finished, so `compose start <workers>` is the precise advice.
- `orchestrator/backup.py:315-338` (`workflow_count`): R23's Workflow check counts through visibility, which is eventually consistent. A Workflow started moments before could be missed. Not verified on SQL visibility.
- `infra/drill.sh:91-104`: R16 and task 2.2 say "`comms_mcp` connects as `praxis_comms`". The drill opens a raw SQLAlchemy connection with `PRAXIS_COMMS_DB_URL`, not through `comms_mcp`. That proves the role and its grants, not the server.
- `orchestrator/workflow_status.py:29-35`: this changes `gc` and `request delete` too, since non-NOT_FOUND Temporal errors now exit 2. Only `reconcile`'s path is tested (`tests/test_cli.py`). The decision log records the change for all three commands.
- `/home/geo/develop/praxismesh/tests/integration/test_backup.py:38-60`: the worker stop and start are simulated by `RecordingCompose`. The real "workers run again" is observed only by drill step 2. This is acknowledged in the module docstring.

### Reuse and placement (all Nits)

- **Worker list in five places:** `orchestrator/backup.py:56` `WORKERS`, `infra/restore.sh:28`, `Makefile:142-143` (`WORKERS` plus `DSH_WORKERS`), `infra/drill.sh:23` and `infra/demo/phase-3a-lifecycle.sh:33`. Only backup.py and restore.sh cross-reference each other (F181); the Makefile lists are not mentioned. If a new writing service is added to the Compose file and the Makefile only, backup keeps it running during the dumps, and its rows get ahead of or behind Temporal (D8).
- **The `compose()` shell wrapper is copied three times:** `infra/restore.sh:32`, `infra/drill.sh:26` and `infra/demo/phase-3a-lifecycle.sh:36`. It parallels `Makefile:25` `COMPOSE`, the Python `DockerCompose` (`backup.py:73-110`) and `tests/support/status.py:15-27`. A change to the flags (for example a second `-f` file) must be made in every copy.
- **The same JSON one-liner under two names:** `json()` at `infra/drill.sh:31` and `field()` at `infra/demo/phase-3a-lifecycle.sh:38` (and in `infra/demo/phase-2-messaging.sh`).
- **Counting rows over `APP_TABLES` twice in one module:** `backup.py:174-176` (`_rows`) and `backup.py:294-299` (`check_empty`). The second also tolerates missing tables, the first does not.
- **Two path guards:** `_safe_path` at `backup.py:121-127` duplicates the relative-path guard `_relative_path` at `/home/geo/develop/praxismesh/common/schemas/task.py:18-22`, with slightly different rules (`.` parts).
- **Good reuse:** `Bucket` moved into `common/blob_store/base.py`, `WorkflowStatus` and `StatusOf` moved into `orchestrator/workflow_status.py` (both taken out of `lifecycle.py`), and `scratch_bucket` was extracted into `tests/support/stack.py`, which `test_blob_store_s3.py` now uses. Other tests (`test_history_payloads.py`, `tests/support/agents.py`, `test_dsh_outcomes.py`) still use the stack's own bucket, which is correct for them.

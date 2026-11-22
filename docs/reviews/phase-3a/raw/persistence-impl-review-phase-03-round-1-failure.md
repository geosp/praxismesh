## Phase 03 implementation review, failure lens (diff 9920f36..d4e32c4)

I found two Major findings and a set of Nits. I traced the units below one step at a time. I read the code and ran nothing.

**Units traced**
- **`orchestrator/backup.py::backup`:** mkdir, then the run lock, then `ps`, `stop`, row counts, three `pg_dump`s, `start` in `finally`, the bucket copy under the lock, then `compose config --images` and the manifest, both after the lock is released.
- **`infra/restore.sh`:** reads the mark, runs check-empty, sets the mark, stops the workers and Temporal, then drops, `databases.sh`, `roles.sh`, `pg_restore` ×3, `roles.sh` again, `load-blobs`, `up temporal`, `start` workers, clears the mark, and runs reconcile with `||` so it never fails the script.
- **`orchestrator/reconcile.py::reconcile`:** with `--reindex` it reindexes under the lock in one transaction. It then reads a REPEATABLE READ snapshot and the bucket listing, then asks Temporal about each unended task.
- **`infra/drill.sh` and `infra/demo/phase-3a-lifecycle.sh`.**

**Helpers I relied on**
- `run_lock` and `session_lock` (`common/persistence/removal.py:66-101`): try-lock on a dedicated AUTOCOMMIT connection, and the unlock suppresses SQLAlchemyError.
- `S3BlobStore.list_objects` (`common/blob_store/s3.py:159-180`): returns `{}` only on `NoSuchBucket`.
- `ensure_bucket` (`s3.py:78-82`).
- The only bucket deletes are in the removal engine (`removal.py:398`) and `RecordingBlobStore.delete` (`repositories.py:768`), so the lock does cover every delete during the copy.
- The CLI catches only `PraxisError` (`orchestrator/cli.py:457-461`).

### Major

**M1 · `orchestrator/backup.py`, `backup()`: the `compose.run(["stop", *stopped])` call sits outside the `try/finally` · D8, task 2.1**
- **Scenario:** `worker-a` and `worker-b` are running. `docker compose stop orchestrator worker-a worker-b` stops two of them and then fails on the third (a daemon error or timeout). `DockerCompose.run` raises `BackupFailed`, but the `finally: compose.run(["start", ...])` is never entered, so the stopped workers stay down.
- **Contract:** task 2.1 requires that "the workers run again afterwards". The module docstring says it "starts them again even if a dump fails". The runbook says "starts them again afterwards, even when a dump fails".
- **Fix:** put the `stop` inside the `try`. Restarting all of `stopped` is harmless.
- **Test:** a `RecordingCompose` whose `stop` records the call and then raises. Assert that the last call is `start worker-a`.

**M2 · `orchestrator/backup.py`, `_copy_bucket()`: any `ClientError` from `head_bucket` is treated as "bucket not created", and the backup still writes a complete-looking manifest · R16, D8**
- **Code:** `except ClientError: return objects  # not created yet`. This catches every client error: 403 AccessDenied, 500, and 503 SlowDown while SeaweedFS is starting or overloaded.
- **Scenario:** a stack with finished tasks, and SeaweedFS answers `head_bucket` with a 503. The backup copies zero objects and writes `manifest.json` with `"objects": []`. Restore accepts the backup, because a manifest is its only completeness test. It drops and loads the databases, loads 0 objects and "succeeds", and reconcile's report is information only. Every reference is then dangling, so the recovery point is silently lost.
- **Compare:** `list_objects` in the same diff (`s3.py:175-178`) narrows this to `NoSuchBucket`. A HEAD on a missing bucket reports code `"404"`, so the check should accept `"404"` and `NoSuchBucket` and re-raise anything else.
- **Test:** wrap the store so `head_bucket` raises `ClientError({"Error": {"Code": "503"}}, "HeadBucket")`. Assert that `backup` raises and that no `manifest.json` exists.

### Nits (one line each)

- **N1:** `backup.py` `backup()`: a SIGKILL or SIGHUP during the dumps leaves the workers stopped, with no record of which ones; the next backup sees none running and never restarts them. The runbook doesn't say to run `make workers-up` after a killed backup. Nit because no data is lost and recovery is manual (D8).
- **N2:** `backup.py` `backup()`: the manifest is written with `write_text`, which isn't atomic; a kill during that write leaves a truncated `manifest.json`. `restore.sh` checks only `[ -f manifest.json ]`, so it then drops and loads the databases and fails at `load-blobs` on the JSON parse, leaving its mark. Fix with write-to-temp plus rename, and parse the manifest in restore's step 1 (D8).
- **N3:** `infra/restore.sh` step 1: it checks neither the manifest's `format`, its `migration` head nor the dump sizes against `manifest.databases.*.bytes`. A truncated dump is found only after the drop, by `pg_restore --exit-on-error` (D8).
- **N4:** `infra/restore.sh` steps 1-2: the mark check, check-empty and `COMMENT ON ROLE` are not atomic. Two concurrent `make restore` runs both pass and then drop and load over each other. Nit because it needs an operator to run two restores at once (R23).
- **N5:** `infra/restore.sh` steps 1-2: a `task submit` that lands between `check-empty` and the drop is destroyed without notice. Nit because it needs an operator acting during a restore (R23).
- **N6:** `backup.py` `backup()`: `compose config --images` runs after the lock is released and before the manifest. If it fails, a backup whose dumps and copy are complete has no manifest. Nit, since the failure is unlikely and only makes the backup unusable (D8).
- **N7:** `backup.py` `backup()`: `target.mkdir(exist_ok=False)` runs before the lock. A run refused with `RemovalBusy` leaves an empty `backups/<time>/`. A second backup in the same second, or `--to` an existing directory, raises `FileExistsError`, which isn't a `PraxisError`, so the user gets a traceback (D4, D8).
- **N8:** `backup.py`: partial backups (no manifest) are never cleaned up, and every dump and blob file is written with the default umask (typically 0644). Clear-text data is left world-readable, against the runbook's "keep them where only operators can read them". This is outside the failure lens but is a mismatch (D8, threat model).
- **N9:** `backup.py` `_copy_bucket()`: a `get_object` failure raises `ClientError`, which `cli.py:459` doesn't catch, so the user gets a traceback instead of an `error:` line. It is correctly left without a manifest (D8).
- **N10:** `common/persistence/removal.py:77-89`, used by `backup`: if the lock connection drops mid-backup (for example, `db` restarts), the advisory lock is released silently. A `gc` could then delete a blob the dump names before `_copy_bucket` reads it. Nit because it needs a database restart during a backup (D4, D8).
- **N11:** `backup.py` `backup()`: during the dumps, only the workers stop. The Temporal server keeps running, and a host-side `agentctl task submit` is not blocked, so a submit can still start a Workflow between the `praxismesh` and `temporal` dumps. That contradicts the plan's claim (D8) that "no Workflow gets ahead of its rows"; the plan defers the full comparison to Phase 9.
- **N12:** `orchestrator/reconcile.py`, `reconcile()` without `--reindex`: it doesn't take the run lock. During a concurrent gc, a snapshot taken before the gc's batch commit plus a listing taken after its bucket delete reports a false dangling reference and exits 1. It is read-only, so the false reports are transient (R17, D4).
- **N13:** `reconcile.py` / `restore.sh`: an `RPCError` other than NOT_FOUND from `workflow_status` crashes reconcile with a traceback and exit 1, the same status as "findings". `restore.sh`'s `|| echo "...listed the findings above"` then reports a crash as findings (R17, D8).
- **N14:** `reconcile.py`: an unended task whose Workflow is "missing" includes a submit still in flight (task row committed, Workflow not yet started), which is reported as never ended (R17).
- **N15:** `orchestrator/backup.py` `check_empty`: it refuses only on `tasks` rows. Message, event or `audit_log` rows with no task rows would be dropped without notice. This matches notes.md#d8 ("tasks is missing or empty") but is narrower than R23's "application database ... holds data".
- **N16:** `tests/integration/test_restore_refusals.py`: the "a Workflow and no task" case is tested with a synthetic `workflows=1` passed to `check_empty`, and `workflow_count` is tested separately. Nothing runs `restore.sh` end to end against a real Workflow with no task row, as task 2.2's Verify implies (R23).
- **N17:** `infra/drill.sh`: step 2 checks only that the workers run after the backup, not that they were stopped during the dumps. `test_backup.py` fakes `ps`, `stop` and `start`, so no test shows real workers being stopped (D8, task 2.1).
- **N18:** `infra/drill.sh`: no step restores into a stack with workers running, so `restore.sh`'s "start the workers that were running" path is never exercised (D8).

### Files
- `/home/geo/develop/praxismesh/orchestrator/backup.py`
- `/home/geo/develop/praxismesh/infra/restore.sh`
- `/home/geo/develop/praxismesh/orchestrator/reconcile.py`
- `/home/geo/develop/praxismesh/infra/drill.sh`
- `/home/geo/develop/praxismesh/common/persistence/removal.py`
- `/home/geo/develop/praxismesh/common/blob_store/s3.py`
- `/home/geo/develop/praxismesh/tests/integration/test_backup.py`
- `/home/geo/develop/praxismesh/tests/integration/test_restore_refusals.py`

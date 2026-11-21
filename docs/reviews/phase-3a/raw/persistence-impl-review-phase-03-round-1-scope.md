I reviewed phase 03 (R16, R17, R23; D4, D8) with the scope lens, over the diff 9920f36..d4e32c4. I found one Major and a set of Nits. No Blockers: the lock, refusal and mark mechanisms hold at the scope D8 and notes.md#d8 promise.

## What holds

- **Backup holds the D4 lock for the whole run** (`orchestrator/backup.py:171`). The lock covers stopping the workers, counting rows, the three dumps, restarting the workers and the bucket copy. The workers restart in a `finally`, and the manifest is written last.
- **Restore's checks come before any change.** The unfinished-restore mark and `check-empty` both run first. The mark is a comment on role `postgres` (`infra/restore.sh:42-52`), so it survives the database drops, and `make reset` clears it. The drill checks this after a SIGKILL (`infra/drill.sh` step 4).
- **`reconcile --reindex` takes the lock; a plain `reconcile` does not** (`orchestrator/reconcile.py:84-86`). Both are tested (`test_reconcile.py::test_reindex_waits_for_no_one_and_fails_on_the_run_lock`). Running `--reindex` twice is also tested.
- **The bucket copy pages through the listing** (`list_objects_v2` paginator) and runs after the application dump, as notes.md#d8 orders.

## Findings

**Major: demo step 4 cannot fail on R22.**
- **Where:** `infra/demo/phase-3a-lifecycle.sh` step 4.
- **Contract:** task 3.2 ("a resubmit that revives the input"). The verification table cites "the demo, step 4" for R22.
- **Scenario:** suppose the `gc` after request C removes C's revived input. The script would still print "gc kept C's input" and pass.
- **Evidence:**
  - The check is `grep -qF "$(cat c-input.key)" gc-after-c.tombstones`.
  - The tombstones never contain a blob key. `AuditRepository.append` (`common/persistence/audit.py:36-37`) says `details` "holds counts, reasons and IDs, never removed content".
  - The subjects are `task:<id>`, `orphans` and similar (`orchestrator/lifecycle.py:459-501`).
  - Nothing later in the demo reads C's input. Step 5 reads only C's artifact.
  - `docs/demos/phase-3a-lifecycle.md:33` records "none of its tombstones names that blob" as the pass condition.
- **Fix / test that would expose it:** have step 4 check C's input directly, for example `blob_objects.removed_at IS NULL` for that key, or a read of the input through `RecordingBlobStore`. Or assert the gc's batch and blob counts are 0. Then run the demo with the revive in `put` disabled; it should fail.

**Nits** (one line each: location, what, why it is only a Nit)

- `orchestrator/reconcile.py:87-93` (R17, D4): a plain reconcile takes its snapshot, then lists the bucket, without the run lock. A gc batch that commits and deletes objects in between makes reconcile report false dangling references and exit 1. Nit because D4 only requires the lock for removal commands and backup; a cheap fix is to hold `run_lock` for the report too, or retry once on dangling.
- `orchestrator/backup.py:171-178` (D8): only the worker containers are stopped. A host `agentctl task submit` can write upload rows and start a Workflow between the `praxismesh` and `temporal` dumps, so a Workflow gets ahead of its rows. Nit because D8 promises only to stop the workers; no test covers a concurrent CLI write.
- `orchestrator/backup.py:171-178` (D8): the Temporal server keeps running during the dumps, so timers and timeouts can still change state. The temporal and temporal_visibility dumps are separate snapshots and can disagree on whether a Workflow is closed. Nit because reconcile lists the resulting never-ended tasks, and notes.md#d8 defers a full Workflow comparison to Phase 9.
- `orchestrator/backup.py:172-174`: `compose stop` runs before the `try`. If it fails partway (some workers stopped), the `finally` never runs and those workers stay stopped. Nit because stop failures are rare.
- `orchestrator/backup.py:169`: the target directory is created before the lock is taken. A backup refused on the lock (`RemovalBusy`) leaves an empty `backups/<time>/`. A retry with the same `--to`, or two backups in the same second, raises an uncaught `FileExistsError` rather than a `PraxisError`. Nit because restore refuses a directory with no manifest.
- `orchestrator/backup.py:125-128`: `_copy_bucket` treats any `ClientError` from `head_bucket` as "no bucket" and writes a backup with zero objects. That includes an access-denied error or a wrong bucket name. `S3BlobStore.list_objects` (`common/blob_store/s3.py:175-178`) only accepts `NoSuchBucket`, so the two helpers disagree. Nit because there is a single set of credentials today.
- `orchestrator/backup.py:118-122`: if the bucket ever holds both key `a` and key `a/b`, the file-versus-directory clash makes the backup fail. Nit because every current key is `sha256/<hex>`.
- `orchestrator/backup.py:213-220` (R23): the application database counts as holding data only when `tasks` has rows. A stack with only uploads, events or messages and an empty bucket would be overwritten. Nit because this matches notes.md#d8 step 1, but R23 says "application database ... holds data".
- `orchestrator/backup.py:234-241` (R23): `count_workflows` reads Temporal's visibility store, which lags. A Workflow started just before `make restore` may not be counted. Nit because the window is small.
- `infra/restore.sh:48-57` (R23): `check-empty` runs while workers and Temporal are still up, and nothing locks between it and the stop. A concurrent submit can land after the check. Nit because the operator is expected to run restore on an idle stack.
- `tests/integration/test_restore_refusals.py:72-76` (R23, task 2.2): the Workflow-without-a-task-row case passes `workflows=1` directly. The real count is tested separately (`test_workflow_count_asks_the_app_namespace`). At the `make restore` level, "refused and changes nothing" is only exercised in drill step 3, with a task row. `test_a_task_row_is_refused` checks nothing for "unchanged" (`assert stored.task_id`). Nit because the script runs `check-empty` before any change.
- `infra/drill.sh` step 4: `kill -KILL -- -$pid` kills the `docker compose exec` client. The `pg_restore` inside the db container usually keeps running. So "a restore killed mid-load" really means "the restore script died mid-load". Nit because the mark-based refusal and the reset-then-restore path still get tested.
- `infra/restore.sh` and `orchestrator/backup.py:250-266` (R16): restore never compares the manifest's `migration` head with the code's Alembic head. Nit because no case in the plan needs it yet.
- `orchestrator/reconcile.py` and `common/persistence/refs.py:312-316` (R17): `orphaned` skips objects whose row is marked removed. So reconcile never lists a "returned" object (row removed and bucket-deleted, object present), which gc does handle (`refs.returned`). Such an object appears after a restore if a revive happened between the dump and the bucket copy. Nit because gc cleans it up and R17 lists only four categories.
- `common/persistence/refs.py:313` (R17): an orphan with no `blob_objects` row takes its age from the bucket's LastModified. After `load-blobs` re-puts every object, that is the restore time, so ages restart at 0 after a restore. Nit because it errs on the safe side for D5.
- `infra/drill.sh` step 5 (R16): "comms_mcp connects" is checked by connecting as `praxis_comms` and reading `tasks`, not by starting `comms_mcp`. Nit because the role check is what R16's Given/Then names.
- Phase file verification table, R13 row: "A gc killed after its first batch" cites the new SIGKILL test, but that test kills a `request delete`, not a gc. Nit because the in-process `[after]` gc test covers the gc case.

Relevant files:
- /home/geo/develop/praxismesh/orchestrator/backup.py
- /home/geo/develop/praxismesh/orchestrator/reconcile.py
- /home/geo/develop/praxismesh/infra/restore.sh
- /home/geo/develop/praxismesh/infra/drill.sh
- /home/geo/develop/praxismesh/infra/demo/phase-3a-lifecycle.sh
- /home/geo/develop/praxismesh/docs/demos/phase-3a-lifecycle.md
- /home/geo/develop/praxismesh/tests/integration/test_backup.py
- /home/geo/develop/praxismesh/tests/integration/test_restore_refusals.py
- /home/geo/develop/praxismesh/tests/integration/test_reconcile.py
- /home/geo/develop/praxismesh/common/persistence/refs.py
- /home/geo/develop/praxismesh/common/persistence/audit.py

Failure-lens review of phase 03 (diff 9920f36..72bf8d6), repository /home/geo/develop/praxismesh

I traced these units in order, with every await and side effect:
- `orchestrator/backup.py::backup`
- `restore.sh` together with `check-backup`, `check-empty` and `load-blobs`
- `orchestrator/reconcile.py::reconcile`
- `infra/drill.sh`
- the demo script

I read these helpers rather than assuming their behaviour:
- `session_lock` / `run_lock`: one AUTOCOMMIT connection, `pg_try_advisory_lock`, unlock in `finally` with errors suppressed (`common/persistence/removal.py:66-101`). A connection lost on process death releases the lock.
- `S3BlobStore.list_objects`: NoSuchBucket now returns `{}` (`common/blob_store/s3.py:159-180`).
- `ensure_bucket` (`s3.py:78-82`).
- `workflow_status`: NOT_FOUND gives `missing`, any other RPC error raises `WorkflowStatusUnavailable` (`orchestrator/workflow_status.py:25-36`).
- Blob deletes happen only in the removal engine under the lock (`common/persistence/removal.py:398`, `repositories.py:769`). So workers restarted before the bucket copy can only add orphans, as notes.md#d8 accepts.

What holds up: a lock refusal creates no directory. The manifest is written last and atomically. A dump or stop failure restarts the workers through `finally`. Ctrl-C also restarts them, because the cancellation reaches the `try` at the next await. The restore mark is set before anything is stopped or dropped, and a killed restore is refused on the next run. `--reindex` runs in one transaction under the lock and rolls back if killed.

## Major

**M1. SIGTERM or SIGKILL during the dumps leaves the workers stopped for good, and the next backup does not notice.** `orchestrator/backup.py:202-221`; task 2.1 ("the workers run again afterwards"), D8.
- **Scenario:** `make backup` runs under a timeout (cron, `timeout`, a CI step limit) and is sent SIGTERM while `pg_dump temporal` runs (`backup.py:213-217`).
  - The CLI installs no SIGTERM handler (grep finds none in `orchestrator/`), so Python exits without running the `finally` at :219-221.
  - The containers were stopped with `docker compose stop`, so Docker treats them as explicitly stopped and `restart: unless-stopped` (`infra/docker-compose.yml:172` and the other workers) never brings them back.
  - The stop is not recorded anywhere. The next `make backup` sees no running workers (`running_workers`, :116-118), stops nothing, restarts nothing and records `"workers_stopped": []`.
- **Outcome:** the platform runs with no workers until someone runs `workers-up`. The directory left behind has no manifest, so restore correctly refuses it.
- **Test that would expose it:** start `python -m orchestrator.cli backup` as a subprocess, using a `RecordingCompose`-style fake whose `exec` blocks. Send SIGTERM. Assert that `start worker-a` was recorded, or that the next backup restarts the workers. Possible fixes: a SIGTERM/SIGHUP handler that cancels the main task, or recording the stopped set (for example in the target directory) and restarting from it on the next run.

**M2. A worker that is restarting when the backup starts is not stopped, and can run Activities between the dumps.** `orchestrator/backup.py:116-118`, `:202-206`; D8 ("Stop the worker services ... so no Activity changes rows or Workflows between the dumps").
- **Scenario:** with the `dsh` profile, `worker-dsh-a` crash-loops until its launcher is ready (`docker-compose.yml:186-189`: "until the launcher is up it exits and is restarted"). `ps --status running` leaves out containers in the `restarting` state, so `stopped` does not include `worker-dsh-a`. Partway through `pg_dump praxismesh` it comes up healthy, picks up an Activity, writes rows and advances its Workflow.
- **Outcome:** `temporal.dump` holds a Workflow that is ahead of the rows in `praxismesh.dump`, which D8 says cannot happen.
- **Same pattern in restore:** `infra/restore.sh:53-60` also filters on `--status running`. This is less harmful there because Temporal is stopped.
- **Test that would expose it:** a `RecordingCompose` whose `ps` reports `worker-a` as restarting. Assert that `stop` still names it. Fix: stop every service in `WORKERS` unconditionally (stopping a stopped service does nothing), and restart those that were running or restarting.

## Nits
- `infra/restore.sh:44-52`, R23: nothing stops two restores from overlapping. The time between `check-empty` (:49) and the mark (:52) is a check-then-act gap: two restores can both pass, and a `task submit` made in that gap is dropped at :64. No lock or atomic mark-or-refuse is taken. This is acceptable only as operator error.
- `infra/restore.sh:78-83`: the mark is cleared only after `compose up --wait temporal` and `compose start` succeed. A Temporal start timeout after a complete load leaves the mark, and the next run tells the operator to `make reset` a fully restored stack. Clearing it right after `load-blobs` would separate "partial load" from "services did not start".
- `infra/restore.sh:18-19`, D8: the mark only blocks restore. `make up` or `workers-up` will run Temporal and the workers against a half-loaded database, and nothing warns. The plan asks only that the rerun refuses, so this is a Nit.
- `infra/drill.sh:70-71`, `:83`: the comment says the kill "takes whole" the restore. Killing the `docker compose exec` client does not kill the `pg_restore` inside the `db` container, which keeps loading until `make reset` stops it. The drill still passes, but the "killed mid-load" state is less dead than described.
- `common/blob_store/s3.py:175-177` with `backup.py:152-158`, R16: since NoSuchBucket now reads as empty, a backup of a stack whose bucket is missing (lost SeaweedFS volume, wrong `S3_BUCKET`) succeeds with 0 objects while rows hold live references. The `_list_bucket` docstring says only a not-yet-created bucket is empty. A cross-check against live `blob_refs` would catch it; this is unverified whether it can happen in practice.
- `orchestrator/reconcile.py:229-239`, R17: plain reconcile takes no lock. If a gc batch commits and deletes its object after the REPEATABLE READ snapshot but before `list_objects`, the result is a false "dangling" entry. It is transient and read-only.
- `orchestrator/reconcile.py:240-247`, R17: unended candidates come from the snapshot, but Temporal is asked afterwards. A task that ends (`end_task`, then the Workflow closes) in between is reported as `never_ended` closed. This is a false positive while workers run, for example right after a restore restarts them (`restore.sh:88`).
- `orchestrator/backup.py:316-322`, R23: `count_workflows` reads Temporal visibility, which can lag. A Workflow started moments before `check-empty` may not be counted yet. Unverified for this visibility store.
- `orchestrator/backup.py:274-277`: a manifest missing `databases[db]`, `file`, `bytes` or `objects` raises KeyError, which surfaces as a traceback rather than `RestoreRefused`. Restore still aborts (`restore.sh:38`), so this is cosmetic.
- `orchestrator/backup.py:278-282`: the integrity check compares sizes only. Blob keys are content hashes (`sha256/<hex>`), so a same-size corruption would pass even though it could be detected.
- `orchestrator/backup.py:236` against `check_backup`: the manifest records `images`, but restore never compares them. A backup restored on a checkout with a different Temporal image loads a `temporal.dump` from another schema version. This is outside the failure lens; recorded so it isn't lost.
- `orchestrator/backup.py:207`: `rows` comes from a separate connection, not pg_dump's snapshot. Host-side `task submit` or `comms` writes are not stopped by stopping the workers, so the manifest's counts can differ from the dump. The counts are informational only.
- `orchestrator/backup.py:219-221`: if `compose start` fails in the `finally`, its `BackupFailed` replaces the original dump error. The original survives only as `__context__`.

Files: /home/geo/develop/praxismesh/orchestrator/backup.py, /home/geo/develop/praxismesh/infra/restore.sh, /home/geo/develop/praxismesh/orchestrator/reconcile.py, /home/geo/develop/praxismesh/infra/drill.sh, /home/geo/develop/praxismesh/common/blob_store/s3.py, /home/geo/develop/praxismesh/common/persistence/removal.py, /home/geo/develop/praxismesh/infra/docker-compose.yml

<!-- Verbatim verifier report (Phase 3A persistence plan, phase 03 gate verification, as-built follow-up, code 4d269be, docs 1b91b61); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-follow-up.md per docs/reviews/README.md rule 1. -->

# Phase 3A persistence phase 03: targeted follow-up verification (rule 6)

Code: 4d269bef0ec2e251515750eed0fe31a1befdc4ec (checkout /tmp/tmp.fhWZ1mSXeS/verify-3a-03).
Docs: 1b91b617ab80247b6d9f2f3bdd34023ba47924b5 (`git show`). Stack: Compose project pmverify3a
(db, s3, temporal, temporal-ui; no workers). I ran no tests, built no images and changed nothing.
`C` below means `docker compose -p pmverify3a --env-file infra/.env -f infra/docker-compose.yml`.

Result: 9 statements confirmed, 0 contradicted, 0 unverifiable. One low-severity wording point under 5.

## docs/architecture/overview.md (lines 332-333)

1. **"Integration, each on a scratch database with an in-memory bucket: ..." (8 files): confirmed.**
   Each file uses `scratch_database("head")` and `MemoryBlobStore()`: test_removal_engine.py:19,31,56;
   test_revive.py:21,29,69; test_event_prune.py:29,41,64; test_gc.py:4,38,47,91;
   test_request_delete.py:5,50,57,86; test_removal_kills.py:5,34,46,161; test_blob_expired.py:21,31,44;
   test_reconcile.py:4-5,24,31,46. test_task_e2e.py and test_dsh_outcomes.py are present in
   tests/integration/.
2. **"Against the stack: `test_backup.py` (real dumps and bucket copy; the worker stop and start
   simulated), `test_restore_refusals.py` (a scratch database, a SeaweedFS bucket of its own and the
   real Temporal), ..." : confirmed.** test_backup.py:6-10 and the `RecordingCompose` class
   (lines 43-71) record `stop` and `start` and send `exec` (the pg_dump) and everything else to the
   real `DockerCompose`. The bucket is `scratch_bucket("backup")` (line 83), which is SeaweedFS
   (tests/support/stack.py:41-56). test_restore_refusals.py:22-23,30,36 uses `scratch_database`,
   `scratch_bucket` and `temporal_client` (stack.py:59-66, a real `Client.connect`). The SIGKILL test
   is test_removal_kills.py:215-241 (`scratch_bucket`, `-signal.SIGKILL`).

## docs/operations/runbook.md, "Backup and restore" (lines 326-350)

3. **"Backup holds the removal lock from its first step to the end of the bucket copy (the manifest
   is written after it releases the lock) ...": confirmed.** orchestrator/backup.py:234 runs
   `async with run_lock(engine):` around the mkdir, the image list, the worker stop, the dumps, the
   start and `_copy_bucket` (line 288). The manifest is built and written at lines 289-301, after
   that block ends.
4. **"... an Activity that was running is retried by Temporal on a worker that runs again, as
   `make recovery-check` shows for a worker killed mid-Activity ...": confirmed, with a low-severity
   wording point.** Makefile:160-161 runs tests/integration/test_recovery.py. That test SIGKILLs the
   worker holding the attempt (lines 118-119) and asserts attempts `[(1, "lost"), (2, "done")]`
   (line 131). It runs the retry on a *different* worker that is still running
   (`... != lost`, line 132), not on a stopped worker that is started again, as happens in a backup.
   It shows the retry mechanism, but not that exact case. Severity: low (the claim is an analogy,
   and the doc says the check shows it "for a worker killed mid-Activity", which is accurate).
   Not run here: no workers, and running tests is out of scope.
5. **"Use the same pinned images as the backup (`images` in `manifest.json` lists the default
   services' images; the worker images are built from the checkout ...)": confirmed.** backup.py:243
   `compose.run(["config", "--images"])`, saved as `"images": sorted(set(images))` (line 299).
   Probe `C config --images` printed only the pinned digests of temporalio/server,
   temporalio/admin-tools, temporalio/ui, paradedb/paradedb:0.26.6-pg16@sha256:c0f2... and
   chrislusf/seaweedfs:4.53@sha256:ccad..., with no `praxismesh-worker:dev` or `praxismesh-dsh:dev`.
   The workers sit behind profiles (docker-compose.yml:135,175,205,239,256), and
   `C config --services` listed only db, s3, temporal-schema, temporal, temporal-namespace and
   temporal-ui.

## docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/notes.md, section d8

6. **"4. Write `manifest.json`: times, row counts, every object with its size and metadata,
   migration head, the database files and sizes, the workers stopped and the default services'
   images." : confirmed.** backup.py:289-300 writes the keys `started_at`/`finished_at`, `rows`,
   `objects` (each with `key`, `bytes`, `content_type`, `metadata`; lines 176-183), `migration`,
   `databases` (`file`, `bytes`), `workers_stopped` and `images`. For the images, see probe 5.
7. **"Restore runs it with `--no-extensions`: the dumps create the extensions themselves." :
   confirmed.** infra/restore.sh:70 runs `praxismesh-databases --no-extensions`. databases.sh:36-39
   exits before `CREATE EXTENSION` (line 43). Probe 1: `docker inspect` on pmverify3a-db-1 shows
   `infra/db/databases.sh -> /usr/local/bin/praxismesh-databases`. Probe 2 (read-only):
   `C exec -T -u postgres db bash -c "pg_dump -Fc -d praxismesh | pg_restore -l | grep -E 'EXTENSION|SCHEMA'"`
   printed `EXTENSION - vector`, `EXTENSION - pg_search` and `SCHEMA - paradedb postgres`.
8. **"4. Load the blobs, clear the mark, start Temporal and the workers that were running or
   restarting, and print `agentctl reconcile`'s report; ... restore does not fail on its exit
   status." : confirmed.** restore.sh runs these in order: `load-blobs` (81), `COMMENT ON ROLE
   postgres IS NULL` (84), `compose up ... temporal temporal-ui` (85), and `compose start $restart`
   (86-89), where `$restart` holds the workers listed as running or restarting (57-61). The
   reconcile exit code is caught with `|| rc=$?` (94), and the final `if` only prints a message
   (98-102), so the script exits 0.
9. **"Before step 2, restore sets a mark (a comment on the `postgres` role). A failure between the
   mark and the end of the load leaves it, so the next restore refuses ...; `make reset` clears the
   stack and the mark" : confirmed.** restore.sh:54 sets the mark before the stop at line 64. With
   `set -euo pipefail` (22), any failure before line 84 exits with the mark still set. Lines 46-50
   refuse with "an earlier restore did not finish". The mark lives in the pgdata volume, and
   Makefile:100 `make reset` runs `down --volumes`. Probe:
   `C exec -T -u postgres db psql -X -tA -d postgres -c "SELECT coalesce(shobj_description(oid,'pg_authid'),'<null>') FROM pg_roles WHERE rolname='postgres'"`
   printed `<null>` (no mark on this stack). Roles praxis_comms, praxismesh and temporal exist.

## Aside (outside the listed statements, for information only)

The opening line of notes.md d8 says backup "holds the D4 lock on its own connection for the whole
run". In the code, the manifest is written after the lock is released (backup.py:289-301). The
runbook already says this (item 3). Severity: low.

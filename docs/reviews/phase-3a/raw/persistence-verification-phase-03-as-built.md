<!-- Verbatim verifier report (Phase 3A persistence plan, phase 03 gate verification, as-built claims, code and docs at 4d269be); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-as-built.md per docs/reviews/README.md rule 1. -->

# As-built documentation check: Phase 3A persistence, phase 03 (reconcile, backup, restore, drill)

Checkout `/tmp/tmp.fhWZ1mSXeS/verify-3a-03`, `git rev-parse HEAD` = `4d269bef0ec2e251515750eed0fe31a1befdc4ec`. The working tree was clean apart from `.verify/`. Stack: Compose project `pmverify3a` (db, s3, temporal, temporal-ui up, no workers). I built no images, changed no source, test or document, and did not touch the `praxismesh` or `pm3adev` projects. Every command ran with `.verify/env.sh` sourced, which unsets the owner's venv.

Scratch writes, all under `.verify/as-built/`: `reconcile.json`, `reconcile.err`, `restore-refused.out`, `manifest-observed.json` (the manifest of a backup I took). The backup itself, the copies I altered for the `check-backup` probes and two altered env files have been deleted.

## Verdict

The docs match the code and runtime for every phase 03 claim, apart from **four Nits and no Blocker or Major**. I found no planned or future behaviour presented as current. One claim could not be checked here: that a running Activity is retried after the backup stops the workers. No workers were running.

## Probes run (documented commands; all read-only for application data)

| # | Command | Observed (quoted) |
|---|---|---|
| P1 | `make status` | "addresses: Temporal 127.0.0.1:57233, UI http://127.0.0.1:58080, S3 http://127.0.0.1:58333, DB 127.0.0.1:55432" / "all services healthy" |
| P2 | `./agentctl reconcile` | exit 0; `"clean": true, "dangling": [], "orphaned": [], "unindexed": [], "never_ended": [], "reindexed": null` |
| P3 | `ENV_FILE=<copy with TEMPORAL_PORT=1> ./agentctl reconcile` | exit 2; "error: cannot reach Temporal: Failed client connect: ... Connection refused" |
| P4 | `ENV_FILE=<copy with DB_PORT=1> ./agentctl reconcile` | exit 2; "error: cannot reach the database: [Errno 111] Connect call failed ('127.0.0.1', 1)" |
| P5 | `./agentctl backup --to .verify/as-built/bk` (no workers running, so the stop and start were no-ops) | exit 0, `{"backup": ".verify/as-built/bk"}`; directory mode `700`; files `manifest.json`, `praxismesh.dump`, `temporal.dump`, `temporal_visibility.dump`, `workers-stopped` (0 bytes), `blobs/sha256/...` (5 objects); manifest keys `['bucket','databases','finished_at','format','images','migration','objects','rows','started_at','workers_stopped']`, `format` 1, `migration` "0007", `rows` holds all 17 APP_TABLES including `audit_log`, `blob_objects` and `blob_refs`; first object `{'key': 'sha256/23fc...', 'bytes': 50, 'content_type': 'text/markdown', 'metadata': {'retention': 'transcript'}}` |
| P6 | `make restore BACKUP=.verify/as-built/bk` into the stack that holds data | "... is a complete backup this checkout can restore", then "error: refusing to restore into a stack that holds data: the application database has rows: tasks 3, ... blob_refs 39; Temporal lists 3 Workflow(s) in the app's namespace; bucket praxismesh holds objects. Run 'make reset' and 'make up' first"; make exit 2. Afterwards the `postgres` role comment was `<null>` (no mark) and the same four services were running. |
| P7 | `python -m orchestrator.backup check-backup` on scratch copies of P5's backup (no manifest; `format` 2; `migration` 0006; `temporal.dump` truncated; one object deleted; one object grown) | each exit 2: "has no manifest.json: not a complete backup" / "the backup has format 2; this checkout reads format 1" / "the backup is at migration 0006; this checkout's migrations are at 0007: restore with a checkout whose head is 0006, then migrate" / "temporal.dump is 10 bytes; the manifest says 70246" / "sha256/fa70... is missing from ..." / "sha256/fa70... is 107 bytes; the manifest says 105" |
| P8 | A psql session holding `pg_advisory_lock(3,0)` on `praxismesh`, then `./agentctl backup --to .verify/as-built/bk2` and `./agentctl reconcile --reindex` | both exit 2: "error: another gc, request delete, events prune or backup is running; try again when it ends"; `bk2` was not created ("No such file or directory") |
| P9 | psql as `postgres` (SELECT only) | roles `postgres`, `temporal`, `praxismesh`, `praxis_comms`; databases include `praxismesh`, `temporal`, `temporal_visibility`; `praxismesh` extensions `pg_search, plpgsql, vector`, `temporal` only `plpgsql`; `alembic_version` 0007; trigger `audit_log_append_only BEFORE DELETE OR UPDATE ON public.audit_log`; `audit_log` columns `id, created_at, actor, action, subject, operation_id, details, retention_class (default 'audit')`; distinct actors `cli:geo` for `gc` and `request.delete` |
| P10 | `docker compose ... config --images`, with and without `--profile workers` | without: the five pinned infra images only. With: adds `praxismesh-worker:dev` |
| P11 | Logs from the acceptance run on this stack: `.verify/06-drill.log`, `.verify/07-demo.log` | drill steps 1 to 6 and "drill: passed", "exit=0"; "killed during: restore: loading praxismesh"; "restore: reconcile listed the findings above (information only; restore succeeded)"; "comms role praxis_comms reads the restored task"; "reconcile lists the removed input as dangling: tasks/<task>/input_refs, upload/<task>" |

## docs/architecture/overview.md, "Phase 3A persistence" (phase 03 rows and bullets)

| Claim (quoted or condensed) | Evidence | Class |
|---|---|---|
| Reconcile: `orchestrator/reconcile.py`; `agentctl reconcile` "reads one snapshot, then the bucket listing" | reconcile.py:87-95 (REPEATABLE READ, `SELECT 1`, then `list_objects`) | confirmed |
| lists dangling references, orphaned objects with their age, unindexed references, unended tasks whose Workflow is closed or missing (`orchestrator/workflow_status.py`) | reconcile.py:96-106; age_hours reconcile.py:57; workflow_status.py:143-154; P2 output keys | confirmed |
| read-only; exit 1 when it lists anything, 2 when it cannot finish (`WorkflowStatusUnavailable` for a Temporal error other than NOT_FOUND) | cli.py:359-377 (`0 if report.clean else 1`), cli.py:469-471 (PraxisError -> 2); workflow_status.py:149-153; P3, P4 exit 2 | confirmed |
| `--reindex` first runs `refs.reindex` under the run lock | reconcile.py:84-86; P8 | confirmed |
| Backup: `orchestrator/backup.py`, `make backup` | Makefile:124-125 | confirmed |
| holds the run lock, creates its directory under it (new, mode 0700) | backup.py:234-241; P5 mode 700; P8 no directory created | confirmed |
| reads the image list, writes the workers to start again (running or restarting) to `workers-stopped` | backup.py:243-246, 119-125; P5 file present | confirmed |
| stops every worker service (`docker compose stop`, project from the env file only) | backup.py:257, 59, 83-97 (check-prereqs.sh `--project-only`) | confirmed (code; with no workers running, P5 could not show a stop) |
| `pg_dump -Fc` for the three databases in the `db` container | backup.py:262-269 | confirmed, P5 |
| starts them again when the stop or a dump fails, or on SIGTERM and SIGHUP (the signal handler raises `BackupFailed`), keeping the first error | backup.py:128-145, 252-278; tests test_backup.py:133,189,246,256 | confirmed (code and tests) |
| lists the bucket through `S3BlobStore.list_objects` (only a bucket not yet created is empty, and only while no live blob is recorded) | s3.py:159-180 (NoSuchBucket -> {}); backup.py:281-287 | confirmed |
| copies every object with its content type and metadata; writes `manifest.json` last through a rename | backup.py:164-184, 196-204, 301; P5 | confirmed |
| Restore: `infra/restore.sh`, `make restore`, `infra/db/databases.sh` | Makefile:128-129 | confirmed |
| Refuses a backup that is not whole or does not fit (check-backup: manifest, format, migration head, every dump and object at its size) | backup.py:314-352; restore.sh:40; P7 | confirmed |
| refuses an unfinished restore (comment on the `postgres` role) | restore.sh:46-50, 54 | confirmed (code; P6 showed no mark after a refusal; P11 showed the refusal after a kill) |
| refuses a stack with rows in any application table, Workflows in the app namespace (`count_workflows`) or bucket objects | backup.py:355-386; P6 | confirmed |
| marks itself, stops every worker and Temporal, drops the three databases, recreates them through `databases.sh --no-extensions` and `roles.sh`, runs `pg_restore --exit-on-error`, loads the objects, clears the mark, starts Temporal and the workers that were running or restarting | restore.sh:54-89 (also stops `temporal-ui`) | confirmed; P9 shows the extensions loaded from the dump after the acceptance restore |
| prints `reconcile`, telling findings (exit 1 with a report) from a failure | restore.sh:93-102; P11 | confirmed |
| `init.sh` creates its databases through the same `databases.sh` | init.sh:26 (`bash /usr/local/bin/praxismesh-databases`); docker-compose.yml:29 mount | confirmed |
| Drill: `infra/drill.sh`, `make drill`; backup, refused restore, reset, a restore killed with SIGKILL while loading, second reset, restore, then `task status`, `task output`, the `praxis_comms` role and a removed object reported dangling | drill.sh:39-138; Makefile:133-134; P11 | confirmed |
| CI's `stack` job runs it last | ci.yml:125-127 (last `run` before the failure-log and clean-up steps) | confirmed |
| A backup whose dump fails starts the workers again and writes no manifest | backup.py:270-277 (raise before line 301); test_backup.py:133 | confirmed |
| A restore killed after it marks itself leaves the mark; the next restore refuses until `make reset` | restore.sh:54, 84; drill.sh:67-93; P11 | confirmed |
| A blob uploaded after the application dump is restored as an orphan; `gc` removes it after the safety window | backup.py:260-262 (praxismesh dumped first, bucket copied after); refs.py:289-316 (an unrecorded object is aged by its bucket `LastModified`); retention.py:28 `SAFETY_WINDOW = 24h` | confirmed (code) |
| Tests: integration "each on a scratch database with an in-memory bucket: ... `test_reconcile.py`, `test_restore_refusals.py`" | test_reconcile.py:46 uses `MemoryBlobStore`. **test_restore_refusals.py:35-38 uses `scratch_bucket(...)`, which is "an S3 store on a bucket of the test's own on the stack's SeaweedFS" (tests/support/stack.py:41-44), and lines 93 and 109 use the real `temporal_client()`** | **contradicted, Nit (N1)** |
| Against the stack: `test_backup.py` (real dumps and bucket copy; worker stop/start simulated), `test_workflow_status.py`, `test_blob_store_s3.py` | test_backup.py:43-74 (`RecordingCompose` passes `exec` to the real Compose and records `stop`/`start`); all files exist | confirmed |
| Unit: `tests/test_cli.py` (`gc`, `request delete`, `reconcile`) | test_cli.py:258, 311, 366 test reconcile; test_cli.py:286 also tests backup (left out of the list, not a contradiction) | confirmed |
| Known limits: Temporal keeps histories for `TEMPORAL_RETENTION` (72 hours) | docker-compose.yml:87, .env.example:31, P-env `TEMPORAL_RETENTION=72h` | confirmed |
| Removal and backup are manual; nothing schedules `gc` or `make backup` | no scheduler in docker-compose.yml, Makefile or workflows; the only `cron` is `links-weekly.yml` (a link check) | confirmed |
| Backups are clear text and unencrypted; recovery point is the last manual backup | backup.py:175 (raw bytes), pg_dump without encryption | confirmed |
| Reconcile lists only unended tasks whose Workflow is closed or missing | reconcile.py:99-106 | confirmed |

## docs/operations/runbook.md

### Removing data: the lock and "Checking consistency"

| Claim | Evidence | Class |
|---|---|---|
| A second run fails at once with "another gc, request delete, events prune or backup is running" | removal.py:92-101; P8 (the message continues "; try again when it ends") | confirmed |
| reconcile lists dangling (live reference, blob missing or marked removed), orphaned with age in hours, `content_key: false` for keys gc never removes, unindexed, never-ended tasks | reconcile.py:41-72; refs.py:289-316 | confirmed |
| exits 1 when it lists anything, and 2 with an `error:` line when it cannot finish (Temporal unreachable) | P3, P4 | confirmed |
| takes no lock (without `--reindex`); `--reindex` indexes under the removal lock and is idempotent | reconcile.py:84-87; P8 | confirmed (idempotency per test_reconcile.py:83; not rerun here) |
| A task listed as never ended can be deleted with `request delete --force` | lifecycle.py:665 statuses, runbook text consistent with code | confirmed (code) |

### Backup and restore

| Claim | Evidence | Class |
|---|---|---|
| `make backup` into `backups/<UTC time>/`; `./agentctl backup --to DIR`; `make restore BACKUP=...`; `make drill` | Makefile:124-134; backup.py:233 (`%Y%m%dT%H%M%SZ`); P5, P6 | confirmed |
| Backup holds the removal lock **for its whole run** | backup.py:234-288 hold it, **but `manifest.json` is written at backup.py:289-301, after `async with run_lock` has exited** | **contradicted, Nit (N2)**: the last step, the manifest write, runs without the lock. The data it records was already captured under the lock, so nothing is lost. |
| stops every worker while it dumps the three databases, starts again those running or restarting, even when a dump or the stop fails or on SIGTERM/SIGHUP | see the overview Backup row | confirmed |
| "an Activity that was running is retried by Temporal" | no workers ran during this check | **unverifiable**, Nit: needs a backup taken while an Activity runs. Not exercised here or by the drill (its task has ended before the backup). |
| copies every bucket object and writes `manifest.json` last, whole or not at all | backup.py:196-204, 301; test_backup.py:218 | confirmed |
| a bucket it cannot list or read fails the backup, and so does one with no objects while rows name live blobs | backup.py:171-172, 187-193, 281-287 | confirmed |
| directory new (existing refused), mode 0700; `backups/` git-ignored | backup.py:238-241; P5; `.gitignore:40 /backups/` (`git check-ignore`) | confirmed |
| a SIGKILL during the dumps leaves the workers stopped; `workers-stopped` was written before anything stopped; the `docker compose ... start $(cat .../workers-stopped)` recovery | backup.py:244-257 | confirmed (code) |
| Restore: "Use the same images as the backup (`images` in `manifest.json`)" | P5/P10: `images` holds only the five pinned infra images, not `praxismesh-worker:dev` or `praxismesh-dsh:dev`, because `config --images` runs without the worker profiles (backup.py:243) | **Nit (N3)**: accurate for the pinned images (schemas.md says "the stack's pinned images"), but the manifest cannot tell an operator which worker image to use |
| `make restore` refuses, changing nothing, for each listed condition | P6, P7; restore.sh:37-51 come before the mark at :54 | confirmed |
| it then stops workers and Temporal, drops and recreates the three databases with grants and `praxis_comms`, loads dumps and objects, starts Temporal and the workers that were running or restarting, prints reconcile's report | restore.sh:54-95 | confirmed |
| restore succeeds even when reconcile lists something, and says so if reconcile failed | restore.sh:93-102 (script ends 0 on both branches); P11 | confirmed |
| A restore that stopped partway leaves a mark; next refuses with "an earlier restore did not finish"; the mark is cleared once dumps and objects are loaded, so a Temporal or worker start failure needs only `make up` | restore.sh:49, 54, 81-85; P11 | confirmed |
| The drill: runs a task on the fake model, backs up, refused restore, resets, kills a restore while loading, resets again, restores, checks status, output, `praxis_comms`, removed object dangling; CI runs it last in `stack`; `DRILL_BUILD=--no-build` reuses the image | drill.sh:22, 39-138; ci.yml:125-127; P11 | confirmed |

## docs/roadmap/schemas.md

| Claim | Evidence | Class |
|---|---|---|
| `audit_log`: `actor` (`cli:<OS user>`), `action`, `subject`, `operation_id`, `details`, class `audit`; trigger refuses UPDATE and DELETE | P9 columns, trigger, actors `cli:geo` | confirmed |
| Phase 03, no migration | head still 0007 (P9); no new revision in `common/persistence/migrations/versions/` after 0007 | confirmed |
| backup directory `backups/<UTC time>/` with three `-Fc` dumps, `blobs/<key>`, `manifest.json` written last | P5; backup.py:233, 262-301 | confirmed |
| manifest fields `format` (1), `started_at`, `finished_at`, `migration`, `databases` (file and size), `rows` (each application table, `blob_refs`, `blob_objects`, `audit_log`), `bucket`, `objects` (key, size, content type, metadata), `workers_stopped`, `images` (pinned images) | P5 keys and values; backup.py:289-300; retention.py:32-53 | confirmed |
| no `manifest.json`: incomplete, restore refuses | P7 | confirmed |
| `postgres` carries the comment `praxismesh-restore-in-progress` while a restore runs | restore.sh:31, 54 | confirmed (code) |

## docs/roadmap/decision-log.md (2026-11-21, three Phase 3A entries)

| Claim | Evidence | Class |
|---|---|---|
| Round 2: backup and restore stop every worker and start again those running or restarting | backup.py:119-125, 257; restore.sh:57-64, 86-89 | confirmed |
| backup handles SIGTERM/SIGHUP and records `workers-stopped` first | backup.py:128-145, 246 | confirmed |
| a bucket with no objects while live blobs are recorded fails a backup | backup.py:282-287 | confirmed |
| restore clears its mark once the load is complete | restore.sh:81-84 | confirmed |
| `reconcile` exits 2 when Temporal or the database is unreachable, and re-reads `ended_at` | P3, P4; reconcile.py:105, 110-118 | confirmed |
| Round 1: `make restore` runs `check-backup` first and refuses a row in any application table | restore.sh:40; backup.py:355-365; P6, P7 | confirmed |
| `agentctl backup` fails on a bucket it cannot list or read | backup.py:171, 190-193 | confirmed |
| a Temporal error other than NOT_FOUND is `WorkflowStatusUnavailable` (exit 2) in `reconcile`, `gc` and `request delete` | workflow_status.py:149-153; gc and delete take `status_of` (lifecycle.py:472, 665) and the error is a `PraxisError` (exit 2, cli.py:469-471) | confirmed (code) |
| Phase 03: backup holds the removal lock, stops the **running** worker services during the dumps | round 2 changed this to every worker service, as the round 2 entry records. A dated log keeps superseded entries. | confirmed (superseded, recorded) |
| restore recreates through `databases.sh` (also used by `init.sh`); the dumps bring the extensions | restore.sh:70; init.sh:26; P9 | confirmed |
| `make drill` runs in CI's `stack` job, last | ci.yml:125-127 | confirmed |

## docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/notes.md, section d8

| Claim | Evidence | Class |
|---|---|---|
| backup holds the D4 lock on its own connection for the whole run | removal.py:66-90 (a dedicated connection). The manifest write falls outside the lock, as in N2. | confirmed, with N2 |
| steps 1-3: stop workers, three `pg_dump -Fc` through `docker compose exec db`, start workers, copy the bucket through the S3 API | backup.py:257-288 | confirmed |
| step 4: manifest holds "times, row counts, object count, migration head, versions" | the manifest has `objects` (a list, no count field) and `images` (image references), no `versions` field (P5) | **Nit (N4a)**: loose wording |
| application database first; a later blob restores as an orphan | backup.py:57, 260-262 | confirmed |
| restore step 1 refusals (whole backup, format, head, sizes, any application row, Temporal API count with system namespaces ignored, empty bucket) | backup.py:314-386 (`count_workflows` on the client's namespace) | confirmed |
| restore step 3 runs `databases.sh`: "the CREATE DATABASE, REVOKE/GRANT CONNECT and extension statements" | restore.sh:70 runs it with `--no-extensions`, and databases.sh:36-39 then skips the extension statements | **Nit (N4b)**: d8 does not say restore skips the extensions. The decision-log phase 03 entry and the overview both do. |
| restore step 4: "start Temporal and the workers" | restore.sh:85-89 start only the workers that were running or restarting | **Nit (N4c)**: less precise than the as-built behaviour |
| "A failure after step 3 starts leaves a partial load, which step 1 then refuses" | the refusal comes from the mark (restore.sh:46-50, set at :54, before step 2) and from check-empty. d8's step 1 list does not name the mark. | **Nit (N4d)**: correct in effect, incomplete |
| drill is opt-in, never in `make smoke`; CI runs it in `stack` after the smoke tests; budget 45 minutes, "about 32 used" | ci.yml:108 `timeout-minutes: 45`, 119-127. The ci.yml comment says "the whole job needs about 32, and the drill about 3 more". | confirmed (32 is the figure without the drill) |

## docs/demos/phase-3a-lifecycle.md

| Claim | Evidence | Class |
|---|---|---|
| Tested commits `2a17101...`, `64091b2...`, `4713b7b` exist | `git cat-file -t` gives "commit" for each; 4713b7b is HEAD's parent | confirmed |
| Script `infra/demo/phase-3a-lifecycle.sh`; steps 0-5 incl. `lifecycle_probe.py age`, `agentctl backup --to backups/demo-...`, `make restore` | script lines 37, 109-119 | confirmed |
| "Phase 03 changes no worker code" | `git diff --stat d5afd28 HEAD -- workers harness_activity common comms_mcp sample_mcp registry` touches only `common/blob_store/base.py` (a new `Bucket` Protocol) and `s3.py` (`list_objects` treats NoSuchBucket as empty). Workers do not call `list_objects`. | confirmed in effect |
| step outputs (expired-read message, tombstones, `check-backup` message, `"clean": true` after restore) | the same strings appear in the independent run on this stack (`.verify/07-demo.log` lines 119-127; P7 message text) | confirmed |
| run timings and counts on the `pmaccept3a`/`pm3adev` stacks; the SIGABRT note | historical records of other stacks, which this check could not access | unverifiable (historical, labelled as the implementer's run; not a defect) |

## Contradicted and unverifiable claims, by severity

There are no Blockers and no Majors.

- **N1, Nit.** docs/architecture/overview.md, Phase 3A "Tests", first bullet: "Integration, each on a scratch database with an in-memory bucket: ... `test_restore_refusals.py`". test_restore_refusals.py:35-38 uses `scratch_bucket`, which is a SeaweedFS bucket on the stack (tests/support/stack.py:41-44), and it uses the real Temporal client (lines 93, 109). It belongs in the "Against the stack" bullet.
- **N2, Nit.** docs/operations/runbook.md, Backup and restore: "**Backup** holds the removal lock for its whole run". The manifest is written after the lock is released: backup.py:289-301 come after the `async with run_lock(engine)` block, which ends at line 288. The dumps and the copy are under the lock, so the effect is nil, but the sentence is not literally true.
- **N3, Nit.** docs/operations/runbook.md: "Use the same images as the backup (`images` in `manifest.json`)". The observed manifest lists only the five pinned infra images (P5, P10). The worker and DSH images (`praxismesh-worker:dev`, `praxismesh-dsh:dev`) are missing because backup.py:243 runs `config --images` without the worker profiles.
- **N4, Nit.** notes.md section d8 is loose in four places: (a) "versions" and "object count" in the manifest; (b) it implies restore runs databases.sh's extension statements, where it passes `--no-extensions`; (c) "start Temporal and the workers", where it starts only those that were running or restarting; (d) step 1 does not name the unfinished-restore mark that the partial-load sentence relies on. The overview, runbook and decision log state the as-built behaviour correctly.
- **U1, unverifiable, Nit.** docs/operations/runbook.md: "an Activity that was running is retried by Temporal". It needs a backup taken while a worker runs an Activity. No workers ran in this check, and the drill backs up after its task has finished.

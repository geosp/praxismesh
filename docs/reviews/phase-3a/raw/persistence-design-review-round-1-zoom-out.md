<!-- Verbatim subagent report (Phase 3A persistence plan design-review round 1, zoom out, at 417e8f9); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged with save-report). -->

I found one Blocker, seven Majors and seven Nits. The Blocker matters most: the plan never says what happens when bytes that are being removed, or were already removed, are uploaded again. Under content keys that collision is routine, and the code shows it leads to live data being deleted or reported as expired. I reviewed the plan files at 417e8f9; the plan directory has no diffs against HEAD.

## Blocker

**B1. Re-upload of the same bytes during or after a removal is unhandled, so live blobs get deleted or read as expired.** (Decisions › D5 and D6; notes.md#d6; Phase 02 task 1.1 and task 1.2)
- **What the code does today:**
  - `RecordingBlobStore.put` upserts with `ON CONFLICT (key) DO UPDATE SET retention_class = ...` only (`common/persistence/repositories.py:642`). It never touches `created_at`, and in the plan nothing clears the new `removed_at`.
  - `S3BlobStore.put` skips the upload when `head_object` finds the key (`common/blob_store/s3.py:92-93`).
- **What the plan relies on:** D6 says "The next run deletes every object with `removed_at` set that the bucket still holds, before new work", and `BlobExpired` is raised "when `blob_objects.removed_at` is set, before the bucket is asked".
- **Three failures that follow, none covered:**
  - (a) A request is deleted, then the same instructions or input file is submitted again (likely for demo prompts). `put` re-uploads, but `removed_at` stays set. Every read of the new task then raises `BlobExpired`, and the next GC or delete run deletes the live object.
  - (b) Concurrency. GC transaction 1 marks a key free. A concurrent `prepare_task` or checkpoint `put` sees the object through `head_object` and skips the upload. GC step 2 deletes the object. The new row indexes a missing blob.
  - (c) The D5 safety window is measured from `blob_objects.created_at`, which is the first upload ever. An old orphan uploaded again by a new attempt is eligible at once, before its reference commits.
- **What the plan should add:**
  - `put` claims the key in `blob_objects` first: clear `removed_at` and bump a `last_put_at`. Only then does it touch S3, and it never skips the upload when the row says removed.
  - The bucket delete re-checks under a row lock that the key is still marked and has not been put since the mark.
  - A test for each of (a), (b) and (c).

## Major

**M1. Removing an expired reference from a row that stays makes that row "unindexed", and then GC refuses to run forever.** (Decisions › D4; Risks bullet 1; notes.md#redact; Phase 03 task 1.1)
- `tasks` rows are class `audit` and are kept. Their `instructions_ref` and `input_refs` are `transcript` (30 days).
- After GC frees those references, or after a `request delete` (notes.md#redact redacts only `result.*` and leaves `instructions_ref` and `input_refs` in place), the JSON still names a blob with no `blob_refs` row.
- By the plan's own definition reconcile then lists it as unindexed, and D4 says "`gc` refuses to run while any reference is unindexed". The first successful GC therefore blocks every later one.
- The plan needs one of: removed references stay in `blob_refs` as tombstoned rows, unindexed means "no index row and no `removed_at`", or the reference JSON is rewritten.

**M2. Writing the tombstone last loses audit records on a crash, for no benefit.** (Decisions › D6; notes.md#d6 step 3; R13, R15)
- `audit_log` is in the same database as the rows. Nothing stops step 1 from writing the tombstone in the same transaction as the row and index changes.
- As planned, a GC killed after step 1 has already removed rows. Its rerun has a different operation ID, so the first batch never gets a tombstone, which breaks R13.
- "One tombstone per operation ID", with batches of 500 committed separately, also leaves the counts in R13 ("listing the counts of rows, references and blobs") undefined across a crash.
- Fix: write a tombstone per batch in transaction 1, or a "started" row plus per-batch rows. This also removes step 3 altogether.

**M3. The D5 safety-window argument is wrong about when references commit.**
- D5 says "An attempt uploads a blob and then references it within one turn". Three counterexamples:
  - **Instructions and inputs.** The CLI uploads them in `prepare_task` (`orchestrator/submit.py:34-42`). They are referenced only when the Workflow's `record_task` Activity runs. If no orchestration worker is running, that gap has no bound.
  - **Artifacts of a `waiting` turn.** They are uploaded in `_finish` (`harness_activity/activity.py:691`) and carried only in Workflow state (`orchestrator/workflow.py` `run.outputs`) until `complete_task`. Today this is bounded only by `max_wall_time_cap: PT1H`.
  - **notes.md#refs is wrong about checkpoints.** It says `checkpoints.finish` holds `outputs[].ref`. It does not: finish is `{status, summary, questions}` (`harness_activity/activity.py:603-611`). The backfill and the writer list are therefore built on a column that names no artifacts.
- The 24 h window may still be acceptable, but D5 should state the real gaps and their bounds, and the refs table should be corrected.

**M4. Rollout has no repair path for references written by old workers, and the database defaults are not addressed.** (Rollout & rollback; Phase 01 task 1.1)
- **No repair path:**
  - Rollout says "migrate, then restart every worker (old workers write no index rows; reconcile reports any)". Reconcile only reports. Nothing indexes those rows afterwards, so GC refuses (D4) with no remedy.
  - Either stop the workers and the CLI before migrating, or add an idempotent `agentctl reconcile --reindex` or rerunnable backfill.
- **Database defaults:**
  - Old workers and SDK-written tables insert `task`. Several tables default `retention_class` to `'task'` (`0003_phase1_tables.py:29-37`, `0005_agent_events.py:35`, `0006_task_messages.py:46`). The event insert in `common/events/table.py:45` relies on that default.
  - The plan never says whether the new checks still allow `task` or whether the server defaults change. If `task` is dropped from the checks, old workers and the SQLAlchemy session tables fail on insert. If it is kept, new rows keep landing in `task` after the remap.
- **Downgrade drops `audit_log`:** that destroys append-only tombstones, and removed blobs cannot come back. The rollback text should say this.

**M5. The `questions` cap rejects output instead of truncating it, which can fail a task.** (Decisions › D9; Phase 01 task 3.2: "a test that returns 21 questions fails validation")
- `summary` is truncated at the source: `summary[:2000]` in `harness_activity/tools.py:222`. `questions` is passed through unbounded at the same line.
- A schema cap on `TurnOutcome` makes a model that asks 21 questions raise a `ValidationError` in the Activity.
- The finish checkpoint already holds those questions, and the retry replays them from `latest.finish` (`harness_activity/activity.py:506-512`). Every attempt therefore fails the same way until the turn is exhausted.
- Fix: cap and truncate in `finish_task_body`, next to the summary truncation.

**M6. `make restore` as described will fail on a "clean stack", and a half-finished restore cannot be retried.** (Decisions › D8; notes.md#d8; R16; Phase 03 task 2.2)
- On a clean Compose stack, `temporal-schema` has already created Temporal's tables, and `make migrate` may have created the app tables. A plain `pg_restore` of `-Fc` dumps into existing schemas fails on objects that already exist. If the app database is not migrated, the "`tasks` is empty" check has no table to read.
- If the load fails after the `praxismesh` dump is in, the emptiness check now refuses every rerun.
- The plan should specify dropping and recreating the three databases with their owner roles (or `--clean --if-exists`), what a partial failure leaves behind, and the recovery step (for example `make reset`).
- Separately, "Rollout & rollback" says nothing about not running `gc` or `delete` during a backup. A removal between the app dump and the bucket copy creates dangling references in the backup.

**M7. Delete-by-request has holes the plan does not state.** (R10-R12; Non-goals; Summary: "deletes everything a request stored")
- **Never-ending tasks block delete.** A terminated Workflow never runs `complete_task`, so its task stays `running` (ADR-0010 "Bad" consequence, `docs/adr/0010-wake-agents-through-a-durable-inbox.md:99-100`). R12 then makes the whole request undeletable, with no override.
- **Joins race the delete.** Nothing stops a task joining the request during or after the delete: `join_request` is checked only through `request_exists` (`orchestrator/cli.py:91`, `common/persistence/repositories.py` `request_exists`).
- **Temporal histories keep content.** The summary, the questions (up to 20×500 chars after D9) and the turn outcomes stay in Temporal histories for `TEMPORAL_RETENTION=72h` and in every Temporal backup. §4.13 says "Deletion never rewrites Temporal history, which is one more reason content stays out of it". R18 bounds size only.
- The plan should either move that text behind blobs or record the residual exposure (Temporal retention plus backups) as accepted, and give terminated tasks a way through (for example a `--force` path that requires Temporal to report the Workflow closed).

## Nits

- **Phase 02 task 1.1:** `agentctl task output` reads through a bare `S3BlobStore` (`orchestrator/cli.py:133`), not `RecordingBlobStore`. R9 needs that call site switched, and the task should name it.
- **Phase 02 task 1.2 vs `RecordingBlobStore.delete`:** that method deletes the `blob_objects` row (`repositories.py:667-670`), which would erase the `removed_at` that `BlobExpired` depends on. The engine must not use it, or the method must change; say which.
- **Phase 01 task 1.3 / notes.md#d3:** `RETENTION_ORDER` (`common/blob_store/base.py:19`) and the S3 object metadata class (`s3.py` `META`) also encode the old classes. `stronger()` raises `KeyError` if `task` is dropped from the order, and R4 ("existing ... blobs move") cannot rewrite S3 metadata in an Alembic migration. Say whether `blob_objects` is the only record of class that gets remapped.
- **Terms › Expiry / notes.md#d2:** `tasks` has no end-time column (`0003_phase1_tables.py:42-58`; only `updated_at`). Name the column expiry uses, and how row expiry is derived for tables keyed by `session_id` or `workflow_id` (`agent_sessions`, `event_logs`, `event_batches`).
- **R14 / Phase 01 task 1.2:** the app role `praxismesh` owns the database and its tables (`infra/db/init.sh`), so it can `TRUNCATE` (row triggers do not fire on it) or disable the trigger. D3's "`audit` until purged" also has no purge path under a refuse-all trigger. State both limits.
- **Phase 02 task 1.2 / D4:** nothing serialises two concurrent `gc` or `delete` runs (for example `pg_advisory_lock`). The idempotent steps tolerate it, but the counts and tombstones do not.
- **notes.md#redact:** it says the session assumption is "checked in task 2.4", but the check is Phase 02 task 3.1.

## Questions 1-5

1. **Root cause:** the index addresses the real cause, which is that references cannot be queried. B1 and M1 are gaps in how the index interacts with content keys and with rows that outlive their references.
2. **Simplicity:** M2 is a simplification (drop step 3). Nothing found is built for an unstated future need.
3. **Placement:** fits the codebase, except M5 (the `questions` cap belongs in `finish_task_body`, next to the summary truncation).
4. **Failure modes:** covered by B1, M1, M2, M5 and M6.
5. **Rollout:** covered by M4 and part of M6.

Relevant files:
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/blob_store/s3.py
- /home/geo/develop/praxismesh/common/blob_store/base.py
- /home/geo/develop/praxismesh/orchestrator/submit.py
- /home/geo/develop/praxismesh/orchestrator/cli.py
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/tools.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0003_phase1_tables.py
- /home/geo/develop/praxismesh/infra/db/init.sh
- /home/geo/develop/praxismesh/docs/adr/0010-wake-agents-through-a-durable-inbox.md

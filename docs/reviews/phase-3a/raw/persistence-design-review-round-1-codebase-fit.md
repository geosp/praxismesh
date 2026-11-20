<!-- Verbatim subagent report (Phase 3A persistence plan design-review round 1, codebase fit, at 417e8f9); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged with save-report). -->

## Design review: Phase 3A persistence and data lifecycle plan (at 417e8f9)

I compared the plan, the three phase files and notes.md with the code. The plan files at 417e8f9 match the working tree. Verdict: two Blockers and nine Majors. Most of the plan's code claims hold, but the deletion-safety design has two gaps that defeat the plan's own main risk, and several named writers or columns are wrong.

### Blockers

**B1. After any delete or GC, `gc` refuses to run for good, and reconcile reports false problems.** Where: plan.md R10, R11, R15, R17, D4; notes.md#redact.
- R11 and notes#redact keep the `tasks` rows, and only `result` is touched.
- `instructions_ref` (NOT NULL, 0003_phase1_tables.py:52) and `input_refs` still hold their `BlobRef` JSON after R10 frees those references.
- D3 also gives instructions and inputs a 30-day `transcript` lifetime, while their owner row is `audit` and kept forever. So ordinary GC strips the index rows of rows that survive.
- R17 then reports those JSON references as "unindexed", or "dangling" since their blob is gone. D4 says "`gc` refuses to run while any reference is unindexed".
- The first `request delete`, or the first 30-day expiry, therefore blocks GC permanently.
- R15's check ("reconciliation reports nothing dangling for that request") fails for the same reason.
- notes#d2 hints that expired index rows might be kept ("free when it has no `blob_refs` row whose `expires_at` is null or in the future"). Phase 02 task 2.1 says GC removes "expired references". The plan must settle one model: keep removed index rows as tombstoned, rewrite the JSON, or define unindexed/dangling to exclude refs whose `blob_objects.removed_at` is set.

**B2. Uploading a removed blob again is not handled, so live data can be deleted or read as expired.** Where: D5, D6, notes#d6, Phase 02 tasks 1.1 and 1.2. Keys are content hashes, so a new task can upload bytes that GC just freed.
- `RecordingBlobStore.put` upserts and updates only `retention_class` (repositories.py:640-646). It neither clears `removed_at` nor refreshes `created_at`. A re-uploaded blob therefore keeps reading as `BlobExpired` (notes#d6: raised "when `blob_objects.removed_at` is set, before the bucket is asked").
- `S3BlobStore.put` does `head_object` and skips the upload when the object exists (s3.py:94-118). After a crash between D6 steps 1 and 2, a new task's put finds the object still there. The rerun then "deletes every object with `removed_at` set that the bucket still holds", which removes the new task's blob.
- The same happens without a crash. GC decides an old blob is free, a concurrent put sees the object and skips the upload, GC deletes it, and the writer's `index_refs` then commits a reference to a missing blob. D5's safety window doesn't help, because `created_at` is the first upload time.
- Needed: `put` (or `index_refs`) must clear the removal mark and record the latest put time, and freeing must be serialized against `index_refs` for the same key (a row lock on `blob_objects`).

### Majors

**M1. The writer the plan wires for `tasks.result` is dead code.** Where: Phase 01 task 2.1; notes#refs; notes#d2.
- The plan says `TaskRepository.complete` writes `tasks.result`, but nothing calls it. The real writer is `MessageRepository.end_task` (messages.py:291-303), called from the `complete_task` Activity (activities.py:150).
- notes#d2 also has `complete_task` set `expires_at` "in its own transaction". A crash between `end_task` and that transaction leaves an ended task whose references never expire.
- Both the indexing and the expiry should go inside `end_task`'s transaction.

**M2. D5's "referenced within one turn" is false for artifacts and submitted inputs.** Where: D5; notes#refs.
- notes#refs says `checkpoints.finish` holds `outputs[].ref`. It doesn't: `finish` is `{status, summary, questions}` (activity.py:600-608).
- Artifacts are uploaded after the finish checkpoint (activity.py:678-692). Until `complete_task` writes `tasks.result`, they exist only in `TurnOutcome` and the Workflow's state (workflow.py:180, 286-290, 417).
- Instructions and inputs are uploaded by `prepare_task` before the Workflow starts (submit.py:34-42). They are indexed only when `record_task` runs.
- If the orchestrator worker is down for more than 24 h, or a task is queued that long, GC deletes blobs a live Workflow will still use.
- Needed: an anchor written with the upload, or a rationale based on worker downtime, plus a corrected notes#refs row.

**M3. "The task's end time" has no column, and row expiry is undefined.** Where: Terms › Expiry; D3; notes#d2; Phase 01 task 1.1; Phase 02 task 2.1.
- `tasks` has no `ended_at` (0003_phase1_tables.py:42-60). Only `updated_at` changes at the end (messages.py:299).
- "Expired rows by class" for tables with no expiry column is not specified. Examples: `agent_sessions` (keyed by `session_id`), `task_messages` (sender and recipient are both tasks), `event_logs` (keyed by `workflow_id`), `idempotency_keys`.
- The backfill doesn't set `expires_at` for tasks that ended before the migration. Left null, existing data never expires.

**M4. The class migration ignores the column defaults that most writers rely on.** Where: Phase 01 tasks 1.1 and 2.2; R4.
- Most inserts omit `retention_class` and take the server default:
  - sample_mcp/server.py:100 and :115
  - common/events/table.py:44, :70 and :88
  - common/persistence/messages.py:284, :473 and :508
  - the openai-agents session tables (0003 docstring)
- The current defaults are `task` (0003:117-138, 0005:35, 0006:79/94). `idempotency_keys` defaults to `audit` (0003:98), but D3 says `transcript`.
- Task 1.1 changes the checks and remaps existing rows, but not the defaults. New rows keep getting the old classes, or fail the new check.
- Checkpoint inserts hardcode `'task'` (repositories.py:398, 427). If the new check drops `task`, old workers fail between "migrate" and "restart every worker" (Rollout & rollback). The plan doesn't say whether the check keeps `task`.

**M5. The class recorded in S3 metadata and the rank of `task` are unspecified.** Where: D3; notes#d3; Phase 01 task 1.3; R4.
- `S3BlobStore.put` and `stat` return the class stored in the object's metadata (s3.py:106-118, 148). The migration remaps only rows, though What changes says "Existing rows and blobs move to the new classes".
- `RETENTION_ORDER` (base.py:18) needs a place for `task`. Depending on that order, a repeat put of bytes first stored as `task` returns a `task` ref, which the new "refused for new writes" rule then rejects.
- R4's "both carry `checkpoint`" fails for bytes first stored as `audit` or `task`. Artifacts are currently written as `audit` (activity.py:691).

**M6. The `questions` cap as a schema constraint can break replay.** Where: D9; Phase 01 task 3.2 ("a test that returns 21 questions fails validation").
- `questions` are unbounded today (task.py:94, 107), and model questions over 500 characters are plausible.
- A cap on `TurnOutcome` or `TaskResult` makes recorded and in-flight histories fail to decode on replay. That is the in-flight-workflow rule, and R5 covers only `retention_class`.
- It also turns model behaviour into Activity failures and retries.
- The existing pattern truncates in the tool (tools.py:221, `summary[:2000]`). Cap there instead, and leave decoding permissive.

**M7. Phase order: requirements depend on code from a later phase.**
- R2 is delivered in Phase 01, but its scenario uses `agentctl reconcile`, which Phase 03 task 1.1 builds.
- D4's refusal "while any reference is unindexed" is needed by Phase 02 task 2.1 and needs the same check.
- R15 (Phase 02, task 3.3) relies on "reconcile-style check".
- The unindexed and dangling queries should move to Phase 01 or early Phase 02.

**M8. Event deletion bypasses the existing prune path.** Where: notes#redact (`agent_events` "rows deleted"); D3 transcript GC.
- `TableTransport.prune` (common/events/table.py:170-209) deletes events and advances `event_logs.retained_base`. Readers rely on that base to report `Expired` (table.py:123-128; cli.py:199). That is ADR-0009's design ("Readers use both expiry checks").
- Deleting rows directly makes `agentctl tail` show silent gaps. GC and delete should reuse `prune`.
- ADR-0009 Consequences also says "Phase 3A's retention work needs time-based partitioning or equivalent". The plan never says whether batched deletes of 500 are that equivalent.

**M9. The R14 trigger does not stop the app role.** Where: R14; Phase 01 task 1.2.
- Migrations run as the app role (migrations/env.py:29, 45), and that role owns the database (infra/db/init.sh: `CREATE DATABASE praxismesh OWNER praxismesh`). So it will own `audit_log`.
- An owner can `DROP` or `DISABLE TRIGGER`, and `TRUNCATE` doesn't fire row-level `UPDATE`/`DELETE` triggers. The scenario passes, but the guarantee doesn't hold.
- Fix: a separate owner role with revoked privileges, or a recorded limitation.
- D3's "audit until purged" also contradicts append-only, and the plan has no purge path.

### Nits
- Phase 02 task 1.1: `agentctl task output` reads through a bare `S3BlobStore` (orchestrator/cli.py:133), so it must switch to `RecordingBlobStore` to see `removed_at`. A "unit test on the memory store" can't see `blob_objects` without a database.
- Phase 01 task 3.1: the existing fixture tests/fixtures/task_workflow_history.json already carries `retention_class: task` (3 payloads), so `test_task_workflow_replay` (tests/test_task_workflow.py:228) already covers R5. Reuse it.
- Phase 02 task 1.2 / D6: `RecordingBlobStore.delete` deletes the `blob_objects` row (repositories.py:660-663), which contradicts keeping `removed_at`. Say the engine calls the inner store.
- D8: the title says "two dumps", but the body and notes#d8 make three.
- Phase 02 task 3.2: `request delete` should take the existing request lock (`_REQUEST_LOCK`, messages.py:296), so a `join_request` task can't join during the delete.
- R12 + notes#d2: a task whose Workflow was terminated stays `running` forever and can never be deleted. Say whether that is accepted.
- notes#redact: `tasks.result.failure_reason` can hold content and isn't in the redaction list.

### Confirmed as described
- `blob_objects`, `APP_TABLES`, `DEFAULT_LIFETIME` (common/persistence/retention.py), `insert_fenced` and `insert`, `TableTransport.publish`, `record_task`, and `blob_ref` on `agent_events` (unused so far).
- The Temporal databases `temporal` and `temporal_visibility` (docker-compose.yml:61-62), the CI `stack` job, the 10-minute `turn_timeout` (registry/templates), and `agent_sessions` keyed by the task ID (activity.py:551).
- schemas.md's line "migrations land with the phase that first needs them" (line 28).
- No Decision contradicts an ADR in force, apart from the ADR-0009 consequence left unaddressed in M8.

Key files:
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/common/blob_store/s3.py
- /home/geo/develop/praxismesh/common/blob_store/base.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/orchestrator/submit.py
- /home/geo/develop/praxismesh/orchestrator/activities.py
- /home/geo/develop/praxismesh/orchestrator/cli.py
- /home/geo/develop/praxismesh/common/events/table.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0003_phase1_tables.py
- /home/geo/develop/praxismesh/harness_activity/tools.py
- /home/geo/develop/praxismesh/infra/db/init.sh

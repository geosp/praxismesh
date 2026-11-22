---
title: Phase 3A persistence and data lifecycle - blob references, retention, deletion and backup
status: closed
created: 2026-11-19
updated: 2026-11-21
design_review: { status: passed, rounds: 3, last: 2026-11-20 }
approved: 2026-11-20
adr_review: 2026-11-21
---

# Phase 3A persistence and data lifecycle - blob references, retention, deletion and backup

## Summary

Plan A of Phase 3A. Stored data gets a lifecycle. A new reference index records, in the same
transaction, every row that names a blob and every upload made for a task (R1, R2); existing data
moves to §4.13's five classes (R4, R19). Operator commands remove expired data (R6-R8) and delete a
request: blobs removed, content redacted, IDs and usage kept, late writes fenced (R10-R12, R24, R25). Each removal batch
writes an append-only tombstone (R13, R14), and a removed blob reads as *expired* (R9). Temporal
histories still hold a deleted task's summary and questions for 72 hours (D12); `questions` is
truncated and a test keeps history payloads under 64 KiB (R18). `make backup` and `make restore`
cover the three databases and SeaweedFS; reconcile lists inconsistencies (R16, R17, R23). Rollout
takes a backup, drains open Workflows and stops the workers first. Main risk: deleting a blob still in use, since identical
bytes share one object. A blob goes only with no live reference, `gc` refuses while any reference
is unindexed, uploading the bytes again revives them (R22), and every command has a dry run.

```text
row write or upload --one transaction--> row + blob_refs rows
agentctl gc | request delete --one transaction--> rows, refs marked removed, blobs marked, tombstone
                             --then, per blob, under its row lock--> SeaweedFS delete if still marked
make backup  --> pg_dump x3 (praxismesh, temporal, temporal_visibility) + bucket copy
make restore --> recreate the databases with their grants --> load --> agentctl reconcile
```

## Why

Phases 1 and 2 record a retention class on every blob and row from its first write (§4.13), but
nothing ever removes anything. Three problems follow:

- **Storage only grows.** Checkpoint snapshots, sessions and events stay forever. Issue #74:
  a stale attempt can upload blobs nothing references, and they are never removed.
- **References are not queryable.** A blob is named inside JSON columns of `tasks`, `checkpoints`
  and `agent_events` (notes.md#refs). No query can answer "is this blob still used?", and two tasks
  storing the same bytes share one object. Deleting safely needs that answer first.
- **Nothing can be deleted on request or restored after a loss.** §4.13 asks for
  delete-by-request with audit tombstones, and for one backup and restore procedure with a
  reconciliation pass, exercised as a drill in Phase 3A.

On 2026-11-19 the project owner split Phase 3A into plans A to D, then folded B into A. Plan C
(request Workflow, triage, delivery modes) and plan D (planning, DAG dispatch, routing) add their
own tables when they first need them (D1). Items marked *(owner)* are the project owner's
decisions of 2026-11-19. **Size:** L. **Hardware:** none beyond the Compose stack.

## What changes

- New table `blob_refs`, written with every row that stores a `BlobRef` and with every upload made
  for a task, and backfilled for rows written before it.
- New columns: `tasks.ended_at`; `blob_objects.removed_at`, `removed_by`, `last_put_at` and
  `bucket_deleted_at`.
- Retention classes become §4.13's: `ephemeral`, `checkpoint`, `transcript`, `artifact`,
  `audit`. `RetentionClass` in `common/schemas/` keeps `task` as a readable value. Existing rows
  and `blob_objects` rows move to the new classes.
- New table `audit_log`, append-only.
- `BlobStore.put` takes an optional task ID; `BlobExpired` is new. Both adapters and
  `RecordingBlobStore` change.
- New `agentctl` commands: `gc`, `request delete`, `reconcile` (with `--reindex`) and `backup`,
  each removal command with `--dry-run`. `agentctl events prune` goes through the removal engine.
- New `make backup`, `make restore` and an opt-in `make drill`.
- A Claim Check test over Workflow histories, and truncation of `questions`.

### Non-goals

- Delete-by-conversation: conversations arrive with the Phase 4 gateway, the OpenAI-compatible
  API *(owner)*.
- Presigned or link-based artifact retrieval: nothing hands a link to a client before Phase 4
  *(owner)*. Retrieval stays `agentctl task output`, scoped to the named task.
- Ceph and GCS adapters: SeaweedFS only *(owner)*.
- Encryption at rest: an accepted risk until Phase 9 *(owner)*.
- Scheduled GC and backups: Phase 7 (Kubernetes CronJobs) and Phase 9 hardening.
- A general outbox (D7). Requests, plans, revisions and budget tables: plans C and D (D1).
- Purging `audit` rows: they are kept; no purge command exists in Phase 3A.

## Terms

- **§4.13**: the persistence section of `docs/roadmap/design-decisions.md`: retention classes,
  the outbox pattern, delete-by-request with tombstones, and the backup and restore drill.
- **Phase 01-03** are this plan's phases; **Phase 1-9** are the roadmap's.
- **Blob**: bytes in SeaweedFS under a content key `sha256/<hex>`, so identical bytes share one
  object; a **`BlobRef`** names one. **`RecordingBlobStore`**: the wrapper around the S3 adapter
  that records each blob in **`blob_objects`** (key, checksum, size, class, first upload time).
- **Task, turn, attempt**: a task runs as one Temporal Workflow; each turn runs the harness
  Activity, retried as attempts. Checkpoint writes are fenced: only the current attempt's insert
  commits, so a **stale attempt** can leave uploads that no row names (ADR-0007).
- **`end_task`**: the repository call, made by the `complete_task` Activity, that writes a task's
  final status and result.
- **Request**: the tasks that share a `tasks.request_id`. `agentctl task submit` mints
  `req-<uuid>`; `--join REQ` adds a task to an existing request. The **request lock** is a
  per-request PostgreSQL advisory lock that messaging and `end_task` take.
- **Ended task**: `tasks.status` is `succeeded`, `failed` or `needs_input`; `tasks.ended_at` is
  its end time. `needs_input` is terminal: the Workflow has finished and returned questions.
- **`questions`**: the list a task's `finish_task` tool returns with `needs_input`;
  **`finish_task_body`** is that tool's handler.
- **Content tables**: `agent_sessions` and `agent_messages` (each task's model conversation),
  `task_messages` (Phase 2 messages between tasks) and `idempotency_keys` (tool results).
- **Holder**: what holds a reference: a row (table, key, column), or a task for its own uploads.
- **Reference index**: `blob_refs`, one row per holder and blob. A **live** reference is one not
  marked removed. **Unindexed**: a reference stored in a row with no index row. **Dangling**: a
  live reference whose blob is missing from the bucket. **Orphaned**: a bucket object with no
  index row.
- **Retention class**: the lifetime label each blob and row carries (D3).
- **Expiry**: the task's `ended_at` plus the class's lifetime, computed when GC runs (D3).
- **Safety window**: how long a blob with no live holder is kept after its last upload (D5).
- **Tombstone**: an `audit_log` row recording a removal, without the removed content.
- **Redact**: replace a content value with the marker `[deleted <date>]`, keeping the row.
- **Reconciliation**: a read-only check that compares rows, the index and the bucket.
- **App role**: the database role `praxismesh` that workers, the CLI and migrations use.
- **Claim Check**: large data stays in the blob store; Temporal carries only its `BlobRef`.
- **Compose stack**, **fake model**, **`make reset`**: the local Docker Compose deployment, the
  scripted model the tests run, and the target that deletes the stack's volumes.

## Requirements

### R1 · Every stored reference is indexed with its holder

Each write of a `BlobRef` into a row, and each upload made for a task, must insert its `blob_refs` rows in the same transaction.
- **Given** a task submitted with two input files, **when** the submit's uploads commit, **then** `blob_refs` holds the instructions and both inputs, held by that task.
- **Given** a fenced checkpoint insert that the fence refuses, **when** it rolls back, **then** no `blob_refs` row held by that checkpoint remains.

### R2 · References stored before the index are indexed

Migration 0007 must index every reference already stored.
- **Given** a database at migration 0006 with tasks, checkpoints, artifacts and events, **when** it is migrated, **then** the unindexed-reference check (phase 01 task 1.4) finds none, and every ended task has its `ended_at`.

### R3 · A shared blob is kept while any live reference remains

A blob is removed only when no live reference to it remains.
- **Given** two tasks that stored identical bytes, **when** one task's request is deleted, **then** the blob still reads for the other task.

### R4 · New writes carry a §4.13 class

Every blob and row written after the change must carry its D3 class, never `task`.
- **Given** a checkpoint written after this change, **when** its row and index rows are read, **then** they carry `checkpoint`.
- **Given** an event inserted without naming a class, **when** it is read, **then** it carries `transcript`.

### R5 · Histories written before the change still decode

A `BlobRef` with the old class `task` must still decode in Workflow and Activity code.
- **Given** a recorded history whose payloads carry `retention_class: task`, **when** it is replayed, **then** replay succeeds.

### R6 · GC removes what has expired

`agentctl gc` must remove everything whose expiry has passed: references, rows, and the blobs they leave with no live reference.
- **Given** a task that ended 8 days ago, and a stale attempt's workspace uploaded after that end, **when** `gc` runs, **then** the checkpoint rows, their references, the late upload and the blobs left without live references are removed (issue #74).

### R7 · GC never removes what has not expired

`gc` never removes a row, reference or blob before its expiry.
- **Given** a running task, or one that ended 6 days ago, **when** `gc` runs, **then** its checkpoints and blobs are unchanged.
- **Given** a submitted task whose Workflow has waited 30 hours for a worker, **when** `gc` runs, **then** its inputs are kept.
- **Given** an `audit` row of any age, **when** `gc` runs, **then** it is kept.

### R8 · An orphaned blob waits for the safety window

An orphaned blob is removed only once its last upload is older than the safety window.
- **Given** a bucket object with no index row, last uploaded 25 hours ago, **when** `gc` runs, **then** it is removed.
- **Given** an orphan last uploaded 1 hour ago, **when** `gc` runs, **then** it is kept.

### R9 · A removed blob reads as expired

Reading a blob whose removal is recorded must raise `BlobExpired` with the removal date.
- **Given** an artifact whose blob GC removed, **when** `agentctl task output` reads it, **then** it fails with "expired" and the removal date, not "not found".

### R10 · Deleting a request removes its blobs

`agentctl request delete` must remove every reference its tasks hold and every blob left with no live reference.
- **Given** a finished request of two tasks with artifacts, **when** it is deleted, **then** none of its artifacts, checkpoints or inputs can be read.

### R11 · Deleting a request redacts its content

The delete must redact every content value D12 lists for the request's tasks.
- **Given** a deleted request, **when** its task results and content tables are read, **then** each listed value holds the marker, and IDs, statuses and usage remain.

### R12 · A request with an unended task is not deleted

`request delete` must refuse while any task of the request has not ended.
- **Given** a request with one running task, **when** it is deleted, **then** the command fails naming that task and nothing changes.

### R13 · Every removal batch leaves a tombstone

Each batch a GC or delete commits must write its tombstone in the same transaction.
- **Given** a request delete, **when** it finishes, **then** its tombstones name the request and their counts sum to the rows, references and blobs removed, with no content.
- **Given** a `gc` killed after its first batch, **when** `audit_log` is read, **then** that batch's tombstone is there.

### R14 · The audit log refuses changes from the app role

`UPDATE` and `DELETE` on `audit_log` by the app role must be refused.
- **Given** the app role, **when** it updates or deletes an `audit_log` row, **then** PostgreSQL refuses.

### R15 · GC and delete are safe to rerun

A GC or delete that stopped partway must finish when run again.
- **Given** a delete killed after some blobs were removed, **when** it runs again, **then** it completes, the dangling check finds nothing for that request, and nothing is counted twice.

### R16 · Restore reproduces a backed-up stack

`make restore` must load a `make backup` of the three databases and the bucket into a clean stack.
- **Given** a stack with finished tasks, **when** it is backed up and restored after `make reset`, **then** `agentctl task status` and `task output` work for those tasks, and `comms_mcp` connects as `praxis_comms`.

### R17 · Reconciliation reports what is inconsistent

`agentctl reconcile` must list dangling references, orphaned blobs, unindexed references and tasks that never ended, and change nothing.
- **Given** a restored backup whose bucket copy missed one blob, **when** reconcile runs, **then** it lists that reference as dangling.
- **Given** an orphaned blob, **when** reconcile runs, **then** it lists it with its age.
- **Given** a task left `running` whose Workflow Temporal reports closed, **when** reconcile runs, **then** it lists the task as never ended.

### R18 · The integration suite keeps large payloads out of histories

No Workflow history of the integration suite may carry a payload over 64 KiB.
- **Given** the suite's Workflows, including a task that returns 20 questions of 500 characters, **when** their histories are checked, **then** every payload is at most 64 KiB.

### R19 · Existing rows move to the new classes

Migration 0007 must give every existing row and `blob_objects` row its D3 class.
- **Given** a row with class `task` before the migration, **when** it is migrated, **then** it carries its table's class from D3.
- **Given** an artifact stored before migration 0007 with class `audit`, **when** it is migrated, **then** its index row and `blob_objects` row carry `artifact`.

### R20 · A task records when it ended

`end_task` must set `tasks.ended_at` in its transaction.
- **Given** a task ending in each terminal status, **when** `end_task` commits, **then** `ended_at` is set.

### R21 · A closed Workflow can be deleted with --force

With `--force`, `request delete` must treat a task as ended when Temporal reports its Workflow closed.
- **Given** a task left `running` by a terminated Workflow, **when** its request is deleted with `--force`, **then** the delete proceeds.
- **Given** a task whose Workflow is still running, **when** its request is deleted with `--force`, **then** the command refuses.

### R22 · Uploading removed bytes again makes them live

A `put` of bytes whose blob is marked removed must leave a live, readable blob.
- **Given** a deleted request, **when** the same input file is submitted again, **then** the new task reads it, and the next `gc` keeps it.
- **Given** a `gc` that marked a blob, **when** a `put` of the same bytes commits before the bucket delete, **then** the object is kept.

### R23 · Restore refuses a stack that holds data

`make restore` must refuse a stack whose application database, Temporal database or bucket holds data.
- **Given** a stack with one task, or with one Workflow and no task row, **when** `make restore` runs, **then** it refuses and changes nothing.

### R24 · A delete touches only the tasks it started with

`request delete` must change only the tasks of the request when it began.
- **Given** a task that joins the request while it is being deleted, **when** the delete finishes, **then** that task's inputs and rows are unchanged.

### R25 · A deleted task accepts no more writes

After `request delete` commits, no attempt of its tasks may write a row or revive a reference.
- **Given** a `--force` delete while the task's Activity is still running, **when** the attempt then inserts a checkpoint, publishes an event and uploads its workspace, **then** the insert and publish are refused, and the upload leaves no live reference.

## Decisions

### D1 · Tables land with the plan that first uses them

This plan adds `blob_refs`, `audit_log` and the new columns, whose first users are here. Requests
go to plan C, and the plan, revision and budget tables to plan D, as `docs/roadmap/schemas.md`
asks ("migrations land with the phase that first needs them"). Rejected: all Phase 3A tables now
(schema with no reader until later plans, untestable here).

### D2 · An explicit reference index, written with its holder

`blob_refs` has one row per holder and blob, with the task, request, class and a removal mark.
Writers insert into it in the holder row's transaction through one helper; uploads insert a row
held by their task. Removed references stay, marked, so a kept row still has its index row. No
expiry is stored: GC computes it (D3), so a late upload expires with its task. Rejected: scanning
JSON columns at GC time (slow; a new column is easy to miss); a Temporal payload codec that moves
payloads to blobs (replaying a history fetches them, so deleting one breaks replay). Details: notes.md#d2

### D3 · §4.13's retention classes and lifetimes

`ephemeral` 1 day after write; from the task's `ended_at`, `checkpoint` 7 days, `transcript` 30
days and `artifact` 90 days; `audit` kept *(owner)*. Each table's class and anchor is one table in
notes.md#d3; wake rows expire only once their recipient has ended (ADR-0010). Migration 0007 changes
the column defaults, and its checks still allow `task`. `blob_objects` and the index decide
lifetimes; S3 metadata is never read for one, and a `task` there ranks as `transcript`. Rejected:
keeping `task` and `audit` (artifacts never expire). Details: notes.md#d3

### D4 · Removal is an operator command with a dry run

`gc`, `request delete`, `events prune` and `reconcile` run on demand and print their plan with
`--dry-run`. Removals commit in batches of at most 500 rows. Every removal command and `agentctl
backup` hold one session-level advisory lock (`pg_advisory_lock(3, 0)`) for their whole run. `gc` refuses while
any reference is unindexed; `reconcile --reindex` repairs them idempotently. Rejected: a Temporal
Schedule or a worker loop now (one machine needs no scheduler; Phase 7 adds a CronJob).

### D5 · A 24-hour safety window for blobs with no live holder

The window covers orphans, and uploads of a task that has no `tasks` row. An orphan goes once its
last upload is more than 24 hours old. A row-less task's uploads go after 24 hours only if Temporal
reports its Workflow missing or closed, so a task queued for a worker keeps its inputs. Rejected:
each template's `turn_timeout` (an orphan's uploader is unknown); no window (pre-0007 orphans cannot
be told from in-flight uploads).

### D6 · Rows, index and tombstone first, then the bucket

Each batch is one transaction: remove or redact the rows, mark their references removed, mark
blobs left with no live reference, and write the tombstone. The bucket delete follows, per blob,
under its `blob_objects` row lock, only if the mark still stands; it then sets `bucket_deleted_at`.
A rerun first finishes marked blobs without it (R15). Rejected: bucket first (a crash leaves rows
naming missing blobs); tombstone last (a crash loses it). Details: notes.md#d6

### D7 · No general outbox in this plan

The Phase 2 wake rows (committed with each message, then drained by the wake dispatcher, ADR-0010)
already follow §4.13's outbox pattern, and nothing else in Phase 3A writes to a second service.
`schemas.md` documents the pattern. Rejected: a generic outbox table now (no user until Phase 5's
GitHub delivery).

### D8 · Backup is three dumps and a bucket copy; restore recreates the databases

`agentctl backup` (behind `make backup`) holds the D4 lock and stops the workers while it dumps
`praxismesh`, `temporal` and `temporal_visibility`, so no Workflow gets ahead of its rows; it then
copies the bucket into `backups/<UTC time>/`. Recovery point: the last
manual backup *(owner)*. Restore refuses a stack with data (R23), drops the databases, recreates
them with `init.sh`'s database statements (moved to a rerunnable script both use) and `roles.sh`,
so the grants return, loads, and prints `reconcile`'s report.
After a partial failure: `make reset`, then restore. Rejected: volume snapshots (not portable). Details: notes.md#d8

### D9 · `questions` truncated at the source; a 64 KiB history test

`finish_task_body` keeps the first 20 questions of at most 500 characters each, as it already
truncates the summary to 2,000; schemas stay permissive, so recorded histories replay. With every
other large value behind a `BlobRef`, that bounds history payloads by design; a test over the
integration suite's histories checks it (R18). Rejected: a schema cap (fails turns and replay);
Temporal's own limits (they warn at 512 KiB and fail at 2 MiB).

### D10 · Uploading again revives a removed blob

`put` collects the bytes (as the S3 adapter already does), then, under the key's `blob_objects`
row lock, clears any removal mark, records the upload time and the task's reference; a reference
marked by a delete stays marked. A removed object is simply missing, so the upload goes through.
A task a delete marked revives nothing: under its task lock, its upload reference is written with
the delete's mark, the blob keeps its mark, and bytes with no live holder are not uploaded
(impl-review F80, F81). The upload reference is unfenced on purpose: it only keeps a
blob alive, which ADR-0007's fence need not guard. Rejected: refusing to `put` removed bytes (a
resubmitted file would fail). Details: notes.md#revive

### D11 · Events expire through the existing prune

GC, delete and `agentctl events prune` remove events through `TableTransport.prune`, which advances
the log's retained base, so `agentctl tail` reports *expired*, not a gap. `prune` gains the
caller's connection, a row limit and reference marking, so it joins D6's batch. ADR-0009 asks
for "time-based partitioning or equivalent"; at one machine's volumes, batched prunes are that
equivalent, and partitioning is Phase 9 hardening. Rejected: deleting event rows directly.

### D12 · Delete-by-request: a fixed task list, redaction and a Temporal residual

`request delete` holds the request lock for its whole run (session-level, same key), and records
the request's task list in its first tombstone; it changes only those tasks (R24). It inserts a
fencing attempt row per task, so ADR-0007's fence refuses any later write by a running attempt
(R25). It deletes
checkpoints, prunes events, empties artifacts, and redacts results and content tables; tasks,
attempts and usage stay (notes.md#redact). `--force` covers closed Workflows (R21). Temporal keeps
summaries, questions and outcomes for `TEMPORAL_RETENTION` (72 hours) and in backups; §4.13 never
rewrites history, and the threat model records it. Rejected: moving that text behind blobs now.

## Assumptions

- The data volume is small (one machine), so the backfill runs inside the migration.
- `agent_sessions` rows belong to one task, through `session_id` (notes.md#redact; phase 02 task 3.1).
- An operator running the CLI is the only actor; `audit_log.actor` records `cli:<OS user>`.

## Risks

- A writer skips the index and GC removes a blob in use → one helper for every writer, uploads held
  by their task, and `gc` refuses while any reference is unindexed (D4).
- The class migration mislabels a table → notes.md#d3 is the one source, and a test checks every
  `APP_TABLES` entry (the list of application tables) against it.
- The app role owns `audit_log`, so it can `TRUNCATE` it or disable the trigger → accepted until a
  separate owner role (Phase 9); R14 stops ordinary updates and deletes.
- Backups hold prompts and outputs in clear text → `backups/` is git-ignored, and the threat model
  records it as accepted until Phase 9 (no encryption at rest).

## Rollout & rollback

Run `make backup`, let open Workflows finish (or cancel them), since blobs named only in their
state would have no index row, stop the workers and every `agentctl` process, then run migration 0007: it adds
the tables and columns, backfills the index, `ended_at` and `last_put_at` (set to the migration
time), remaps classes and changes the defaults. Then start the new workers and use the new CLI. A
worker started too early writes unindexed references; `reconcile --reindex` repairs them, and `gc`
refuses until then. Downgrade drops the new tables and columns and maps classes back; it works only
before new code writes anything and with no Workflow running, since old code cannot decode the new
classes. Otherwise roll back by restoring the pre-migration backup. Nothing is deleted unless an
operator runs a command.

## Open questions

- None

## Impact

- Packages / directories: `common/persistence/`, `common/blob_store/`, `common/schemas/`,
  `common/events/`, `harness_activity/`, `orchestrator/` (CLI, submit), `infra/` (Makefile
  targets, restore script, `db/` init scripts and their Compose mounts), `tests/`, `.github/` (CI drill step), `docs/` (schemas, runbook, threat model, as-built overview).
- Data: new `blob_refs`, `audit_log`; the new columns; `retention_class` values, defaults and
  checks on every application table; the bucket.
- Jobs / APIs: `agentctl gc`, `request delete`, `reconcile`, `backup`; `make backup`, `make
  restore`; the `BlobStore.put` signature. Workflow code is unchanged; it decodes the widened
  `RetentionClass`.

## Links

- `docs/roadmap/phases/phase-3a.md`: Phase 3A tasks 1, 2, 9 and 10 (schema, BlobStore and Claim
  Check, retention and deletion, backup drill).
- `docs/roadmap/design-decisions.md` §4.13: classes, deletion and the backup drill.
- `docs/security/threat-model.md`: where the accepted risks are recorded.
- Issue #92: Phase 3A tracking issue (the plan split and the project owner's decisions).
- Issue #74: remove blobs left unreferenced by stale attempts.
- ADR-0007: fenced attempt writes; why stale attempts leave unreferenced blobs.
- ADR-0009: events in a PostgreSQL table, pruned with a retained base (D11).
- ADR-0010: the durable inbox; its wake rows are the outbox pattern D7 relies on.

## Phases

| Phase | Title | Delivers | Status | Tasks |
| --- | --- | --- | --- | --- |
| 01 | Reference index, classes, audit log and the payload guard | R1, R2, R4, R5, R14, R18, R19, R20 | done | 13/13 |
| 02 | GC and delete-by-request | R3, R6, R7, R8, R9, R10, R11, R12, R13, R15, R21, R22, R24, R25 | done | 10/10 |
| 03 | Backup, restore, reconciliation and acceptance | R16, R17, R23 | done | 7/7 |

## Decision log

- 2026-11-20 · phase 02 apply: `request delete` takes its task locks without waiting and retries,
  because a message write takes the task lock before the request lock; `--force` also accepts a
  Workflow Temporal no longer knows; a dry run is one transaction rolled back at the end. Mechanics
  within R21 and D12 (notes.md#redact, notes.md#d6); no requirement or decision changed.
- 2026-11-21 · phase 02 impl-review round 2: a delete marks its tasks' uploads in its capped
  later batches, the fencing row being the delete's mark (F125, F146); a delete refuses while a
  reference of its tasks is unindexed, as gc does (F144). Mechanics within D4 and D12
  (notes.md#redact); no requirement or decision changed.

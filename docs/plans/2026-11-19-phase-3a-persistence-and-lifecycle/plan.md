---
title: Phase 3A persistence and data lifecycle - blob references, retention, deletion and backup
status: draft
created: 2026-11-19
updated: 2026-11-19
design_review: { status: none, rounds: 0, last: null }
approved: null
adr_review: null
---

# Phase 3A persistence and data lifecycle - blob references, retention, deletion and backup

## Summary

The first of three Phase 3A plans. Stored data finally gets a lifecycle. Every row that names a
blob also writes a row in a new blob reference index, in the same transaction (R1, R2). With
that index, an operator command removes expired blobs and rows by retention class (R5-R8) and
deletes everything a request stored (R10-R12). Each removal leaves an append-only audit record
(R13). Reading a removed blob then reports *expired*, not *missing* (R9). `make backup` and
`make restore` cover both PostgreSQL databases and SeaweedFS, and a reconciliation report lists
what a restore left inconsistent (R15-R17). A guard test keeps large payloads out of Temporal
histories (R18). Main risk: one blob can be shared by several tasks, because keys are content
hashes, so deleting too much is the failure that matters. Only an index with no remaining
reference may remove a blob, and every command can run as a dry run first.

```text
writer --one transaction--> row with BlobRef + blob_refs row
agentctl gc / delete --> blob_refs (still referenced?) --> SeaweedFS delete --> audit_log
make backup --> pg_dump (praxismesh, temporal, temporal_visibility) + bucket copy
make restore --> clean stack --> agentctl reconcile (dangling refs, orphaned blobs)
```

## Why

Phases 1 and 2 record a retention class on every blob and row from its first write (§4.13), but
nothing ever removes anything. Three problems follow:

- **Storage only grows.** Checkpoint snapshots, sessions and events stay forever. Issue #74:
  a stale harness attempt can upload blobs nothing references, and they are never removed
  (ADR-0007 records why they exist).
- **References are not queryable.** A blob is named inside JSON columns of four tables (notes.md#refs).
  No query can answer "is this blob still used?", and because keys are content hashes, two
  tasks storing the same bytes share one object. Deleting safely needs that answer first.
- **Nothing can be deleted on request or restored after a loss.** §4.13 asks for
  delete-by-request with audit tombstones, and for one backup and restore procedure with a
  reconciliation pass, exercised as a drill in Phase 3A.

The owner split Phase 3A into three plans on 2026-11-19; this is the first. Plans C (request
Workflow, triage, delivery modes) and D (planning, DAG dispatch, routing) add their own tables
when they first need them (D1). **Size:** L. **Hardware:** none beyond the Compose stack (the
fake model is enough). **Owner inputs:** the retention lifetimes (D3), decided 2026-11-19.

## What changes

- New table `blob_refs`, written by every writer of a `BlobRef` column, and backfilled for rows
  written before it.
- Retention classes change to §4.13's: `ephemeral`, `checkpoint`, `transcript`, `artifact`,
  `audit`. Existing rows and blobs move to the new classes.
- New table `audit_log`, append-only.
- `BlobStore` gains `BlobExpired`, raised for a blob that a removal recorded.
- New `agentctl` commands: `gc`, `request delete`, `reconcile`, each with `--dry-run`.
- New `make backup` and `make restore`.
- A Claim Check guard test over Workflow histories, and a cap on `questions`.

### Non-goals

- Delete-by-conversation: conversations arrive with the Phase 4 gateway (owner, 2026-11-19).
- Presigned or link-based artifact retrieval: nothing hands a link to a client before Phase 4
  (owner, 2026-11-19). Retrieval stays `agentctl task output`, scoped to the named task.
- Ceph and GCS adapters: SeaweedFS only (owner, 2026-11-19).
- Encryption at rest: recorded as an accepted risk until Phase 9 (owner, 2026-11-19).
- Scheduled GC and scheduled backups: Phase 7 (Kubernetes CronJobs) and Phase 9 hardening.
- A general outbox: the wake rows of Phase 2 already follow the pattern; nothing else in 3A crosses
  services (D7).
- Requests, plans, revisions and budget tables: plans C and D (D1).

## Terms

- **Blob**: bytes in SeaweedFS under a content key `sha256/<hex>`; a **`BlobRef`** names one.
- **Owner (of a reference)**: the row that stores a `BlobRef`, named by table, key and column.
- **Reference index**: the `blob_refs` table, one row per stored reference.
- **Retention class**: the lifetime label each blob and row carries (D3).
- **Ended task**: a task whose `tasks.status` is `succeeded`, `failed` or `needs_input`.
- **Expiry**: when a reference or row may be removed: the task's end time plus its class's lifetime.
- **Safety window**: how long an unreferenced blob is kept after upload (D5).
- **Tombstone**: an `audit_log` row that records a removal, without the removed content.
- **Redact**: replace a content column's value with a fixed marker, keeping the row.
- **Reconciliation**: a read-only check that compares rows, the index and the bucket.
- **App role**: the database role the workers and CLI use.

## Requirements

### R1 · Every stored reference is indexed with its row

Each write of a `BlobRef` into a row must insert its `blob_refs` rows in the same transaction.
- **Given** a task submitted with two input files, **when** `record_task` commits, **then** `blob_refs` holds the instructions and both inputs for that task.
- **Given** a fenced checkpoint insert that the fence refuses, **when** it rolls back, **then** no `blob_refs` row for its workspace remains.

### R2 · References stored before the index are indexed

The migration that adds `blob_refs` must index every reference already stored.
- **Given** a database at migration 0006 with tasks, checkpoints, artifacts and events, **when** it is migrated, **then** `agentctl reconcile` reports no unindexed reference.

### R3 · A shared blob is kept while any reference remains

A blob is removed only when no live reference to it remains.
- **Given** two tasks that stored identical bytes, **when** one task's request is deleted, **then** the blob still reads for the other task.

### R4 · Every new blob and row gets a §4.13 class

Writers must assign the classes of D3, and the migration must move existing rows and blobs to them.
- **Given** a checkpoint written after this change, **when** its row and blob are read, **then** both carry `checkpoint`.
- **Given** a row with class `task` before the migration, **when** it is migrated, **then** it carries its table's new class from D3.

### R5 · Histories written before the change still decode

A `BlobRef` with the old class `task` must still decode in Workflow and Activity code.
- **Given** a recorded history whose payloads carry `retention_class: task`, **when** it is replayed, **then** replay succeeds.

### R6 · GC removes what has expired

`agentctl gc` must remove every reference, row and unreferenced blob whose expiry has passed.
- **Given** a task that ended 8 days ago, **when** `gc` runs, **then** its checkpoint rows, their references and the blobs left without references are removed.

### R7 · GC never removes what has not expired

`gc` never removes a row or reference before its expiry, nor a blob any live reference names.
- **Given** a running task, or one that ended 6 days ago, **when** `gc` runs, **then** its checkpoints and blobs are unchanged.
- **Given** an `audit` row of any age, **when** `gc` runs, **then** it is kept.

### R8 · Unreferenced uploads are removed only after the safety window

A blob with no reference must be removed once it is older than the safety window, and kept until then.
- **Given** a blob uploaded by a superseded attempt 25 hours ago with no reference, **when** `gc` runs, **then** it is removed (issue #74).
- **Given** an unreferenced blob uploaded 1 hour ago, **when** `gc` runs, **then** it is kept.

### R9 · A removed blob reads as expired

Reading a blob that GC or a delete removed must raise `BlobExpired`, naming the removal.
- **Given** an artifact whose blob GC removed, **when** `agentctl task output` reads it, **then** it fails with "expired" and the removal date, not "not found".

### R10 · Deleting a request removes its blobs

`agentctl request delete` must remove every reference its tasks own and every blob left without references.
- **Given** a finished request of two tasks with artifacts, **when** it is deleted, **then** none of its artifacts, checkpoints or inputs can be read.

### R11 · Deleting a request redacts its content rows

The delete must redact the request's prompt and transcript content in PostgreSQL and keep the rows (notes.md#redact).
- **Given** a deleted request, **when** its tasks, messages, sessions and tool results are read, **then** every content column holds the redaction marker, and IDs, statuses and usage remain.

### R12 · A request with a running task is not deleted

`request delete` must refuse while any task of the request has not ended.
- **Given** a request with one running task, **when** it is deleted, **then** the command fails naming that task and nothing changes.

### R13 · Every removal leaves a tombstone

Each GC or delete run must write `audit_log` rows: what was removed, why, by whom and when, never the content.
- **Given** a request delete, **when** it finishes, **then** `audit_log` holds one tombstone for the request, listing the counts of rows, references and blobs.

### R14 · The audit log is append-only

The app role must not update or delete `audit_log` rows.
- **Given** the app role, **when** it updates or deletes an `audit_log` row, **then** PostgreSQL refuses.

### R15 · GC and delete are safe to rerun

A GC or delete that stopped partway must finish correctly when run again, with one tombstone per delete.
- **Given** a delete killed after some blobs were removed, **when** it runs again, **then** it completes, and reconciliation reports nothing dangling for that request.

### R16 · Backup and restore cover all three stores

`make backup` must capture the application database, Temporal's two databases and the bucket; `make restore` must load them into a clean stack only.
- **Given** a stack with finished tasks, **when** it is backed up and restored into a new stack, **then** `agentctl task status` and `task output` work there for those tasks.
- **Given** a stack that already holds data, **when** `make restore` runs, **then** it refuses and changes nothing.

### R17 · Reconciliation reports what is inconsistent

`agentctl reconcile` must list dangling references, orphaned blobs and unindexed references, and change nothing.
- **Given** a restored backup whose bucket copy missed one blob, **when** reconcile runs, **then** it lists that reference as dangling.
- **Given** a blob in the bucket with no reference, **when** reconcile runs, **then** it lists it as orphaned with its age.

### R18 · No large payload enters a Workflow history

No Workflow history payload may exceed 64 KiB.
- **Given** the integration suite's Workflows, including a task that returns 20 questions of 500 characters, **when** their histories are checked, **then** every payload is at most 64 KiB.

## Decisions

### D1 · Tables land with the plan that first uses them

This plan adds only `blob_refs` and `audit_log`, whose first users are here. Requests go to plan
C, and plans, revisions and budgets to plan D, as `schemas.md` asks ("migrations land with the
phase that first needs them"). Rejected: all Phase 3A tables now (schema with no reader until
later plans, untestable here).

### D2 · An explicit reference index, written with its row

`blob_refs (blob_key, owner_table, owner_key, owner_column, task_id, request_id, retention_class,
expires_at)`. Writers insert into it in the same transaction as the referencing row, through one
repository helper. Rejected: scanning JSON columns at GC time (slow, and a new column is easy to
miss); a Temporal payload codec that offloads payloads transparently (replay would break once a
blob is deleted). Details: notes.md#d2

### D3 · §4.13's retention classes and lifetimes

`ephemeral` 1 day after write; `checkpoint` 7 days after the task ends; `transcript` (sessions,
events, messages, tool results, instructions and inputs) 30 days; `artifact` 90 days; `audit`
until purged. `task` stays decodable but is no longer written (R5). Owner decision 2026-11-19.
Rejected: keeping `task` and `audit` only (artifacts would never expire). Details: notes.md#d3

### D4 · Removal is an operator command with a dry run

`agentctl gc`, `request delete` and `reconcile` run on demand, print what they would do with
`--dry-run`, and work in batches of 500. `gc` refuses to run while any reference is unindexed.
Rejected: a Temporal Schedule or a worker loop now (no
scheduler is needed on one machine; Phase 7 adds a CronJob).

### D5 · A 24-hour safety window

An unreferenced blob is removed once it is older than 24 hours. An attempt uploads a blob and
then references it within one turn, and no template's `turn_timeout` exceeds 10 minutes, so a
blob still waiting for its reference is always younger than the window. Rejected: each template's
`turn_timeout` (an orphan's uploader is unknown).

### D6 · Index first, then bucket; tombstone last

A removal deletes the index and row changes in one transaction that records the blob keys it
freed in `blob_objects.removed_at`, then deletes the freed objects, then writes the tombstone. A
crash leaves only objects already marked removed, which the rerun deletes (R15). Rejected:
bucket first (a crash leaves rows naming missing blobs). Details: notes.md#d6

### D7 · No general outbox in this plan

The Phase 2 wake rows (committed with the message, drained by a dispatcher) already follow
§4.13's outbox pattern, and nothing else in Phase 3A writes to a second service. The pattern is
documented in `schemas.md`. Rejected: a generic outbox table now (no user until Phase 5's
GitHub delivery).

### D8 · Backup is two dumps and a bucket copy, restore is into a clean stack

`make backup` runs `pg_dump` of `praxismesh`, then `temporal` and `temporal_visibility`, then copies the
bucket, into `backups/<UTC time>/`. Recovery point: the time of the last manual backup (owner
2026-11-19). Restore refuses a non-empty stack and ends with `agentctl reconcile`. Rejected:
volume snapshots (not portable, need the stack stopped). Details: notes.md#d8

### D9 · A 64 KiB payload guard, enforced by a test

A test helper reads each Workflow history from the integration suite and fails on any payload
over 64 KiB (R18). `questions` is capped at 20 entries of 500 characters. Rejected: Temporal's
own limits (they warn at 512 KiB and fail at 2 MiB, too late).

## Assumptions

- The data volume is small (one machine), so the backfill runs inside the migration and batching
  at 500 is enough.
- `agent_sessions` rows belong to one task, through its `session_id` (notes.md#redact).
- An operator running the CLI is the only actor; `audit_log.actor` records `cli:<OS user>`.

## Risks

- A writer that skips the index makes GC remove a blob still in use → one helper for every
  writer; reconciliation reports unindexed references, and GC refuses to run while any exist (D4).
- The class migration mislabels a table → the D3 table in `notes.md` is the one source, and a
  test checks every `APP_TABLES` entry against it.
- A restore loads over live data → restore checks that the stack is empty first (R16).
- Backups hold prompts and outputs in clear text → `backups/` is git-ignored, and the threat
  model records it as an accepted risk until Phase 9 (no encryption at rest).

## Rollout & rollback

Migration 0007 adds `blob_refs` and `audit_log`, backfills the index and remaps classes. Its
downgrade drops both tables and maps the new classes back to `task` and `audit`. Deploy order:
migrate, then restart every worker (old workers write no index rows; reconcile reports any).
No command deletes anything unless an operator runs it.

## Open questions

- None

## Impact

- Packages / directories: `common/persistence/`, `common/blob_store/`, `common/schemas/`,
  `harness_activity/`, `orchestrator/` (CLI, submit), `infra/` (Makefile targets, backup scripts),
  `tests/`, `docs/` (schemas, runbook, threat model, as-built overview).
- Data: new `blob_refs`, `audit_log`; `blob_objects.removed_at`; `retention_class` values and
  checks on every application table; the SeaweedFS bucket.
- Jobs / APIs: `agentctl gc`, `request delete`, `reconcile`; `make backup`, `make restore`;
  no Workflow code changes beyond the schemas they decode.

## Links

- `docs/roadmap/phases/phase-3a.md`: Phase 3A tasks 1, 2, 9 and 10 (schema, BlobStore and Claim
  Check, retention and deletion, backup drill).
- `docs/roadmap/design-decisions.md` §4.13: classes, deletion and the backup drill.
- Issue #92: Phase 3A tracking issue (the three-plan split and owner decisions).
- Issue #74: remove blobs left unreferenced by stale attempts.
- ADR-0007: fenced attempt writes; why stale attempts leave unreferenced blobs.
- ADR-0010: the durable inbox; its wake rows are the outbox pattern D7 relies on.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | Reference index, classes, audit log and the payload guard | draft | 0/10 |
| 02 | GC and delete-by-request | draft | 0/7 |
| 03 | Backup, restore, reconciliation and acceptance | draft | 0/7 |

## Decision log

- None.

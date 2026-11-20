# Notes · Phase 3A persistence and data lifecycle

Evidence and mechanics behind [plan.md](plan.md). Read the plan first.

## refs

Where a `BlobRef` is stored today (migrations 0003-0005, at `cc93e4e`), all as JSON:

| Table | Column | What it names | Written by |
|---|---|---|---|
| `tasks` | `instructions_ref` | the task's instructions | `TaskRepository.record_task` |
| `tasks` | `input_refs` | input files, by workspace path | `TaskRepository.record_task` |
| `tasks` | `result` (`artifacts[].ref`) | output files | `TaskRepository.complete` |
| `checkpoints` | `workspace_ref` | workspace snapshot | `CheckpointRepository.insert`, `insert_fenced` |
| `checkpoints` | `session_ref` | DSH session archive | same |
| `checkpoints` | `finish` (`outputs[].ref`) | the finished turn's outputs | same |
| `agent_events` | `blob_ref` | an event's attached blob (unused so far) | `TableTransport.publish` |

Blobs are content-addressed (`common/blob_store/base.py`): the same bytes always get the same
key, so two tasks that upload one file share one object. `RecordingBlobStore` records every
upload in `blob_objects` (key, checksum, size, class, time).

Blobs written with no row: a stale attempt's workspace, session and artifact uploads when the
fence refuses its checkpoint (ADR-0007; issue #74). They appear only in `blob_objects`.

## d2

`blob_refs` columns: `blob_key` (FK-free, the content key), `owner_table`, `owner_key` (the
owner row's primary key as text), `owner_column`, `task_id`, `request_id`, `retention_class`,
`created_at`, `expires_at` (null until the task ends, except `ephemeral`). Primary key: owner
table, key, column and blob key, so a rewrite of the same reference is a no-op.

- **Writers** call one helper, `index_refs(conn, owner, refs, task_id, request_id, class)`,
  inside the transaction that writes the owner row. Every row in the table above gets it.
- **Expiry** is set when a task ends: `complete_task` sets `expires_at = ended_at + lifetime` for
  every reference of that task, in its own transaction. A task that never ends (a terminated
  Workflow, ADR-0010's accepted case) never expires; reconcile lists such tasks.
- **A blob is free** when it has no `blob_refs` row whose `expires_at` is null or in the future.
- **The backfill** reads the JSON columns above with PostgreSQL JSON functions, in the migration.
- **Why not a codec:** Temporal's documented claim-check pattern stores payloads outside the
  history through a payload codec. Replaying such a history fetches the blob again, so a deleted
  blob breaks replay (§4.13 deletes blobs; histories are never rewritten).

## d3

The one source for each table's and blob kind's class. A test compares it with `APP_TABLES`.

| Rows | Class | Blobs | Class |
|---|---|---|---|
| `tasks`, `task_attempts`, `usage_ledger`, `audit_log` | `audit` | instructions, input files | `transcript` |
| `checkpoints` | `checkpoint` | workspace snapshots, session archives | `checkpoint` |
| `agent_sessions`, `agent_messages`, `agent_events`, `event_logs`, `task_messages`, `task_inbox`, `idempotency_keys` | `transcript` | event attachments | `transcript` |
| `sample_orders` | `artifact` | output files (artifacts) | `artifact` |
| `event_batches`, `message_wakes` | `ephemeral` | | |
| `blob_objects`, `blob_refs` | the blob's or reference's class | | |

- Lifetimes: `ephemeral` 1 day after write; `checkpoint` 7 days, `transcript` 30 days and
  `artifact` 90 days after the task ends; `audit` until purged. Settings in
  `common/persistence/retention.py`.
- **Old values.** The migration maps each table's `task` and `audit` rows to the table's new class.
  Stored JSON `BlobRef`s keep their recorded `retention_class` (rewriting them gains nothing):
  the index row is what decides a blob's lifetime. `RetentionClass` keeps `task` as a readable
  value so recorded payloads still decode (R5); writers never use it.
- **A blob's class** in `blob_objects` is the longest-lived class of its references, as `put`
  already does for repeats. Order: `ephemeral` < `checkpoint` < `transcript` < `artifact` < `audit`.

## redact

What `request delete` does to each table, for every task of the request:

| Table | Action |
|---|---|
| `tasks` | `result.summary`, `result.questions` replaced by the marker `[deleted <date>]`; `result.artifacts` emptied; IDs, status, usage kept |
| `checkpoints` | rows deleted (their references are freed) |
| `agent_sessions`, `agent_messages` | message content replaced by the marker; rows kept |
| `task_messages` | `body` replaced by the marker |
| `idempotency_keys` | `result` replaced by the marker |
| `agent_events` | rows deleted (payloads hold no text, but offsets and names describe the work) |
| `task_attempts`, `usage_ledger` | kept unchanged (audit, no content) |

`agent_sessions.session_id` is derived from the task ID by both runners (assumption in plan.md;
checked in task 2.4).

## d6

Order of one removal batch (GC or delete):

1. One transaction: delete or redact the rows, delete their `blob_refs` rows, and set
   `blob_objects.removed_at` and `removed_by` for each blob left free.
2. Delete each freed object from the bucket. A missing object is not an error (`delete`'s contract).
3. One transaction: write the tombstone (`audit_log`), unless this run's operation ID already has one.

A crash after step 1 leaves objects marked removed but still in the bucket. The next run deletes
every object with `removed_at` set that the bucket still holds, before new work. `BlobExpired` is
raised when `blob_objects.removed_at` is set, before the bucket is asked.

## d8

`make backup` (`infra/backup.sh`), into `backups/<UTC time>/`:

1. `pg_dump -Fc praxismesh` through `docker compose exec db`.
2. `pg_dump -Fc` of `temporal` and `temporal_visibility`.
3. Copy every bucket object to `blobs/<key>` through the S3 API (boto3, already a dependency).
4. Write `manifest.json`: times, row counts, object count, migration head, versions.

Order: the application database first, so a blob uploaded after its dump is an orphan (harmless;
GC removes it) and no restored row names a blob newer than the copy. Temporal's dumps come next,
so a Workflow may be newer than the restored rows. Reconcile covers references and blobs only, as
§4.13 asks; comparing Workflows with rows is Phase 9 hardening.

`make restore BACKUP=backups/<time>` checks that `tasks` and the bucket are empty, stops Temporal,
loads the three dumps, loads the blobs, starts Temporal and runs `agentctl reconcile`.

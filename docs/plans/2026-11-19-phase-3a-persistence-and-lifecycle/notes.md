# Notes · Phase 3A persistence and data lifecycle

Evidence and mechanics behind [plan.md](plan.md). Read the plan first.

## refs

Where a `BlobRef` is stored today (migrations 0003-0006, at `cc93e4e`), all as JSON:

| Table | Column | What it names | Written by |
|---|---|---|---|
| `tasks` | `instructions_ref` | the task's instructions | `TaskRepository.record_task` |
| `tasks` | `input_refs` | input files, by workspace path | `TaskRepository.record_task` |
| `tasks` | `result` (`artifacts[].ref`) | output files | `MessageRepository.end_task`, from the `complete_task` Activity (`TaskRepository.complete` is unused) |
| `checkpoints` | `workspace_ref` | workspace snapshot | `CheckpointRepository.insert`, `insert_fenced` |
| `checkpoints` | `session_ref` | DSH session archive | same |
| `agent_events` | `blob_ref` | an event's attached blob (unused so far) | `TableTransport.publish` |

`checkpoints.finish` is `{status, summary, questions}` and names no blob.

Blobs are content-addressed (`common/blob_store/base.py`): the same bytes always get the same
key. `S3BlobStore.put` collects the whole body, then skips the upload when `head_object` finds
the key. `RecordingBlobStore.put` upserts `blob_objects` and changes only its class.

Gaps between an upload and the row that names it, today:

- **Instructions and inputs**: uploaded by `prepare_task` in the CLI, named only when the
  Workflow's `record_task` Activity runs. Unbounded if no orchestrator worker runs.
- **Artifacts**: uploaded in the harness's `_finish`, carried in Workflow state until
  `complete_task` (bounded by `max_wall_time_cap`, 1 hour, for a `waiting` turn).
- **Stale attempts**: workspace, session and artifact uploads whose fenced checkpoint is refused
  (ADR-0007; issue #74). No row ever names them.

All three are covered by upload references (d2): `prepare_task` mints the task ID before it
uploads, and the harness knows its task.

## d2

`blob_refs` columns: `blob_key` (no foreign key), `holder_table`, `holder_key` (the holder row's
primary key as text), `holder_column`, `task_id`, `request_id`, `retention_class`, `created_at`,
`expires_at`, `removed_at`, `removed_by`. Primary key: holder table, key, column and blob key, so
rewriting the same reference is a no-op. An upload reference has holder table `upload`, holder key
the task ID and an empty column.

- **Writers** call one helper, `index_refs(conn, holder, refs, task_id, request_id, class)`,
  inside the transaction that writes the holder row. Every row in the refs table gets it, and
  `RecordingBlobStore.put` writes the upload reference (revive).
- **Expiry**: `end_task` sets `tasks.ended_at` and `expires_at = ended_at + lifetime` for every
  reference the task holds, in its own transaction (R20). `ephemeral` references expire one day
  after `created_at`. An upload reference whose task has no `tasks` row 24 hours after upload
  expires then (D5).
- **Live** means `removed_at` is null. GC marks a reference removed once `expires_at` has passed;
  a delete marks its request's references removed. Marked rows stay.
- **A blob is free** when it has no live reference. It is then marked in `blob_objects` (d6).
- **Checks**, shared by migration tests, `gc` and `reconcile` (phase 01 task 1.4):
  - *unindexed*: a `BlobRef` in a refs-table column with no `blob_refs` row for that holder and key;
  - *dangling*: a live reference whose key is marked removed or missing from the bucket;
  - *orphaned*: a `blob_objects` row with no `blob_refs` row.
- **The backfill** reads the JSON columns with PostgreSQL JSON functions, in the migration. It
  sets `tasks.ended_at` from `updated_at` for ended tasks, then each reference's expiry.
- **Reindex**: `reconcile --reindex` runs the same backfill query for unindexed references only;
  rerunning it is a no-op.
- **Why not a codec:** Temporal's documented claim-check pattern stores payloads outside the
  history through a payload codec. Replaying such a history fetches the blob again, so a deleted
  blob breaks replay (§4.13 deletes blobs; histories are never rewritten).

## d3

The one source for each table's and blob kind's class, and for when a row expires. A test compares
it with `APP_TABLES`.

| Rows | Class | Expires from |
|---|---|---|
| `tasks`, `task_attempts`, `usage_ledger`, `audit_log` | `audit` | never |
| `checkpoints` | `checkpoint` | its task's `ended_at` |
| `agent_sessions` (`session_id` = task ID), `agent_messages` (through its session) | `transcript` | the task's `ended_at` |
| `event_logs`, `agent_events` (`workflow_id` = task ID) | `transcript` | the task's `ended_at`, through prune (D11) |
| `task_messages` | `transcript` | the later `ended_at` of sender and recipient |
| `task_inbox`, `idempotency_keys` (`task_id`) | `transcript` | the task's `ended_at` |
| `sample_orders` | `artifact` | its task's `ended_at` |
| `event_batches`, `message_wakes` | `ephemeral` | `created_at` |
| `blob_objects`, `blob_refs` | the blob's or reference's class | with its references |

| Blobs | Class |
|---|---|
| instructions, input files, event attachments | `transcript` |
| workspace snapshots, session archives | `checkpoint` |
| output files (artifacts) | `artifact` |

- Lifetimes: `ephemeral` 1 day, `checkpoint` 7 days, `transcript` 30 days, `artifact` 90 days,
  `audit` kept. Settings in `common/persistence/retention.py`. A row of a task that never ended
  never expires; reconcile lists such tasks.
- **Defaults and checks.** Migration 0007 sets each table's server default to its class above:
  the event, message, sample and SDK session inserts rely on defaults, and checkpoint inserts stop
  hardcoding `'task'`. Every check allows the five classes plus `task`, so an old worker started
  by mistake still inserts; a later migration drops `task` once nothing writes it.
- **Old values.** The migration maps each table's `task` and `audit` rows to the table's class.
  Each `blob_objects` row gets the longest-lived class of its index rows after the backfill, or
  `ephemeral` for an orphan. Stored JSON `BlobRef`s and S3 object metadata keep their recorded
  class: the index decides lifetimes.
- **Order:** `ephemeral` < `checkpoint` < `transcript` < `artifact` < `audit`. `RETENTION_ORDER`
  gives `task` the rank of `transcript`, and `stronger` returns `transcript` for it, so a repeat
  `put` of bytes first stored as `task` never yields a `task` ref. `RetentionClass` keeps `task`
  so recorded payloads still decode (R5); writers never use it.

## revive

`RecordingBlobStore.put(data, class, task)`:

1. Collect the bytes and compute the key.
2. One transaction: `INSERT ... ON CONFLICT DO UPDATE` on `blob_objects` (row locked), clearing
   `removed_at` and setting `last_put_at = now()`; insert the task's upload reference. Note whether
   the key was marked.
3. Upload to the bucket: always if the key was marked or new, otherwise only if `head_object`
   misses (the existing skip).

The bucket step of a removal (d6) locks the same row, re-reads it, and deletes the object only if
`removed_at` is still set and `last_put_at` is older than `removed_at`, holding the lock until the
delete returns. The cases:

- *Resubmitted bytes after a delete*: step 2 clears the mark; step 3 uploads; the next `gc` sees a
  live upload reference.
- *`put` between a removal's transaction and its bucket delete*: the bucket step sees the mark
  cleared and skips.
- *Bucket delete first*: step 2 waits for the lock, finds the mark, and step 3 uploads again.
- *An old orphan uploaded again*: `last_put_at` restarts the safety window, and the upload
  reference keeps it live.

`last_put_at` is backfilled from `created_at`. Removal never calls `RecordingBlobStore.delete`,
which deletes the `blob_objects` row; it calls the inner store.

## redact

What `request delete` does to each table, for every task of the request:

| Table | Action |
|---|---|
| `tasks` | `result.summary`, `result.questions` and `result.failure_reason` replaced by the marker `[deleted <date>]`; `result.artifacts` emptied; IDs, status, usage, `instructions_ref` and `input_refs` kept (their references marked removed) |
| `checkpoints` | rows deleted (their references marked removed) |
| `agent_sessions`, `agent_messages` | message content replaced by the marker; rows kept |
| `task_messages` | `body` replaced by the marker |
| `idempotency_keys` | `result` replaced by the marker |
| `agent_events`, `event_logs` | pruned to the end of the log (D11): offsets and names describe the work |
| `task_attempts`, `usage_ledger` | kept unchanged (audit, no content) |

- The delete takes the request lock (`_REQUEST_LOCK` in `common/persistence/messages.py`), which
  `end_task` and messaging already take, then checks that every task has ended (R12). A joining
  task is checked only by `request_exists` today, so `record_task` takes the lock too.
- With `--force`, a task that has not ended counts as ended when Temporal's `describe` reports
  its Workflow closed (terminated, cancelled, timed out). The delete then sets the task to
  `failed` with `ended_at` now, in the same batch.
- `agent_sessions.session_id` is the task ID on both runners (assumption; phase 02 task 3.1).
- **Residual**: Temporal histories keep each turn's summary, questions and outcome for
  `TEMPORAL_RETENTION` (72 hours) after the Workflow closes, and in every backup taken before.
  The threat model records it (phase 01 task 4.1).

## d6

Order of one removal batch (GC or delete), at most 500 rows:

1. One transaction: delete, prune or redact the rows; mark their references removed; for each
   blob left with no live reference, lock its `blob_objects` row, re-check, and set `removed_at`
   and `removed_by` (the operation ID); write the batch's tombstone (`audit_log`: action, subject,
   reason, actor, time, operation ID, counts of rows, references and blobs).
2. For each marked blob, the bucket step in revive. A missing object is not an error.

A run first finishes every marked blob still in the bucket, from earlier runs, before new work.
A run's tombstones share its operation ID; counts are per batch, so nothing is counted twice
across a rerun. `BlobExpired` is raised when `removed_at` is set, before the bucket is asked;
`agentctl task output` reads through `RecordingBlobStore` for this.

## d8

`make backup` (`infra/backup.sh`), into `backups/<UTC time>/`, holding the D4 advisory lock:

1. `pg_dump -Fc praxismesh` through `docker compose exec db`.
2. `pg_dump -Fc` of `temporal` and `temporal_visibility`.
3. Copy every bucket object to `blobs/<key>` through the S3 API (boto3, already a dependency).
4. Write `manifest.json`: times, row counts, object count, migration head, versions.

Order: the application database first, so a blob uploaded after its dump is an orphan (harmless;
GC removes it) and no restored row names a blob newer than the copy. The lock keeps removals out
between the dump and the copy. Temporal's dumps come next, so a Workflow may be newer than the
restored rows. Reconcile covers references and blobs only, as §4.13 asks; comparing Workflows with
rows is Phase 9 hardening.

`make restore BACKUP=backups/<time>`:

1. Refuse unless `tasks` is missing or empty and the bucket is empty (R23).
2. Stop the workers and Temporal.
3. Drop and recreate `praxismesh`, `temporal` and `temporal_visibility` with their owner roles,
   then `pg_restore` each dump.
4. Load the blobs, start Temporal and the workers, and run `agentctl reconcile`.

A failure after step 3 starts leaves a partial load, which step 1 then refuses; `make reset`
clears the stack, and restore runs again.

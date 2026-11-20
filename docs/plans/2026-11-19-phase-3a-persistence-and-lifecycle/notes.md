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
the key, and rewrites the object's class metadata through `copy_object` when a stronger class is
asked for. `RecordingBlobStore.put` uploads first, then upserts `blob_objects`, changing only its
class.

Gaps between an upload and the row that names it, today:

- **Instructions and inputs**: uploaded by `prepare_task` in the CLI, named only when the
  Workflow's `record_task` Activity runs. Unbounded if no orchestrator worker runs.
- **Artifacts**: uploaded in the harness's `_finish`, carried in Workflow state until
  `complete_task` (bounded by `max_wall_time_cap`, 1 hour, for a `waiting` turn).
- **Stale attempts**: workspace, session and artifact uploads whose fenced checkpoint is refused
  (ADR-0007; issue #74), possibly after the task has ended. No row ever names them.

All three are covered by upload references (d2). The harness knows its task; `prepare_task`
today mints the task ID after uploading, and phase 01 task 2.2 moves it first.

## d2

`blob_refs` columns: `blob_key` (no foreign key), `holder_table`, `holder_key` (the holder row's
primary key as text), `holder_column`, `task_id`, `request_id` (null for upload references), `retention_class`, `created_at`,
`removed_at`, `removed_by`. Primary key: holder table, key, column and blob key. An upload
reference has holder table `upload`, holder key the task ID and an empty column. On conflict the
stronger class wins, as `blob_objects` already does for its class, and a GC mark is cleared; a
mark set by a delete (`removed_by` names a delete operation) stays, so a late upload by a deleted
task never makes its reference live again (R25).

- **Writers** call one helper, `index_refs(conn, holder, refs, task_id, request_id, class)`,
  inside the transaction that writes the holder row. Every row in the refs table gets it, and
  `RecordingBlobStore.put` writes the upload reference (revive).
- **Expiry is computed, never stored.** A live reference is expired when:
  - its task has `ended_at` and `ended_at + lifetime(class)` is past; or
  - its class is `ephemeral` and `created_at` is more than a day ago; or
  - it is an upload reference, its task has no `tasks` row, its `blob_objects.last_put_at` is
    more than 24 hours ago, and Temporal's `describe` of the Workflow (ID = task ID) reports it
    missing or closed (D5).

  A reference written after its task ended (a stale attempt's late upload) therefore expires
  with the rest of the task.
- **Live** means `removed_at` is null. GC marks expired references removed; a delete marks the
  references of its fixed task list. Marked rows are never deleted.
- **A blob is free** when it has no live reference. It is then marked in `blob_objects` (d6).
- **Checks**, shared by migration tests, `gc` and `reconcile` (phase 01 task 1.4):
  - *unindexed*: a `BlobRef` in a refs-table column with no `blob_refs` row for that holder and key;
  - *dangling*: a live reference whose key is marked removed or missing from the bucket;
  - *orphaned*: a bucket object (from a listing) with no `blob_refs` row, aged by
    `blob_objects.last_put_at` or, for an object with no `blob_objects` row, its `LastModified`.
- **The backfill** reads the JSON columns with PostgreSQL JSON functions, in the migration. Each
  index row's class comes from d3's blob table by holder table and column, never from the JSON
  (old artifacts say `audit`; old inputs say `task`). It sets `tasks.ended_at` from `updated_at` for ended tasks, and `blob_objects.last_put_at` to the
  migration time: the old `put` never recorded a repeat upload, so an older time could be wrong.
- **Reindex**: `reconcile --reindex` runs the same backfill query for unindexed references only,
  and inserts a `blob_objects` row (`last_put_at` = now) for each bucket object that has none;
  rerunning it is a no-op.
- **Fence:** the upload reference is written outside ADR-0007's fence. It can only keep a blob
  alive until its task's expiry; it never changes a checkpoint, a result or a turn's outcome.

## d3

The one source for each table's class and expiry anchor. A test compares it with `APP_TABLES`.

| Rows | Class | Expires from |
|---|---|---|
| `tasks`, `task_attempts`, `usage_ledger`, `audit_log` | `audit` | never |
| `checkpoints` | `checkpoint` | its task's `ended_at` |
| `agent_sessions` (`session_id` = task ID), `agent_messages` (through its session) | `transcript` | the task's `ended_at` |
| `event_logs`, `agent_events` (`workflow_id` = task ID) | `transcript` | the task's `ended_at`, through prune (D11) |
| `task_messages` | `transcript` | the later `ended_at` of sender and recipient |
| `task_inbox`, `idempotency_keys` (`task_id`) | `transcript` | the task's `ended_at` |
| `sample_orders` | `artifact` | its task's `ended_at` |
| `message_wakes` | `ephemeral` | the recipient task's `ended_at` (ADR-0010: kept until delivered) |
| `event_batches` | `ephemeral` | the task's `ended_at` (`publish` prunes a log's rows after 600 s only on its next publish) |
| `blob_objects`, `blob_refs` | the blob's or reference's class | never deleted; marked removed |

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
  `ephemeral` for an orphan. Stored JSON `BlobRef`s keep their recorded class.
- **S3 metadata.** The adapter still writes a class into object metadata and may rewrite it
  (`copy_object`), but nothing reads it to decide a lifetime: the index and `blob_objects` do.
- **Order:** `ephemeral` < `checkpoint` < `transcript` < `artifact` < `audit`. `RETENTION_ORDER`
  gives `task` the rank of `transcript`, and `stronger` returns `transcript` for it, so a repeat
  `put` of bytes first stored as `task` never yields a `task` ref. `RetentionClass` keeps `task`
  so recorded payloads still decode (R5); writers never use it.

## revive

`BlobStore.put(data, *, content_type, retention, task_id=None)`: the protocol, `S3BlobStore`,
`MemoryBlobStore` and `RecordingBlobStore` all take the new argument. `RecordingBlobStore.put`:

1. Collect the bytes and compute the key.
2. One transaction, locking `blob_objects` before `blob_refs` (the order every removal uses too):
   upsert `blob_objects` (row locked), clearing `removed_at` and `bucket_deleted_at` and setting
   `last_put_at = now()`; upsert the task's upload reference (d2: a delete's mark stays).
3. Upload through the inner store. If the bucket step already deleted the object, `head_object`
   misses and the bytes go up; if it has not, it will see the cleared mark and skip.

The bucket step of a removal (d6) locks the same row, re-reads it, and deletes the object only if
`removed_at` is still set, holding the lock until the delete returns, then sets
`bucket_deleted_at`. No timestamp comparison is needed: a `put` that committed first has cleared
the mark. The cases:

- *Resubmitted bytes after a delete*: step 2 clears the mark; step 3 uploads; the next `gc` sees a
  live upload reference.
- *`put` between a removal's transaction and its bucket delete*: the bucket step sees the mark
  cleared and skips.
- *Bucket delete first*: step 2 waits for the lock, finds the mark, and step 3 uploads again.
- *An old orphan uploaded again*: `last_put_at` restarts the safety window, and the upload
  reference keeps it live.

Removal never calls `RecordingBlobStore.delete`, which deletes the `blob_objects` row; it calls the
inner store.

## redact

What `request delete` does to each table, for every task in its fixed list:

| Table | Action |
|---|---|
| `tasks` | `result.summary` replaced by the marker `[deleted <date>]`; `result.questions` replaced by `["[deleted <date>]"]` if not empty; `result.failure_reason` replaced by the marker only if set; `result.artifacts` emptied; IDs, status, usage, `instructions_ref` and `input_refs` kept (their references marked removed) |
| `checkpoints` | rows deleted (their references marked removed) |
| `agent_sessions`, `agent_messages` | message content replaced by the marker; rows kept |
| `task_messages` | `body` replaced by the marker |
| `idempotency_keys` | `result` replaced by the marker |
| `agent_events`, `event_logs` | pruned to the end of the log (D11): offsets and names describe the work |
| `sample_orders`, `task_inbox`, `message_wakes` | rows deleted |
| `task_attempts` | kept, plus one fencing row per task (below) |
| `usage_ledger` | kept unchanged (audit, no content) |

The markers keep `TaskResult` valid, so `agentctl task output` still reads the row.

- **Lock and task list.** The delete opens a dedicated connection and takes
  `pg_advisory_lock(2, hashtext(REQ))`, the session form of `_REQUEST_LOCK` in
  `common/persistence/messages.py`; the two forms conflict, so `end_task`, messaging and a joining
  `record_task` (which takes the lock too; today a join is checked only by `request_exists`) wait
  until the delete ends. Under the lock it reads the request's tasks, checks they have ended (R12),
  and writes the list into its first tombstone. Every batch selects by that list, never by
  `request_id`, so a joining task's upload references, written before its `tasks` row, are untouched.
- **Fence.** The first batch inserts, for each task, a `task_attempts` row with a turn and attempt
  above any existing one and status `deleted`. ADR-0007's fence (`NO_NEWER_ATTEMPT`) then refuses
  every later checkpoint, event and message write by a still-running attempt (R25).
- **`--force`**: a task that has not ended counts as ended when Temporal's `describe` reports its
  Workflow closed (terminated, cancelled, timed out). The delete then sets the task to `failed`
  with `ended_at` now, in the first batch.
- `agent_sessions.session_id` is the task ID on both runners (assumption; phase 02 task 3.1).
- **Residual**: Temporal histories keep each turn's summary, questions and outcome for
  `TEMPORAL_RETENTION` (72 hours) after the Workflow closes, and in every backup taken before.
  The threat model records it (phase 01 task 4.1).

## d6

Order of one removal batch (GC or delete), at most 500 rows:

1. One transaction: lock the `blob_objects` rows of every key the batch's references name, in key
   order (the order `put` uses); delete, prune (`prune(conn=..., limit=...)`, both optional so
   `MemoryTransport` and the `EventTransport` protocol still fit) or redact the rows; mark their
   references removed; for each blob left with no live reference set `removed_at` and `removed_by`
   (the operation ID); write the batch's tombstone (`audit_log`: action, subject, reason, actor,
   time, operation ID, counts of rows, references and blobs).
2. For each marked blob, the bucket step in revive. A missing object is not an error.

A run first finishes every blob with `removed_at` set and `bucket_deleted_at` null, from earlier
runs, before new work; that set stays small. A run's tombstones share its operation ID; counts are
per batch, so nothing is counted twice across a rerun. `BlobExpired` is raised when `removed_at` is
set, before the bucket is asked; `agentctl task output` reads through `RecordingBlobStore` for this.

The existing `agentctl events prune` becomes a removal through this engine: it takes the D4 lock
and `--dry-run`, its events' references are marked and each batch gets a tombstone.

## d8

`agentctl backup` (behind `make backup`), into `backups/<UTC time>/`. It holds the D4 lock on its
own connection for the whole run:

1. Stop the worker services (`docker compose stop`), so no Activity changes rows or Workflows
   between the dumps.
2. `pg_dump -Fc` of `praxismesh`, `temporal` and `temporal_visibility` through
   `docker compose exec db`, then start the workers again.
3. Copy every bucket object to `blobs/<key>` through the S3 API (boto3, already a dependency).
4. Write `manifest.json`: times, row counts, object count, migration head, versions.

Order: the application database first, so no restored row names a blob newer than the copy. A blob
uploaded after the dump is restored as a bucket object with no row: an orphan by the bucket listing
(d2), which `gc` removes after the window. The lock keeps removals out between the dump and the
copy. With the workers stopped, no Workflow advances between the dumps. Reconcile covers
references, blobs and unended tasks whose Workflow is closed; a full comparison of every Workflow
with its rows is Phase 9 hardening.

`make restore BACKUP=backups/<time>` (`infra/restore.sh`):

1. Refuse unless `tasks` is missing or empty, Temporal's API lists no Workflow in the app's
   namespace (system namespaces ignored; no SQL on Temporal's databases, ADR-0002), and the
   bucket is empty (R23).
2. Stop the workers and Temporal.
3. Drop `praxismesh`, `temporal` and `temporal_visibility`, then run `infra/db/databases.sh`: the
   `CREATE DATABASE`, `REVOKE`/`GRANT CONNECT` and extension statements, moved out of `init.sh`
   (which runs them once through it; Compose mounts it next to `init.sh`). Then run `roles.sh` (already rerunnable) and `pg_restore`
   each dump.
4. Load the blobs, start Temporal and the workers, and print `agentctl reconcile`'s report; its
   findings are information, so restore does not fail on its exit status.

A failure after step 3 starts leaves a partial load, which step 1 then refuses; `make reset`
clears the stack, and restore runs again.

**The drill** is `make drill`, opt-in and never part of `make smoke`, because it runs `make reset`.
It needs a stack started with `make up`: it backs up, resets, runs `make up`, restores into the same
project and checks the result. CI runs it as its own step in the `stack` job, after the smoke
tests, so the job starts no second stack (its budget is 45 minutes, about 32 used).

<!-- Verbatim subagent report (Phase 3A persistence plan design-review round 2, codebase fit, at c6efe44); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged with save-report). -->

Review of /home/geo/develop/praxismesh/docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle (plan.md, phases 01-03, notes.md) against the code at fa87484

Verdict: 8 Major findings and 10 Nits. No Blockers. Most claims about the code are accurate. These all check out:
- `TaskRepository.complete` has no callers.
- `S3BlobStore.put` collects the body and skips the upload when `head_object` finds the key.
- `RecordingBlobStore.put` upserts and changes only the class.
- `finish_task_body` cuts the summary to 2,000 characters (tools.py:222), and it is the only place that sets `state.finish`, so both runners go through it.
- The replay fixture carries exactly 3 `retention_class: task` payloads.
- `agent_events.blob_ref` is never set.
- `max_wall_time_cap` is PT1H and `TEMPORAL_RETENTION` is 72h.
- `_REQUEST_LOCK` exists, `request_exists` is the only check on a join, and the next migration number is 0007.

## Major

**M1. The request lock ends with each transaction, but the delete commits in batches.** (Decisions › D12, D4; notes.md#redact)
- The lock is `pg_advisory_xact_lock(2, hashtext(:r))` (common/persistence/messages.py:32), so it is released at every commit.
- D4 commits "in batches of at most 500 rows". So "takes the existing request lock, so no task joins or ends mid-delete" holds only inside one batch.
- A task can join between batches; `record_task` takes the lock only for its own transaction. If later batches select by request, they redact or remove a running task's data, after R12's check already ran in the first batch.
- Fix: the plan should require a session-level lock on the same key for the whole delete (it conflicts with the xact form), or one transaction for the ended-task check plus a fixed task list.

**M2. D11's prune cannot join D6's single transaction per batch.** (D11 vs D6; phase 02 task 1.4)
- `TableTransport.prune` opens its own `async with self.engine.begin()` (common/events/table.py:162-198), and the `EventTransport` protocol has no connection parameter (transport.py:101-108).
- D6 needs rows, reference marks, blob marks and the tombstone in one transaction. If events are pruned through the current `prune`, a crash between the prune and the batch leaves events deleted with no tombstone and their `blob_refs` still live, which breaks R13.
- The plan should state that `prune` gains a variant that runs on the caller's connection and marks the events' references removed.

**M3. GC deletes pending wake rows, which contradicts ADR-0010 (accepted).** (notes.md#d3: "`event_batches`, `message_wakes` | `ephemeral` | `created_at`"; Open questions says "None")
- ADR-0010 says a wake row is "committed with the message and kept until its Signal is accepted" and "wake rows wait for a stopped dispatcher" (docs/adr/0010-wake-agents-through-a-durable-inbox.md, around lines 61 and 87).
- Removing `message_wakes` one day after `created_at` drops wakes the dispatcher has not delivered yet. The sleeper then wakes only at its next deadline or timeout.
- Fix: either expire wake rows only once the recipient task has ended, or record the deviation under Open questions.

**M4. References written after `end_task` never get an expiry, so stale-attempt uploads can still leak (issue #74).** (notes.md#d2 "Expiry"; R6, R20; phase 01 task 2.3)
- Expiry is set only inside `end_task`.
- Upload references from `RecordingBlobStore.put` are unfenced. A stale attempt can still upload after the task ended: harness_activity/activity.py:536 puts the workspace before `insert_fenced`.
- `insert_fenced` also succeeds after the end if no newer attempt exists, for example after `schedule_to_close` with `close_unfinished`.
- Those rows get `expires_at` NULL, so GC never removes them, and reconcile does not list them.
- Related: if `put` inserts an upload reference `ON CONFLICT DO NOTHING` over one already marked removed, the blob ends up live in `blob_objects` with no live reference. No later batch would mark it, so it leaks.
- The plan should require `index_refs` and `put` to set `expires_at` from `tasks.ended_at` when it is already set, and to clear the removal mark on conflict.

**M5. D5 treats "no `tasks` row after 24 h" as "never started", which can delete blobs a task still needs.** (D5; notes.md#d2 "An upload reference whose task has no tasks row 24 hours after upload expires then")
- The notes themselves say the gap before `record_task` is "Unbounded if no orchestrator worker runs" (notes.md#refs).
- A Workflow that started while the orchestrator worker was down for more than 24 hours loses its instructions and inputs to GC. When the worker returns, `record_task` indexes references to removed blobs and the turn fails with `BlobExpired`. That is the plan's stated main risk.
- Fix: GC can ask Temporal `describe` before expiring a row-less upload reference, as `--force` already does in R21.

**M6. A rerun cannot tell which marked blobs are still in the bucket.** (D6 "A rerun first finishes marked blobs still in the bucket"; notes.md#d6; phase 02 task 1.2)
- notes.md#d2 and #revive add only `removed_at`, `removed_by` and `last_put_at`.
- Marked rows are kept forever, because `BlobExpired` needs them. So with no "bucket deleted" field or completed-run record, every `gc` or delete must HEAD or delete every blob ever removed. That work grows without bound.
- The plan should add the missing state, for example a `bucket_deleted_at` column or a per-operation completion row.

**M7. Bucket-only objects are never treated as orphans.** (Terms "Orphaned: a blob with no index row"; notes.md#d2 "*orphaned*: a `blob_objects` row with no `blob_refs` row"; notes.md#d8)
- notes.md#d8 says "a blob uploaded after its dump is an orphan (harmless; GC removes it)".
- After a restore, such an object has no `blob_objects` row, because the dump predates it. Under the d2 definition, neither `gc` (R8) nor `reconcile` (R17) ever sees it.
- The plan should either define orphans as bucket keys with no live reference (which needs a bucket listing) or correct the claim in d8.

**M8. Restore's drop-and-recreate loses the database-level setup from init.sh and roles.sh.** (D8; notes.md#d8 restore step 3)
- infra/db/init.sh creates the three databases from `template0`, runs `REVOKE CONNECT ... FROM PUBLIC` and `GRANT CONNECT` to `temporal` and `praxismesh`.
- infra/db/roles.sh runs `GRANT CONNECT ON DATABASE praxismesh TO praxis_comms`.
- `pg_restore` without `--create` does not restore database-level grants. A plain `CREATE DATABASE ... OWNER` gives PUBLIC CONNECT again, and `praxis_comms` (comms_mcp) loses CONNECT.
- R16's check (`task status` and `task output` only) would not catch this.
- The restore step should replay those statements (or use `pg_restore --create`), and the drill should also exercise comms_mcp.

## Nits

- **notes.md#d3, `event_batches`:** the table has no `created_at`; its timestamp column is `seen_at` (migration 0005). Publish already deletes these rows after 600 s (table.py:84-89).
- **notes.md#redact and R11:** "`result.questions` ... replaced by the marker" is ambiguous. `TaskResult.questions` is `list[str]` and `failure_reason` is `str | None` (common/schemas/task.py:105-106), and `task output` calls `TaskResult.model_validate(row["result"])` (orchestrator/cli.py:128). A string, or a marker where `failure_reason` was None, would break validation or change its meaning.
- **phase 03 task 3.2:** the demo asks for "a delete with its tombstone and expired read", but a delete empties `result.artifacts` (notes.md#redact). `task output` then reports "has no output" and never reaches `BlobExpired`. R9's path exists only after GC.
- **ADR-0007 follow-up ("any new write path for attempts ... must take the fence or justify why it need not"):** the harness's new upload-reference write in phase 01 task 2.2 is unfenced on purpose, but the plan never says why.
- **phase 01 task 2.2:** `put(data, class, task)` changes a signature that the harness and submit code call through the `BlobStore` protocol (harness_activity/activity.py:194, harness_activity/dsh/session.py:60, orchestrator/submit.py:30). The plan does not say whether the protocol and `MemoryBlobStore` change too, and mypy runs in CI.
- **D3 "S3 object metadata is left as written":** `S3BlobStore.put` still rewrites the metadata through `copy_object` whenever a stronger class is requested (common/blob_store/s3.py:107-118).
- **notes.md#revive and #d6, lock order:** `put` locks `blob_objects` and then writes `blob_refs`, while a removal batch updates `blob_refs` and then locks `blob_objects`. Overlapping keys can deadlock. PostgreSQL aborts one side, but the plan should fix one order.
- **Existing `agentctl events prune`:** it (orchestrator/cli.py:263-273) deletes holder rows without marking their references or writing a tombstone. Once phase 01 indexes event references, this becomes a removal path the plan does not cover.
- **D4 lock scope:** it must be session-level to span batches and `infra/backup.sh`, which runs `pg_dump` plus a boto3 copy. A shell script needs a held psql session or a Python wrapper. The plan specifies neither the scope nor the key.
- **phase 03 task 2.3:** the CI `stack` job has a 45-minute timeout and already needs "about 32" (.github/workflows/ci.yml:106-107). A second Compose project with workers, using its own `ENV_FILE` and ports, is not budgeted, and `make smoke` would need to start it.

Reuse and patterns: no duplicated capability found. The plan correctly builds on `TableTransport.prune` and `retained_base` (`agentctl tail` already prints `expired`), `_REQUEST_LOCK`, the protocol's existing `put` and `delete`, and the `APP_TABLES` list.

Tasks and coverage: every requirement in each phase's `delivers` maps to a task, the task counts (13, 10, 7) match the table, and the order builds: migration, then writers, then removal engine, then backup. Apart from M1, M4 and M5, each Given/When/Then scenario can be tested as written.

Files referenced:
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/events/table.py
- /home/geo/develop/praxismesh/common/events/transport.py
- /home/geo/develop/praxismesh/common/blob_store/s3.py
- /home/geo/develop/praxismesh/common/schemas/task.py
- /home/geo/develop/praxismesh/orchestrator/cli.py
- /home/geo/develop/praxismesh/orchestrator/submit.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/dsh/session.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0005_agent_events.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0006_task_messages.py
- /home/geo/develop/praxismesh/infra/db/init.sh
- /home/geo/develop/praxismesh/infra/db/roles.sh
- /home/geo/develop/praxismesh/docs/adr/0007-fence-harness-attempts-in-one-transaction.md
- /home/geo/develop/praxismesh/docs/adr/0010-wake-agents-through-a-durable-inbox.md
- /home/geo/develop/praxismesh/.github/workflows/ci.yml

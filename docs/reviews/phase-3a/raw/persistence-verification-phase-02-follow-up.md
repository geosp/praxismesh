<!-- Verbatim verifier report (Phase 3A persistence plan, phase 02 gate verification, as-built follow-up of the corrected statements; code 4dde76d, docs 0d9db27); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-follow-up.md per docs/reviews/README.md rule 1. -->

# Phase 3A persistence phase 02: targeted follow-up verification (docs rule 6)

Code: 4dde76d70a3a7e378dddb1a7714f0a9ddc76362a (checkout). Docs: 0d9db273d179c27f8abb203e85524625c1ef040d.
Stack: pmverify3a (db, temporal, s3 up; workers stopped). Probes were read-only: psql `BEGIN READ ONLY`, `--help`, `gc --dry-run`, `docker compose config`.

**Docs-only check.** `git diff --stat 4dde76d 0d9db27` shows that only README.md, docs/architecture/overview.md, docs/operations/runbook.md, the plan's notes.md and two new docs/reviews/phase-3a/raw/*.md reports changed. No code changed. **Confirmed.**

## 1. runbook.md, "Removing data" (lines 226-236 at 0d9db27): confirmed

- **Lifetimes.** checkpoint 7 days, transcript 30, artifact 90, ephemeral 1 day, audit kept: `common/persistence/retention.py:18-24`.
  - Rows count from the task's end: `orchestrator/lifecycle.py:283-290` (`t.ended_at + make_interval`).
  - Wake and event-batch rows count from their task's end: `RowRule("message_wakes", "recipient_workflow")` and `RowRule("event_batches", "workflow_id")` at `lifecycle.py:266-267`.
  - An ephemeral blob reference counts from its `created_at`: `common/persistence/refs.py:351-352`.
  - The audit tables (tasks, attempts, usage, audit_log) are class `audit`: `retention.py:33-36`.
- **"Apart from the housekeeping…"** The only deletes outside lifecycle/removal are these:
  - `common/events/table.py:82`: the publisher drops `event_batches` rows older than the horizon.
  - `orchestrator/dispatcher.py:97`: the dispatcher deletes a wake once it is signalled.
  - `transport.prune` is called only from `lifecycle.py:144`. The blob `delete` is called only from `removal.py:398`.
  - All three commands expose `--dry-run` ("print the plan; change nothing"). Observed in `praxis gc|request delete|events prune --help`.
- **"A dry run holds the locks…"**
  - A dry run is one transaction, rolled back at the end: `common/persistence/removal.py:196-210`.
  - Each batch locks `blob_objects ... FOR UPDATE` (`removal.py:273`), and `put` takes the same row lock (`repositories.py:696-720`).
  - `request delete` takes the task locks with `pg_try_advisory_xact_lock` (`removal.py:256-261`). Its first batch has `record_empty=True`, so its savepoint is committed and the locks last until the transaction ends. Checkpoint and other writes take `TASK_LOCK` (`repositories.py:409` and others).
  - `finish_pending` returns 0 in a dry run (`removal.py:248-253`), and gc skips `finish(back)` (`lifecycle.py:501`).
  - Probe: `gc --dry-run` printed `"dry_run": true, ... "finished_from_earlier_runs": 0`. The `audit_log` row count was 18 before and 18 after.

## 2. runbook.md, "Tombstones" (line 290): confirmed

- The trigger is `BEFORE UPDATE OR DELETE ... FOR EACH ROW` and raises: migration `0007_blob_refs_and_classes.py:180-190`.
- Probe: `pg_trigger` shows `audit_log_append_only|O|CREATE TRIGGER ... BEFORE DELETE OR UPDATE ON public.audit_log FOR EACH ROW ...`.
- `pg_tables.tableowner` = `praxismesh`, the app role. That role can therefore `TRUNCATE` the table, which a row trigger does not cover, as the sentence states.

## 3. overview.md, Components rows (lines 306, 307, 310): confirmed

- **Reference index.** Expiry is computed at query time (`refs.py:336-357`). Probe: `\d blob_refs` has the columns blob_key, holder_table, holder_key, holder_column, task_id, request_id, retention_class, created_at, removed_at and removed_by. There is no expiry column.
- **Classes and lifetimes.** `retention.py:18-64`: `DEFAULT_LIFETIME`, `TABLE_CLASS` and `REFERENCE_CLASS` match. The legacy class `task` (30 days) is not mentioned; that is an omission, not a contradiction.
- **Removals.** Each claim and where it is in the code:
  - Session request lock for the run: `lifecycle.py:585-588` and `620`.
  - Task list fixed in the first tombstone (`details.tasks`): `lifecycle.py:712-722`. Probe: the first `request.delete` tombstone has `"reason": "request delete", "tasks": [...]`.
  - `deleted` fencing row under the task locks: `lifecycle.py:688-711`.
  - Checkpoints, sample_orders, task_inbox and message_wakes deleted: `DELETE_ROWS`, `lifecycle.py:578-583`.
  - Events pruned, content redacted, and all references marked, uploads included (`live_references` takes no holder filter): `lifecycle.py:740-782` and `removal.py:120-134`.
  - Batch size at most 500 (`BATCH_LIMIT = 500`): `removal.py:46`.

## 4. notes.md (#redact, #d6): confirmed

- **Fence.** The insert uses turn `max(turn)+1`, attempt 1 and outcome `deleted` (`lifecycle.py:690-697`). `NO_NEWER_ATTEMPT` includes `OR n.outcome = 'deleted'` (`common/persistence/fence.py:36-40`). Checkpoints (`repositories.py:418`), events (`events/table.py:67`) and messages (`messages.py:376`) use it.
- **agent_sessions.** `FencedSQLAlchemySession(task_id, ...)` makes the session ID the task ID (`harness_activity/session_store.py:57-71`). DSH passes its own `DshSessionStore` (`activity.py:444`, `dsh/runner.py:266`). Probe: all 15 `agent_sessions` rows match a task ID, and all of them belong to `openai` profile tasks. No rows exist for the 196 `dsh` or 4 `default` tasks.
- **d6 tombstone list.** `AuditRepository.append` takes action, subject, details (counts) and operation_id, with an actor (`removal.py:281-288`). The time is `audit_log.created_at`.
  - gc and request delete batches carry a `reason` (`lifecycle.py:353, 456-511, 718-789`).
  - An `events.prune` batch carries only `workflow_id` (`lifecycle.py:145-151`).
  - Probe tombstones show `{"reason": ..., "rows", "references", "blobs"}` and no content.

## 5. README.md (lines 100, 156): confirmed

- **`make workers-up` comment.** `Makefile:126-131` builds and starts `orchestrator worker-a worker-b` and `dsh-a worker-dsh-a dsh-b worker-dsh-b`. `docker compose config` shows that worker-a and worker-b run template `local-default`, which has `harness: openai_agents`. The two DSH pairs are dsh-a/worker-dsh-a and dsh-b/worker-dsh-b.
- **"Run `make smoke` …"**
  - `Makefile:108-109` runs `pytest -m integration tests/integration --ignore=tests/integration/test_recovery.py`.
  - Collection: `testpaths = ["tests"]` (`pyproject.toml:47`). `tests/test_runner_conformance.py:72` marks its dsh param as integration.
  - The orchestrator role runs the wake `Dispatcher` (`workers/main.py:197-199`).
  - CI order (`ci.yml:119-122`): `make smoke` runs before `make workers-check`, the first step that starts workers.

## Result

5 of 5 statement groups confirmed. None contradicted, none unverifiable.

---
id: ADR-0013
title: Remove data only through one removal engine, in tombstoned batches under one run lock, rows before the bucket
status: accepted
date: 2026-11-21
issue: "#92"
related:
  - docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md
  - docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/notes.md
  - docs/adr/0012-index-every-blob-reference-with-its-holder.md
  - docs/adr/0009-use-a-postgresql-event-table-for-agent-events.md
supersedes: null
superseded_by: null
---

# ADR-0013: Remove data only through one removal engine, in tombstoned batches under one run lock, rows before the bucket

## Context and problem statement

Phase 3A added three ways for data to leave the stack: retention GC by class, delete-by-request,
and event pruning. Each removes rows, marks references (ADR-0012) and deletes blobs from the
bucket, and each can be killed partway. §4.13 asks for audit tombstones that say what was removed
without holding the removed content, and the operator needs to see a removal before it happens.
A crash between a row change and a bucket delete must never leave a row that names a missing
blob, and two removals, or a removal and a backup, must not interleave.

## Considered options

- One shared removal engine that every removal command uses: operator commands with `--dry-run`,
  one session-level run lock, batches of at most 500 rows, each one transaction that changes the
  rows, marks references and blobs and writes its tombstone, then the bucket deletes.
- Each command removing in its own way, deleting from the bucket first.
- A scheduled removal (a Temporal Schedule or a worker loop) now.

## Decision outcome

Chosen option: "One shared removal engine", because it makes every removal resumable and
auditable in the same way. Rows, index marks and the tombstone commit together; the bucket delete
follows per blob under its `blob_objects` row lock and only if the mark still stands, and a rerun
first finishes the marked blobs a stopped run left (R15). Bucket-first was rejected because a
crash leaves rows naming missing blobs; a tombstone written last would be lost on a crash. A
schedule was rejected for now: one machine needs no scheduler, and Phase 7 adds a CronJob that
calls the same commands.

How it is used (plan D4, D6):
- `agentctl gc`, `agentctl request delete REQ [--force]` and `agentctl events prune` run on the
  engine (`common/persistence/removal.py`), each with `--dry-run` (one transaction rolled back).
- Every removal command and `agentctl backup` hold one advisory lock (`pg_advisory_lock(3, 0)`,
  session level) for their whole run; a second one fails at once.
- Tombstones go to the append-only `audit_log`: counts, reasons and IDs, never removed content.
  The application role cannot `UPDATE` or `DELETE` its rows.

### Consequences

- Good, because a killed removal finishes when run again, with nothing dangling or counted twice,
  and every committed batch has its tombstone.
- Good, because a future removal (Phase 4's delete-by-conversation, Phase 7's scheduled GC) reuses
  the engine instead of re-solving ordering, locking and auditing.
- Bad, because removals are serial: one run lock for the stack, so a long delete blocks gc and
  backup until it finishes.
- Bad, because the app role still owns `audit_log` and can `TRUNCATE` it (threat model R10);
  append-only holds against `UPDATE` and `DELETE` only.
- Follow-up: a new removal command must use the engine and take the run lock.

### Confirmation

- `tests/integration/test_removal_engine.py` and `test_removal_kills.py` (a SIGKILL after a
  committed batch) check the order, the tombstones and the rerun.
- `tests/integration/test_audit_log.py::test_app_role_cannot_change_audit_rows` checks the
  append-only rule.
- `tests/integration/test_backup.py` checks a gc started during a backup fails on the lock.

## Links

- Issue #92; implementation plan docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle (R6-R15,
  R21, R24; D4, D6, D11, D12; notes.md#d6); plan §4.13; ADR-0009 (events prune).

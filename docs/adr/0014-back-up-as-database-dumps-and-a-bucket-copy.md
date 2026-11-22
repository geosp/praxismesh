---
id: ADR-0014
title: Back up the Compose stack as three database dumps and a bucket copy, and restore only into an empty stack
status: accepted
date: 2026-11-21
issue: "#92"
related:
  - docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md
  - docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/notes.md
  - docs/operations/runbook.md
  - docs/adr/0002-paradedb-as-postgresql-server.md
  - docs/adr/0013-remove-data-only-through-the-removal-engine.md
supersedes: null
superseded_by: null
---

# ADR-0014: Back up the Compose stack as three database dumps and a bucket copy, and restore only into an empty stack

## Context and problem statement

§4.13 asks for `make backup` and `make restore` for the Compose stack and a drill that restores
into a clean stack and reports what is inconsistent. The stack keeps state in three PostgreSQL
databases on one server (`praxismesh`, `temporal`, `temporal_visibility`; ADR-0002) and in the
SeaweedFS bucket. A backup must not let a Workflow get ahead of its rows, and must not name a
blob newer than its bucket copy. The owner set the recovery point as the last manual backup.

## Considered options

- Logical dumps (`pg_dump -Fc`) of the three databases with the workers stopped, then a copy of
  every bucket object through the S3 API, with a manifest written last; restore recreates the
  databases and loads them into a stack that holds no data.
- Docker volume snapshots.

## Decision outcome

Chosen option: "Three dumps and a bucket copy", because it is portable across hosts and Docker
storage drivers and uses only the tools the stack already has (`pg_dump` in the `db` container,
boto3). Volume snapshots were rejected as not portable and not consistent across the database and
the bucket.

How it is used (plan D8):
- `agentctl backup` (`make backup`) holds ADR-0013's run lock, stops every worker service during
  the dumps (the application database first) and starts again those that were running, copies the
  bucket, and writes `manifest.json` last; a directory without it is incomplete.
- `make restore BACKUP=...` checks the backup against this checkout (format, migration head,
  sizes), refuses a stack with any application row, any Workflow in the app namespace or any
  bucket object (R23), recreates the databases through `infra/db/databases.sh` and `roles.sh`,
  loads the dumps and objects, and prints `agentctl reconcile`'s report as information. A restore
  stopped partway leaves a mark that makes the next one refuse until `make reset`.
- `make drill` exercises the procedure in CI's `stack` job.

### Consequences

- Good, because a backup can be restored on another host, and reconcile reports exactly which
  references a restore lost.
- Bad, because the workers stop for the length of the dumps, and a removal waits for the backup.
- Bad, because backups hold prompts, outputs and conversations in clear text (encryption at rest
  is an accepted risk until Phase 9), and a backup taken before a `request delete` still holds
  that request's data.
- Bad, because the recovery point is manual; there is no point-in-time recovery, and a backup
  restores only with a checkout at its migration head.
- Follow-up: Phase 9 hardening may replace this with scheduled, encrypted or point-in-time backups
  (a new ADR superseding this one); Kubernetes (Phase 8) needs its own procedure.

### Confirmation

- `make drill` in CI's `stack` job: backup, a refused restore, a killed restore, reset, restore,
  then `task status`, `task output`, the comms role and a reported dangling reference.
- `tests/integration/test_backup.py`, `test_restore_refusals.py` and `tests/test_backup_check.py`.

## Links

- Issue #92; implementation plan docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle (R16,
  R17, R23; D8; notes.md#d8); runbook "Backup and restore"; plan §4.13.

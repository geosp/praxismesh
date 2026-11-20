---
phase: 3
title: Backup, restore, reconciliation and acceptance
status: draft
branch: null
base: null
delivers: [R16, R17, R23]
design_review: { status: changes-requested, rounds: 3, last: 2026-11-20 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 03 · Backup, restore, reconciliation and acceptance

## Goal

A stack can be backed up, restored into a clean stack and checked, as §4.13's drill asks; the
plan's acceptance suite and demo pass, and the as-built documentation describes them.

## Tasks

### 1. Reconciliation

- [ ] 1.1 `agentctl reconcile [--reindex]`: prints the phase 01 checks (dangling references, orphaned blobs with age, unindexed references) and tasks left unended whose Workflow Temporal reports closed; read-only without `--reindex`; exit status 1 when anything is listed (R17). Verify: integration tests that seed each case.

### 2. Backup and restore

- [ ] 2.1 `agentctl backup` and `make backup`, holding the D4 lock on its own connection, in the order of notes.md#d8; `backups/` git-ignored (D8). Verify: a backup of a stack with finished tasks has the three dumps, every object and a manifest; a `gc` started during it fails on the lock.
- [ ] 2.2 `infra/db/databases.sh` (the database statements moved out of `init.sh`), `infra/restore.sh` and `make restore BACKUP=...`, as notes.md#d8: refuses a stack with data in `praxismesh`, `temporal` or the bucket, then drops and recreates the three databases with their grants, reruns `roles.sh`, loads, starts Temporal and runs reconcile (R16, R23, D8). Verify: restore into a stack with a task, or a Workflow and no task, changes nothing; restore after `make reset` succeeds and `comms_mcp` connects; after a restore killed mid-load, `make reset` and a second restore succeed; a fresh `make up` still initialises through `init.sh`.
- [ ] 2.3 The drill as an integration test: back up the stack, `make reset`, restore into the same project, then `task status`, `task output` and `comms_mcp` work, and reconcile lists one dangling reference after a deliberately removed object (R16, R17; notes.md#d8). Verify: the test passes in the CI `stack` job within its 45-minute budget.

### 3. Acceptance and demo

- [ ] 3.1 Run the acceptance suite: every scenario of R1-R24, mapped to its test in the phase file's verification evidence. Verify: unit and integration runs pass from a clean worktree whose `infra/.env` comes from `infra/.env.example`.
- [ ] 3.2 Demo script `infra/demo/phase-3a-lifecycle.sh` and record `docs/demos/phase-3a-lifecycle.md`: a request with an artifact, a dry-run GC, a GC with its tombstone and the artifact's expired read, a delete of a second request with its tombstone and redacted output, a resubmit that revives the input, a backup, `make reset`, a restore and its reconcile report. Verify: the script runs end to end on the fake model.
- [ ] 3.3 As-built overview section, runbook ("Backup and restore"), `schemas.md` and decision log. Verify: `check_plans.py` and the link check pass.

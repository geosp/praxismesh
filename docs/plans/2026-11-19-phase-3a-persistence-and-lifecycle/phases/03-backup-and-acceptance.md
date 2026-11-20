---
phase: 3
title: Backup, restore, reconciliation and acceptance
status: draft
branch: null
base: null
delivers: [R16, R17]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 03 · Backup, restore, reconciliation and acceptance

## Goal

A stack can be backed up, restored into a clean stack and checked, as §4.13's drill asks; the
plan's acceptance suite and demo pass, and the as-built documentation describes them.

## Tasks

### 1. Reconciliation

- [ ] 1.1 `agentctl reconcile`: dangling references, orphaned blobs (with age), unindexed references and tasks that never ended; read-only, exit status 1 when anything is listed (R17). Verify: integration tests that seed each case.

### 2. Backup and restore

- [ ] 2.1 `infra/backup.sh` and `make backup`, in the order of D8; `backups/` git-ignored (R16, D8; notes.md#d8). Verify: a backup of a stack with finished tasks has the three dumps, every object and a manifest.
- [ ] 2.2 `infra/restore.sh` and `make restore BACKUP=...`: refuses a stack that holds data, then loads, starts Temporal and runs reconcile (R16, D8). Verify: restore into a non-empty stack changes nothing.
- [ ] 2.3 The drill as an integration test: back up one Compose project, restore into a second, then `task status` and `task output` work there, and reconcile lists one dangling reference after a deliberately removed object (R16, R17). Verify: the test passes in the CI `stack` job.

### 3. Acceptance and demo

- [ ] 3.1 Run the acceptance suite: every scenario of R1-R18, mapped to its test in the phase file's verification evidence. Verify: unit and integration runs pass from a clean worktree whose `infra/.env` comes from `infra/.env.example`.
- [ ] 3.2 Demo script `infra/demo/phase-3a-lifecycle.sh` and record `docs/demos/phase-3a-lifecycle.md`: a request with an artifact, a dry-run GC, a delete with its tombstone and expired read, a backup, a restore into a second project and its reconcile report. Verify: the script runs end to end on the fake model.
- [ ] 3.3 As-built overview section, runbook ("Backup and restore"), `schemas.md` and decision log. Verify: `check_plans.py` and the link check pass.

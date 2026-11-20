---
phase: 1
title: Reference index, classes, audit log and the payload guard
status: in-progress
branch: feat/92-phase-3a-index-and-classes
base: 8cc4355fca7578866edcc8647f086fcdc69c6557
delivers: [R1, R2, R4, R5, R14, R18, R19, R20]
design_review: { status: passed, rounds: 3, last: 2026-11-20 }
impl_review: { status: none, rounds: 0, last: null }
approved: 2026-11-20
---

# Phase 01 · Reference index, classes, audit log and the payload guard

## Goal

Every stored `BlobRef` and every upload made for a task is indexed with its holder, old ones
included; every blob and row carries a §4.13 class; ended tasks have their end time; the audit log
exists; the reference checks run; and no Workflow history of the suite carries a large payload.
Nothing is removed yet.

## Tasks

### 1. Schema and checks

- [x] 1.1 Migration 0007: `blob_refs`, `audit_log`, `tasks.ended_at`; `blob_objects.removed_at`, `removed_by`, `last_put_at` (backfilled to the migration time) and `bucket_deleted_at`; new server defaults and checks (the five classes plus `task`); the class remap, the reference backfill (classes from notes.md#d3's blob table, never the JSON) and the end-time backfill (R2, R19, D2, D3; notes.md#d2, notes.md#d3). Verify: the superuser creates a scratch database, migrates it to 0006, seeds rows of every kind in notes.md#refs (including an `audit` artifact), migrates to 0007, downgrades and upgrades again.
- [x] 1.2 `audit_log` refuses `UPDATE` and `DELETE` from the app role through a trigger (R14). Verify: integration test as the app role.
- [x] 1.3 `RetentionClass` gains `checkpoint`, `transcript` and `artifact`; `task` stays readable, ranks as `transcript` in `RETENTION_ORDER` and is never written; lifetimes in `retention.py`; a test checks every `APP_TABLES` entry against notes.md#d3 (R4, R5, D3). Verify: unit tests, including a repeat `put` over `task` metadata.
- [ ] 1.4 The reference checks (unindexed, dangling, orphaned from a bucket listing; notes.md#d2) and the expiry query as one repository module, and `reconcile --reindex`'s idempotent backfill, which also adds `blob_objects` rows for bucket-only objects (R2, D4). Verify: integration tests that seed each case, including a bucket object with no row; reindex run twice changes nothing the second time.

### 2. Writers

- [ ] 2.1 One helper, `index_refs`, writes `blob_refs` rows in the caller's transaction. `record_task`, both checkpoint inserts and the event publish call it; the unused `TaskRepository.complete` is removed (R1, D2). Verify: integration tests per writer; a refused fenced checkpoint leaves no index row.
- [ ] 2.2 `BlobStore.put` gains an optional `task_id` in the protocol and all three stores; `RecordingBlobStore.put` writes `last_put_at` and the upload reference in one transaction, `blob_objects` locked first, the stronger class winning (notes.md#revive steps 1-2); `prepare_task` mints the task ID before uploading; the harness passes its task (R1, D2, D10). Verify: integration test that a submit's uploads are held by its task before `record_task` runs; mypy passes.
- [ ] 2.3 `end_task` indexes the artifacts and sets `tasks.ended_at`, in its transaction (R1, R20). Verify: integration test for each terminal status.
- [ ] 2.4 Writers use the new classes: instructions and inputs `transcript`, workspace and session blobs `checkpoint`, artifacts `artifact`; checkpoint inserts stop hardcoding `'task'` (R4). Verify: integration test of a fake-model task reads each class back from rows and `blob_refs`.
- [ ] 2.5 `AuditRepository.append(conn, action, subject, details)` in the caller's transaction, with actor `cli:<OS user>` (R13's store). Verify: integration test.

### 3. Compatibility and the guard

- [ ] 3.1 Confirm `test_task_workflow_replay` and its fixture (3 payloads with `retention_class: task`) still pass with the new `RetentionClass` (R5). Verify: `pytest tests/test_task_workflow.py`.
- [ ] 3.2 `finish_task_body` keeps the first 20 questions of at most 500 characters (D9). Verify: unit test with 21 questions of 600 characters.
- [ ] 3.3 A history helper that fails on any payload over 64 KiB, run over the integration suite's Workflows (R18, D9). Verify: a task that returns 20 questions of 500 characters passes; a seeded 65 KiB payload fails.

### 4. Documentation

- [ ] 4.1 `schemas.md` (the new tables and column, the classes, D7's outbox pattern); the threat model (no encryption at rest and clear-text backups, the app role owning `audit_log`, content kept in Temporal histories for 72 hours: all accepted until Phase 9); the decision log. Verify: `check_plans.py` and the link check pass.

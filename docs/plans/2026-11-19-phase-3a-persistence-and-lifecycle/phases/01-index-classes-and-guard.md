---
phase: 1
title: Reference index, classes, audit log and the payload guard
status: draft
branch: null
base: null
delivers: [R1, R2, R4, R5, R14, R18]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · Reference index, classes, audit log and the payload guard

## Goal

Every stored `BlobRef` is indexed with its row, old ones included; every blob and row carries a
§4.13 class; the audit log exists and cannot be rewritten; and no Workflow history carries a
large payload. Nothing is removed yet.

## Tasks

### 1. Schema

- [ ] 1.1 Migration 0007: `blob_refs` and `audit_log`; `blob_objects.removed_at` and `removed_by`; the new class values in every `retention_class` check; the class remap and the reference backfill (R2, R4, D2, D3; notes.md#refs, notes.md#d3). Verify: `make migrate` from 0006 with seeded rows of every kind in notes.md#refs; downgrade and upgrade again.
- [ ] 1.2 `audit_log` is append-only for the app role: a trigger refuses `UPDATE` and `DELETE` (R14). Verify: integration test as the app role.
- [ ] 1.3 `RetentionClass` gains `checkpoint`, `transcript` and `artifact`; `task` stays readable and is refused for new writes; lifetimes in `retention.py`; a test checks every `APP_TABLES` entry against notes.md#d3 (R4, R5, D3). Verify: unit tests.

### 2. Writers

- [ ] 2.1 One helper, `index_refs`, writes `blob_refs` rows in the caller's transaction. `record_task`, `complete`, both checkpoint inserts and the event publish call it (R1, D2). Verify: integration tests per writer; a refused fenced checkpoint leaves no index row.
- [ ] 2.2 Writers use the new classes: instructions and inputs `transcript`, workspace and session blobs `checkpoint`, artifacts `artifact` (R4). Verify: integration test of a fake-model task reads each class back from rows and `blob_objects`.
- [ ] 2.3 `complete_task` sets `expires_at` on the task's references when it ends (D2, D3). Verify: integration test for each terminal status.
- [ ] 2.4 `AuditRepository.append(action, subject, details)` with actor `cli:<OS user>` (R13's store). Verify: integration test.

### 3. Compatibility and the guard

- [ ] 3.1 A replay test with a recorded history whose payloads carry `retention_class: task` (R5). Verify: `pytest tests/test_task_workflow.py` replay passes.
- [ ] 3.2 A history helper that fails on any payload over 64 KiB, run over the Workflows of the integration suite; `questions` capped at 20 of 500 characters (R18, D9). Verify: a test that returns 21 questions fails validation; a test that returns 20 of 500 characters passes the guard.

### 4. Documentation

- [ ] 4.1 `schemas.md` (the two tables, the classes, the outbox pattern of D7), the threat model (no encryption at rest, backups in clear text: accepted until Phase 9), the decision log. Verify: `check_plans.py` and the link check pass.

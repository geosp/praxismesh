---
phase: 2
title: GC and delete-by-request
status: draft
branch: null
base: null
delivers: [R3, R6, R7, R8, R9, R10, R11, R12, R13, R15]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-19 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · GC and delete-by-request

## Goal

An operator can remove what has expired and delete everything one request stored, safely: shared
blobs survive, every removal leaves a tombstone, a removed blob reads as expired, and a run
stopped partway finishes when run again.

## Tasks

### 1. The removal engine

- [ ] 1.1 `BlobExpired`: `RecordingBlobStore` raises it from `get`, `stream` and `stat` when `blob_objects.removed_at` is set, naming the date; `agentctl task output` reports it (R9, D6). Verify: unit test on the memory store; integration test through the CLI.
- [ ] 1.2 One removal engine for GC and delete, in the order of D6: rows and index in one transaction that marks freed blobs, then the bucket, then one tombstone per operation ID; a rerun first deletes marked objects still in the bucket (R3, R13, R15, D6; notes.md#d6). Verify: integration tests for a shared blob and for a crash after each step.

### 2. GC

- [ ] 2.1 `agentctl gc [--dry-run]`: expired rows by class, expired references, free blobs, and unreferenced blobs past the 24-hour window, in batches of 500; refuses while any reference is unindexed (R6, R7, R8, D4, D5). Verify: integration tests with times set in the rows: ended 8 and 6 days ago, running, `audit` of any age, orphans 25 hours and 1 hour old.

### 3. Delete-by-request

- [ ] 3.1 Check the assumption that each `agent_sessions` row belongs to one task, through its `session_id`, on both runners (notes.md#redact). Verify: a test that reads the session IDs of a finished task on each runner. If it fails, pause and propose a plan update.
- [ ] 3.2 `agentctl request delete REQ [--dry-run]`: refuses while any task of the request has not ended; redacts and deletes as notes.md#redact; frees the request's references (R10, R11, R12). Verify: integration tests for a finished two-task request, a running one and a request sharing a blob with another.
- [ ] 3.3 Kill tests: a delete and a GC killed mid-batch, then run again (R15). Verify: one tombstone per operation; reconcile-style check finds nothing dangling.

### 4. Documentation

- [ ] 4.1 Runbook ("Removing data": gc, delete, dry runs, what an expired read means) and the as-built overview's draft section. Verify: the link check passes.

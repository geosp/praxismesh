---
phase: 2
title: GC and delete-by-request
status: draft
branch: null
base: null
delivers: [R3, R6, R7, R8, R9, R10, R11, R12, R13, R15, R21, R22]
design_review: { status: changes-requested, rounds: 2, last: 2026-11-19 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · GC and delete-by-request

## Goal

An operator can remove what has expired and delete one request's data, safely: shared blobs
survive, uploading removed bytes again revives them, every removal batch leaves a tombstone, a
removed blob reads as expired, and a run stopped partway finishes when run again.

## Tasks

### 1. The removal engine

- [ ] 1.1 `BlobExpired`: `RecordingBlobStore` raises it from `get`, `stream` and `stat` when `blob_objects.removed_at` is set, naming the date; `agentctl task output` reads through `RecordingBlobStore` and reports it (R9, D6). Verify: integration tests through the store and the CLI.
- [ ] 1.2 One removal engine for GC and delete, in the order of D6: per batch of at most 500, one transaction for rows, reference marks, blob marks and the tombstone; then the bucket step under the row lock; a run first finishes earlier marked blobs; it calls the inner store, never `RecordingBlobStore.delete` (R3, R13, R15, D6; notes.md#d6). Verify: integration tests for a shared blob and for a crash after each step.
- [ ] 1.3 `put` revives a marked blob (notes.md#revive step 3) (R22, D10). Verify: integration tests for a resubmitted file after a delete, a `put` between the mark and the bucket delete, a bucket delete before the `put`, and an old orphan uploaded again.
- [ ] 1.4 Events leave through `TableTransport.prune` (D11). Verify: after a GC, `agentctl tail` of that task reports expired, not a gap.
- [ ] 1.5 `gc`, `request delete` and `make backup` share one advisory lock; a second run fails at once, naming the holder (D4). Verify: integration test with two concurrent runs.

### 2. GC

- [ ] 2.1 `agentctl gc [--dry-run]`: expired references and rows by class (notes.md#d3), free blobs, orphans past the window; refuses while the unindexed check finds any (R6, R7, R8, D4, D5). Verify: integration tests with times set in the rows: ended 8 and 6 days ago, running, `audit` of any age, orphans 25 hours and 1 hour old, an upload whose task never got a row.

### 3. Delete-by-request

- [ ] 3.1 Check the assumption that each `agent_sessions` row belongs to one task, through its `session_id`, on both runners (notes.md#redact). Verify: a test that reads the session IDs of a finished task on each runner. If it fails, pause and propose a plan update.
- [ ] 3.2 `agentctl request delete REQ [--dry-run] [--force]`: takes the request lock (and `record_task` takes it for a joining task); refuses while any task has not ended, unless `--force` and Temporal reports its Workflow closed; redacts and removes as notes.md#redact (R10, R11, R12, R21, D12). Verify: integration tests for a finished two-task request, a running one, a terminated Workflow with and without `--force`, and a request sharing a blob with another.
- [ ] 3.3 Kill tests: a delete and a GC killed mid-batch, then run again (R13, R15). Verify: every committed batch has its tombstone, the counts sum once, and the dangling check finds nothing.

### 4. Documentation

- [ ] 4.1 Runbook ("Removing data": gc, delete, `--force`, dry runs, the lock, what an expired read means) and the as-built overview's draft section. Verify: the link check passes.

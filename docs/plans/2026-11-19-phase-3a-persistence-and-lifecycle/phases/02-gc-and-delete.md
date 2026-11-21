---
phase: 2
title: GC and delete-by-request
status: in-progress
branch: feat/92-phase-3a-gc-and-delete
base: 9a81933360104aa0d9abf9ed89db7c357fb17b8b
delivers: [R3, R6, R7, R8, R9, R10, R11, R12, R13, R15, R21, R22, R24, R25]
design_review: { status: passed, rounds: 3, last: 2026-11-20 }
impl_review: { status: none, rounds: 0, last: null }
approved: 2026-11-20
---

# Phase 02 · GC and delete-by-request

## Goal

An operator can remove what has expired and delete one request's data, safely: shared blobs
survive, uploading removed bytes again revives them, every removal batch leaves a tombstone, a
removed blob reads as expired, and a run stopped partway finishes when run again.

## Tasks

### 1. The removal engine

- [x] 1.1 `BlobExpired`: `RecordingBlobStore` raises it from `get`, `stream` and `stat` when `blob_objects.removed_at` is set, naming the date; `agentctl task output` reads through `RecordingBlobStore` and reports it (R9, D6). Verify: integration tests through the store and the CLI.
- [x] 1.2 One removal engine for GC, delete and `events prune`, in the order of D6: per batch of at most 500, one transaction that first locks the batch's `blob_objects` rows in key order, then rows, reference marks, blob marks and the tombstone; then the bucket step under the row lock, setting `bucket_deleted_at`; a run first finishes marked blobs without it; it calls the inner store, never `RecordingBlobStore.delete` (R3, R13, R15, D6; notes.md#d6). Verify: integration tests for a shared blob and for a crash after each step.
- [x] 1.3 `put` revives a GC-marked blob and leaves a delete's mark (notes.md#revive, notes.md#d2) (R22, D10). Verify: integration tests for a resubmitted file after a delete, a `put` between the mark and the bucket delete, a bucket delete before the `put`, and an old orphan uploaded again.
- [x] 1.4 `TableTransport.prune` gains an optional connection and row limit and marks references; events leave only through it, and `agentctl events prune` runs through the engine with `--dry-run` (D11). Verify: after a GC, `agentctl tail` of that task reports expired, not a gap; a GC killed after a prune batch leaves the prune and its tombstone both committed or both absent; mypy passes.
- [ ] 1.5 One helper holds `pg_advisory_lock(3, 0)` on a dedicated connection for a whole run; `gc`, `request delete` and `events prune` use it, and phase 03 adds `agentctl backup`; a second run fails at once (D4). Verify: integration test with two concurrent runs across several batches.

### 2. GC

- [x] 2.1 `agentctl gc [--dry-run]`: expired references and rows by class (notes.md#d2, notes.md#d3), free blobs, orphans past the window; asks Temporal before expiring a row-less task's uploads; refuses while the unindexed check finds any (R6, R7, R8, D4, D5). Verify: integration tests with times set in the rows: ended 8 and 6 days ago, a stale upload after the end, running, `audit` of any age, an undelivered wake row, orphans 25 hours and 1 hour old, a row-less upload whose Workflow is closed and one whose Workflow is queued, and `event_batches` rows of an ended task.

### 3. Delete-by-request

- [x] 3.1 Check the assumption that each `agent_sessions` row belongs to one task, through its `session_id`, on both runners (notes.md#redact). Verify: a test that reads the session IDs of a finished task on each runner. If it fails, pause and propose a plan update.
- [ ] 3.2 `agentctl request delete REQ [--dry-run] [--force]`: holds the session-level request lock for the whole run (and `record_task` takes the lock for a joining task); fixes the task list in its first tombstone, takes each task's `TASK_LOCK` in task-ID order before any `blob_objects` lock (notes.md#redact, impl-review F81), and inserts each task's fencing attempt row; refuses while any task has not ended, unless `--force` and Temporal reports its Workflow closed; redacts and removes as notes.md#redact (R10, R11, R12, R21, R24, R25, D12). Verify: integration tests for a finished two-task request, a running one, a terminated Workflow with and without `--force`, a request sharing a blob with another, a task joining mid-delete, a `--force` delete while the Activity still runs (its later checkpoint, event and upload change nothing), and `task output` of a redacted task.
- [ ] 3.3 Kill tests: a delete and a GC killed mid-batch, then run again (R13, R15). Verify: every committed batch has its tombstone, the counts sum once, and the dangling check finds nothing.

### 4. Documentation

- [ ] 4.1 Runbook ("Removing data": gc, delete, `--force`, dry runs, the lock, what an expired read means) and the as-built overview's draft section. Verify: the link check passes.

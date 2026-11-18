---
phase: 1
title: Event table and agentctl tail
status: draft
branch: null
base: null
delivers: [R1, R2, R3, R4, R5, R6, R7, R8]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-18 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · Event table and agentctl tail

## Goal

Every harness attempt, on either runner, publishes its events to the event table, fenced and
batched, and `agentctl tail` follows a task live, resumes from an offset and reports expiry.

## Tasks

### 1. Event store

- [ ] 1.1 Add the event part of migration 0005: `event_logs` (workflow, next offset, retained base), `agent_events` (workflow, offset, task, attempt, seq, type, payload, blob ref, time), `event_batches` (workflow, batch ID, seen at) (D1, notes.md#d1). Verify: `alembic upgrade head` and `downgrade -1` on a copy of the dev database.
- [ ] 1.2 Port `transport.py` (interface, `Expired`, `expiry_for`, `guarded`) and the table transport into `common/events/`, on the app engine, with `prune(workflow, below=| older_than=)` (D1, D4, R1, R2, R3). Verify: the spike's shared suite, ported to `tests/integration/test_event_table.py`, passes against the table and the in-memory reference, including the notify-during-fetch test.
- [ ] 1.3 Fence the publish: task advisory lock, newer-attempt check, then the counter row (D2, R4). Verify: an integration test publishes from attempt 1 after attempt 2 started and gets `FenceRejected` with nothing stored; a test runs a fenced checkpoint insert and a publish of the same task concurrently 200 times without deadlock.

### 2. Publishing from turns

- [ ] 2.1 Add `BatchingPublisher` (an `EventSink`): buffer, flush on 64 events or 200 ms, final flush at attempt end, batch IDs `<workflow>:<attempt_id>:<n>`; a refused flush marks the attempt superseded so `before_model_call` raises `Superseded` (D2, R4, R6, R7). Verify: unit tests with a fake transport for the R6 and R7 scenarios and for a refused flush.
- [ ] 2.2 Wire it into `run_harness_turn` for both runners; emit `reset` at attempt start with the restored checkpoint, one `token` event per model response with counts only, `status` at turn end; give `openai_agents` tool events through its run hooks (D3, R5, R8). Verify: `tests/integration/test_harness_activity.py` and the DSH activity tests assert the stored events for a fake-model turn, a lost attempt (reset), and that no payload holds model text.
- [ ] 2.3 Port the spike's load runner to `tests/benchmarks/event_load.py` with the fence on, and record the publish p95 and Temporal and database CPU (risk: fence cost). Verify: publish-to-display p95 stays at most 1 s in each of 3 runs (the spike's R6); results committed under `tests/benchmarks/results/`.

### 3. agentctl

- [ ] 3.1 Add `./agentctl` and `tail TASK [--after N] [--no-follow]`: one line per event with offset, attempt, type and payload; an `Expired` line; stop following when the task completes (D5, R2, R3). Verify: `tests/test_cli.py` cases for resume after N, an expiry line, and a stop at completion.
- [ ] 3.2 Add `events prune` (D4). Verify: prune below 15, then `tail --after 5` prints `Expired(15)` first.
- [ ] 3.3 Update `schemas.md` (event table, `AgentEvent` offsets), the decision log and `docs/operations/runbook.md` (tail, prune). Verify: `check_plans.py` and the link check pass.

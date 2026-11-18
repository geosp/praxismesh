---
phase: 1
title: Event table and agentctl tail
status: draft
branch: null
base: null
delivers: [R1, R2, R3, R4, R5, R6, R7, R8, R9]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · Event table and agentctl tail

## Goal

Every harness attempt, on either runner, publishes its events to the event table through one fenced,
batching publisher, and `agentctl tail` follows a task live, resumes from an offset and reports pruning.

## Tasks

### 1. Event store

- [ ] 1.1 Add migration 0005: `event_logs`, `agent_events`, `event_batches` (D1, notes.md#d1). Verify: `alembic upgrade head` then `downgrade -1` on a copy of the dev database.
- [ ] 1.2 Port `transport.py` (interface, `Expired`, `expiry_for`, `guarded`), `memory.py` and the table transport into `common/events/`, on the app engine, with `prune` and the batch-row cleanup (D1, D4, R1, R2, R3). Verify: the spike's shared suite, ported to `tests/integration/test_event_table.py`, passes against the table and the in-memory reference, including the notify-during-fetch test.
- [ ] 1.3 Fence the publish in notes.md#d2's order (D2, R4). Verify: an integration test publishes from attempt 1 after attempt 2 started and nothing is stored; a test runs a fenced checkpoint insert and a publish of one task concurrently 200 times without deadlock.

### 2. Publishing from turns

- [ ] 2.1 Add `BatchingPublisher` (an `EventSink`) with R7's flush rule and batch IDs `<workflow>:<attempt_id>:<n>`; a refused flush sets a flag that `before_model_call` and the final flush turn into `Superseded` (D2, R5, R7, R8). Verify: unit tests with a fake transport for each R7 and R8 scenario and for a refusal during a long tool call (R5).
- [ ] 2.2 `run_harness_turn` creates the attempt's `AttemptEvents` and passes it to `HarnessRunner.run` (new `events` argument); `DshRunner` uses it instead of its own sink; the Activity emits `reset` (with the restored checkpoint) and `status`; `openai_agents` emits tool and `token` events through its run hooks (D2, D3, R6, R9). Verify: the harness and DSH activity integration tests assert the stored events for a fake-model turn and for a lost attempt (`reset` first), one `seq` sequence per attempt, and no model text in any payload.
- [ ] 2.3 Port the spike's load runner to `tests/benchmarks/event_load.py` with the fence on, and record publish p95 and Temporal and database CPU (Risks: fence cost). Verify: publish-to-display p95 is at most 1 s in each of 3 runs (the spike's R6) and publish p95 is under 250 ms; results committed under `tests/benchmarks/results/`.

### 3. agentctl

- [ ] 3.1 Add `./agentctl` and `tail TASK [--after N] [--no-follow]` (D5, R2, R3). Verify: `tests/test_cli.py` cases for resume after N, an `Expired` line, and a stop when the task ends.
- [ ] 3.2 Add `events prune` (D4, R3). Verify: prune below 15, then `tail --after 5` prints `Expired(15)` first.
- [ ] 3.3 Update `schemas.md` (event tables, offsets), the decision log and `docs/operations/runbook.md` (tail, prune). Verify: `check_plans.py` and the link check pass.

### 4. Demo and as-built

- [ ] 4.1 Record a demo in `docs/demos/phase-2-events.md`: `tail` a live DSH task, stop and resume with `--after`, prune and show `Expired`, kill the worker mid-turn and show the next attempt's `reset` (R2, R3, R9). Verify: a dry run from a clean worktree whose `infra/.env` comes from `infra/.env.example`.
- [ ] 4.2 Add a "Phase 2 events" section to `docs/architecture/overview.md` (components, data, failure and recovery, limits). Verify: the verifier's as-built check.

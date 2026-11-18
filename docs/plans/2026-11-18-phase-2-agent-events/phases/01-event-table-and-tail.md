---
phase: 1
title: Event table and agentctl tail
status: draft
branch: null
base: null
delivers: [R1, R2, R3, R4, R5, R6, R7, R8, R9]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-18 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · Event table and agentctl tail

## Goal

Every harness attempt, on either runner, publishes its events to the event table through one fenced,
batching publisher, and `agentctl tail` follows a task live, resumes from an offset and reports pruning.

## Tasks

### 1. Event store

- [ ] 1.1 Add migration 0005: `event_logs`, `agent_events`, `event_batches`, each with `retention_class` `task`, and add them to the table list in `common/persistence/retention.py` (D1, notes.md#d1). Verify: `alembic upgrade head` then `downgrade -1` on a copy of the dev database; the retention test covers the new tables.
- [ ] 1.2 Move `_TASK_LOCK` and `_NO_NEWER_ATTEMPT` into `common/persistence/fence.py` and use them from the repositories (D2). Verify: the existing fence tests pass unchanged.
- [ ] 1.3 Port `transport.py` (interface, `Expired`, `expiry_for`, `guarded`), `memory.py` and the table transport into `common/events/`, with `publish(workflow, task, turn, attempt, batch_id, events)`, the fence from `fence.py`, `prune` and the batch-row cleanup (D1, D2, D4, R1-R4). Verify: the spike's shared suite, ported to `tests/integration/test_event_table.py`, passes against the table and the in-memory reference, including the notify-during-fetch test; a publish from attempt 1 after attempt 2 started stores nothing; a fenced checkpoint insert and a publish of one task run concurrently 200 times without deadlock.

### 2. Publishing from turns

- [ ] 2.1 Add `BatchingPublisher` (an `EventSink`) to `harness_activity/events.py`: R7's triggers and cap, one publish at a time in batch order, re-sends with the same batch ID (3 tries, ~2 s), `emit` safe from any thread, a shielded `close()` that flushes and stops the background task (D2, R1, R7, R8, R9). Verify: unit tests with a fake transport for each R7 and R8 scenario, a lost reply (re-send stores once), a slow publish overlapping the next trigger (order kept), and `close()` during cancellation.
- [ ] 2.2 In `run_harness_turn`, create the attempt's `AttemptEvents` and publisher and pass `events` to `HarnessRunner.run` (both runners, and the test runners in `tests/integration/test_harness_activity.py`, `test_dsh_usage.py`, `test_dsh_activity.py` and `tests/test_runner_conformance.py`); emit `reset` first and `status` before the final flush; run the flush before the finish checkpoint, raising `Superseded` on refusal, and on failure and cancel paths log a refusal and keep the original error; `openai_agents` emits tool and `token` events through its run hooks (D2, D3, R5, R6, R8, R9). Verify: integration tests for a fake-model turn, a lost attempt (`reset` first, offsets in `seq` order), a refused final flush (no finish rows), a runner failure and a cancellation (events stored, original error kept), and no model text in any payload.
- [ ] 2.3 Port the spike's load runner to `tests/benchmarks/event_load.py` with the fence on (Risks). Verify: publish-to-display p95 at most 1 s in each of 3 runs (the spike's R6), publish p95 under 250 ms, database CPU at most double the spike's table runs; results committed under `tests/benchmarks/results/`.

### 3. agentctl

- [ ] 3.1 Add `./agentctl` and `tail TASK [--after N] [--no-follow]` (D5, R2, R3). Verify: `tests/test_cli.py` cases for resume after N, an `Expired` line, and the final read after the task ends.
- [ ] 3.2 Add `events prune` (D4, R3). Verify: prune below 15, then `tail --after 5` prints `Expired(15)` first.
- [ ] 3.3 Update `schemas.md` (event tables, offsets), the decision log and `docs/operations/runbook.md` (tail, prune). Verify: `check_plans.py` and the link check pass.

### 4. Demo and as-built

- [ ] 4.1 Record a demo in `docs/demos/phase-2-events.md`: `tail` a live DSH task, stop and resume with `--after`, prune and show `Expired`, kill the worker mid-turn and show the next attempt's `reset` (R2, R3, R9). Verify: a dry run from a clean worktree whose `infra/.env` comes from `infra/.env.example`.
- [ ] 4.2 Add a "Phase 2 events" section to `docs/architecture/overview.md` (components, data, failure and recovery, limits). Verify: the verifier's as-built check.

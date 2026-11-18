---
phase: 1
title: Event table and agentctl tail
status: impl-reviewed
branch: feat/79-agent-events
base: 41c0bcfbb192e7211ff1100d0849856215aef7a3
delivers: [R1, R2, R3, R4, R5, R6, R7, R8, R9]
design_review: { status: passed, rounds: 2, last: 2026-11-18 }
impl_review: { status: passed, rounds: 1, last: 2026-11-18 }
approved: 2026-11-18
---

# Phase 01 · Event table and agentctl tail

## Goal

Every harness attempt, on either runner, publishes its events to the event table through one fenced,
batching publisher, and `agentctl tail` follows a task live, resumes from an offset and reports pruning.

## Tasks

### 1. Event store

- [x] 1.1 Add migration 0005: `event_logs`, `agent_events`, `event_batches`, each with `retention_class` `task`, and add them to `PHASE1_TABLES` in `common/persistence/retention.py`, renamed `APP_TABLES` with its comment updated (D1, notes.md#d1). Verify: `alembic upgrade head` then `downgrade -1` on a copy of the dev database; the retention test covers the new tables.
- [x] 1.2 Move `_TASK_LOCK`, `_NO_NEWER_ATTEMPT` and `FenceRejected` into `common/persistence/fence.py` and use them from every fenced write in the repositories (D2). Verify: the existing fence tests pass unchanged.
- [x] 1.3 Port `transport.py` (interface, `Expired`, `expiry_for`, `guarded`), `memory.py` and the table transport into `common/events/`, with `publish(workflow, task, turn, attempt, batch_id, events)`, the fence from `fence.py`, `prune` and the batch-row cleanup (D1, D2, D4, R1-R4). Verify: the spike's shared suite, ported to `tests/integration/test_event_table.py`, passes against the table and the in-memory reference, including the notify-during-fetch test; a publish from attempt 1 after attempt 2 started stores nothing; a fenced checkpoint insert and a publish of one task run concurrently 200 times without deadlock.

### 2. Publishing from turns

- [x] 2.1 Add `BatchingPublisher` (an `EventSink`) to `harness_activity/events.py`: R7's triggers and cap, one publish at a time in batch order, frozen batches re-sent unchanged after a database error (backoff 0.25, 0.5, 1 s, then at each trigger), `emit` safe from any thread, a shielded `close()` bounded by 10 s that flushes and stops the background task (D2, R1, R7, R8, R9). Verify: unit tests with a fake transport for each R7 and R8 scenario; a lost reply (re-send stores once); every try failing after a commit while more events arrive, then a success (each event stored once); a slow publish overlapping the next trigger (order kept); `close()` during cancellation; batch IDs naming the attempt (two attempts never collide).
- [x] 2.2 In `run_harness_turn`, create the attempt's `AttemptEvents` and publisher and pass `events` (a required argument) to `HarnessRunner.run`; remove `DshRunner`'s `sink` parameter; give `HarnessActivities` its transport in `workers/main.py`; update every caller (`tests/integration/test_harness_activity.py`, `test_dsh_usage.py`, `test_dsh_activity.py`, `test_dsh_capabilities.py`, `tests/support/dsh_container.py`, `tests/test_runner_conformance.py`); emit `reset` first and `status` before the final flush; run the flush at the start of `_finish`, raising `Superseded` on refusal, and on failure and cancel paths log a refusal and keep the original error; `openai_agents` emits tool and `token` events through its run hooks (D2, D3, R5, R6, R8, R9). Verify: integration tests for a fake-model turn, a lost attempt (`reset` first, offsets in `seq` order), a refused final flush on the normal path and on the restore short-circuit path (no finish writes), a runner failure and a cancellation (events stored, original error kept), and no model text in any payload.
- [x] 2.3 Port the spike's load runner to `tests/benchmarks/event_load.py` and run it fenced and unfenced in one session (Risks). Verify: publish-to-display p95 at most 1 s in each of 3 fenced runs (the spike's R6), publish p95 under 250 ms, fenced database CPU at most double unfenced; results committed under `docs/benchmarks/`.

### 3. agentctl

- [x] 3.1 Add `./agentctl` and `tail TASK [--after N] [--no-follow]` (D5, R2, R3). Verify: `tests/test_cli.py` cases for resume after N, an `Expired` line, `--no-follow`, and the final read after the Workflow closes.
- [x] 3.2 Add `events prune` (D4, R3). Verify: prune below 15, then `tail --after 5` prints `Expired(15)` first.
- [x] 3.3 Update `schemas.md` (event tables, offsets, event types and payloads, `status` as the runner's result), the decision log and `docs/operations/runbook.md` (tail, prune). Verify: `check_plans.py` and the link check pass.

### 4. Demo and as-built

- [ ] 4.1 Record a demo in `docs/demos/phase-2-events.md`: `tail` a live DSH task, stop and resume with `--after`, prune and show `Expired`, kill the worker mid-turn and show the next attempt's `reset` (R2, R3, R9). Verify: a dry run from a clean worktree whose `infra/.env` comes from `infra/.env.example`.
- [ ] 4.2 Add a "Phase 2 events" section to `docs/architecture/overview.md` (components, data, failure and recovery, limits). Verify: the verifier's as-built check.

---
title: Phase 2 events - the event table and agentctl tail
status: draft
created: 2026-11-18
updated: 2026-11-18
design_review: { status: changes-requested, rounds: 1, last: 2026-11-18 }
approved: null
adr_review: null
---

# Phase 2 events - the event table and agentctl tail

## Summary

The first half of roadmap Phase 2: agents become observable. Each harness attempt, on either runner,
publishes its events through one batching publisher to a PostgreSQL event table (ADR-0009). Every
publish takes ADR-0007's fence, so a superseded attempt stores nothing (R4, R5). Publishes run one at
a time per attempt and retry with the same batch ID, and the attempt's last events are flushed before
its finish is written (R7, R8, D2). Each attempt's first event is a `reset` (R9). Offsets are gap-free
per workflow; `agentctl tail` follows a task live, resumes after an offset, and reports pruned events
(`agentctl events prune`) before later ones (R1-R3, D4, D5). Payloads never carry model text (R6). The
messaging half is a separate plan (`docs/plans/2026-11-18-phase-2-events-and-comms`).

```text
run_harness_turn: AttemptEvents -> BatchingPublisher --one fenced batch at a time--> agent_events
                                                                     NOTIFY agent_events |
                                                        agentctl tail --follow (LISTEN + 1 s poll)
```

Main risk: the fence's per-task lock on every batch slows publishing. Phase 01 task 2.3 measures it;
above 250 ms p95 per publish, the plan returns to design review to change R7's batching.

## Why

Roadmap Phase 2 (`docs/roadmap/phases/phase-2.md`) is next. Today events go to a no-op sink
(`harness_activity/events.py`), only the DSH runner emits them, and nothing stores or shows them. The
event-transport spike (issue #76) chose the table (ADR-0009) and left four questions open for this
phase: the fence's lock order and cost, what offsets are counted per (keying), tenant scoping, and
where token text lives. The owner decided on 2026-11-18 that token events carry counts only. This plan
was split from the messaging plan after two design-review rounds found no Major issue in this part.

## What changes

- Migration 0005: `event_logs`, `agent_events`, `event_batches`, each with a retention class (D1).
- `common/events/`: the spike's interface, reader rule, in-memory reference and table transport (D1).
- `common/persistence/fence.py`: the fence's lock and check, shared by every fenced write (D2).
- `BatchingPublisher` in `harness_activity/events.py`, owned by `run_harness_turn`; `HarnessRunner.run` gains `events` (D2).
- Activity-level events for both runners; tool and token events for `openai_agents` (D3).
- `./agentctl` with `tail` and `events prune` (D4, D5); `schemas.md`, runbook, demo, as-built overview.

### Non-goals

- Messaging, the comms MCP and waiting tasks (the messaging plan).
- Model text in events; the gateway SSE endpoint (Phase 4); the UI (Phase 8); tenants (Phase 4).
- Scheduled retention of events (Phase 3A, the retention and blob-GC phase).

## Terms

- **Task / turn / attempt**: a task is one `TaskWorkflow`; it runs turns (Activity `run_harness_turn`); a turn runs as attempts (Temporal tries). Attempts are rows in `task_attempts`.
- **Runner**: the harness that runs a turn: `DshRunner` (DeepSeek Harness, the default) or `openai_agents`.
- **Checkpoint**: a row saving a turn's session position and workspace; an attempt restores the newest one.
- **`before_model_call`**: the hook every runner calls before each model request; it already stops a superseded attempt.
- **`AttemptEvents`**: the existing helper that numbers one attempt's events (`seq`, from 0) and hands them to a sink.
- **Workflow ID**: a task's `TaskWorkflow` ID; today it equals the task ID, and it survives Continue-As-New.
- **Offset**: an event's position in its workflow's log, from 1, with no gaps.
- **Retained base**: the lowest offset still stored for a workflow.
- **`Expired(base)`**: what a reader yields when events it asked for were pruned; reading resumes at `base`.
- **Batch / batch ID**: the events one publish stores together, named `<workflow>:<attempt_id>:<n>`.
- **Reader rule**: a reader yields `Expired` when its offset is below the retained base, or when offsets jump because events were pruned during the read; a repeated offset is an error.
- **Fence**: ADR-0007's rule that an attempt's write is valid only while no newer turn or attempt of its task exists, checked under the per-task advisory lock.
- **Superseded**: the exception that ends an attempt the fence refused.

## Requirements

### R1 · Each event is stored once, at a gap-free offset

An accepted event is stored once per workflow, including when its batch is re-sent within 600 s, and offsets have no gaps.
- **Given** a publish whose commit succeeded but whose reply was lost, **when** the publisher re-sends the batch, **then** it is stored once.
- **Given** two attempts of one task publishing in turn, **when** both finish, **then** offsets run 1..N with no gap.

### R2 · A reader resumes without gaps or repeats

A reader that resumes after offset N gets every retained event above N, in order, each once.
- **Given** `agentctl tail` stopped after offset 20, **when** it reconnects with `--after 20`, **then** it prints 21 onwards and nothing earlier.

### R3 · Pruned events are reported, never skipped

A reader asking for events below the retained base is told so before it gets any later event.
- **Given** events pruned below 15, **when** a reader asks after 5, **then** it sees `Expired(15)` and then 15 onwards.

### R4 · A superseded attempt's batch is refused

A batch from an attempt that a newer turn or attempt of its task has replaced is never stored.
- **Given** attempt 2 of a turn has started, **when** attempt 1 publishes, **then** nothing is stored.

### R5 · A refused final flush stops the finish

An attempt whose final flush is refused raises `Superseded` before it writes its finish checkpoint or outcome.
- **Given** attempt 2 started while attempt 1 ran its last tool call, **when** attempt 1 finishes, **then** it raises `Superseded` and stores no finish checkpoint, outcome or artifact.

### R6 · Events never carry model text

Event payloads hold only counts, names, IDs and statuses.
- **Given** a turn with three model responses, **when** it ends, **then** its three `token` events hold token counts and no text.

### R7 · Events are batched

A publish carries at most 64 events, and starts only when 64 are buffered, 200 ms after the oldest unpublished event, or when the attempt ends.
- **Given** 640 events emitted at once, **when** the turn ends, **then** they were stored in 10 batches.
- **Given** 3 events within 50 ms and then none, **when** 200 ms pass, **then** they were stored in one batch.

### R8 · An ending attempt flushes its events

Every event an attempt emitted before it ended is stored, unless the attempt was superseded or its worker process was killed.
- **Given** a turn that ends 10 ms after its last tool event, **when** it returns, **then** that event is stored.
- **Given** a runner failure or a cancellation, **when** the attempt ends, **then** its events, including a final `status`, are stored.

### R9 · Each attempt opens with a reset event

An attempt's first event is a `reset` naming its attempt and the checkpoint it restored from (none for a fresh start), and offsets follow `seq` within an attempt.
- **Given** a turn whose first attempt was lost, **when** attempt 2 starts, **then** `tail` shows its `reset` before its other events, in `seq` order.

## Decisions

### D1 · Port the spike's table; offsets per workflow ID

`common/events/` takes the spike's interface, reader rule, in-memory reference and table transport,
on the app's SQLAlchemy engine. `event_logs` holds each workflow's next offset and retained base;
`agent_events` the events; `event_batches` the batch IDs seen in the last 600 s, which is how a re-sent
batch is recognised (D2 bounds re-sends well below that). Each publish `NOTIFY`s; following readers
`LISTEN` and poll every 1 s. Rows carry retention class `task`. Offsets are per workflow ID, which
Continue-As-New keeps. Rejected: `seq` as offset (it restarts each attempt). Details: notes.md#d1

### D2 · One publisher per attempt, one publish at a time

`run_harness_turn` creates the attempt's `AttemptEvents` over a `BatchingPublisher` and passes it to
the runner. The publisher runs one publish at a time, in batch order, and re-sends a batch with the
same ID on a database error, up to 3 times over ~2 s. Each publish takes the task lock, checks for a
newer turn or attempt, then locks the workflow's `event_logs` row, using `fence.py` like every fenced
write. The final flush runs shielded, before the finish writes. Rejected: the runner owning events
(two `seq` counters); unfenced events (ADR-0007). Details: notes.md#d2

### D3 · Events for both runners; token counts only

The Activity emits `reset` at attempt start and `status` (the outcome or failure) before the final
flush. `openai_agents` emits tool events and one `token` event per response through its run hooks;
DSH already emits both, with counts only. Token events carry counts (owner decision, 2026-11-18).
Rejected: model text in a blob per response (Phase 4/8 decide).

### D4 · Manual pruning only

`agentctl events prune --task T (--below N | --older-than 7d)` deletes events and advances the
retained base to the lowest remaining offset. Rejected: a retention job now (Phase 3A owns retention).

### D5 · `agentctl` wraps the existing CLI

`./agentctl` runs `orchestrator.cli` with `infra/.env` (database and Temporal settings). `tail TASK
[--after N] [--no-follow]` prints one line per event (offset, attempt, type, payload) and each
`Expired`; once the `tasks` row is no longer `running` it reads once more to the end and stops.
Rejected: a console script (the project is not a package).

## Assumptions

- One tenant; `tail` is an operator command with database access. Tenant scoping comes with Phase 4.
- The event tables share the app database with checkpoints, so a final flush that still fails after its re-sends means the attempt could not have written its finish either; the attempt then fails retryably.
- A finished workflow keeps its last 600 s of batch rows until Phase 3A's retention (D1 deletes old rows on publish).

## Risks

- The fence lock slows publishing → phase 01 task 2.3 measures publish p95; above 250 ms the plan returns to design review to change R7.
- Event writes add database load → task 2.3 compares database CPU with the spike's table run; more than double returns to design review.

## Rollout & rollback

Migration 0005 is additive. Order: migrate, then restart the harness workers. `TaskWorkflow` is
unchanged, so running tasks are unaffected: their next attempt starts publishing. Rollback: redeploy
the previous workers; events stop being written and the tables stay, unused.

## Open questions

- None

## Impact

- Packages / directories: `common/events/` (new), `common/persistence/` (migration 0005, `fence.py`, `retention.py`), `harness_activity/`, `workers/`, `orchestrator/cli.py`, `agentctl` (new), `tests/`, `docs/`.
- Data: migration 0005 (`event_logs`, `agent_events`, `event_batches`).
- Jobs / APIs: `run_harness_turn`, `HarnessRunner.run` (gains `events`), the CLI.

## Links

- ADR-0009 - events in a PostgreSQL table behind an event-transport interface; Phase 2's commitments and open items.
- ADR-0007 - every attempt write path takes the per-task fence.
- `docs/spikes/event-transport.md` - the spike's measurements, reader rule and table mechanics.
- `docs/plans/2026-11-18-phase-2-events-and-comms` - the messaging half of Phase 2.
- Issue #79 - Phase 2.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | Event table and agentctl tail | draft | 0/12 |

## Decision log

- None yet (the plan is not approved).

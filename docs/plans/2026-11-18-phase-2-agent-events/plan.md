---
title: Phase 2 events - the event table and agentctl tail
status: draft
created: 2026-11-18
updated: 2026-11-18
design_review: { status: none, rounds: 0, last: null }
approved: null
adr_review: null
---

# Phase 2 events - the event table and agentctl tail

## Summary

The first half of roadmap Phase 2: agents become observable. Each harness attempt, on either runner,
publishes its events through one batching publisher to a PostgreSQL event table (ADR-0009). Every
publish takes ADR-0007's fence, so a superseded attempt stores nothing, and a refused publish ends the
attempt `Superseded` at its next model call or when it finishes (R4, R5). Offsets are gap-free per
workflow; `agentctl tail` follows a task live, resumes after an offset, and reports pruned events
before it shows later ones (R1-R3). Payloads never carry model text (R6). The messaging half (comms
MCP, inbox, waiting tasks) is a separate plan (`docs/plans/2026-11-18-phase-2-events-and-comms`).

```text
run_harness_turn: AttemptEvents -> BatchingPublisher --fenced batch--> agent_events
                                                                          ^
                                                       agentctl tail --follow (LISTEN + 1 s poll)
```

Main risk: the fence's per-task lock on every batch slows publishing; task 2.3 measures it against a
stated limit.

## Why

Roadmap Phase 2 (`docs/roadmap/phases/phase-2.md`) is next. Today events go to a no-op sink
(`harness_activity/events.py`), only the DSH runner emits them, and nothing stores or shows them. The
event-transport spike (issue #76) chose the table (ADR-0009) and left this phase the fence's lock order
and cost, keying and token text. The owner decided on 2026-11-18 that token events carry counts only.
This part was split from the messaging plan after two design-review rounds found no Major issue in it
(`docs/plans/2026-11-18-phase-2-events-and-comms/reviews.md`).

## What changes

- Migration 0005: `event_logs`, `agent_events`, `event_batches` (D1).
- `common/events/`: the spike's interface, reader rule, in-memory reference and table transport (D1).
- One per-attempt publisher owned by `run_harness_turn`; `HarnessRunner.run` gains `events` (D2).
- Activity-level events for both runners; tool and token events for `openai_agents` (D3).
- `./agentctl` with `tail` and `events prune` (D4, D5); `schemas.md`, runbook, as-built overview.

### Non-goals

- Messaging, the comms MCP and waiting tasks (the messaging plan).
- Model text in events; the gateway SSE endpoint (Phase 4); the UI (Phase 8); tenants (Phase 4).
- Scheduled retention of events (Phase 3A).

## Terms

- **Task / turn / attempt**: a task is one `TaskWorkflow`; it runs turns (Activity `run_harness_turn`); a turn runs as attempts (Temporal tries).
- **Runner**: the harness that runs a turn: `DshRunner` (DeepSeek Harness, the default) or `openai_agents`.
- **Checkpoint**: a row saving a turn's session position and workspace; an attempt restores the newest one.
- **`before_model_call`**: the hook every runner calls before each model request.
- **`AttemptEvents`**: the existing helper that numbers one attempt's events (`seq`, from 0) and hands them to a sink.
- **Workflow ID**: a task's `TaskWorkflow` ID; it survives Continue-As-New.
- **Offset**: an event's position in its workflow's log, from 1, with no gaps.
- **Retained base**: the lowest offset still stored for a workflow.
- **Batch / batch ID**: the events one publish stores together, named `<workflow>:<attempt_id>:<n>`.
- **Reader rule**: a reader reports `Expired` when its offset is below the retained base or an offset jumps during a read, and fails on a repeated offset.
- **Fence**: ADR-0007's rule that an attempt's write is valid only while no newer turn or attempt of its task exists, checked under the per-task advisory lock.
- **Superseded**: the exception that ends an attempt the fence refused.

## Requirements

### R1 · Each event is stored once, at a gap-free offset

An accepted event is stored exactly once per workflow, and its workflow's offsets have no gaps.
- **Given** a batch publish retried after a lost reply, **when** the retry lands, **then** the batch is stored once.
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

### R5 · A refused publish ends the attempt

An attempt whose publish was refused raises `Superseded` at its next model call or when it finishes, whichever comes first.
- **Given** a refused publish during a 60 s tool call, **when** the call returns and the turn finishes, **then** the attempt ends `Superseded` and stores no checkpoint.

### R6 · Events never carry model text

Event payloads hold only counts, names, IDs and statuses.
- **Given** a turn with three model responses, **when** it ends, **then** its three `token` events hold token counts and no text.

### R7 · Events are batched

An attempt publishes only when 64 events are buffered, 200 ms after its oldest unpublished event, or when it ends.
- **Given** 640 events emitted at once, **when** the turn ends, **then** they were stored in 10 batches.
- **Given** 3 events within 50 ms and then none, **when** 200 ms pass, **then** they were stored in one batch.

### R8 · An ending attempt flushes its events

Every event an attempt emitted before it ended is stored, unless the attempt was superseded (R4).
- **Given** a turn that ends 10 ms after its last tool event, **when** it returns, **then** that event is stored.

### R9 · Each attempt opens with a reset event

An attempt's first event is a `reset` naming its attempt and the checkpoint it restored from.
- **Given** a turn whose first attempt was lost, **when** attempt 2 starts, **then** `tail` shows its `reset` before its other events.

## Decisions

### D1 · Port the spike's table; offsets per workflow ID

Move the interface, reader rule, in-memory reference and table transport into `common/events/`, using
the app database's SQLAlchemy engine, with tables from migration 0005. Offsets are per workflow ID;
`seq` stays per attempt. A publish deletes that workflow's batch rows older than 600 s (the spike's
re-send horizon). Rejected: per-task offsets (not what observers address); `seq` as offset (it
restarts each attempt). Details: notes.md#d1

### D2 · One publisher per attempt; fence with the task lock first

`run_harness_turn` creates the attempt's `AttemptEvents` over a `BatchingPublisher` and passes it to
the runner (`HarnessRunner.run` gains `events`; `DshRunner` stops building its own). The publisher
flushes per R7. A publish takes the task lock, checks for a newer turn or attempt, then locks the
workflow's `event_logs` row: the same order as every fenced write. A refusal sets a flag that
`before_model_call` and the final flush raise as `Superseded` (R5). Rejected: the runner owning events
(two `seq` counters per attempt); unfenced events (ADR-0007). Details: notes.md#d2

### D3 · Events for both runners; token counts only

The Activity emits `reset` at attempt start and `status` at turn end. `openai_agents` emits tool events
and one `token` event per response through its run hooks; DSH already emits both. Token events carry
counts (owner decision, 2026-11-18). Rejected: model text in a blob per response (Phase 4/8 decide).

### D4 · Manual pruning only

`agentctl events prune --task T (--below N | --older-than D)` deletes events and advances the retained
base, so tests and the demo show expiry. Rejected: a retention job now (Phase 3A owns retention).

### D5 · `agentctl` wraps the existing CLI

`./agentctl` runs `orchestrator.cli` with `infra/.env`. `tail TASK [--after N] [--no-follow]` resolves
the task's workflow ID, prints one line per event (offset, attempt, type, payload) and each `Expired`,
and stops following when the task ends. Rejected: a console script (the project is not a package).

## Assumptions

- One tenant; `tail` is an operator command with database access. Tenant scoping comes with Phase 4.
- Each publish's task lock adds under 20 ms at the spike's load; task 2.3 measures it.
- A finished workflow keeps its last batch rows until Phase 3A's retention (D1 deletes only on publish).

## Risks

- The fence lock slows publishing → task 2.3 measures it; above 250 ms p95 the plan returns to design review to change R7.
- Event writes add database load → task 2.3 records database CPU; ADR-0009's revisit trigger applies.

## Rollout & rollback

Migration 0005 is additive. Order: migrate, then restart the harness workers. `TaskWorkflow` is
unchanged, so running tasks are unaffected: their next attempt starts publishing. Rollback: redeploy
the previous workers; events stop being written and the tables stay, unused.

## Open questions

- None

## Impact

- Packages / directories: `common/events/` (new), `common/persistence/migrations/`, `harness_activity/`, `workers/`, `orchestrator/cli.py`, `agentctl` (new), `tests/`, `docs/`.
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
| 01 | Event table and agentctl tail | draft | 0/11 |

## Decision log

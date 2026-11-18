---
title: Phase 2 - real-time events and the comms MCP
status: draft
created: 2026-11-18
updated: 2026-11-18
design_review: { status: none, rounds: 0, last: null }
approved: null
adr_review: null
---

# Phase 2 - real-time events and the comms MCP

## Summary

Agents become observable and can talk to each other. Harness attempts publish their `AgentEvent`s in
batches to a PostgreSQL event table (ADR-0009), fenced like every other attempt write (ADR-0007), and
`agentctl tail` follows a task live, resumes from an offset and reports expiry (R1-R9). A stdio MCP
server, `comms_mcp`, lets an agent post status, message or ask another task of the same request (R10,
R19). Messages are durable rows; a dispatcher wakes the recipient's `TaskWorkflow` with a Signal (D6).
A turn may now end `waiting`: the Workflow sleeps on its inbox until a message, a question deadline or
its idle timeout, and uses Continue-As-New while it waits (D7, D11). Asking ends the asker's turn; the
reply wakes it (D8). Three phases: events, then messaging, then acceptance and the demo.

```text
harness Activity --batches--> agent_events <--follow-- agentctl tail
     |  comms_mcp --send/ask--> agent_messages + wake row --> dispatcher --Signal--> TaskWorkflow
     |                                                                               (waiting -> next turn)
```

Main risks: the per-task fence lock on every event batch (measured in phase 01), and a local model
that does not follow the ask-then-wait protocol (scripted fake model in acceptance tests; D8).

## Why

Roadmap Phase 2 (`docs/roadmap/phases/phase-2.md`) is next. Today events go to a no-op sink
(`harness_activity/events.py`), only the DSH runner emits them, nothing stores or shows them, and a
`TaskWorkflow` ends once its turns finish, so an agent has no way to receive a message or wait for one.
The event-transport spike (issue #76) chose the table and listed what Phase 2 must still decide
(ADR-0009): the fence's lock order and cost, scoping, keying and token text. The owner settled four
behaviour questions on 2026-11-18 (D7, D8, D9 and D3's token rule).

## What changes

- Migration 0005: event table, counters and batch IDs; message inbox and wake rows (D1, D6).
- `common/events/`: the spike's interface, reader rule and table transport, ported (D1).
- A batching, fenced event publisher in `run_harness_turn`; Activity-level events for both runners (D2, D3).
- `agentctl`: a wrapper for the existing CLI, with `tail` and `events prune` (D4, D5).
- `comms_mcp/`: `post_status`, `send_to_agent`, `ask_agent`, `get_task_context` (D8, D9, D13).
- `finish_task` gains `waiting`; `TaskWorkflow` waits, wakes, and continues as new (D7, D11, D12).
- A dispatcher loop in the orchestrator worker (D6). Profile fields `idle_timeout`, `max_ask_wait`.
- New template versions granting `comms`; `schemas.md`, decision log, as-built overview.

### Non-goals

- Model text in events, the gateway SSE endpoint (Phase 4), the UI (Phase 8), tenants (Phase 4).
- Scheduled event and message retention and blob garbage collection (Phase 3A, issue #74).
- A planner that creates multi-agent tasks (Phase 3A); here tasks join a request through the CLI.

## Terms

- **Request**: one client submission (`request_id`); every task it starts shares it.
- **Task / turn / attempt**: a task is one `TaskWorkflow`; it runs turns (`run_harness_turn`); a turn runs as attempts (Temporal tries).
- **Workflow ID**: a task's `TaskWorkflow` ID; it survives Continue-As-New.
- **Offset**: an event's position in its workflow's log, from 1, with no gaps.
- **Retained base**: the lowest offset still stored for a workflow.
- **Batch / batch ID**: the events one publish stores together, named `<workflow>:<attempt_id>:<n>`.
- **Reader rule**: before a read, report `Expired` if the offset is below the retained base; during it, an offset jump is `Expired` and a repeat is an error (`common/events/`).
- **Fence**: ADR-0007's rule: a write by an attempt is valid only while no newer turn or attempt of its task exists, checked under the per-task advisory lock.
- **Message / question / reply**: an inbox row from one task to another; a question is a message that expects a reply by its deadline; a reply names the question it answers.
- **Waiting**: a task between turns whose last turn ended with `finish_task(status="waiting")`.
- **Wake**: a Signal telling a waiting task's Workflow to check its inbox.
- **Dispatcher**: the loop in the orchestrator worker that turns wake rows into Signals.
- **Idle timeout**: how long a waiting task waits with nothing pending before it completes.

## Requirements

### R1 · Each event is stored once, at a gap-free offset

An accepted event is stored exactly once per workflow, and its workflow's offsets have no gaps.
- **Given** an attempt whose batch publish is retried after a lost reply, **when** the retry lands, **then** the batch is stored once.
- **Given** two attempts of one task publishing in turn, **when** both finish, **then** offsets run 1..N with no gap.

### R2 · A reader resumes without gaps or repeats

A reader that resumes after offset N gets every retained event above N, in order, each once.
- **Given** `agentctl tail` stopped after offset 20, **when** it reconnects with `--after 20`, **then** it prints 21 onwards and no earlier event.

### R3 · Expiry is reported, never skipped

A reader asking for events below the retained base is told before it gets any later event.
- **Given** events pruned below 15, **when** a reader asks after 5, **then** it sees `Expired(15)` and then 15 onwards.

### R4 · A superseded attempt publishes nothing

A batch from an attempt that a newer attempt has replaced is refused, and that attempt stops.
- **Given** attempt 2 of a turn has started, **when** attempt 1 publishes, **then** nothing is stored and attempt 1 ends `Superseded`.

### R5 · Events never carry model text

Event payloads hold only counts, names, IDs and statuses; a token event carries token counts.
- **Given** a turn with three model responses, **when** it ends, **then** there are three token events whose payloads have counts only.

### R6 · Events are batched

An attempt publishes only when 64 events are buffered, 200 ms after its oldest unpublished event, or when it ends.
- **Given** 640 events emitted at once, **when** the turn ends, **then** they were stored in 10 batches.
- **Given** 3 events within 50 ms and then none, **when** 200 ms pass, **then** they were stored in one batch.

### R7 · An ending attempt flushes its events

Every event an attempt emitted before it ended is stored, unless the attempt was superseded (R4).
- **Given** a turn that ends 10 ms after its last tool event, **when** it returns, **then** that event is stored.

### R8 · Each attempt opens with a reset event

Each attempt's first event is a `reset` naming its attempt and the checkpoint it restored from.
- **Given** a turn whose first attempt was lost, **when** attempt 2 starts, **then** `tail` shows its `reset` before any of its other events.

### R9 · Temporal history stays bounded

Events and message bodies never enter Temporal history, and a waiting task continues as new before its run's history exceeds 2,000 events.
- **Given** a task woken 100 times, **when** its runs are inspected, **then** no run's history exceeds 2,000 events.

### R10 · Messages stay inside their request

A task may message only tasks of its own request; any other message is refused and recorded.
- **Given** tasks in two requests, **when** one sends to the other, **then** the tool returns an error, no message is delivered, and the refusal is stored.

### R11 · An accepted message is durable

A message is stored before its sender is told it was sent, and is delivered to the recipient exactly once.
- **Given** a sent message and a worker killed before the recipient's turn, **when** the turn reruns, **then** the message is delivered once.

### R12 · A message wakes a waiting task

A message to a waiting task starts that task's next turn with the message in its input.
- **Given** task B waiting, **when** A sends to B, **then** B runs a turn whose input holds A's message.

### R13 · A reply wakes the asker

A reply to a question starts the asker's next turn with the reply in its input.
- **Given** A asked B and is waiting, **when** B replies, **then** A runs a turn holding the reply and the question's correlation ID.

### R14 · An unanswered question ends at its deadline

A question with no reply by its deadline expires; the asker's next turn is told so.
- **Given** a question with a 30 s deadline and no reply, **when** 30 s pass, **then** the asker runs a turn saying no answer came.

### R15 · A late reply is refused

A reply to an expired or cancelled question is refused with an error to the replier.
- **Given** an expired question, **when** the recipient replies, **then** the tool returns "question expired" and nothing is delivered.

### R16 · A waiting task waits at most its idle timeout

A waiting task with no pending question and no message completes after its idle timeout.
- **Given** an idle timeout of 60 s, **when** no message arrives, **then** the task completes `succeeded` after ~60 s.

### R17 · Questions never wait in a cycle

A question whose recipient is waiting, directly or through others, on a question from the asker is refused.
- **Given** A waits on a question to B, **when** B asks A, **then** B's ask is refused as a cycle.

### R18 · Cancellation reaches the other side

When a task ends, its open questions are cancelled and askers waiting on it are told.
- **Given** A waits on a question to B, **when** B is cancelled, **then** A runs a turn saying B ended without replying.

### R19 · comms_mcp acts only as its own task

`comms_mcp` takes its task, turn and attempt from the worker, never from tool arguments, and its writes are fenced.
- **Given** a stale attempt's `comms_mcp`, **when** it sends, **then** the send is refused.

### R20 · In-flight Phase 1 tasks still replay

The changed `TaskWorkflow` replays histories recorded by the Phase 1 code without nondeterminism.
- **Given** a recorded Phase 1 history, **when** the replayer runs the new code, **then** it passes.

## Decisions

### D1 · Port the spike's table; offsets per workflow ID

Move the interface, reader rule and table transport into `common/events/`, on the app database's
engine, with tables from migration 0005. Offsets are per workflow ID, which Continue-As-New keeps;
`seq` stays per attempt and `attempt_id` tells attempts apart. Rejected: per-task offsets (the same
today, but a task is not what observers address); `seq` as offset (it restarts each attempt).
Details: notes.md#d1

### D2 · Batch in the Activity; fence with the task lock first

The Activity buffers events and publishes every 200 ms or 64 events, and at attempt end. A publish
takes the per-task advisory lock, checks for a newer attempt, then locks the counter row: the same
order as every fenced write, so no deadlock. A refusal makes the next `before_model_call` raise
`Superseded`. Rejected: unfenced events (ADR-0007), one transaction per event. Details: notes.md#d2

### D3 · Activity-level events for both runners; token counts only

`run_harness_turn` emits `reset` at attempt start and `status` at turn end; each model response
gives one `token` event with counts (owner decision). `openai_agents` gains tool events through its
run hooks, so both runners report the same kinds. Rejected: model text in a blob per response
(owner chose counts; text waits for Phase 4/8).

### D4 · Manual pruning in Phase 2

`agentctl events prune --workflow W (--below N | --older-than D)` deletes events and advances the
retained base; it is how tests and the demo show expiry. Scheduled retention is Phase 3A's. Rejected:
a retention job now (Phase 3A owns retention and GC).

### D5 · `agentctl` wraps the existing CLI

`./agentctl` at the repo root runs `orchestrator.cli` with `infra/.env`. `agentctl tail TASK
[--after N] [--no-follow]` prints one line per event and its offset, a line per `Expired`, and stops
following when the task completes. `task submit --request REQ` joins an existing request. Rejected:
a packaged console script (the project is not a package, `pyproject.toml`).

### D6 · Durable inbox, wake rows and a dispatcher

`comms_mcp` writes the message (body in a blob, `task` retention) and a wake row in one transaction.
A dispatcher in the orchestrator worker `LISTEN`s, polls every 1 s as a fallback, and Signals
`inbox` to the recipient's Workflow, deleting the wake row only after Temporal accepted it. The
Signal is a hint: the Workflow reads its inbox through an Activity. Rejected: Signals from
`comms_mcp` (a worker subprocess with a Temporal client, against §4.4); one long-polling Activity
per waiting task (a worker slot and connection each). Details: notes.md#d6

### D7 · `waiting` turns and the wait loop

`finish_task` accepts `waiting` (owner decision). On a `waiting` outcome the Workflow waits for an
`inbox` Signal, the earliest question deadline, the idle timeout or the wall-time deadline. It then
runs `claim_inbox`, which assigns undelivered messages and expired or cancelled questions to the next
turn, once (keyed by task and turn), and the turn's input lists them. Waits count against the task's
wall-time budget. Rejected: keeping finished tasks open; a fresh task per message (both owner-rejected).

### D8 · Asking ends the turn

`ask_agent(task, text, wait)` stores a question with a deadline (`wait`, capped by the profile's
`max_ask_wait`) and returns its correlation ID; the system prompt tells the agent to then call
`finish_task(status="waiting")`. A reply is `send_to_agent(task, text, reply_to=ID)`. A reply that
arrives while the asker still runs is delivered at its next wait. Rejected: blocking in the tool
call (owner decision: DSH calls time out at 150 s; a crash loses the wait).

### D9 · Request scope, identity from the worker

A task may message only tasks with its `request_id` (owner decision); refusals are stored as
`rejected` rows. `comms_mcp` reads task, turn and attempt from `PRAXIS_*` variables the worker sets.
Rejected: profile allow lists (new registry fields now), audit-only (does not reject).

### D10 · Cycle check under a request lock

An ask takes a per-request advisory lock and follows open questions from the recipient; reaching the
asker refuses it. Deadlines are the backstop. Rejected: deadlines alone (a cycle then always costs a
full deadline).

### D11 · Continue-As-New while waiting

Before each wait, the Workflow continues as new when Temporal suggests it or after 40 wakes,
carrying a compact `TaskState` (resolved task, counters, usage, deadline). Turns restore from
checkpoints, so no session state is carried. Rejected: never continuing (R9 fails at ~100 wakes).

### D12 · Patch the Workflow

New Workflow behaviour sits behind `workflow.patched("phase2-wait")`, with a replay test of a
recorded Phase 1 history (R20). Rejected: a new Workflow type (callers and the CLI name `TaskWorkflow`).

### D13 · `comms_mcp` as a stdio server like `sample_mcp`

`comms_mcp/` is a stdio MCP server granted through `registry/mcp/comms.yaml`; templates `local-dsh`
v2 and `local-default` v2 grant it. The worker passes turn and attempt as well as the task ID, and
its writes take the fence (R19). Rejected: built-in tools in each runner (two copies of the logic).

## Assumptions

- One tenant; scoping is by request (D9). Tenant columns come with the Phase 4 gateway.
- Defaults: `idle_timeout` PT10M, `max_ask_wait` PT10M, question deadline PT5M, message body at most 16 KB.
- The fake model can script two agents (tests/support/fake_model); the live demo uses the local model.
- Each publish's lock costs under 20 ms at the spike's load; phase 01 task 2.3 measures it.

## Risks

- The fence lock on every batch slows checkpoints → measure in phase 01 (2.3); if p95 publish exceeds 250 ms, publish fewer, larger batches.
- The dispatcher is down → wake rows wait and are sent when it restarts; deadlines still fire as timers.
- A model asks but does not call `waiting` → the reply is delivered at its next wait; acceptance tests use the fake model.
- Many waiting tasks each hold a Workflow → they hold no worker slot; Continue-As-New bounds history.

## Rollout & rollback

Migration 0005 is additive. Deploy order: migrate, then workers, then the CLI. New template versions
start new tasks only; running tasks keep their template version. Rollback: redeploy the previous
workers; tasks already waiting stay waiting until their idle timeout fires on the new code, so drain
waiting tasks before rolling back. The migration stays (unused tables).

## Open questions

- None

## Impact

- Packages / directories: `common/events/`, `common/persistence/`, `common/schemas/`, `harness_activity/`, `orchestrator/`, `workers/`, `comms_mcp/` (new), `registry/`, `agentctl` (new), `tests/`, `docs/`.
- Data: migration 0005 (`agent_events`, `event_logs`, `event_batches`, `agent_messages`, `message_wakes`); message bodies in the blob store.
- Jobs / APIs: `TaskWorkflow` (patched), `run_harness_turn`, new Activity `claim_inbox`, the `inbox` Signal, the dispatcher, `finish_task` status `waiting`.

## Links

- ADR-0009 - events in a PostgreSQL table behind an event-transport interface; lists Phase 2's commitments and open items.
- ADR-0007 - every attempt write path takes the per-task fence.
- `docs/spikes/event-transport.md` - the spike's measurements, reader rule and table mechanics.
- Issue #79 - this phase; issue #74 - blob GC (Phase 3A).

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | Event table and agentctl tail | draft | 0/9 |
| 02 | Inbox, comms MCP and waiting tasks | draft | 0/10 |
| 03 | Acceptance and demo | draft | 0/7 |

## Decision log

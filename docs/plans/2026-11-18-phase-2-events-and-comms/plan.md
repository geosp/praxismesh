---
title: Phase 2 - real-time events and the comms MCP
status: draft
created: 2026-11-18
updated: 2026-11-18
design_review: { status: changes-requested, rounds: 1, last: 2026-11-18 }
approved: null
adr_review: null
---

# Phase 2 - real-time events and the comms MCP

## Summary

Agents become observable and can talk to each other. Each harness attempt publishes its events in
batches to a PostgreSQL event table (ADR-0009), and `agentctl tail` follows a task live, resumes from
an offset and reports pruned events (R1-R8). A stdio MCP server, `comms_mcp`, lets an agent message or
ask another task of its own request; tasks join a request with `task submit --join` (R10, D5). Messages
are durable rows; a dispatcher wakes the recipient's `TaskWorkflow` with a Signal (D6). A turn may end
`waiting`: the Workflow then checks its inbox and sleeps until a message, a question deadline, its idle
timeout or its wall-time budget, and continues as new while it waits (D7, D11). An agent that asks is
told to wait, and `finish_task` refuses `done` while its questions are open (D8). Woken turns have their
own budget, `max_wakes` (D14). Three phases: events, then messaging, then acceptance and the demo.

```text
run_harness_turn --batches--> agent_events <--follow-- agentctl tail
   |  comms_mcp --send/ask--> agent_messages + message_wakes --> dispatcher --Signal--> TaskWorkflow
   |                                                                       (claim_inbox -> next turn)
```

Risks: the fence lock on every event batch (measured in phase 01); a model that asks but never waits
(D8's refusal). Rollout drains running tasks before workers switch, and rollback drains tasks started on
the new code, because the old code cannot replay them (Rollout & rollback).

## Why

Roadmap Phase 2 (`docs/roadmap/phases/phase-2.md`) is next. Today events go to a no-op sink
(`harness_activity/events.py`), only the DSH runner emits them, and nothing stores or shows them. A
`TaskWorkflow` ends once its turns finish, so an agent cannot receive or wait for a message. The
event-transport spike (issue #76) chose the table and left the fence's lock order and cost, scoping,
keying and token text to this phase (ADR-0009). The owner settled seven behaviour questions on
2026-11-18 (D3's token rule, D7, D8, D9, D14 and the budget and refusal rules in D7 and D8).

## What changes

- Migrations 0005 (event tables, phase 01) and 0006 (message tables and the `praxis_comms` grants, phase 02).
- `common/events/`: the spike's interface, reader rule, in-memory reference and table transport (D1).
- One per-attempt event publisher, owned by `run_harness_turn` and passed to both runners (D2, D3).
- `agentctl`: a wrapper for the existing CLI, with `tail`, `events prune` and `task submit --join` (D4, D5).
- `comms_mcp/` with `post_status`, `send_to_agent`, `ask_agent`, `get_task_context` (D8, D9, D13, D15).
- `finish_task` gains `waiting`; `TaskWorkflow` waits, claims, wakes and continues as new (D7, D11, D12).
- A dispatcher in the orchestrator worker (D6); profile fields `idle_timeout`, `max_ask_wait`, `max_wakes`.
- The fake model scripts several agents (D16); new template versions grant `comms`; docs.

### Non-goals

- Model text in events, the gateway SSE endpoint (Phase 4), the UI (Phase 8), tenants (Phase 4).
- Scheduled retention of events and messages, and blob garbage collection (Phase 3A, issue #74).
- A planner that creates multi-agent tasks (Phase 3A); here tasks join a request through the CLI.

## Terms

- **Owner**: the project owner, who makes the decisions marked "owner decision".
- **Request**: one client submission (`request_id`); every task it starts shares it.
- **Task / turn / attempt**: a task is one `TaskWorkflow`; it runs turns (Activity `run_harness_turn`); a turn runs as attempts (Temporal tries).
- **Runner**: the harness that runs a turn, `DshRunner` (DeepSeek Harness, the default) or `openai_agents`.
- **Checkpoint**: a row saving a turn's session position and workspace; an attempt restores the newest one, and a finished turn's checkpoint holds its finish report.
- **`before_model_call`**: the hook every runner calls before each model request.
- **Resolved task**: the task's template, limits and queue, fixed by `resolve_capabilities` when the task starts.
- **Workflow ID**: a task's `TaskWorkflow` ID; it survives Continue-As-New.
- **Offset**: an event's position in its workflow's log, from 1, with no gaps.
- **Retained base**: the lowest offset still stored for a workflow.
- **Batch / batch ID**: the events one publish stores together, named `<workflow>:<attempt_id>:<n>`.
- **Reader rule**: a reader reports `Expired` when its offset is below the retained base, and when an offset jumps during a read.
- **Fence**: ADR-0007's rule that an attempt's write is valid only while no newer turn or attempt of its task exists, checked under the per-task advisory lock.
- **Superseded**: the exception that ends an attempt the fence refused.
- **Message / question / reply**: an inbox row from one task to another; a question expects a reply by its deadline; a reply names the question it answers.
- **Open question**: a question that is neither answered, expired nor cancelled.
- **Waiting**: a task between turns whose last turn ended with `finish_task(status="waiting")`.
- **Wake**: a Signal telling a waiting task's Workflow to check its inbox; **woken turn**: a turn that a claim started.
- **Claim**: Activity `claim_inbox`, which assigns a task's undelivered inbox rows to its next turn.
- **Dispatcher**: the loop in the orchestrator worker that turns wake rows into Signals.
- **`TaskState`**: the compact state a waiting Workflow carries into its next run.
- **Design §4.4**: the roadmap's design section on agent communications (`docs/roadmap/design-decisions.md`).

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

A batch from an attempt that a newer attempt has replaced is never stored.
- **Given** attempt 2 of a turn has started, **when** attempt 1 publishes, **then** nothing is stored.

### R5 · A refused publish ends the attempt

An attempt whose publish was refused ends `Superseded` at its next model call or when it finishes, whichever comes first, and writes nothing more.
- **Given** a refused publish during a 60 s tool call, **when** the call returns and the turn finishes, **then** the attempt ends `Superseded` and stores no checkpoint.

### R6 · Events never carry model text

Event payloads hold only counts, names, IDs and statuses; a token event carries token counts.
- **Given** a turn with three model responses, **when** it ends, **then** it stored three token events whose payloads hold counts only.

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

### R10 · Messages stay inside their request

A task may message only tasks of its own request.
- **Given** tasks in two requests, **when** one sends to the other, **then** the tool returns an error and nothing is delivered.

### R11 · Refused messages are recorded

Every refused send or ask is stored as a `rejected` row with its reason.
- **Given** a cross-request send, **when** it is refused, **then** a `rejected` row names the sender, the recipient and the reason.

### R12 · An accepted message is stored before the sender is told

`send_to_agent` and `ask_agent` return success only after the message row has committed.
- **Given** the database fails during a send, **when** the tool returns, **then** it reports an error.

### R13 · A message is delivered exactly once

An accepted message reaches exactly one turn of its recipient, even when sender or recipient attempts are retried.
- **Given** a send and then a worker killed before the sender's turn ends, **when** the turn reruns and repeats the send, **then** the recipient gets one message.
- **Given** a recipient attempt lost after its claim, **when** the turn reruns, **then** it gets the same messages again and no later turn gets them.

### R14 · A message wakes a waiting task

A message to a waiting task starts that task's next turn with the message in its input.
- **Given** task B waiting, **when** A sends to B, **then** B runs a turn whose input holds A's message.

### R15 · A wake is never lost

A message that arrives while its recipient is running, or before a Continue-As-New, is claimed before the recipient next sleeps.
- **Given** a reply that lands while the asker's turn runs, **when** that turn ends `waiting`, **then** the next turn starts at once with the reply.

### R16 · A reply wakes the asker

A reply to a question starts the asker's next turn with the reply and the question's correlation ID.
- **Given** A asked B and is waiting, **when** B replies, **then** A runs a turn holding the reply and the correlation ID.

### R17 · An unanswered question ends at its deadline

A question with no reply by its deadline expires, and the asker's next turn is told so.
- **Given** a question with a 30 s deadline and no reply, **when** 30 s pass, **then** the asker runs a turn saying no answer came.

### R18 · A late reply is refused

A reply to an expired or cancelled question, or after its deadline, is refused with an error to the replier.
- **Given** a question past its deadline, **when** the recipient replies, **then** the tool returns "question expired" and nothing is delivered.

### R19 · A task with open questions cannot finish

`finish_task` with `done` or `needs_input` returns an error while the task has open questions (owner decision).
- **Given** A has an open question, **when** A calls `finish_task("done")`, **then** the tool returns an error naming the question.

### R20 · An idle task completes after its idle timeout

A waiting task with no open question and no message completes `succeeded` after its idle timeout.
- **Given** an idle timeout of 60 s, **when** no message arrives, **then** the task completes `succeeded` within 60-65 s.

### R21 · A waiting task out of wall time ends by its open questions

A waiting task whose wall-time budget runs out completes `succeeded` with no open question, and `failed` with one (owner decision).
- **Given** a waiting task with an open question, **when** its wall time runs out, **then** it completes `failed` with "wall-time budget exhausted".

### R22 · Woken turns have their own budget

Woken turns count against `max_wakes` and never against `max_turns` (owner decision).
- **Given** `max_turns` 6 and `max_wakes` 50, **when** a task is woken 20 times, **then** it is not stopped by a turn budget.

### R23 · Questions never wait in a cycle

A question whose recipient is waiting, directly or through others, on a question from the asker is refused.
- **Given** A waits on a question to B, **when** B asks A, **then** B's ask is refused as a cycle.

### R24 · A task's end reaches the tasks waiting on it

When a task ends, its open questions are cancelled, questions to it are cancelled, and every task waiting on one of them is woken.
- **Given** A waits on a question to B, **when** B is cancelled, **then** A runs a turn saying B ended without replying.

### R25 · Messages to an ended task are refused

A send or ask to a task that has completed or failed is refused.
- **Given** B has completed, **when** A asks B, **then** the tool returns "recipient ended" and A is not left waiting.

### R26 · comms_mcp acts only as its own task

`comms_mcp` takes its task, turn and attempt from the worker, never from tool arguments.
- **Given** a tool call naming another task as sender, **when** it runs, **then** the message's sender is the calling task.

### R27 · comms_mcp writes are fenced

A send, ask or reply from a superseded attempt is refused.
- **Given** a stale attempt's `comms_mcp`, **when** it sends, **then** the send is refused and nothing is stored.

### R28 · Temporal history stays bounded

Events and message bodies never enter Temporal history, and no run of a waiting task exceeds 2,000 history events.
- **Given** a task woken 100 times (test registry, `max_wakes` 200), **when** its runs are inspected, **then** none exceeds 2,000 events.

### R29 · In-flight Phase 1 tasks still replay

The changed `TaskWorkflow` replays histories recorded by the Phase 1 code without nondeterminism.
- **Given** the recorded Phase 1 history in `tests/fixtures/`, **when** the replayer runs the new code, **then** it passes.

## Decisions

### D1 · Port the spike's table; offsets per workflow ID

Move the interface, reader rule, in-memory reference and table transport into `common/events/`, on
the app engine, with tables from migration 0005. Offsets are per workflow ID, which Continue-As-New
keeps; `seq` (an event's number within its attempt) stays per attempt. A publish also deletes that
workflow's batch rows older than 600 s. Rejected: per-task offsets (not what observers address);
`seq` as offset (it restarts each attempt). Details: notes.md#d1

### D2 · One publisher per attempt; fence with the task lock first

`run_harness_turn` creates the attempt's `AttemptEvents` over a `BatchingPublisher` and passes it to
the runner (`HarnessRunner.run` gains `events`). The publisher flushes per R7. A publish takes the task
lock, checks for a newer attempt, then locks the counter row, the same order as every fenced write. A
refusal is recorded; `before_model_call` and the attempt's final flush raise `Superseded` (R5).
Rejected: the runner owning events (two `seq` counters per attempt); unfenced events (ADR-0007).
Details: notes.md#d2

### D3 · Events for both runners; token counts only

The Activity emits `reset` at attempt start and `status` at turn end. `openai_agents` emits tool events
and one `token` event per response through its run hooks; DSH already does both. Token events carry
counts (owner decision). Rejected: model text in a blob per response (waits for Phase 4/8).

### D4 · Manual pruning in Phase 2

`agentctl events prune --task T (--below N | --older-than D)` deletes events and advances the retained
base, so tests and the demo can show expiry. Rejected: a retention job now (Phase 3A owns retention).

### D5 · `agentctl` wraps the existing CLI

`./agentctl` runs `orchestrator.cli` with `infra/.env`. `tail TASK [--after N] [--no-follow]` prints
one line per event and each `Expired`, and stops following when the task ends. `task submit --join REQ`
puts the new task in an existing request; `--request` keeps its meaning (a JSON request file).
Rejected: a console script (the project is not a package); letting clients name a new request ID.

### D6 · Durable inbox, wake rows and a dispatcher

A message and its wake row commit in one transaction, body in a `text` column (at most 16 KB). The
dispatcher `LISTEN`s, polls every 1 s, takes rows `FOR UPDATE SKIP LOCKED`, Signals `inbox`, and deletes
a row once the Signal is accepted. The Signal is only a hint (D7). Rejected: bodies in blobs (S3 access
for `comms_mcp`, orphan blobs); Signals from `comms_mcp` (a Temporal client in a worker subprocess,
against design §4.4); a long-polling Activity per waiting task (a worker slot each). Details: notes.md#d6

### D7 · `waiting` turns, the claim and the wait loop

On a `waiting` outcome the Workflow runs `claim_inbox` first. A non-empty claim starts a woken turn
at once; an empty one returns the next deadline among the task's open questions, and the Workflow
waits for an `inbox` Signal, that deadline, the idle timeout or the wall-time deadline, then claims
again. A Signal sets a `woken` flag at any time; `TaskState` carries it. Claims are keyed by task and
turn, use the Workflow's time for expiry, and the woken turn's input lists the claimed rows. On idle
timeout or wall time the task ends per R20 and R21. Rejected: keeping finished tasks open; a fresh
task per message (owner). Details: notes.md#d7

### D8 · Asking: ask, then wait

`ask_agent(task, text, wait?)` stores a question with a deadline (`wait`, default PT5M, at most
`max_ask_wait`) and returns its correlation ID and an instruction to call `finish_task("waiting")`.
`finish_task("done" | "needs_input")` is refused while questions are open (R19). A reply is
`send_to_agent(task, text, reply_to=ID)`. Rejected: blocking in the tool call (owner: DSH calls time
out at 150 s; a crash loses the wait); turning `done` into `waiting` silently (owner).

### D9 · Request scope, identity from the worker

A task may message only tasks with its `request_id` (owner decision). `comms_mcp` reads `PRAXIS_TASK_ID`,
`PRAXIS_TURN` and `PRAXIS_ATTEMPT`, set by the worker. Rejected: profile allow lists (new registry
fields now); audit only (does not reject).

### D10 · Message writes in one lock order

Every message write takes, in order: the sender's task lock (fence), then the request lock, a two-key
advisory lock in its own namespace. Recipient status, the cycle check and `cancel_for` run under the
request lock. Rejected: locking recipient tasks (two task locks in either order can deadlock).

### D11 · Continue-As-New while waiting

Before sleeping, the Workflow continues as new when Temporal suggests it or after 40 woken turns in
the run, carrying `TaskState` (resolved task, counters, usage, deadlines, `woken`). A continued run
skips `resolve_capabilities` and `record_task` and claims first. Rejected: never continuing (R28 fails
at ~100 wakes). Details: notes.md#d7

### D12 · Patch the Workflow

New Workflow behaviour sits behind `workflow.patched("phase2-wait")`; the existing `TaskWorkflow`
replay test and its Phase 1 fixture must keep passing (R29). Rejected: a new Workflow type (callers
and the CLI name `TaskWorkflow`).

### D13 · `comms_mcp` as a stdio server like `sample_mcp`

`comms_mcp/` is granted through `registry/mcp/comms.yaml`; templates `local-dsh` v2 and `local-default`
v2 grant it. It connects with `PRAXIS_COMMS_DB_URL`, a `praxis_comms` role allowed only the message
tables and reads of `tasks` and `task_attempts`. The idempotency key is the sender task, turn, tool and
canonical arguments, so a retried attempt repeating a send stores nothing. Rejected: built-in tools in
each runner (two copies); the app role (full write access). Details: notes.md#d6

### D14 · A wake budget

Profiles gain `max_wakes` (default 50, capped by the template's `max_wakes_cap`); woken turns count
against it, not `max_turns` (owner decision). Tokens and wall time cover all turns. Rejected: woken
turns as ordinary turns with raised caps (working and woken turns would compete for one budget).

### D15 · Status and context tools

`post_status(stage, progress?)` takes a fixed stage name and a 0-100 percentage and returns them; the
Activity's tool-call hook publishes them as a `status` event, so events keep one producer (D2).
`get_task_context()` returns the request's tasks: IDs, profiles and statuses. Rejected: free-text
status (model text in events, R6); `comms_mcp` publishing events (a second producer).

### D16 · A multi-agent fake model

The fake model picks a script by a `[script:NAME]` marker in the task instructions, and a step may use
`${result.N.field}` to reuse a field of an earlier tool result, such as a correlation ID. Rejected:
one fake endpoint per agent (two templates for one test).

## Assumptions

- One tenant; scoping is by request (D9). Tenant columns come with the Phase 4 gateway.
- Defaults: `idle_timeout` PT10M, `max_ask_wait` PT10M, question deadline PT5M, `max_wakes` 50.
- Each publish's task lock adds under 20 ms at the spike's load; phase 01 task 2.3 measures it, and the risk below names the limit that changes the plan.
- Two identical sends in one turn are one message (D13's key).

## Risks

- The fence lock slows publishing → phase 01 task 2.3 measures it; above 250 ms p95 the plan returns to design review to change R7's batching.
- The dispatcher is down → wake rows wait for it; deadlines and idle timeouts still fire as Workflow timers.
- A model ignores the ask-then-wait instruction → R19 refuses `done`; deadlines bound the wait.
- Many waiting tasks → each holds a Workflow but no worker slot; Continue-As-New bounds history.

## Rollout & rollback

Migrations 0005 and 0006 are additive. Order: stop new submissions and let running tasks finish;
migrate; deploy the orchestrator worker (it decodes `waiting` and runs the patched Workflow); deploy
harness workers with the v2 templates; then the CLI. Draining first matters because a worker serves
one template version and refuses others (`registry/loader.py`). Rollback: drain every task started
on the new code (the old code cannot replay their patched histories or `TaskState` inputs), delete
leftover `message_wakes` rows, then redeploy the old workers. The new tables stay, unused.

## Open questions

- None

## Impact

- Packages / directories: `common/events/` (new), `common/persistence/`, `common/schemas/`, `harness_activity/`, `orchestrator/`, `workers/`, `comms_mcp/` (new), `registry/`, `tests/support/fake_model/`, `infra/`, `agentctl` (new), `tests/`, `docs/`.
- Data: migration 0005 (`event_logs`, `agent_events`, `event_batches`); 0006 (`agent_messages`, `message_wakes`, `praxis_comms` grants).
- Jobs / APIs: `TaskWorkflow` (patched), `run_harness_turn`, `HarnessRunner.run` (gains `events`), Activity `claim_inbox`, Signal `inbox`, the dispatcher, `finish_task` status `waiting`, profile and template fields.

## Links

- ADR-0009 - events in a PostgreSQL table behind an event-transport interface; lists Phase 2's commitments and open items.
- ADR-0007 - every attempt write path takes the per-task fence.
- `docs/spikes/event-transport.md` - the spike's measurements, reader rule and table mechanics.
- Issue #79 - this phase; issue #74 - blob GC (Phase 3A).

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | Event table and agentctl tail | draft | 0/9 |
| 02 | Inbox, comms MCP and waiting tasks | draft | 0/12 |
| 03 | Acceptance and demo | draft | 0/8 |

## Decision log

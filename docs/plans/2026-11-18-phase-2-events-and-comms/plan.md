---
title: Phase 2 messaging - comms MCP, inbox and waiting tasks
status: draft
created: 2026-11-18
updated: 2026-11-18
design_review: { status: changes-requested, rounds: 2, last: 2026-11-18 }
approved: null
adr_review: null
---

# Phase 2 messaging - comms MCP, inbox and waiting tasks

## Summary

The second half of roadmap Phase 2: agents talk to each other. A stdio MCP server, `comms_mcp`, lets
an agent message or ask another task of its own request; tasks join a request with `task submit
--join` (R10, D5). Messages are durable rows in PostgreSQL; a dispatcher turns wake rows into `inbox`
Signals (D6). A turn may end `waiting`: the Workflow claims its inbox, and sleeps only if nothing came,
until a Signal, a question deadline, its idle timeout or its wall-time budget (D7). An asker is told to
wait, and `finish_task` refuses to finish while its questions are open (R19, D8). Questions that would
wait in a cycle are refused (R23). When a task ends, by any path including cancellation, its questions
close, its waiters wake, and messages it never took are marked undelivered (R24, R30). Woken turns
have their own budget, `max_wakes`, and long waits continue as new (D11, D14). Builds on the events
plan (`docs/plans/2026-11-18-phase-2-agent-events`), merged in PR #85.

```text
comms_mcp --send/ask (fenced)--> task_messages + message_wakes --NOTIFY--> dispatcher --Signal--> TaskWorkflow
                                        ^                                                    | claim_inbox (IDs only)
                                        +-------------- run_harness_turn reads bodies <------+
```

Risks: a real model that regenerates a send after a crash delivers it twice (Assumptions); waiting
tasks must be drained before workers switch, and a new database role needs a superuser step (Rollout).

## Why

Roadmap Phase 2 (`docs/roadmap/phases/phase-2.md`) asks for the comms MCP, a durable inbox, correlated
replies, idle wake-up, timeouts and cycle protection. Today a `TaskWorkflow` ends once its turns
finish, so an agent cannot receive or wait for a message, and every `task submit` starts a new request.
The owner decided on 2026-11-18 that an idle agent waits between turns, that asking ends the asker's
turn, that messaging stays inside a request, that woken turns have their own budget, that a waiting
task out of wall time ends by its open questions, and that `finish_task` refuses to finish with open
questions. Two design-review rounds shaped this revision (`reviews.md`).

## What changes

- Migration 0006: `task_messages`, `message_wakes`, table grants for the `praxis_comms` role (D6, D13).
- `infra/db/roles.sh`: creates `praxis_comms` and its `CONNECT` and `USAGE` grants; safe to rerun (D13).
- `comms_mcp/` with `post_status`, `send_to_agent`, `ask_agent`, `get_task_context` (D8, D9, D13, D15).
- `finish_task` gains `waiting`; `TaskWorkflow` claims, waits, wakes and continues as new (D7, D11, D12).
- The dispatcher in the orchestrator worker (D6); `task submit --join` (D5).
- Profile fields `idle_timeout`, `max_ask_wait`, `max_wakes`; template field `max_wakes_cap` (D14).
- The fake model scripts several agents (D16); new template versions grant `comms`; docs and demo.

### Non-goals

- Event storage and `agentctl tail` (the events plan).
- Tenants (Phase 4); scheduled retention of messages (Phase 3A); a planner that creates multi-agent tasks (Phase 3A).

## Terms

- **Owner**: the project owner, who makes the decisions marked "owner decision".
- **Registry**: the YAML files under `registry/` that define profiles, templates and MCP servers.
- **Profile**: a registry entry a task is submitted with; it sets the task's limits and allowed templates.
- **Template / template version**: a registry entry for a worker type (runner, model, MCP servers, caps); a worker serves one version of each template and refuses turns for another.
- **Request**: one client submission (`request_id`); every task it starts shares it.
- **Task / turn / attempt**: a task is one `TaskWorkflow`; it runs turns (Activity `run_harness_turn`); a turn runs as attempts (Temporal tries).
- **Runner**: the harness that runs a turn: `DshRunner` (DeepSeek Harness, the default) or `openai_agents`.
- **Checkpoint**: a row saving a turn's session position and workspace; a finished turn's checkpoint holds its finish report.
- **Resolved task**: the task's template, limits and queue, fixed by Activity `resolve_capabilities` at start.
- **Fence**: ADR-0007's rule that an attempt's write is valid only while no newer turn or attempt of its task exists.
- **Message / question / reply**: an inbox row from one task to another; a question expects a reply by its deadline and has a correlation ID; a reply names that ID.
- **Open question**: a question not answered, expired or cancelled, whose deadline has not passed.
- **Waiting**: a task between turns whose last turn ended with `finish_task(status="waiting")`.
- **Claim**: Activity `claim_inbox`, which assigns a task's pending inbox rows to its next turn and returns their IDs.
- **Woken turn**: a turn started because a claim returned rows.
- **Dispatcher**: the loop in the orchestrator worker that turns wake rows into `inbox` Signals.
- **`cancel_for`**: the step, run when a task ends, that closes its questions and messages and wakes affected waiters.
- **`TaskState`**: the compact state a waiting Workflow carries into its next run.
- **Design §4.4**: the roadmap's design section on agent communications (`docs/roadmap/design-decisions.md`).

## Requirements

### R10 · Messages stay inside their request

A task may message only tasks of its own request.
- **Given** tasks in two requests, **when** one sends to the other, **then** the tool returns an error and nothing is delivered.

### R11 · Rule refusals are recorded

A send or ask refused by the request, recipient, cycle or deadline rules is stored as a `rejected` row with its reason.
- **Given** a cross-request send, **when** it is refused, **then** a `rejected` row names the sender, the recipient and the reason.

### R12 · An accepted message is stored before the sender is told

`send_to_agent` and `ask_agent` return success only after the message row has committed.
- **Given** the database fails during a send, **when** the tool returns, **then** it reports an error.

### R13 · A message reaches at most one turn

An accepted message is delivered to at most one turn of its recipient, and a repeated identical send stores nothing.
- **Given** a send, then the worker killed and the turn rerun with the same send, **when** the recipient claims, **then** it gets one message.
- **Given** a recipient attempt lost after its claim, **when** the turn reruns, **then** it reads the same messages and no later turn gets them.

### R14 · A message wakes a waiting task

A message to a waiting task starts that task's next turn with the message in its input.
- **Given** task B waiting, **when** A sends to B, **then** B runs a turn whose input holds A's message.

### R15 · A wake is never lost

A message that arrives while its recipient runs, or before a Continue-As-New, is claimed before the recipient next sleeps.
- **Given** a reply that lands while the asker's turn runs, **when** that turn ends `waiting`, **then** the next turn starts at once with the reply.

### R16 · A reply wakes the asker

A reply to a question starts the asker's next turn with the reply and the question's correlation ID.
- **Given** A asked B and is waiting, **when** B replies, **then** A runs a turn holding the reply and the correlation ID.

### R17 · An unanswered question ends at its deadline

A question with no reply by its deadline expires, and the asker's next turn is told so.
- **Given** a question with a 30 s deadline and no reply, **when** 30 s pass, **then** the asker runs a turn saying no answer came.

### R18 · A late reply is refused

A reply to a question that is not open is refused with an error to the replier.
- **Given** a question past its deadline, **when** the recipient replies, **then** the tool returns "question expired" and nothing is delivered.

### R19 · A task with open questions cannot finish

`finish_task` with `done` or `needs_input` returns an error to the model while the task has open questions, and the run continues (owner decision).
- **Given** A has an open question, **when** A calls `finish_task("done")` on either runner, **then** the tool returns an error naming the question and the model gets another step.

### R20 · An idle task completes after its idle timeout

A waiting task with no open question and no message completes `succeeded` after its idle timeout.
- **Given** an idle timeout of 60 s, **when** no message arrives, **then** the task completes `succeeded` within 60-65 s.

### R21 · Out of wall time with no open question succeeds

A waiting task whose wall-time budget runs out with no open question completes `succeeded` (owner decision).
- **Given** a waiting task with no open question, **when** its wall time runs out, **then** it completes `succeeded`.

### R31 · Out of wall time with an open question fails

A waiting task whose wall-time budget runs out with an open question completes `failed` (owner decision).
- **Given** a waiting task with an open question, **when** its wall time runs out, **then** it completes `failed` with "wall-time budget exhausted".

### R22 · Woken turns have their own budget

Woken turns count against `max_wakes` and never against `max_turns` (owner decision).
- **Given** `max_turns` 6 and `max_wakes` 50, **when** a task is woken 20 times, **then** no turn budget stops it.

### R23 · Questions never wait in a cycle

A question whose recipient is waiting, directly or through others, on a question from the asker is refused.
- **Given** A waits on a question to B, **when** B asks A, **then** B's ask is refused as a cycle.

### R24 · A task's end wakes the tasks waiting on it

When a task ends by any path, including cancellation while it waits, every question to or from it closes and every task waiting on one of them is woken.
- **Given** A waits on a question to B and B is waiting, **when** B is cancelled, **then** A runs a turn saying B ended without replying.

### R25 · Messages to an ended task are refused

A send or ask to a task that has completed or failed is refused.
- **Given** B has completed, **when** A asks B, **then** the tool returns "recipient ended" and A is not left waiting.

### R30 · A message never taken is marked undelivered

When a task ends, its pending and claimed-but-unread messages are marked `undelivered`, and `get_task_context` shows them to their senders.
- **Given** A sends to B while B runs, **when** B's turn ends `done`, **then** the message is `undelivered` and A's `get_task_context` lists it.

### R32 · A waiting task's result carries its outputs

A task that ends while waiting returns the outputs of its last `waiting` turn.
- **Given** a turn that writes an output and ends `waiting`, **when** the idle timeout ends the task, **then** its result lists that output.

### R26 · comms_mcp acts only as its own task

`comms_mcp` takes its task, turn and attempt from the worker, never from tool arguments.
- **Given** a tool call naming another task as sender, **when** it runs, **then** the message's sender is the calling task.

### R27 · comms_mcp writes are fenced

A send, ask or reply from a superseded attempt is refused, and nothing is stored.
- **Given** a stale attempt's `comms_mcp`, **when** it sends, **then** the tool returns an error and no row is written.

### R28 · Message bodies stay out of Temporal history

No message body enters Temporal history; claims and Signals carry only IDs and counts.
- **Given** a woken turn with three 16 KB messages, **when** its run's history is inspected, **then** no event holds a body.

### R33 · Waiting runs stay bounded

No run of a waiting task exceeds 2,000 history events.
- **Given** a task woken 100 times (test profile, `max_wakes` 200), **when** its runs are inspected, **then** none exceeds 2,000 events.

### R29 · In-flight Phase 1 tasks still replay

The changed `TaskWorkflow` replays histories recorded by the Phase 1 code without nondeterminism.
- **Given** the recorded Phase 1 history in `tests/fixtures/`, **when** the replayer runs the new code, **then** it passes.

## Decisions

### D5 · Joining a request from the CLI

`task submit --join REQ` puts the new task in an existing request; the CLI checks a task with that
request exists before submitting. `--request` keeps its meaning (a JSON request file). Rejected:
letting clients name a new request ID (scope rests on requests, R10).

### D6 · Durable inbox, wake rows and a dispatcher

A message, its wake row and a `NOTIFY message_wakes` commit in one transaction; the body is a `text`
column (at most 16 KB). The dispatcher `LISTEN`s, polls every 1 s, takes rows `FOR UPDATE SKIP LOCKED`
and Signals `inbox`. It deletes a row once the Signal is accepted, or when the Workflow is closed or
missing (logged); other errors keep the row for the next poll. Rejected: bodies in blobs (S3 access
for `comms_mcp`, orphans); Signals from `comms_mcp` (a Temporal client in a worker subprocess, against
design §4.4); one long-polling Activity per waiting task (a worker slot each). Details: notes.md#d6

### D7 · Claim before sleeping

After a `waiting` turn the Workflow runs `claim_inbox`, which returns claimed row IDs, a count and the
next deadline among the task's open questions, never bodies. A count above zero starts a woken turn,
whose Activity reads the bodies by task and turn. Otherwise the Workflow sleeps until an `inbox`
Signal, that deadline, the idle timeout or the wall-time deadline, then claims again. A `waiting` turn
writes a finish record and its outputs; the Workflow keeps the latest outputs for its result (R32).
Rejected: keeping finished tasks open; a fresh task per message (owner). Details: notes.md#d7

### D8 · Ask, then wait; `finish_task` checks open questions

`ask_agent(task, text, deadline_s?)` stores a question (default 300 s, at most `max_ask_wait`) and
returns its correlation ID with an instruction to call `finish_task("waiting")`. The Activity gives
`finish_task` an open-question check; a refusal leaves the run going. `openai_agents` stops on an
accepted `finish_task` only (a `tool_use_behavior` function); DSH already does. Rejected: blocking in
the tool call (owner: DSH calls time out at 150 s); turning `done` into `waiting` silently (owner).

### D9 · Request scope, identity from the worker

A task may message only tasks with its `request_id` (owner decision). `comms_mcp` reads
`PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT`, which the worker sets when it starts the MCP
servers for each attempt (both runners); the attempt is Temporal's attempt number, the fence key.
Rejected: profile allow lists (new registry fields now); audit only (does not reject).

### D10 · Message writes in one lock order

Every message write takes the sender's task lock and fence check, then a request lock (a two-key
advisory lock in its own namespace). Recipient status, the cycle walk and `cancel_for` run under the
request lock. Rejected: locking recipient tasks (two task locks taken in either order can deadlock).

### D11 · Continue-As-New while waiting

Before sleeping, the Workflow continues as new when Temporal suggests it or its run's history passes
1,000 events, carrying `TaskState` (resolved task, counters, usage, deadline, latest outputs) as an
optional second `run` argument. A continued run skips `resolve_capabilities` and `record_task` and
claims first. Rejected: never continuing (R33 fails at ~100 wakes). Details: notes.md#d7

### D12 · Patch the Workflow

New Workflow behaviour sits behind `workflow.patched("phase2-wait")`, and the existing replay test
keeps passing (R29). Rollout drains tasks, but a task the drain misses must still replay; the patch
makes that safe. Rejected: a new Workflow type (callers and the CLI name `TaskWorkflow`).

### D13 · `comms_mcp` as a scoped stdio server

`comms_mcp/` is granted through `registry/mcp/comms.yaml`, like `sample_mcp` (the example shop server).
It connects as `praxis_comms`, which may write only the message tables and read `tasks` and
`task_attempts`. Its idempotency key is the sender task, turn, tool and canonical arguments.
Rejected: built-in tools in each runner (two copies); the app role (full write access).

### D14 · A wake budget and its path

Profiles gain `idle_timeout`, `max_ask_wait` and `max_wakes`, with defaults; templates gain
`max_wakes_cap`. `resolve_capabilities` puts them in the resolved task; the Activity passes
`max_ask_wait` to `comms_mcp`. Woken turns count against `max_wakes`, not `max_turns` (owner).
Rejected: woken turns as ordinary turns with raised caps (one budget for two kinds of turn).

### D15 · Status and context tools

`post_status(stage, progress?)` takes a stage from a fixed list (`planning`, `working`, `waiting`,
`reviewing`, `done`) and a 0-100 percentage; both runners' tool-event paths publish it as a `status`
event through the attempt's publisher. `get_task_context()` returns the request's tasks (IDs,
profiles, statuses) and the caller's undelivered messages. Rejected: free-text status (model text in
events); `comms_mcp` publishing events (a second producer per attempt).

### D16 · A multi-agent fake model

The fake model picks a script by a `[script:NAME]` marker in the task instructions, and a step may use
`${result.N.field}` to reuse a field of an earlier tool result, such as a correlation ID. Rejected:
one fake endpoint per agent (two templates for one test).

### D17 · Ending a task closes its messages

`complete_task` marks the task ended and runs `cancel_for` in one transaction under the request lock:
questions to and from it are cancelled, its pending and claimed-but-unread messages become
`undelivered`, and askers waiting on it get wake rows. The Workflow runs `complete_task` on every
ending, including a cancellation caught during a wait. Rejected: leaving rows pending (senders never learn).

## Assumptions

- One tenant; scoping is by request (D9). Tenant columns come with the Phase 4 gateway.
- Defaults: `idle_timeout` PT10M, `max_ask_wait` PT10M, `max_wakes` 50.
- A model that regenerates a send after a crash writes different text, so the repeat is a new message; only identical repeats are deduplicated (R13).
- A Workflow terminated (not cancelled) never runs `complete_task`; its task stays `running`, and sends to it are accepted until their deadlines.

## Risks

- The dispatcher is down → wake rows wait for it; deadlines and idle timeouts still fire as Workflow timers.
- A model ignores the ask-then-wait instruction → R19 keeps it from finishing; deadlines bound the wait.
- Many waiting tasks → each holds a Workflow but no worker slot; Continue-As-New bounds history.

## Rollout & rollback

Prerequisite: the events plan is deployed. Order: stop new submissions; let running tasks finish, or
cancel waiting ones with `temporal workflow cancel`; run `infra/db/roles.sh` as the database superuser
(creates `praxis_comms`); migrate (0006 grants it the message tables); deploy the orchestrator worker,
which accepts `waiting`; deploy harness workers with the v2 templates; then the CLI. Draining matters
because a worker serves one template version (Terms). Rollback: drain tasks started on the new code,
because the old code cannot replay their histories; delete leftover `message_wakes` rows; redeploy the
old workers. The tables and role stay, unused.

## Open questions

- None

## Impact

- Packages / directories: `comms_mcp/` (new), `common/persistence/`, `common/schemas/`, `harness_activity/`, `orchestrator/`, `workers/`, `registry/`, `tests/support/fake_model/`, `infra/db/`, `infra/`, `tests/`, `docs/`.
- Data: migration 0006 (`task_messages`, `message_wakes`, grants); role `praxis_comms`.
- Jobs / APIs: `TaskWorkflow` (patched), `run_harness_turn`, `complete_task`, Activity `claim_inbox`, Signal `inbox`, the dispatcher, `finish_task` status `waiting`, profile and template fields, `task submit --join`.

## Links

- `docs/plans/2026-11-18-phase-2-agent-events` - the events half: the event table, publisher and `agentctl tail`.
- ADR-0007 - every attempt write path takes the per-task fence.
- ADR-0009 - events in a PostgreSQL table; message transport stays PostgreSQL per design §4.4.
- Issue #79 - Phase 2.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 02 | Inbox, comms MCP and waiting tasks | draft | 0/15 |
| 03 | Acceptance and demo | draft | 0/7 |

## Decision log

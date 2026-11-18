---
title: Phase 2 messaging - comms MCP, inbox and waiting tasks
status: draft
created: 2026-11-18
updated: 2026-11-18
design_review: { status: passed, rounds: 3, last: 2026-11-18 }
approved: null
adr_review: null
---

# Phase 2 messaging - comms MCP, inbox and waiting tasks

## Summary

The second half of roadmap Phase 2: agents talk to each other. A stdio MCP server, `comms_mcp`, lets
an agent message or ask another task of its own request; tasks join a request with `task submit
--join` (R10, D5). Messages are durable rows in PostgreSQL, and a sleeping recipient is woken once by an
`inbox` Signal (D6). A turn may end `waiting`. The Workflow then claims its inbox: if anything is
pending, the next turn starts at once; if not, it sleeps until a Signal, a question deadline or its idle
timeout (D7). Out of wall time, it succeeds with no open question and fails with one (R21, R31). An
asker is told to wait, and `finish_task` refuses to finish while its questions are open or their
replies unread (R19, D8). When a task ends, by any path, its questions close and its waiters wake
(R24, D17). Woken turns have their own budget, and runs continue as new (D11, D14).

```text
comms_mcp --send/ask (fenced)--> task_messages + message_wakes --NOTIFY--> dispatcher --Signal--> TaskWorkflow
                                        ^                                                    | claim_inbox (IDs only)
                                        +-------------- run_harness_turn reads bodies <------+
```

Risks (see Risks): the dispatcher or database down while tasks wait, and a model that ignores the
ask-then-wait instruction. Rollout needs a superuser step for the new database role, and a rollback
must first drain the tasks started on the new code (Rollout & rollback).

## Why

Roadmap Phase 2 (`docs/roadmap/phases/phase-2.md`) asks for the comms MCP, a durable inbox, correlated
replies, idle wake-up, timeouts and cycle protection. Today a `TaskWorkflow` ends once its turns
finish, so an agent cannot receive or wait for a message, and every `task submit` starts a new request.
The owner settled six behaviours on 2026-11-18 (D7, D8, D9, D14, R19, R21 and R31). The events half
(`docs/plans/2026-11-18-phase-2-agent-events`) is merged; this plan's requirement and decision numbers
continue after that plan's. Three design-review rounds shaped this revision (`reviews.md`).

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
- **`record_task` / `complete_task`**: the Activities that write the task's row in `tasks` when it starts and its result when it ends; `task_attempts` holds one row per attempt.
- **`max_turns`, wall-time budget**: existing profile limits, capped by the template: the most turns a task may run, and the time from the task's start (kept across Continue-As-New) by which it must end.
- **`needs_input`**: the existing `finish_task` status for a task that cannot continue without the user.
- **Orchestrator worker / harness workers**: the worker that runs `TaskWorkflow` and its short Activities / the workers that run `run_harness_turn` for one template each.
- **App role**: the database role the workers use, with write access to every application table.
- **Fence**: ADR-0007's rule that an attempt's write is valid only while no newer turn or attempt of its task exists.
- **Message / question / reply**: an inbox row from one task to another; a question expects a reply by its deadline and has a correlation ID; a reply names that ID.
- **Open question**: a question not answered, expired or cancelled, whose deadline has not passed.
- **Unread reply**: a reply to the task's own question that no turn of the task has read yet.
- **Waiting**: a task between turns whose last turn ended with `finish_task(status="waiting")`.
- **Claim**: Activity `claim_inbox`, which marks the task's questions past their deadline expired, assigns its pending inbox rows (messages, replies, and its own expired or cancelled questions) to its next turn, and returns their IDs.
- **Sleeping**: a waiting task whose last claim found nothing; only a sleeping task is sent a Signal.
- **Woken turn**: a turn started because a claim returned rows.
- **Dispatcher**: the loop in the orchestrator worker that turns wake rows into `inbox` Signals.
- **`cancel_for`**: the step, run when a task ends, that closes its questions and messages and wakes affected waiters.
- **`TaskState`**: the compact state a waiting Workflow carries into its next run.
- **Publisher**: the events plan's per-attempt event stream (`BatchingPublisher`), which both runners' tool events go through.
- **Fake model**: the scripted model endpoint the integration tests use (`tests/support/fake_model`).
- **Design §4.4**: the roadmap's design section on agent communications (`docs/roadmap/design-decisions.md`).

## Requirements

### R10 · Messages stay inside their request

A task may message only tasks of its own request.
- **Given** tasks in two requests, **when** one sends to the other, **then** the tool returns an error and nothing is delivered.

### R11 · Rule refusals are recorded

A send, ask or reply refused by the request, ended-task, cycle or closed-question rules is stored as a `rejected` row with its reason.
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

`finish_task` with `done` or `needs_input` returns an error to the model while the task has open questions or unread replies, and the run continues (owner decision, extended to unread replies).
- **Given** A has an open question, **when** A calls `finish_task("done")` on either runner, **then** the tool returns an error naming the question and the model gets another step.
- **Given** B replied while A's turn ran, **when** A calls `finish_task("done")`, **then** it is refused until A has waited and read the reply.

### R20 · An idle task completes after its idle timeout

A waiting task with no open question and no message completes `succeeded` once it has slept, without a wake, for its idle timeout.
- **Given** an idle timeout of 60 s, **when** no message arrives, **then** the task completes `succeeded` within 60-65 s.

### R21 · Out of wall time with no open question succeeds

A waiting task whose wall-time budget runs out with no open question completes `succeeded` (owner decision).
- **Given** a waiting task with no open question, **when** its wall time runs out, **then** it completes `succeeded`.

### R22 · Woken turns have their own budget

Turns started by a claim count against `max_wakes` and never against `max_turns`; when `max_wakes` is used up the task fails with "wake budget exhausted" (owner decision).
- **Given** `max_turns` 6 and `max_wakes` 50, **when** a task is woken 20 times, **then** no turn budget stops it.

### R23 · Questions never wait in a cycle

A question is refused when its recipient is the asker itself, or is waiting, directly or through others, on an answer from the asker.
- **Given** A waits on a question to B, **when** B asks A, **then** B's ask is refused as a cycle.
- **Given** task A, **when** A asks A, **then** the ask is refused.

### R24 · A task's end wakes the tasks waiting on it

When a task ends by any path, including cancellation or a failed claim while it waits, every question to or from it closes and every task waiting on one of them is woken.
- **Given** A waits on a question to B and B is waiting, **when** B is cancelled, **then** A runs a turn saying B ended without replying.

### R25 · Messages to an ended task are refused

A send or ask to or from a task that has completed or failed is refused.
- **Given** B has completed, **when** A asks B, **then** the tool returns "recipient ended" and A is not left waiting.

### R26 · comms_mcp acts only as its own task

`comms_mcp` takes its task, turn and attempt from the worker, never from tool arguments.
- **Given** a tool call naming another task as sender, **when** it runs, **then** the message's sender is the calling task.

### R27 · comms_mcp writes are fenced

A send, ask or reply from a superseded attempt is refused, and nothing is stored.
- **Given** a stale attempt's `comms_mcp`, **when** it sends, **then** the tool returns an error and no row is written.

### R28 · Message bodies stay out of Temporal history

Claims and Signals carry only IDs, counts and deadlines, never a message body.
- **Given** a woken turn with three 16 KB messages, **when** its run's history is inspected, **then** no event holds a body.

### R29 · In-flight Phase 1 tasks still replay

The changed `TaskWorkflow` replays histories recorded by the Phase 1 code without nondeterminism.
- **Given** the recorded Phase 1 history in `tests/fixtures/`, **when** the replayer runs the new code, **then** it passes.

### R30 · A message never taken is marked undelivered

When a task ends, its pending and claimed-but-unread messages are marked `undelivered`, and `get_task_context` shows them to their senders.
- **Given** A sends to B while B runs, **when** B's turn ends `done`, **then** the message is `undelivered` and A's `get_task_context` lists it.

### R31 · Out of wall time with an open question fails

A waiting task whose wall-time budget runs out with an open question completes `failed` (owner decision).
- **Given** a waiting task with an open question, **when** its wall time runs out, **then** it completes `failed` with "wall-time budget exhausted".

### R32 · A waiting task's result carries its outputs

A task that ends while waiting returns the outputs of its last `waiting` turn.
- **Given** a turn that writes an output and ends `waiting`, **when** the idle timeout ends the task, **then** its result lists that output.

### R33 · Waiting runs stay bounded

No run of a waiting task exceeds 2,000 history events, however often it is woken or messaged.
- **Given** a task woken 100 times back to back (test profile and template, `max_wakes` 200), **when** its runs are inspected, **then** none exceeds 2,000 events.
- **Given** 50 messages sent to a task during one turn, **when** the turn ends, **then** the run received at most one `inbox` Signal for them.

## Decisions

### D5 · Joining a request from the CLI

`task submit --join REQ` puts the new task in an existing request; the CLI checks a task with that
request exists before submitting. `--request` keeps its meaning (a JSON request file). Rejected:
letting clients name a new request ID (scope rests on requests, R10).

### D6 · Durable inbox, wake rows and a dispatcher

A message commits with its body in a `text` column (at most 16 KB). Only if the recipient is sleeping
does the same transaction add its one wake row (at most one per recipient) and `NOTIFY message_wakes`,
so Signals scale with sleeps, not messages. The dispatcher `LISTEN`s, polls every 1 s, takes rows
`FOR UPDATE SKIP LOCKED` and Signals `inbox`; it deletes a row once the Signal is accepted or the
Workflow is closed or missing (logged), and keeps it on other errors. Rejected: bodies in blobs (S3 access
for `comms_mcp`, orphans); Signals from `comms_mcp` (a Temporal client in a worker subprocess, against
design §4.4); one long-polling Activity per waiting task (a worker slot each). Details: notes.md#d6

### D7 · Claim before sleeping

After a `waiting` turn the Workflow runs `claim_inbox`, which expires due questions, returns claimed
row IDs, a count and the next open-question deadline, never bodies, and marks the task sleeping when
the count is zero. A count above zero starts a woken turn, whose Activity reads the bodies by task and
turn and marks them `read` (a fenced write). Otherwise the Workflow sleeps until an `inbox` Signal,
that deadline, the idle timeout (restarted at each sleep) or the wall-time deadline, then claims
again. The claim retries until the wall-time deadline; if it still fails, or the task is cancelled,
the task ends through `complete_task` (D17).
Rejected: keeping finished tasks open; a fresh task per message (owner decisions). Details: notes.md#d7

### D18 · A waiting turn keeps its outputs

A `waiting` turn writes a finish record, so a lost attempt after `finish_task("waiting")` does not
rerun the model, and collects its outputs like `done`. The Workflow keeps the latest outputs for its
result (R32). Rejected: outputs only on `done` (a task ending while waiting would return none).

### D8 · Ask, then wait; `finish_task` checks open questions

`ask_agent(task, text, deadline_s?)` stores a question (default 300 s, clamped to `max_ask_wait`) and
returns its correlation ID with an instruction to call `finish_task("waiting")`. The Activity gives
`finish_task` a check for open questions and unread replies, run under the request lock so an ask in
the same model step is seen; a refusal leaves the run going. `openai_agents` stops on an
accepted `finish_task` only (a `tool_use_behavior` function); DSH already does. Rejected: blocking in
the tool call (owner: DSH calls time out at 150 s); turning `done` into `waiting` silently (owner).

### D9 · Request scope, identity from the worker

A task may message only tasks with its `request_id` (owner decision). `comms_mcp` reads
`PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT`, which the worker sets when it starts the MCP
servers for each attempt (both runners); the attempt is Temporal's attempt number, the fence key.
Rejected: profile allow lists (new registry fields now); audit only (does not reject).

### D10 · Message writes in one lock order

Every attempt write (send, ask, reply, marking rows read) takes the sender's task lock and fence check,
then the request lock: `pg_advisory_xact_lock(2, hashtext(request_id))`, a key space apart from the
task locks. Sender and recipient status, the cycle walk, the claim and `cancel_for` run under the
request lock; the claim and `cancel_for` run in the orchestrator, not an attempt, so they take no fence. Rejected: locking recipient tasks (two task locks taken in either order can deadlock).

### D11 · Continue-As-New while waiting

After every `waiting` outcome, before it claims, the Workflow continues as new when Temporal suggests
it or its run's history passes 1,000 events, carrying `TaskState` (resolved task, counters, usage, deadline, latest outputs) as an
optional second `run` argument. A continued run skips `resolve_capabilities` and `record_task` and
claims first. Rejected: never continuing (R33 fails at ~100 wakes). Details: notes.md#d7

### D12 · Patch the Workflow

The loop is restructured around the new endings, so the changed code sits behind
`workflow.patched("phase2-wait")` and the existing Phase 1 replay test keeps passing (R29). A Phase 1
history never reaches the waiting path, so the patch guards only command order on the old paths. Rejected: a new Workflow type (callers and the CLI name `TaskWorkflow`).

### D13 · `comms_mcp` as a scoped stdio server

`comms_mcp/` is granted through `registry/mcp/comms.yaml`, like `sample_mcp` (the example shop server).
It connects as `praxis_comms`, which may write only the message tables and read `tasks` and
`task_attempts`. Its idempotency key is the sender task, turn, tool and the arguments as sorted-key
JSON. Templates v2 grant it with a new prompt file, since the template hash covers the prompt.
Rejected: built-in tools in each runner (two copies); the app role (full write access).

### D14 · A wake budget and its path

Profiles gain `idle_timeout`, `max_ask_wait` and `max_wakes`, with defaults; templates gain
`max_wakes_cap` (default 100); the effective `max_wakes` is the smaller, as for `max_turns`.
`resolve_capabilities` puts them in the resolved task; `TurnInput` gains `max_ask_wait` (with a
default), which the Activity passes to `comms_mcp`. Turns started by a claim count against
`max_wakes`; every other turn, including a `continue` after a woken turn, counts against `max_turns`.
Rejected: woken turns as ordinary turns with raised caps (one budget for two kinds of turn).

### D15 · Status and context tools

`post_status(stage, progress?)` takes a stage from a fixed list (`planning`, `working`, `waiting`,
`reviewing`, `done`) and a 0-100 percentage; in `comms_mcp` it only validates them, and both runners'
tool-event paths publish the validated values as a `status` event through the attempt's publisher. `get_task_context()` returns the request's tasks (IDs,
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
ending: done, a budget, a cancellation or a failed claim during a wait. Rejected: leaving rows pending
(senders never learn).

## Assumptions

- One tenant; scoping is by request (D9). Tenant columns come with the Phase 4 gateway.
- Defaults: `idle_timeout` PT10M, `max_ask_wait` PT10M, `max_wakes` 50.
- A model that regenerates a send after a crash writes different text, so the repeat is a new message; only identical repeats are deduplicated (R13).
- A Workflow terminated (not cancelled) never runs `complete_task`; its task stays `running`, and sends to it are accepted until their deadlines.
- On `openai_agents`, the `sh` tool runs in the worker container and can read its environment, including the comms database URL, as it can `PRAXIS_SAMPLE_DB_URL` today; DSH runs commands in its isolated container. A known limit for `openai_agents`.
- The `--join` check runs in the CLI; a task may join a request whose tasks have all ended, and its messages to them are then refused (R25).

## Risks

- The dispatcher is down → wake rows wait for it; deadlines and idle timeouts still fire as Workflow timers.
- The database is down while tasks wait → claims retry until each task's wall-time deadline (D7); past it, the task ends through `complete_task`, which also needs the database, so a long outage leaves such tasks `failed` once it returns.
- A model ignores the ask-then-wait instruction → R19 keeps it from finishing; deadlines bound the wait.
- Many waiting tasks → each holds a Workflow but no worker slot; Continue-As-New bounds history.

## Rollout & rollback

Prerequisite: the events plan is deployed. Order:
1. Stop clients submitting (there is no submit gate) and let running tasks finish, because a worker
   serves one template version and the v2 templates replace v1.
2. `make db-roles` as the database superuser (creates `praxis_comms`; safe to rerun), then `make migrate`
   (0006 grants it the message tables).
3. Deploy the orchestrator worker first (it accepts `waiting` and the new `TurnInput` field), then the
   harness workers with the v2 templates, then the CLI.

Rollback: drain every task started on the new code, since the old code cannot replay its histories
(cancel waiting ones with `temporal workflow cancel`); delete leftover `message_wakes` rows; redeploy
the old workers. The tables and role stay, unused.

## Open questions

- None

## Impact

- Packages / directories: `comms_mcp/` (new), `common/persistence/`, `common/schemas/`, `harness_activity/`, `orchestrator/`, `workers/`, `registry/`, `tests/support/fake_model/`, `infra/db/`, `infra/`, `tests/`, `docs/`.
- Data: migration 0006 (`task_messages`, `message_wakes`, grants); role `praxis_comms`.
- Jobs / APIs: `TaskWorkflow` (patched), `run_harness_turn`, `complete_task`, Activity `claim_inbox`, Signal `inbox`, the dispatcher, `finish_task` status `waiting`, `TurnInput.max_ask_wait`, profile and template fields, `task submit --join`, `make db-roles`.

## Links

- `docs/plans/2026-11-18-phase-2-agent-events` - the events half: the event table, publisher and `agentctl tail`.
- ADR-0007 - every attempt write path takes the per-task fence.
- ADR-0009 - events in a PostgreSQL table; message transport stays PostgreSQL per design §4.4.
- Issue #79 - Phase 2.

## Phases

Phase 01 (the event table) is the events plan's; this plan's phases are 02 and 03, and their tasks are
in `phases/`.

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 02 | Inbox, comms MCP and waiting tasks | draft | 0/15 |
| 03 | Acceptance and demo | draft | 0/7 |

## Decision log

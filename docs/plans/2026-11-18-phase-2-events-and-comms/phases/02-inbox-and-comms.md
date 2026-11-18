---
phase: 2
title: Inbox, comms MCP and waiting tasks
status: draft
branch: null
base: null
delivers: [R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20, R21, R22, R23, R24, R25, R26, R27, R28, R29]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-18 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · Inbox, comms MCP and waiting tasks

## Goal

Tasks of one request message and ask each other through `comms_mcp`; a waiting task claims its inbox,
wakes on a message, reply, deadline, idle timeout or wall-time limit, and its history stays bounded.

## Tasks

### 1. Inbox

- [ ] 1.1 Add migration 0006: `agent_messages`, `message_wakes`, and grants for the `praxis_comms` role, which `infra/db/init.sh` creates (D6, D13, notes.md#d6). Verify: upgrade and downgrade on a copy of the dev database; a test connects as `praxis_comms` and is refused a write to `tasks`.
- [ ] 1.2 Add `MessageRepository`: `send`, `ask` (with the cycle check), `reply` (checks status and deadline), `claim(task, turn, now)`, `cancel_for(task)` (writes wake rows for affected waiters), each in D10's lock order and fenced (D6, D10, D13, R10-R13, R17, R18, R23-R25, R27). Verify: an integration test for each scenario of those requirements, and a repeated `send` with the same key stored once.
- [ ] 1.3 Add `MessageEnvelope` to `common/schemas/` and `schemas.md` (D6). Verify: schema unit tests.

### 2. comms_mcp

- [ ] 2.1 Add `comms_mcp/` with `post_status`, `send_to_agent`, `ask_agent`, `get_task_context`, and `registry/mcp/comms.yaml` (D8, D9, D13, D15, R26). Verify: tests through the MCP client for each tool, including a refused cross-request send and a sender argument that is ignored.
- [ ] 2.2 Pass `PRAXIS_TURN` and `PRAXIS_ATTEMPT` to MCP servers (`harness_activity/config.py`); publish `post_status` calls as `status` events from the tool-call hook; add `local-dsh` v2 and `local-default` v2 granting `comms`, with `max_wakes_cap` and the ask-then-wait prompt text; `make registry-lock` (D8, D13, D14, D15). Verify: `tests/test_registry.py`; the DSH capability test lists the comms tools.
- [ ] 2.3 Add `task submit --join REQ`: `TaskRequest` gains an optional request ID, and `prepare_task` refuses one with no existing task (D5). Verify: `tests/test_submit.py` and `tests/test_cli.py` cases.

### 3. Waiting tasks

- [ ] 3.1 Add `waiting` to `finish_task`, `RunResult`, `AttemptOutcome` and `TurnOutcome`; refuse `done` and `needs_input` while questions are open; add profile fields `idle_timeout`, `max_ask_wait`, `max_wakes` (D7, D8, D14, R19). Verify: runner conformance tests for `waiting` and for the refusal.
- [ ] 3.2 Scope the restore path's finish replay to the same turn; a woken turn's input renders its claimed rows instead of the continue message (D7, notes.md#d7). Verify: an integration test where turn 2 after a `waiting` turn 1 runs the model and sees its messages.
- [ ] 3.3 Add the `claim_inbox` Activity: runs `claim` with the Workflow's time, returns the claimed rows and the next deadline (D7, R13, R15, R17). Verify: a rerun of the same claim returns the same rows; a claim after the deadline returns the expiry.
- [ ] 3.4 Patch `TaskWorkflow`: claim before sleeping, the `inbox` Signal and `woken` flag, the wait timers, R20 and R21 endings, `cancel_for` on every ending, `max_wakes`, Continue-As-New with `TaskState` (D7, D11, D12, D14, R14-R17, R20-R22, R24, R28, R29). Verify: `tests/test_task_workflow.py` time-skipping tests for each of those scenarios, including 100 wakes under 2,000 events per run; the existing replay test passes.
- [ ] 3.5 Add the dispatcher to the orchestrator worker (D6, R14). Verify: an integration test stops the dispatcher, sends, restarts it, and the recipient wakes; a wake for a closed Workflow is deleted and logged.

### 4. Docs

- [ ] 4.1 Update `schemas.md`, the decision log and the runbook (joining a request, waiting tasks, the dispatcher, `PRAXIS_COMMS_DB_URL`). Verify: `check_plans.py` and the link check pass.

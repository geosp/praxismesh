---
phase: 2
title: Inbox, comms MCP and waiting tasks
status: draft
branch: null
base: null
delivers: [R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20, R21, R22, R23, R24, R25, R26, R27, R28, R29, R30, R31, R32, R33]
design_review: { status: changes-requested, rounds: 2, last: 2026-11-18 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · Inbox, comms MCP and waiting tasks

## Goal

Tasks of one request message and ask each other through `comms_mcp`; a waiting task claims its inbox
before sleeping, wakes on a message, reply, deadline, idle timeout or wall-time limit, and every ending
closes its messages and wakes its waiters.

## Tasks

### 1. Schemas and registry

- [ ] 1.1 Add `idle_timeout`, `max_ask_wait`, `max_wakes` (profile), `max_wakes_cap` (template) and the resolved fields, all with defaults; fill them in `resolve_capabilities` (D14, R22, R29). Verify: `tests/test_registry.py`; the existing `TaskWorkflow` replay test still decodes the Phase 1 `ResolvedTask`.
- [ ] 1.2 Add `waiting` to `finish_task`, `RunResult`, `AttemptOutcome` and `TurnOutcome`; a `waiting` turn writes a finish record and collects outputs like `done` (D7, R32). Verify: runner conformance tests for `waiting`, and a lost attempt after `finish_task("waiting")` that does not rerun the model.

### 2. Inbox

- [ ] 2.1 Add `infra/db/roles.sh` (creates `praxis_comms` with `CONNECT` and schema `USAGE`, safe to rerun; called by `init.sh` on fresh volumes) and migration 0006 (tables, grants, revokes on downgrade); add `PRAXIS_COMMS_DB_PASSWORD` and `PRAXIS_COMMS_DB_URL` to `infra/.env.example`, `infra/check-prereqs.sh` and the harness workers' Compose env (D6, D13, notes.md#d6). Verify: on a copy of the dev volume, `roles.sh` twice then upgrade and downgrade; a test as `praxis_comms` is refused a write to `tasks`.
- [ ] 2.2 Add `MessageRepository`: `send`, `ask` (cycle walk), `reply`, `claim`, `read_claimed`, `open_questions`, `end_task` (`cancel_for` with the task's status change), each in D10's lock order and fenced (D6, D10, D17, R10-R13, R17, R18, R23, R25, R27, R30). Verify: an integration test for each scenario of those requirements.
- [ ] 2.3 Add `MessageEnvelope` to `common/schemas/` and `schemas.md` (D6). Verify: schema unit tests.

### 3. comms_mcp

- [ ] 3.1 Add `comms_mcp/` with the four tools and `registry/mcp/comms.yaml` (D8, D9, D13, D15, R26). Verify: tests through the MCP client for each tool, including a refused cross-request send and an ignored sender argument.
- [ ] 3.2 In `build_config`, pass `PRAXIS_TURN`, `PRAXIS_ATTEMPT` (Temporal's attempt) and `PRAXIS_MAX_ASK_WAIT` to MCP servers; publish `post_status` calls as `status` events in both runners' tool paths; give `finish_task` the open-question check; make `openai_agents` stop only on an accepted `finish_task` (D8, D9, D15, R19). Verify: conformance tests on both runners for a refused `finish_task("done")` that lets the model continue, and for a `status` event.
- [ ] 3.3 Add `local-dsh` v2 and `local-default` v2 granting `comms`, with `max_wakes_cap` and the ask-then-wait prompt text; `make registry-lock` (D8, D13, D14). Verify: `tests/test_registry.py`; the DSH capability test lists the comms tools.
- [ ] 3.4 Add `task submit --join REQ` with the existence check (D5). Verify: `tests/test_cli.py` and `tests/test_submit.py` cases, including an unknown request refused.

### 4. Waiting tasks

- [ ] 4.1 Scope the restore path's finish replay to the same turn; a woken turn's input renders its claimed rows from `read_claimed` (D7, R13, R14, R16). Verify: an integration test where the turn after a `waiting` turn runs the model and sees its messages, and a rerun reads the same rows.
- [ ] 4.2 Add Activity `claim_inbox(task, turn, now)`: returns IDs, a count and the next deadline (D7, R15, R17, R28). Verify: a rerun returns the same IDs; a claim after a deadline returns the expiry; the result holds no body.
- [ ] 4.3 Patch `TaskWorkflow`: claim before sleeping, the `inbox` Signal, the wait timers, the R20, R21 and R31 endings, `max_wakes`, `complete_task` on every ending including a cancellation during the wait, Continue-As-New with `TaskState` (D7, D11, D12, D14, D17, R14-R17, R20-R22, R24, R29, R31-R33). Verify: `tests/test_task_workflow.py` time-skipping tests for each scenario, including a cancel during the wait and 100 wakes with every run under 2,000 events; the replay test passes.
- [ ] 4.4 Make `complete_task` call `end_task` (D17, R24, R30). Verify: an integration test where B ends `done` with a pending message (marked `undelivered`) and A, waiting on B, is woken.
- [ ] 4.5 Add the dispatcher to the orchestrator worker (D6, R14). Verify: an integration test stops the dispatcher, sends, restarts it, and the recipient wakes; a wake for a closed Workflow is deleted and logged.

### 5. Docs

- [ ] 5.1 Update `schemas.md`, the decision log and the runbook (`roles.sh`, joining a request, waiting tasks, draining, the dispatcher). Verify: `check_plans.py` and the link check pass.

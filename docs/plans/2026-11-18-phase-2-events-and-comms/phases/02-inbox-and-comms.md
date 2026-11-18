---
phase: 2
title: Inbox, comms MCP and waiting tasks
status: draft
branch: null
base: null
delivers: [R9, R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-18 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · Inbox, comms MCP and waiting tasks

## Goal

Tasks of one request message and ask each other through `comms_mcp`; a waiting task wakes on a
message, a reply, a deadline or its idle timeout, and its history stays bounded.

## Tasks

### 1. Inbox

- [ ] 1.1 Add the message part of migration 0005: `agent_messages` (ID, request, sender and recipient task, kind, correlation and reply-to IDs, deadline, status, body ref, idempotency key, claimed turn) and `message_wakes` (notes.md#d6). Verify: upgrade and downgrade on a copy of the dev database.
- [ ] 1.2 Add `MessageRepository`: fenced `send` (request check, idempotency key from task, turn, attempt and call number, message and wake row in one transaction), `ask` with the cycle check under a request lock, `reply` that refuses expired or cancelled questions, `claim` for a task and turn, `expire_due`, `cancel_for` (D6, D9, D10, R10, R11, R15, R17, R18, R19). Verify: integration tests for each scenario of R10, R11, R15, R17 and R19, and a repeated `send` with the same key stored once.
- [ ] 1.3 Add `MessageEnvelope` to `common/schemas/` and `schemas.md` (D6). Verify: schema unit tests.

### 2. comms_mcp

- [ ] 2.1 Add `comms_mcp/` with `post_status`, `send_to_agent`, `ask_agent`, `get_task_context` (the request's tasks: IDs, profiles, statuses), and `registry/mcp/comms.yaml` (D8, D9, D13). Verify: unit tests through the MCP client for each tool, including a refused cross-request send.
- [ ] 2.2 Pass `PRAXIS_TURN` and `PRAXIS_ATTEMPT` to MCP servers (`harness_activity/config.py`); add `local-dsh` v2 and `local-default` v2 granting `comms`, the prompt text for ask-then-wait, and `make registry-lock` (D8, D13). Verify: `tests/test_registry.py`; the DSH capability test lists the comms tools.

### 3. Waiting tasks

- [ ] 3.1 Accept `finish_task(status="waiting")` in both runners and `TurnOutcome`; add profile fields `idle_timeout` and `max_ask_wait` (D7, D8). Verify: runner conformance tests for `waiting`.
- [ ] 3.2 Add the `claim_inbox` Activity (runs `expire_due`, then `claim`, idempotent per task and turn) and deliver claimed messages, replies, expiries and cancellations in the next turn's input (D7, R12, R13, R14, R18). Verify: integration tests rerun the same claim and get the same messages.
- [ ] 3.3 Patch `TaskWorkflow`: the wait loop, the `inbox` Signal, idle-timeout completion, `cancel_for` on completion and cancellation, Continue-As-New with `TaskState` (D7, D11, D12, R9, R16, R18, R20). Verify: `tests/test_task_workflow.py` time-skipping tests for wake, deadline, idle timeout, cancellation and 100 wakes under 2,000 events per run; a replay test of a recorded Phase 1 history.
- [ ] 3.4 Add the dispatcher to the orchestrator worker: `LISTEN`, 1 s poll, Signal, delete the wake row after the Signal is accepted; a wake for a closed Workflow is dropped and recorded (D6, R11, R12). Verify: an integration test stops the dispatcher, sends, restarts it, and the recipient wakes.

### 4. Docs

- [ ] 4.1 Update `schemas.md`, the decision log and the runbook (submit into a request, waiting tasks, the dispatcher). Verify: `check_plans.py` and the link check pass.

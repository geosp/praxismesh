---
phase: 1
title: Harness seam and registry
status: draft
branch: null
base: null
delivers: [R1, R2, R11]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-15 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · Harness seam and registry

## Goal

Both runners can sit behind one session store. The registry accepts a versioned
`dsh` harness. An `AgentEvent` sink exists. `openai_agents` behaviour is unchanged.

## Tasks

### 1. Seam

- [ ] 1.1 Add the session store interface (load, truncate, capture, acknowledge) and move `run_harness_turn` onto it, with `SQLAlchemySession` as its first implementation (D1). Verify: `uv run pytest` passes; the conformance suite takes a runner fixture and passes for `openai_agents`.

### 2. Harness value

- [ ] 2.1 Add `dsh` to `Harness` in `common/schemas/base.py`, to `SUPPORTED_HARNESSES` and to `docs/roadmap/schemas.md`, with a decision-log line (R1). Verify: registry tests accept a `dsh` template and reject an unknown harness.
- [ ] 2.2 Enforce matching `harness` between a profile and its allowed templates (R2). Verify: a mismatched profile fails to load.
- [ ] 2.3 Add the DSH pin fields (release, wheel and native binary digests) to `registry.lock` generation (R12). Verify: `make registry-lock` writes them; a changed digest fails the lock check.

### 3. Events

- [ ] 3.1 Add the `AgentEvent` sink with no-op and in-memory implementations, and emit `status`, `tool_call`, `tool_result` and `token` events from `openai_agents` (R11, D8). Verify: a unit test sees ordered events with attempt ID and no prompt text.

---
phase: 1
title: Harness seam and registry
status: draft
branch: null
base: null
delivers: [R1, R2]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · Harness seam and registry

## Goal

Both runners sit behind one session/checkpoint interface, and the registry accepts
a versioned `dsh` harness, with `openai_agents` behaviour unchanged.

## Tasks

### 1. Seam

- [ ] 1.1 Extract session load, truncation and checkpoint position into an interface used by `run_harness_turn`; keep `SQLAlchemySession` as its first implementation (R2, D1). Verify: `uv run pytest` and `tests/test_runner_conformance.py` pass unchanged.

### 2. Registry

- [ ] 2.1 Add `dsh` to supported harnesses with lock pinning and profile/template matching (R1, D5). Verify: registry tests for accepted `dsh`, rejected unknown harness, and lock hash.
- [ ] 2.2 Add the harness event interface with a no-op sink and `openai_agents` emitting status, tool and token events (R8). Verify: unit test of ordered events with attempt identity and no prompt text.

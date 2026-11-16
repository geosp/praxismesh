---
phase: 1
title: Harness seam and registry
status: done
branch: feat/62-dsh-harness-seam
base: 0f32d7dd3077fcc13d03f7b16e7de7481e34c954
delivers: [R1, R2, R3]
design_review: { status: passed, rounds: 3, last: 2026-11-15 }
impl_review: { status: passed, rounds: 2, last: 2026-11-15 }
approved: 2026-11-15
verification: { status: passed, last: 2026-11-15 }
demo: { status: passed, last: 2026-11-15 }
evidence:
  code_sha: 4969d4dbeaddd6fd8f6af777a9b0fdbe50db0bb3
  docs_sha: 38e379ce6849e315e3f4a779bf1ef08d1cbb060a
  review: docs/plans/2026-11-15-dsh-production-harness/reviews.md
  verification: docs/reviews/general-dsh-production-harness/verification-phase-01.md
  demo: docs/demos/general-dsh-production-harness-01.md
---

# Phase 01 · Harness seam and registry

## Goal

The cgroup boundary is proven possible, both runners can sit behind one fenced
session store, and the registry accepts `dsh`, `local-dsh` and the `dsh` profile.

## Tasks

### 0. Gate

- [x] 0.1 Probe cgroup v2 freeze, per-attempt UID and mount namespace in a container with the notes.md#d3 Compose settings (D3, Assumptions). Verify: a probe script freezes and kills a process tree; if freeze fails, SIGSTOP works with its stated limit; if both fail, stop and return to the owner.

### 1. Seam

- [x] 1.1 Add the session store (load, truncate, capture, commit) and the D10 transactional fence, and move `run_harness_turn` onto them with `SQLAlchemySession` (D1, D10). Verify: `uv run pytest` passes; the conformance suite runs through a runner fixture for `openai_agents` (R3).

### 2. Registry

- [x] 2.1 Add `dsh` to `Harness` (`common/schemas/base.py`), `SUPPORTED_HARNESSES` and `docs/roadmap/schemas.md`, with a decision-log line (R1). Verify: registry tests reject an unknown harness.
- [x] 2.2 Move the profile/template harness check (`registry/loader.py:101-105`) from resolve time to load time (R2). Verify: a mismatched profile fails to load.
- [x] 2.3 Add the `local-dsh` template (`concurrency_per_pod: 1`, `context_window`) and the `dsh` profile, and lock them (D5, D7). Verify: `make registry-lock` pins both; a `dsh` profile resolves `local-dsh`.

### 3. Events

- [x] 3.1 Add the `AgentEvent` sink with no-op and in-memory implementations (D8). Verify: a unit test records ordered events with attempt ID.

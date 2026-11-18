---
phase: 3
title: Acceptance and demo
status: draft
branch: null
base: null
delivers: [R2, R6, R9, R10, R11, R12, R13, R14, R18]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 03 · Acceptance and demo

## Goal

The roadmap Phase 2 Accept line passes as integration tests on the Compose stack, the demo is run and
recorded, and the as-built overview describes what runs.

## Tasks

### 1. Acceptance tests

- [ ] 1.1 Add `tests/integration/test_two_agents.py` with fake-model scripts for two DSH tasks in one request: A asks B, B is waiting and wakes, B replies, A resumes with the answer (R12, R13). Verify: the test passes on the Compose stack.
- [ ] 1.2 Add the failure cases: an unanswered question times out (R14); a cross-request message is refused (R10); the DSH worker is killed after a send and before B's turn, and the message is delivered once (R11, R18); a task continues as new while waiting and still receives its reply (R9, R18). Verify: each passes; the Continue-As-New case asserts a new run ID.
- [ ] 1.3 Add a reconnect test: `tail` stops mid-run, resumes with `--after`, and the printed offsets have no gap or repeat (R2). Verify: passes.
- [ ] 1.4 Add a busy-response check: a scripted turn emitting 2,000 events keeps its run's history under 200 events and stores the events in batches (R6, R9). Verify: the test reports history event count and size.

### 2. Demo and docs

- [ ] 2.1 Write the demo script (`infra/demo/phase-2.sh` or a documented walkthrough) for the roadmap checklist with the local model: tail, ask, wake, reconnect, timeout, refused message, history bound. Verify: a dry run from a clean `infra/.env.example` worktree.
- [ ] 2.2 Add the Phase 2 section to `docs/architecture/overview.md` (components, data, failure and recovery, limits, deviations). Verify: the verifier's as-built check.
- [ ] 2.3 Update `AGENTS.md` status, `PROJECT_PLAN.md` status and the roadmap Phase 2 checkboxes after verification. Verify: `check_plans.py` passes.

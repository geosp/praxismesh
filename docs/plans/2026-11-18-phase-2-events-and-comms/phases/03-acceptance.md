---
phase: 3
title: Acceptance and demo
status: draft
branch: null
base: null
delivers: [R10, R13, R14, R16, R17, R19, R24, R30, R33]
design_review: { status: changes-requested, rounds: 2, last: 2026-11-18 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 03 · Acceptance and demo

## Goal

The roadmap Phase 2 Accept line passes as integration tests on the Compose stack, the demo is run and
recorded, and the as-built overview describes what runs.

## Tasks

### 1. Acceptance tests

- [ ] 1.1 Extend the fake model with per-task scripts and result references (D16). Verify: unit tests for script selection and `${result.N.field}`.
- [ ] 1.2 Add `tests/integration/test_two_agents.py`: two DSH tasks in one request; A asks B, B is waiting and wakes, B replies, A resumes with the answer (R14, R16). Verify: passes on the Compose stack.
- [ ] 1.3 Add the failure cases: an unanswered question times out (R17); a cross-request message is refused (R10); the DSH worker is killed after a send and before the turn ends, and the message is delivered once (R13); B is cancelled while waiting, and A is told (R24). Verify: each passes.
- [ ] 1.4 Add the ending cases: A's `finish_task("done")` is refused while its question is open and A then waits (R19); B ends `done` with an unread message, which A's `get_task_context` lists as undelivered (R30). Verify: each passes.
- [ ] 1.5 Add a Continue-As-New case with a test profile (`max_wakes` 200): a task woken 100 times keeps every run under 2,000 history events and still receives a reply after a new run starts (R33). Verify: passes and reports run IDs and history sizes.

### 2. Demo and docs

- [ ] 2.1 Write the demo walkthrough for the roadmap checklist with the local model (tail, ask, wake, reconnect, timeout, refused message, history bound) and record the run in `docs/demos/phase-2.md`. Verify: a dry run from a clean worktree whose `infra/.env` comes from `infra/.env.example`.
- [ ] 2.2 Add the Phase 2 messaging section to `docs/architecture/overview.md` (components, data, failure and recovery, limits, deviations) and update the `AGENTS.md` and `PROJECT_PLAN.md` status lines after verification. Verify: the verifier's as-built check; `check_plans.py` passes.

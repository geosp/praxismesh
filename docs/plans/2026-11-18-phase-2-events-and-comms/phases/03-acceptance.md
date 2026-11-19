---
phase: 3
title: Acceptance and demo
status: done
branch: feat/79-agent-messaging
base: c1dbee715362602f959a36afd5aca4ecda3bd552
delivers: [R10, R13, R14, R16, R17, R19, R24, R30, R33]
design_review: { status: passed, rounds: 3, last: 2026-11-18 }
impl_review: { status: passed, rounds: 1, last: 2026-11-19 }
approved: 2026-11-18
verification: { status: passed, last: 2026-11-19 }
demo: { status: passed, last: 2026-11-19 }
evidence:
  code_sha: 417c441c0f3c65ec637f873113a41d72aeda1e0e
  docs_sha: 8e9802ad67a36d28fbf8785cf4dd2ab58e65d051
  review: docs/plans/2026-11-18-phase-2-events-and-comms/reviews.md
  verification: docs/reviews/phase-2/verification-messaging.md
  demo: docs/demos/phase-2.md
---

# Phase 03 · Acceptance and demo

## Goal

The roadmap Phase 2 Accept line passes as integration tests on the Compose stack, the demo is run and
recorded, and the as-built overview describes what runs.

## Tasks

### 1. Acceptance tests

- [x] 1.1 Extend the fake model with per-task scripts and result references (D16). Verify: unit tests for script selection and `${result.N.field}`.
- [x] 1.2 Add `tests/integration/test_two_agents.py`: two DSH tasks in one request; A asks B, B is waiting and wakes, B replies, A resumes with the answer (R14, R16). Verify: passes on the Compose stack.
- [x] 1.3 Add the failure cases: an unanswered question times out (R17); a cross-request message is refused (R10); the DSH worker is killed after a send and before the turn ends, and the message is delivered once (R13); B is cancelled while waiting, and A is told (R24). Verify: each passes.
- [x] 1.4 Add the ending cases: A's `finish_task("done")` is refused while its question is open and A then waits (R19); B ends `done` with an unread message, which A's `get_task_context` lists as undelivered (R30). Verify: each passes.
- [x] 1.5 Add history cases with a test profile and template (`max_wakes` and `max_wakes_cap` 200): a task woken 100 times back to back keeps every run under 2,000 history events and still receives a reply after a new run starts; 50 messages sent during one turn bring at most one `inbox` Signal (R33). Verify: passes and reports run IDs, history sizes and Signal counts.

### 2. Demo and docs

- [x] 2.1 Write the demo walkthrough for the roadmap checklist with the local model (tail, ask, wake, reconnect, timeout, refused message, history bound) and record the run in `docs/demos/phase-2.md`. Verify: a dry run from a clean worktree whose `infra/.env` comes from `infra/.env.example`.
- [x] 2.2 Add the Phase 2 messaging section to `docs/architecture/overview.md` (components, data, failure and recovery, limits, deviations) and update the `AGENTS.md` and `PROJECT_PLAN.md` status lines after verification. Verify: the verifier's as-built check; `check_plans.py` passes.

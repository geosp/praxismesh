---
phase: 3
title: Acceptance and default switch
status: draft
branch: null
base: null
delivers: [R2, R9]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 03 · Acceptance and default switch

## Goal

`local-dsh@1` passes the benchmark rule, and the owner can switch the `default`
profile to it with a one-line rollback.

## Tasks

### 1. Acceptance

- [ ] 1.1 Add `local-dsh@1` and run `make benchmark` on it and on `local-default@1` the same day (R9, R2, D5). Verify: DSH loses at most one task against the baseline; both results recorded under `docs/benchmarks/`.

### 2. Switch

- [ ] 2.1 Switch the `default` profile to `local-dsh@1` after owner approval, keeping `local-default@1` loadable (D5). Verify: registry lock updated; a task on the `default` profile runs on DSH.
- [ ] 2.2 Document operation, rollback and the upstream-barrier follow-up in the runbook (D6). Verify: rollback walkthrough reverts the profile and a task runs on `openai_agents`.

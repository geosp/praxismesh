---
phase: 3
title: Acceptance and default switch
status: draft
branch: null
base: null
delivers: [R4, R19]
design_review: { status: changes-requested, rounds: 2, last: 2026-11-15 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 03 · Acceptance and default switch

## Goal

`local-dsh` meets the baseline rule, and the owner can switch the `default`
profile to it with a two-field rollback.

## Tasks

### 1. Acceptance

- [ ] 1.1 Add `--profile` to `tests/benchmarks/run.py` (`running_workers` already takes a template), and set `local-dsh`'s `turn_timeout` and `max_wall_time_cap` as in `local-default` (D5). Verify: a benchmark dry run selects each profile.
- [ ] 1.2 Run `make benchmark` on `dsh` and on `default` the same day (R19, R4). Verify: each fails at most one task; both results are recorded under `docs/benchmarks/`.

### 2. Switch

- [ ] 2.1 After the owner approves the cost (Open questions), point the `default` profile at `dsh`/`local-dsh` (D5). Verify: the load-time check accepts it, and a `default` task runs on DSH.
- [ ] 2.2 Create `docs/operations/runbook.md` with the deploy order, the bounded drain, rollback and the upstream barrier follow-up (D6). Verify: a walkthrough reverts the two fields, and a new task runs on `openai_agents`.

---
phase: 3
title: Acceptance and default switch
status: draft
branch: null
base: null
delivers: [R3, R14]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-15 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 03 · Acceptance and default switch

## Goal

`local-dsh@1` meets the baseline rule. The owner can switch the `default` profile
to it, with a two-field rollback.

## Tasks

### 1. Acceptance

- [ ] 1.1 Add `--profile` and `--template` to `tests/benchmarks/run.py` and a template parameter to `tests/support/workers.py`. Add `local-dsh@1`, with `turn_timeout` and `max_wall_time_cap` as in `local-default@1`, and the `dsh` profile (D5). Verify: a benchmark dry run selects each template.
- [ ] 1.2 Run `make benchmark` on `dsh` and on `default` the same day (R14, R3). Verify: DSH loses at most one task; both results are recorded under `docs/benchmarks/`.

### 2. Switch

- [ ] 2.1 After owner approval of cost (Open questions), point the `default` profile at `local-dsh@1` (D5). Verify: `profile.harness` and `allowed_templates` are `dsh`/`local-dsh@1`; a `default` task runs on DSH.
- [ ] 2.2 Create `docs/operations/runbook.md` with the deploy order, drain or cancel steps, rollback and the upstream barrier follow-up (D6). Verify: a walkthrough reverts the two fields, and a new task runs on `openai_agents`.

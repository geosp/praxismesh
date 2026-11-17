---
phase: 3
title: Acceptance and default switch
status: in-progress
branch: feat/62-dsh-acceptance
base: 285dd44034aef6c2bd4e40d6ae14811e546b7048
delivers: [R4, R19, R20]
design_review: { status: passed, rounds: 4, last: 2026-11-16 }
impl_review: { status: changes-requested, rounds: 1, last: 2026-11-17 }
approved: 2026-11-15
---

# Phase 03 · Acceptance and default switch

## Goal

`local-dsh` meets the baseline rule, its licence notices are recorded, and the
owner can switch the `default` profile to it, and back, with `openai_agents`
still selectable through its own profile.

## Tasks

### 1. Acceptance

- [x] 1.1 Add `--profile` to `tests/benchmarks/run.py`: take the template from the profile instead of `TEMPLATE`, label the harness and name the results by profile, and for a `dsh` profile start a paired DSH container (a non-pytest helper shared with `tests/support/dsh.py`) and point `DSH_CONTROL` at it (D5). Verify: a one-task smoke run per profile, written outside `docs/benchmarks/` and not judged against the baseline, completes; its file name and `harness` label follow the profile.
- [x] 1.2 Run `make benchmark` on `dsh` and on `default` the same day (R19, R4). Verify: each fails at most one task; both results are recorded under `docs/benchmarks/`.
- [x] 1.3 Record the licence notices of every distribution in `infra/dsh/requirements.txt` under `docs/licences/dsh/`, with a check in CI that each pinned distribution has one (R20). Verify: the check passes, and fails when a notice is removed.

### 2. Switch

- [x] 2.1 Add an `openai` profile allowing `local-default`, repoint the tests and Make targets that assume `default` is `local-default` (`tests/test_registry.py`, `tests/test_runner_conformance.py` (R3 resolves through `openai`), `test_recovery.py`, `test_task_e2e.py`, `test_tracing.py`, `test_submit.py`, `make workers-check`, `make workers-up`), and add the second DSH pair (notes.md#rollout). Then, after the owner approves the cost, point `default` at `dsh`/`local-dsh` (D5). Verify: CI passes; a `default` task runs on DSH and an `openai` task on `openai_agents`.
- [x] 2.2 Create `docs/operations/runbook.md` from notes.md#rollout: deploy order, the switch and revert steps, the drain bound, roll-forward only, refusing workers, and the upstream barrier follow-up (D6). Verify: a walkthrough reverts the switch, a DSH task started before it finishes on DSH, and a new task runs on `openai_agents`.

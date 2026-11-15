---
phase: 2
title: DSH runner and worker pair
status: draft
branch: null
base: null
delivers: [R4, R5, R6, R7, R8, R9, R10, R12, R13]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-15 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · DSH runner and worker pair

## Goal

A `tpl.local-dsh` worker and its DSH container run turns through `DshRunner`.
The spike's control cases pass as production integration tests.

## Tasks

### 1. Worker pair

- [ ] 1.1 Build the DSH container image (pinned release, digests, licence notices) and the launcher. The launcher checks digests at start-up, runs one process group per attempt, kills it when the control socket closes, and reaps leftovers at start-up (D3, R7, R12). Verify: a mismatched digest blocks start-up; killing the control socket stops the attempt within 5 s.
- [ ] 1.2 Add the `dsh` worker and DSH container pair to `infra/docker-compose.yml`, sharing an attempt volume, with no network and no credentials in the DSH container (D3). Verify: `docker compose up` starts both; cgroup freeze and thaw work from the launcher (Assumptions).
- [ ] 1.3 Choose the runner from `template.harness` in `workers/main.py` (D1). Verify: a `dsh` template's queue gets `DshRunner`; `local-default` is unchanged.

### 2. Runner

- [ ] 2.1 Port the classification, ownership, gateway ledger, executor and barrier to `harness_activity/dsh/` with their spike tests, and add the D7 migration (R4, R5, R8, R9, D2, D6, D7, D9). Verify: the ported unit tests pass; `alembic upgrade head` adds `usage_known` and the nullable token columns.
- [ ] 2.2 Implement `DshRunner`: production tools, skills and MCP over the executor; commands through the launcher; DSH events mapped to the D8 sink (R10, R11, D4). Verify: the conformance suite, marked `integration` and skipped in CI, passes for `dsh` with a scripted provider.
- [ ] 2.3 Port the recovery, stop, accounting and R13 outcome cases, plus worker SIGKILL, as integration tests (R4–R9, R13). Verify: `uv run pytest -m integration` passes them and no DSH process remains.

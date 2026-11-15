---
phase: 2
title: DSH runner and worker pair
status: draft
branch: null
base: null
delivers: [R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18]
design_review: { status: changes-requested, rounds: 2, last: 2026-11-15 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · DSH runner and worker pair

## Goal

A `tpl.local-dsh` worker and its DSH container run turns through `DshRunner`, and
the spike's control cases pass as production integration tests.

## Tasks

### 1. Worker pair

- [ ] 1.1 Build the DSH image with the pinned release and digests recorded in the registry lock and the granted `cli_tools`. Build the launcher: it reports its digests, gives each attempt a cgroup, command UID and mount namespace, kills on control-socket close, and reaps processes and orphan trees at start (D3, D4, R17). Verify: the worker refuses a launcher whose reported digest differs from the lock.
- [ ] 1.2 Add the DSH worker pair to `infra/docker-compose.yml` with a tmpfs attempt volume and the notes.md#d3 settings (D3). Verify: `docker compose up` starts both with no network or credentials in the DSH container.
- [ ] 1.3 Choose the runner from `template.harness` in `workers/main.py` (D1). Verify: `tpl.local-dsh` gets `DshRunner`; `local-default` is unchanged.

### 2. Runner

- [ ] 2.1 Add the D7 migration and update `Checkpoint`, `CheckpointRepository`, the restore path and the result schemas (`schemas.md`, decision log) (D1, D7, R12). Verify: `alembic upgrade head` on a copy of the dev database; checkpoint round-trip tests with a session blob.
- [ ] 2.2 Port classification, attempt order, gateway ledger with pre-dispatch rows, and barrier to `harness_activity/dsh/` with their spike tests (D2, D6, D9, R11, R13). Verify: ported unit tests pass, including the D9 charge.
- [ ] 2.3 Split the tool bodies out of `FunctionTool` (`harness_activity/tools.py`) so the executor and `openai_agents` share them (D4). Verify: conformance suite unchanged for `openai_agents`.
- [ ] 2.4 Implement `DshRunner`: executor tools and skills, commands through the launcher, notes.md#r14 features off, events from executor and gateway (R14, R16). Verify: a test per disabled feature; the conformance suite (marked `integration`, skipped in CI) passes for `dsh` with a scripted provider.
- [ ] 2.5 Port the recovery, stop, accounting and R18 cases, plus worker SIGKILL, a backgrounded command and a session-file read, as integration tests (R5–R15, R18). Verify: `uv run pytest -m integration` passes them and no attempt process or tree remains.

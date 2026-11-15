---
phase: 2
title: DSH runner and worker image
status: draft
branch: null
base: null
delivers: [R3, R4, R5, R6, R7, R8]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · DSH runner and worker image

## Goal

`DshRunner` runs a turn in a pinned per-attempt container with production
gateway, executor and barrier, and passes the spike's control cases as
production tests.

## Tasks

### 1. Packaging

- [ ] 1.1 Build a worker-side DSH image pinning the release, wheel digests and native binary hashes, with licence notices; scope container start to that image (D3). Verify: image build is reproducible from the lock; a preflight rejects a mismatched digest.

### 2. Runner

- [ ] 2.1 Port the gateway ledger, executor, ordered ownership and session-marker barrier as production modules (R3, R5, D2, D6). Verify: ported unit tests from `spikes/dsh-harness/test_task_policy.py` and `test_usage_ledger.py` pass.
- [ ] 2.2 Implement `DshRunner` with production tools, skills and MCP over the executor and DSH events mapped to the R8 interface (R6, R7, R8, D4). Verify: conformance suite runs on a `dsh` test template with a scripted provider.
- [ ] 2.3 Port the recovery, bounded-stop, accounting and outcome cases (including lost-after-finish, deadline, cancel) as integration tests against real workers (R3, R4, R5, R7). Verify: `uv run pytest -m integration` for those cases passes and leaves no containers.

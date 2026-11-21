# Phase 3A persistence, phase 01: acceptance walkthrough

Date: 2026-11-20. Tested implementation: `56c0170872fd14efa3f7902779284b9a32d382ba` (the
migration round trip and the live guard probe were run at `bbfe1ce`; `56c0170` changes only
Alembic's logging setup and a test). Contract: [plan](../plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md),
phase 01. Phase 01 has no demo checklist: the plan's demo is phase 03's (task 3.2). This record
collects the behaviour the gate verifiers observed instead; it is not a live audience demo.
Verdict and full evidence: [verification-persistence-01.md](../reviews/phase-3a/verification-persistence-01.md)
and its [raw reports](../reviews/phase-3a/raw/).

## Environment

A disposable worktree of the tested commit; `infra/.env` from `infra/.env.example` with only the
README "Several checkouts" and "Model endpoint" changes (Compose project `pmverify3a`, DB
`127.0.0.1:55432`, Temporal `57233`, S3 `58333`, `VLLM_BASE_URL=http://spark-01:8000`). Python
3.11 through `uv`; stack images as pinned in `infra/docker-compose.yml`.

## Steps

| # | Command or action | Expected | Observed | Result |
| --- | --- | --- | --- | --- |
| 1 | `make up`, `make status`, `make migrate` | healthy; migrations to 0007 | `all services healthy`; `Running upgrade 0006 -> 0007` | pass |
| 2 | Scratch database `verify_m0007`: `alembic ... -x database=verify_m0007 upgrade 0006`, seed every kind in notes.md#refs (4 tasks: succeeded, failed, needs_input, running; `audit` artifacts; checkpoints; events; an orphan blob), `upgrade 0007`, `downgrade 0006`, `upgrade 0007` | every reference indexed with its holder and D3 class; `audit` artifacts become `artifact`; `ended_at` set for ended tasks only; the round trip is clean (R2, R19) | 13 index rows covering every notes.md#refs column; `unindexed after migration: []`; `ended_at` set for succeeded, failed and needs_input, null for running; the two `audit` artifacts carry `artifact` in `blob_refs` and `blob_objects`; identical after the downgrade and upgrade (the downgrade maps blob classes back as `test_migration_0007` asserts, not exactly to the old values) | pass |
| 3 | `UPDATE` and `DELETE` on `audit_log` as the app role | refused (R14) | `ERROR:  audit_log is append-only: UPDATE refused` and `... DELETE refused` | pass |
| 4 | Live history-guard probe: a small and a 65 KiB Workflow (`verify-small-…`, `verify-big-…`) | the guard passes the small one and fails the large one (R18) | 1 KiB input: no failure; 65 KiB: `verify-big-68cc2c13 event 1 (workflow_execution_started_event_attributes): 66590 bytes`; both terminated | pass |
| 5 | `make workers-down`, then `uv run --env-file infra/.env pytest -m integration -rs` and `make smoke` at `56c0170` | pass, none skipped | `280 passed`; `250 passed`; the session history guard reported nothing | pass |
| 6 | Failure case: the same suite at `bbfe1ce` | (found by this verification) | `test_refusals_are_logged_with_ids[dsh]` failed after the in-process migrations; fixed in `56c0170`, which also adds a regression test that fails without the fix | recovered |

## Cleanup

The scratch database `verify_m0007` was dropped and the probe Workflows terminated. Afterwards
the pmverify3a stack was left running for the follow-up checks and is torn down with `make reset`
in the worktree, which is then removed (`git worktree remove`). The owner's `praxismesh` stack was
not touched.

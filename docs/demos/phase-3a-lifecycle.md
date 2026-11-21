# Phase 3A persistence and data lifecycle: demo

Date: 2026-11-21. Tested commit: `2a171018182294e8c05fb7ecd785f54df06bdb29`. Contract:
[plan](../plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md), phase 03 task 3.2.
Script: [`infra/demo/phase-3a-lifecycle.sh`](../../infra/demo/phase-3a-lifecycle.sh). This is the
implementer's run, recorded for the gate. Phase 03's gate verification checks it independently.

## Environment

- A clean worktree of the tested commit. `infra/.env` came from `infra/.env.example`, changed only
  as README "Several checkouts" and "Model endpoint" say: Compose project `pmaccept3a`, ports
  15432, 17233, 18080 and 18333, and `VLLM_BASE_URL=http://spark-01:8000`. The demo's tasks run
  on the fake model.
- Python 3.11 through `uv` 0.13.5; Docker 29.9.3; stack images as pinned in
  `infra/docker-compose.yml`.
- `DEMO_BUILD=--no-build`: the workers ran the existing `praxismesh-worker:dev` image. Phase 03
  changes no worker code: reconcile, backup and restore are CLI and scripts. CI's `make drill`
  builds the image.

Command: `ENV_FILE=infra/.env DEMO_BUILD=--no-build bash infra/demo/phase-3a-lifecycle.sh .verify/demo`.
It took 2 min 8 s and exited 0.

## Steps

| # | Step | Expected | Observed | Result |
| --- | --- | --- | --- | --- |
| 0 | `make reset`, `make up`, `make migrate`; fake model and three workers | a fresh stack | healthy; migrations at 0007 | pass |
| 1 | Request A: `agentctl task submit --wait --input orders-a.csv --output order-summary.md` | succeeds with an artifact | `task-989e7ffe-…`, succeeded; `task output` prints `# Order summary` | pass |
| 2a | Set A's `ended_at` 91 days back (`lifecycle_probe.py age`, the only change made outside `agentctl`); `agentctl gc --dry-run` | the plan, by reason | `batches 8, rows 35, references 13, blobs 5`: checkpoints, sessions, messages, tool results, sample orders, event batches, events, references | pass |
| 2b | `agentctl gc` | the same removal, with tombstones | the same counts (operation `gc:fb9f15b1…`); 8 tombstones `gc task:task-989e7ffe-…` with counts and reasons, no content | pass |
| 2c | `agentctl task output A order-summary.md` | expired, with the date (R9) | `error: blob sha256/fa703411… expired: removed on 2026-11-21 17:25 UTC` | pass |
| 3 | Request B: submit, then `request delete REQ --dry-run`, then `request delete REQ` | removed, redacted, recorded (R10, R11, R13) | `batches 9, rows 31, references 13, blobs 5` (`delete:2282abed…`); its tombstones include `request delete` and `request delete complete`; status `succeeded`, `summary "[deleted 2026-11-21]"`, `artifacts []`, `tokens_in 400` kept; `task output` gives `has no output 'order-summary.md' (outputs: none)` | pass |
| 4 | Request C resubmits B's input, then `agentctl gc` | the removed blob is live again and kept (R22) | C succeeded, reading `sha256/b5b255af…`; `gc` gave `batches 0`, and none of its tombstones names that blob. That check could not fail (tombstones never hold keys; impl-review F167); the rerun below checks the input itself | pass |
| 5 | `agentctl backup --to backups/demo-…`, `make reset`, `make up`, `make restore BACKUP=…` | restored, with reconcile's report (R16, R17) | `restore: done`; reconcile `"clean": true` with every list empty; C's `task status` is `succeeded` and `task output` prints `# Order summary` | pass |

## Failure and recovery

These are shown by the drill, run from the same worktree right before the demo:
`DRILL_BUILD=--no-build make drill` took 2 min 1 s and exited 0.

- A restore into a stack with data was refused, and the task's output was unchanged.
- A restore was killed (SIGKILL) during `restore: loading praxismesh`. The next restore refused
  with "an earlier restore did not finish". After `make reset` and `make up`, a restore succeeded.
- After the restore, `task status`, `task output` and the `praxis_comms` role worked. With the
  task's input removed from the bucket, `reconcile` exited 1 and listed exactly
  `tasks/<task>/input_refs` and `upload/<task>` as dangling.

## Acceptance suite (task 3.1)

From the same worktree:

- Every AGENTS.md check exited 0, with 378 unit tests passed.
- `uv run --env-file infra/.env pytest -m integration -rs`, workers stopped: 354 passed, none
  skipped (15 min 6 s).
- Each requirement scenario is mapped to its tests in the phase file's
  [Verification evidence](../plans/2026-11-19-phase-3a-persistence-and-lifecycle/phases/03-backup-and-acceptance.md#verification-evidence).

## Rerun after impl review round 1

Date: 2026-11-21. Tested commit: `64091b28055fbb71763044258aff59956006096e` (impl-review round 1
fixes, F165-F194). This checkout, not a clean worktree, on the separate dev stack
`ENV_FILE=infra/.env.pm3adev` (Compose project `pm3adev`, ports 15432, 17233, 18080 and 18333; no
`VLLM_BASE_URL`), with `DEMO_BUILD=--no-build` and `DRILL_BUILD=--no-build`. The round's fixes
change no worker code.

- **Demo.** `ENV_FILE=infra/.env.pm3adev DEMO_BUILD=--no-build bash infra/demo/phase-3a-lifecycle.sh`
  took 2 min 12 s and exited 0. Step 4 now runs `lifecycle_probe.py live` on C's input:
  `removed_at None, removed_by None, bucket_deleted_at None; in the bucket: True`, after a `gc`
  with `batches 0, blobs 0`. With that row marked removed by hand, the probe exited 1, where the
  old tombstone check still passed. Step 5 printed `... is a complete backup this checkout can
  restore` (the new `check-backup` step), and reconcile `"clean": true`.
- **One earlier run aborted.** It exited 134 (SIGABRT) in step 4 with no message, after `gc`
  and the write of C's input key: the `agentctl task status` there runs with `2>/dev/null`.
  Not reproduced in 60 runs of that command (plain and piped as the demo pipes it) or 25 of the
  probe; the code it runs is outside this round's diff.
- **Drill.** `DRILL_BUILD=--no-build make drill ENV_FILE=infra/.env.pm3adev` took 1 min 54 s and
  exited 0. Its step 5 now fails when restore reports reconcile as failed. That check found a
  defect in the round's own fix (a `printf | grep -q` under pipefail read findings as a
  failure), fixed in `64091b2`. The drill failed before that fix and passed with it.
- **Suites.** Every AGENTS.md check exited 0, with 388 unit tests passed. The integration suite
  (`uv run --env-file infra/.env.pm3adev pytest -m integration -rs`, workers stopped) ran at
  `d98b76a`, which has every Python change of the round: 358 passed and 4 skipped. The skips are
  `test_model_endpoints.py`, because this env file sets no `VLLM_BASE_URL`. The two later commits
  add comments and change the shell scripts the drill runs.

## Cleanup

The demo and the drill deleted their backups. The `pmaccept3a` stack was torn down with `make
reset`, and the worktree was removed. The owner's `praxismesh` stack was not touched.

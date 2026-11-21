<!-- Verbatim verifier report (Phase 3A persistence plan, phase 03 gate verification, acceptance and demo, at 4d269be); reviewers: fresh-subagent (verifier, resumed once after an API authentication error); copied unchanged by the coordinator from .verify/report-acceptance.md per docs/reviews/README.md rule 1. -->

# Phase 3A persistence, phase 03: acceptance verification

Checkout `/tmp/tmp.fhWZ1mSXeS/verify-3a-03`, `git rev-parse HEAD` = `4d269bef0ec2e251515750eed0fe31a1befdc4ec`. The working tree was clean apart from `.verify/`, and I changed no source, test or document. Stack: Compose project `pmverify3a`, ports 55432/57233/58080/58333, `VLLM_BASE_URL=http://spark-01:8000` (`diff infra/.env.example infra/.env` shows only those lines, plus the two DB URLs that follow `DB_PORT`, as README "Several checkouts" directs). I built no images: the drill used `DRILL_BUILD=--no-build` and the demo used `DEMO_BUILD=--no-build`, both reusing `praxismesh-worker:dev` (32736cc1e390). The `praxismesh` and `pm3adev` projects were not touched: 15 of their containers were running before and after.

Harness note (not a repository finding): the calling shell had `VIRTUAL_ENV=/home/geo/develop/praxismesh/.venv` (the owner's working copy) on PATH. Every command ran after `unset VIRTUAL_ENV` and with that path removed (`.verify/env.sh`), so nothing used the owner's venv.

Logs: `.verify/01-setup.log`, `02-up.log`, `03-checks.log`, `03-checks-summary.log`, `04-integration.log`, `05-collect-*.txt`, `06-drill.log`, `07-demo.log` (and `demo/`), `08-r23-task.log`, `09-r23-workflow.log`, `10-r23-workflow.log`, `11-killed-restore.log`, `11-killed.out`, `12-reconcile-live.log`.

## 1. Prerequisites (documented steps only)

| # | Step (source) | Observed |
|---|---|---|
| 1 | `uv python install 3.11` (README Set up) | exit 0 |
| 2 | `uv sync --locked` (README, AGENTS.md) | exit 0; "Checked 86 packages" on re-run |
| 3 | `infra/.env`: already copied from `.env.example`, with the project, ports and model edits (README Local stack, Several checkouts, Model endpoint) | as stated in the brief; verified by diff |
| 4 | `make up` | "stack is up; run 'make status' for addresses and health" |
| 5 | `make status` | "addresses: Temporal 127.0.0.1:57233, UI http://127.0.0.1:58080, S3 http://127.0.0.1:58333, DB 127.0.0.1:55432", "model endpoint: http://spark-01:8000 answers /v1/models", "all services healthy" |
| 6 | `make migrate` | upgrades 0001 -> 0007, ending at "Running upgrade 0006 -> 0007, Phase 3A persistence plan, phase 01 ..." |
| 7 | Workers stopped for the integration suite (README: "with the worker containers stopped") | none had been started: `compose ps --status running` showed only db, s3, temporal, temporal-ui |

No undocumented step was needed. `gitleaks` and `lychee` are not installed on this host. README marks gitleaks as optional ("if gitleaks is installed"), and the link check runs only in CI (lychee-action).

## 2. Acceptance suites

### AGENTS.md checks (`.verify/03-checks-summary.log`)

| Command | Exit | Summary |
|---|---|---|
| `uv sync --locked` | 0 | "Checked 86 packages" |
| `uv run ruff check .` | 0 | "All checks passed!" |
| `uv run ruff format --check .` | 0 | "558 files already formatted" |
| `uv run mypy` | 0 | "Success: no issues found in 190 source files" |
| `uv run pytest` (unit) | 0 | "397 passed, 367 deselected in 59.92s" |
| `uv run .agents/sync_agents.py --check` | 0 | "ok: 3 generated agent file(s) up to date" |
| `uv run .github/scripts/check_plans.py` | 0 | "Validated 8 implementation plan(s); 0 error(s)" |
| `uv run .github/scripts/check_dsh_licences.py` | 0 | "licence notices present for 7 pinned DSH distributions" |
| gitleaks | not run | not installed; README makes it optional |
| offline link check (lychee, task 3.3 Verify) | **blocked** | CI-only action; lychee is not installed locally |

### Full integration suite, workers stopped

`uv run --env-file infra/.env pytest -m integration -rs` exited 0 with "367 passed, 397 deselected in 914.86s (0:15:14)". Nothing was skipped: with `VLLM_BASE_URL` set and reachable, `test_model_endpoints.py` ran as well.

Evidence-table coverage: I parsed every test the phase's verification-evidence table names (57 references) against `pytest --collect-only` for the unit and integration suites. Every reference exists. The one that is not a test is R18's `tests/support/history_guard.py`, a session guard; `tests/integration/conftest.py:11` imports it. All collected tests passed, so every scenario mapped to a test passed.

### `make drill`

`DRILL_BUILD=--no-build make drill` exited 0 in 112 s (`.verify/06-drill.log`). It ran on the stack just after the integration suite, as CI does. Output by step:

- Step 1: "task task-f2777f24-ce0f-4751-8768-41464f7258a7 succeeded".
- Step 2: `{"backup": "backups/drill-20261121T212513Z"}`, then "the workers run again" (real worker containers).
- Step 3: "refused; the task's output is unchanged". The drill asserts that the output contains "refusing to restore".
- Step 4: "killed during: restore: loading praxismesh", then "the next restore refuses; reset and up again". The drill asserts that the output contains "an earlier restore did not finish".
- Step 5: "restore: done; reconcile's report follows", then "restore: reconcile listed the findings above (information only; restore succeeded)", then "comms role praxis_comms reads the restored task".
- Step 6: "removed sha256/06e2da63... from the bucket", then "reconcile lists the removed input as dangling: tasks/task-f2777f24-.../input_refs, upload/task-f2777f24-...".
- Final line: "drill: passed".

The CI wiring is visible in `.github/workflows/ci.yml`: `- run: make drill` follows `make recovery-check` in the `stack` job, with `timeout-minutes: 45`. A CI run of it is **blocked** here (no CI run observed). Locally the drill took 112 s.

### Task Verify lines

| Task | Verify | Evidence | Result |
|---|---|---|---|
| 1.1 | integration tests that seed each case | `test_reconcile.py` 7 tests passed (dangling, orphan with age, unindexed then reindexed, never-ended closed and missing, read-only). Live CLI (`.verify/12-reconcile-live.log`): with a task set back to `running` and an orphan put in the bucket, `./agentctl reconcile` printed `"never_ended": [{"task_id": "task-90d39287-...", "workflow": "closed"}]` and an orphan with `"age_hours": 0.0, "content_key": true`, then "reconcile exit=1". The tasks md5 was the same before and after (`6828e911...`). After I reverted both, it printed `"clean": true` and "reconcile exit=0" | pass |
| 2.1 | three dumps, every object, manifest; workers run again; gc during it fails on the lock | `test_backup.py::test_a_backup_has_three_dumps_every_object_and_a_manifest` (asserts `"another gc"` in the gc refusal, PGDMP dumps, objects, manifest) and 10 more backup tests passed; drill step 2 "the workers run again". `make backup` (`.verify/08-r23-task.log`) produced three `.dump` files, `blobs/`, `manifest.json` (`'migration': '0007'`, `'rows': {'tasks': 3, ...}`, `images` pinned) and a directory of mode `drwx------` | pass |
| 2.2 | refusals change nothing; restore after reset works and comms connects; killed restore -> reset -> restore works; fresh `make up` initialises via init.sh | see R23 below; `.verify/11-killed-restore.log`; db logs on a fresh volume: "PraxisMesh database init completed" (init.sh calls `praxismesh-databases`) | pass |
| 2.3 | `make drill` passes as its own CI step after the smoke tests within 45 min | drill passes locally (112 s); CI step present in `ci.yml` | pass locally; CI run blocked |
| 3.1 | unit and integration pass from a clean worktree whose env comes from `.env.example` | 397 unit and 367 integration tests passed | pass |
| 3.2 | demo runs end to end on the fake model | section 3 | pass |
| 3.3 | `check_plans.py` and the link check pass | check_plans exit 0; link check blocked | partly blocked |

### R16, R17, R23 Given/When/Then

- **R16** (backed up, reset, restored: `task status`, `task output`, comms): **pass**.
  - Drill step 5.
  - Demo step 5: "task C after the restore: succeeded", then "# Order summary".
  - My own run in `.verify/11-killed-restore.log`, after `make reset`, `make up` and `make restore`: "status succeeded", "# Order summary", "comms: praxis_comms 3".
- **R17.1** (restored backup missing one blob: listed as dangling): **pass**.
  - Drill step 6, quoted above.
  - `test_reconcile.py::test_a_missing_blob_is_listed_as_dangling` passed.
- **R17.2** (orphan listed with its age): **pass**.
  - `test_an_orphan_is_listed_with_its_age` passed.
  - The live CLI output quoted above.
- **R17.3** (task left `running` with a closed Workflow: listed as never ended): **pass**.
  - `test_a_task_whose_workflow_closed_is_listed_as_never_ended` passed.
  - Live against real Temporal: `"workflow": "closed"`, as quoted.
- **R23** (one task, or one Workflow and no task row: refused, unchanged): **pass**.
  - Task row (`.verify/08-r23-task.log`): `make restore` printed "error: refusing to restore into a stack that holds data: the application database has rows: tasks 3, ...; Temporal lists 3 Workflow(s) in the app's namespace; bucket praxismesh holds objects. Run 'make reset' and 'make up' first (this deletes the stack's data)" and make exited 2. Before and after: `3|0893d766f4572bb10effe8d2c0a77d5d`, task C `succeeded`, `objects 5`. Unchanged.
  - Workflow, no task row (`.verify/10-r23-workflow.log`): `make reset` and `make up`, then a started Workflow `verify-r23-wf` (status 1, RUNNING). `make restore` printed "error: refusing to restore into a stack that holds data: Temporal lists 1 Workflow(s) in the app's namespace. ..." and exited 2. Afterwards: "workflow 1" (still running), bucket `NoSuchBucket`, "public tables: 0", restore mark `''`. Unchanged.
  - The `test_restore_refusals.py` tests (8) passed.

## 3. Demo

Command: `ENV_FILE=infra/.env DEMO_BUILD=--no-build bash infra/demo/phase-3a-lifecycle.sh .verify/demo`. It exited 0 in 118 s (`.verify/07-demo.log`), and the last line was "== demo passed; output in .verify/demo".

| # | Step | Expected (doc) | Observed | Result |
|---|---|---|---|---|
| 0 | `make reset`, `make up`, `make migrate`; fake model and three workers | "a fresh stack" | `== 0. ...` with no error (the script's `set -e` and `mk` would abort on failure) | pass |
| 1 | Request A with an input and an artifact | "succeeds with an artifact" | "task A: task-f83a7111-6ed6-4e88-b48a-d8331be8399f", then "# Order summary" | pass |
| 2a | A's end set 91 days back; `gc --dry-run` | "the plan, by reason" | "ended_at set to 2026-08-22 21:28 UTC (91 days ago)"; `"dry_run": true, "batches": 8, "rows": 34, "references": 13, "blobs": 5`, with by_reason for checkpoints, agent_messages, agent_sessions, idempotency_keys, sample_orders, event_batches, events and references | pass (see observation O1) |
| 2b | `gc` | "the same removal, with tombstones" | `"dry_run": false`, the same counts, `"operation": "gc:0fb5b07b..."`; 8 tombstone lines `cli:geo gc task:task-f83a7111-...` with counts and reasons and no content | pass |
| 2c | `task output A` | "expired, with the date (R9)" | "error: blob sha256/fa7034119c33... expired: removed on 2026-11-21 21:28 UTC" | pass |
| 3 | Request B; `request delete --dry-run`, then `request delete` | "removed, redacted, recorded (R10, R11, R13)" | "batches": 9, "rows": 31, "references": 13, "blobs": 5 (`delete:cb2b6185...`). The tombstones include "request delete" and "request delete complete". `{'status': 'succeeded', ..., 'summary': '[deleted 2026-11-21]', 'artifacts': [], 'tokens_in': 400}`, then "error: task task-6ed78ef4-... has no output 'order-summary.md' (outputs: none)" | pass |
| 4 | Request C resubmits B's input, then `gc` | "the removed blob is live again and kept (R22)" | `"batches": 0, ... "blobs": 0`; "sha256/8309b307...: removed_at None, removed_by None, bucket_deleted_at None; in the bucket: True" | pass |
| 5 | `backup`, `make reset`, `make up`, `make restore` | "restored, with reconcile's report (R16, R17)" | `{"backup": "backups/demo-20261121T212819Z"}`, "... is a complete backup this checkout can restore", "the stack holds no data", "loaded 5 object(s)", "restore: done", `"clean": true` with every list empty, "task C after the restore: succeeded", "# Order summary" | pass |

Failure and recovery items:

| Item | Expected (doc) | Observed | Result |
|---|---|---|---|
| Restore into a stack with data | refused; task output unchanged | Drill step 3: "refused; the task's output is unchanged". My run quoted the diagnostic itself: "error: refusing to restore into a stack that holds data: ..." (exit 2, state unchanged) | pass |
| Restore killed (SIGKILL) during loading | the next restore refuses with "an earlier restore did not finish"; after reset and up, a restore succeeds | Drill step 4: "killed during: restore: loading praxismesh". My run (`.verify/11-killed-restore.log`): killed rc=137 after "restore: loading praxismesh"; the next `make restore` printed "restore: an earlier restore did not finish. Run 'make reset' and 'make up' (this deletes the stack's data), then restore again" and exited 2; `make reset`, `make up`, `make restore` then printed "restore: done" and `"clean": true`, exit 0 | pass |
| Dangling report | reconcile exits 1 and lists exactly `tasks/<task>/input_refs` and `upload/<task>` | Drill step 6, quoted above. The drill asserts that reconcile exits non-zero and that the set of new holders equals those two | pass |

## 4. Final state

The `pmverify3a` stack is up with the restored demo data:
- db, s3, temporal and temporal-ui are healthy.
- No worker containers exist.
- Reconcile prints `"clean": true` and exits 0.

I deleted the backup I made myself (`backups/20261121T212958Z`); the drill and the demo deleted theirs. `backups/` is empty.

## Observations (no requirement failed)

- **O1 (demo record).** The recorded run in `docs/demos/phase-3a-lifecycle.md` (step 2a) says "rows 35" and lists "tool results" among the reasons. This run gave rows 34, and its reasons included `idempotency_keys` and no tool results. The documented expectation ("the plan, by reason") holds; only the recorded figures differ.
- **O2 (test residue).** The integration suite leaves rows in the stack's app database that later show up in reconcile. The drill ran right after the suite, and its restore report listed 488 dangling references (for example `sha256/000...0` held by `checkpoints/task-test-...`) and 116 never-ended tasks (`task-act-...`, `"workflow": "missing"`). Restore treated them as information, as the runbook says. Reconcile on a developer stack after a test run is therefore noisy.
- **O3 (transient, outside phase 03).** Once, immediately after `make up`, a Temporal client `start_workflow` failed with "Namespace default is not found". I retried after a fresh `make reset` and `make up`, and that time it succeeded on the first attempt. Restore's `check-empty` counts Workflows through the same API, so in that window it would fail closed rather than proceed. I did not see that happen in any restore here.

## Blocked

- Offline link check (task 3.3 Verify): lychee is not available locally; it runs in CI only.
- gitleaks: not installed (optional per README).
- `make drill` as a CI `stack` step within 45 minutes (task 2.3 Verify): no CI run observed. The workflow file has the step and the budget, and the drill passes locally in 112 s.

Verdict: PASS. Every suite, the drill and every demo step passed with quoted output, and every Verify line and every Given/When/Then of R16, R17 and R23 is shown. Three checks are blocked (local link check, gitleaks, the CI drill run), and there are three observations, none of them a requirement failure.

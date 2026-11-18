<!-- Verbatim verifier report (verification-phase-03-acceptance, code_sha d55f3add6dcb9e2db2d4bf3047f3bb78be0cfdf7); fresh verifier subagent; saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Phase 03 acceptance verification: DSH production harness (acceptance and default switch)

- Checkout: /tmp/claude-1000/-home-geo-develop-praxismesh/599639d3-a59f-4a32-945c-fd5372c3c537/scratchpad/verify-03
- Commit: `d55f3add6dcb9e2db2d4bf3047f3bb78be0cfdf7` (`git rev-parse HEAD` at the end of the run. `git status --short` shows only `?? .verify/`)
- Date: 2026-11-17 local (UTC rolled over to 2026-11-18 during the run, so result files are dated 2026-11-18)
- Disposable Compose project: **`verify03acc`**. Ports: DB 25432, Temporal 27233, Temporal UI 28080, S3 28333. All are bound to 127.0.0.1.
- Logs: `.verify/` in the checkout (file names are given below)

**Verdict: PASS.** Every task's Verify item passed, with the output quoted below. Two items could not be observed here: GitHub CI for this commit (no runs exist), and gitleaks/actionlint (not installed). Their local equivalents passed. There is one documentation finding (F1, low).

## 1. Prerequisites (documented steps only)

| # | Step (source) | Result |
|---|---|---|
| 1 | `cp infra/.env.example infra/.env` (README "Local stack") | done |
| 2 | Edited `infra/.env`: `COMPOSE_PROJECT_NAME=verify03acc`, `DB_PORT=25432`, `TEMPORAL_PORT=27233`, `TEMPORAL_UI_PORT=28080`, `S3_PORT=28333` (README "Several checkouts", .env.example) | done |
| 3 | `VLLM_BASE_URL` = the owner's value (coordinator instruction). `VLLM_MODEL`/`VLLM_API_KEY` left as in the example | done |
| 4 | `PRAXIS_SAMPLE_DB_URL` port changed 5432 -> 25432 | **not in README's "Several checkouts" text**: see F1 |
| 5 | `uv python install 3.11; uv sync --locked` (README "Set up") | exit 0 (`01-uv-sync.log`) |
| 6 | `make up` | exit 0: "stack is up; run 'make status' for addresses and health" (`02-make-up.log`) |
| 7 | `make status` | exit 0: "addresses: Temporal 127.0.0.1:27233, UI http://127.0.0.1:28080, S3 http://127.0.0.1:28333, DB 127.0.0.1:25432" / "model endpoint: http://<host>:8000 answers /v1/models" / "all services healthy" |
| 8 | `make migrate` | exit 0: "Running upgrade 0003 -> 0004, DSH migration plan D7: explicit unknown usage, a usage ledger, session blobs." |
| 9 | `make workers-up` (README "Running an agent task", runbook Deploy step 2). Run after the benchmarks so that the Compose DSH workers do not poll `tpl.local-dsh` alongside the benchmark's in-process worker | exit 0. orchestrator, worker-a/b, dsh-a/b and worker-dsh-a/b are up and healthy. Worker env `VLLM_BASE_URL=http://<host>:8000` (the real model, not fake-model) |

Environment notes, not findings: the inherited shell had `VIRTUAL_ENV` pointing at the owner's venv, which caused uv to warn "does not match the project environment path `.venv` and will be ignored". I ran with `unset VIRTUAL_ENV`. gitleaks and actionlint are not installed on this host.

## 2. Acceptance suites

| Command | Exit | Summary (quoted) |
|---|---|---|
| `uv run ruff check .` | 0 | "All checks passed!" |
| `uv run ruff format --check .` | 0 | "352 files already formatted" |
| `uv run mypy` | 0 | "Success: no issues found in 123 source files" |
| `uv run pytest` | 0 | "286 passed, 178 deselected in 33.48s" |
| `uv run .agents/sync_agents.py --check` | 0 | "ok: 3 generated agent file(s) up to date" |
| `uv run .github/scripts/check_plans.py` | 0 | "Validated 4 implementation plan(s); 0 error(s)" |
| `uv run .github/scripts/check_dsh_licences.py` (R20, CI `lint` step) | 0 | "licence notices present for 7 pinned DSH distributions" |
| `gitleaks git --config .gitleaks.toml --redact .` | - | **blocked**: gitleaks not installed (README: "if gitleaks is installed") |
| actionlint | - | **blocked**: not installed |
| `make smoke` (CI `stack` job) | 0 | "154 passed in 244.70s" (the model endpoint was set, so the model tests ran too) |
| `make restart-check` | 0 | "restart-check: PASS (repeat starts changed nothing; retention change applied and restored; revision 0004; Workflow and object survived)" |
| `make unhealthy-check` | 0 | "unhealthy-check: PASS (make status and the smoke test named the stopped db)" |
| `make workers-check` (submits on `openai`, fake model) | 0 | `"status": "succeeded"`, `"template": "local-default"` |
| `make recovery-check` | 0 | "5 passed in 58.24s" |
| `make benchmark ARGS="--profile dsh"` (R19) | 0 | "passed 10 of 10. Within the regression limit (baseline 10)." (`20-bench-dsh.log`) |
| `make benchmark ARGS="--profile openai"` (R4) | 0 | "passed 10 of 10. Within the regression limit (baseline 10)." (`21-bench-openai.log`) |
| `make benchmark ARGS="--profile default"` (task 1.2 names `default`, which now resolves to local-dsh) | 0 | "passed 10 of 10. Within the regression limit (baseline 10)." (`22-bench-default.log`) |

GitHub CI (`ci-ok`) for this commit: **not observable**. `gh run list --commit d55f3add...` and `--branch feat/62-dsh-acceptance` returned no runs. Every job of `.github/workflows/ci.yml` that can run locally passed (above). gitleaks, actionlint, lychee and dependency review were not run.

## 3. Demo: task Verify items in order

### 1.1 `--profile` in the benchmark
- Command: `make benchmark ARGS="--profile <p> --only t01-order-total --out $PWD/.verify/smoke-<p>"` for p in default, dsh, openai.
- Expected: "a one-task smoke run per profile, written outside `docs/benchmarks/` and not judged against the baseline, completes; its file name and `harness` label follow the profile."
- Observed (`10-smoke-*.log`, `smoke-*/`):
  - default: exit 0, "passed 1 of 1. Not judged against the baseline (written outside docs/benchmarks)." File `2026-11-17-default.md`, header "# Agent benchmark: default (local-dsh@1)", `| harness | \`deepseek-harness-sdk 0.2.2rc2\` |`. The log contains "building and starting a DSH container".
  - dsh: exit 0, same verdict line. File `2026-11-18-dsh.md`, "(local-dsh@1)", harness `deepseek-harness-sdk 0.2.2rc2`, paired DSH container started.
  - openai: exit 0, same verdict line. File `2026-11-18-openai.md`, "(local-default@1)", harness `openai-agents 0.24.0`, no DSH container started.
  - No container labelled `praxismesh.dsh-test` remained afterwards (`docker ps -a --filter label=praxismesh.dsh-test` printed nothing).
- **PASS**

### 1.2 Same-day benchmarks (R19, R4)
- Commands: `make benchmark ARGS="--profile dsh"`, then `--profile openai`, then `--profile default`, one at a time on the same UTC day (2026-11-18).
- Expected: "each fails at most one task; both results are recorded under `docs/benchmarks/`." R4: `local-default` at most one failure. R19: `dsh` at most one failure.
- Observed:
  - dsh: 10/10, local-dsh@1, `deepseek-harness-sdk 0.2.2rc2`, tokens_in total 164267, 279.2 s, all usage_known true.
  - openai: 10/10, local-default@1, `openai-agents 0.24.0`, tokens_in 126436, 220.6 s.
  - default: 10/10, local-dsh@1, tokens_in 174136, 306.2 s.
  - Each run printed "Within the regression limit (baseline 10)."
  - Ratios (dsh/openai): about 1.30x input tokens and 1.27x wall time. This is consistent with the runbook's "about 1.3x".
  - Recorded in the commit: `docs/benchmarks/2026-11-17-dsh.json` (local-dsh@1, 10 passed) and `2026-11-17-default.json` (local-default@1, openai-agents 0.24.0, 10 passed, run when `default` was still openai_agents).
  - The runs wrote new `docs/benchmarks/2026-11-18-*` files. I moved them to `.verify/bench-results/` so the checkout stays at the frozen commit; the committed files were never modified.
- **PASS**

### 1.3 Licence notices check (R20)
- Command: `uv run .github/scripts/check_dsh_licences.py`. Then a temporary change: I moved `docs/licences/dsh/pydantic-2.14.3/LICENSE` away and reran; later I moved the whole `docs/licences/dsh/annotated-types-0.8.0` directory away and reran. Both were restored, and `git status` was clean afterwards apart from `.verify/`.
- Expected: "the check passes, and fails when a notice is removed."
- Observed (`05-licence-negative.log`):
  - Intact: "licence notices present for 7 pinned DSH distributions", exit 0. That is one per pin in `infra/dsh/requirements.txt` (7 `==` pins).
  - LICENSE removed: "error: pydantic-2.14.3: docs/licences/dsh/pydantic-2.14.3 has no notice file" / "refresh with: uv run .github/scripts/check_dsh_licences.py export", exit 1.
  - Directory removed: "error: annotated-types-0.8.0: no licence notices in docs/licences/dsh/annotated-types-0.8.0", exit 1.
  - Restored: exit 0.
  - CI wiring: `.github/workflows/ci.yml:53` `- run: uv run .github/scripts/check_dsh_licences.py` in the `lint` job.
- **PASS**

### 2.1 `openai` profile, second DSH pair, `default` on DSH
- Expected: "CI passes; a `default` task runs on DSH and an `openai` task on `openai_agents`."
- CI: local equivalents passed (section 2). GitHub CI is not observable.
- Commands (runbook Deploy step 3), after `make workers-up`:
  `make task PROFILE=default PROMPT="Order 3 units of SKU-1 and write order-summary.md." OUTPUT=order-summary.md`, then the same with `PROFILE=openai`.
- Observed (`45-task-*.log`):
  - default: exit 0, `"status": "succeeded"`, `"template": "local-dsh"`, `"usage_known": true`. `make task-status` shows the attempt `'73708d28104f@1/local-dsh'`, and 73708d28104f is `verify03acc-worker-dsh-a-1`. `make task-output ... FILE=order-summary.md` printed "| SKU-1 | 3 | 12.50 | 37.50 |".
  - openai: exit 0, `"status": "succeeded"`, `"template": "local-default"`, attempt `'af5637296f57@1/local-default'`, and af5637296f57 is `verify03acc-worker-b-1`.
  - Second pair present: `dsh-a`, `dsh-b`, `worker-dsh-a`, `worker-dsh-b` all "Up (healthy)" (DSH containers "Up").
  - The repointed tests use `openai`: `tests/test_registry.py:26`, `tests/test_runner_conformance.py:128`, `tests/integration/test_recovery.py:62`, `test_task_e2e.py:51`, `test_tracing.py:76`, `test_submit.py:22`. The `workers-check` target uses `PROFILE=openai`.
- **PASS** (GitHub CI itself is not observed)

### 2.2 Runbook revert walkthrough (failure/recovery item)
Script: `.verify/scripts/revert.sh`. Log: `.verify/50-revert-walkthrough.log`.

A first attempt (`50-revert-walkthrough-attempt1-scriptbug.log`) failed in my own script's JSON parsing before any registry edit. Its DSH task (task-a05eecf4...) simply completed on local-dsh. I fixed the script and reran.

| Runbook step | Action | Observed |
|---|---|---|
| (pre) | `uv run --env-file infra/.env python -m orchestrator.cli task submit --profile default ...` (multi-SKU order + two more files) | `task-458373dd-cf43-4032-bd36-116521716c60`; submit log `"template": "local-dsh"` |
| 1 | wait for first attempt (`task status`) | `{'workflow': 'RUNNING', 'checkpoints': 0, 'template': 'local-dsh', 'attempts': [(1, 1, '73708d28104f@1/local-dsh', 'started')]}` |
| 2 | edit `registry/profiles/default.yaml` to the revert row | diff `-harness: dsh` `+harness: openai_agents` `-allowed_templates: [local-dsh]` `+allowed_templates: [local-default]` |
| 3 | `make registry-lock` | exit 0. Only `M registry/profiles/default.yaml` changed (the lock is unchanged, as the runbook says) |
| 4 | `make workers-up` | "old task before workers-up: workflow=RUNNING attempts=1 checkpoints=0". workers-up exit 0. orchestrator, worker-a/b and worker-dsh-a/b were "Recreated"; dsh-a/b stayed "Running". Then "old task after workers-up: workflow=RUNNING attempts=1 checkpoints=1" |
| 6 | `make task PROFILE=default PROMPT=... OUTPUT=order-summary.md` | exit 0, `"status": "succeeded"`, `"template": "local-default"`, attempt `d74a468224f6@1/local-default` (= `verify03acc-worker-a-1`) |
| drain | wait for the pre-revert task | `workflow: COMPLETED`, task `profile: default`, `template: local-dsh`, `status: succeeded` |

Pre-revert task attempts (`43-old-task-status.json`):
- turn 1 attempt 1, `73708d28104f@1/local-dsh` (old worker-dsh-a), outcome **`lost`**
- turn 1 attempt 2, `de54591be9be@1/local-dsh` (new worker-dsh-b), outcome `done`
- result: `{'status': 'succeeded', 'template': 'local-dsh', 'attempts': 2, 'usage_known': False}`, artifact `order-summary.md`
- orders recorded once each: `[{'sku': 'SKU-4', 'qty': 2}, {'sku': 'SKU-5', 'qty': 1}, {'sku': 'SKU-2', 'qty': 3}, {'sku': 'SKU-1', 'qty': 1}]`

Expected (runbook): "Tasks already running keep their template and finish on the harness they started on." "Step 4 restarts every worker, the DSH workers too. An attempt in flight is lost and retried on the restarted worker from its last checkpoint, with no repeated side effect; the lost attempt's usage is charged conservatively, so that task's result reports `usage_known: false`." Observed: exactly that, with the documented diagnostic (attempt `lost`, `usage_known: false`), not a silent success. **PASS**

Restore: `git checkout registry/profiles/default.yaml`, `make registry-lock` (no change), `make workers-up` (exit 0). Then `make task PROFILE=default ...` gave `"status": "succeeded"`, `"template": "local-dsh"`, `"usage_known": true` (`61-post-restore-default.log`). The checkout is back at the frozen commit with no tracked changes.

## 4. Findings

- **F1 (low, documentation).** README "Several checkouts" tells you to give each checkout its own `COMPOSE_PROJECT_NAME` and ports. It does not say that `PRAXIS_SAMPLE_DB_URL` in `infra/.env` embeds the DB host port (`127.0.0.1:5432`). `.env.example` says this URL "is the host address for local runs", so host-process workers (benchmark, smoke, recovery-check) use it for the sample MCP server. A second checkout that changes only `DB_PORT` would point that server at the first stack's database, which has the same default password. I changed it preemptively, so this is inferred from the documentation and not reproduced.
- Observation (not a defect): `make workers-check` starts `fake-model`, and `make workers-up` does not remove it. It stays running, unused, until `make workers-down`.

## 5. Left running

Project `verify03acc` is still up: db (127.0.0.1:25432), temporal (127.0.0.1:27233), temporal-ui (127.0.0.1:28080), s3 (127.0.0.1:28333), orchestrator, worker-a, worker-b, dsh-a, dsh-b, worker-dsh-a, worker-dsh-b (real model), plus the idle fake-model. The workers were rebuilt from the frozen commit's registry (`default` -> local-dsh). The owner's `praxismesh` project was not touched.

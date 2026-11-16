<!-- Verbatim subagent report (verification phase 02, acceptance and demo, fresh verifier at 62ffc7618a78fac516a9b745bf7140d3e92a9d7d); saved by the coordinator per docs/reviews/README.md rule 1; scratch paths replaced by <verify-checkout>. -->

## Verification report: DSH migration phase 02 (DSH runner and worker pair) at commit 62ffc7618a78fac516a9b745bf7140d3e92a9d7d

Checkout: <verify-checkout>. Logs are in <verify-checkout>/.verify/, numbered 01 to 31. The only file I added outside `.verify/` is the git-ignored `infra/.env`. I edited no tracked files.

**Verdict: fail.** The documented integration suite (`make smoke`, and `uv run --env-file infra/.env pytest -m integration`) has 4 failures on a stack set up from `infra/.env.example`. Every other check and every demo item passed with quoted output.

### 1. Prerequisites (steps run)
1. `cp infra/.env.example infra/.env`, then edited it: `COMPOSE_PROJECT_NAME=pmverify02`, `DB_PORT=25432`, `TEMPORAL_PORT=27233`, `TEMPORAL_UI_PORT=28080`, `S3_PORT=28333`. I also changed `PRAXIS_SAMPLE_DB_URL` to port 25432. The README says to change the name and ports for a second checkout, but not this URL; it carries the port too (cosmetic).
2. `uv python install 3.11 && uv sync --locked`: exit 0.
3. `make up`: exit 0, "stack is up". `make status`: exit 0, "all services healthy", "addresses: Temporal 127.0.0.1:27233, UI http://127.0.0.1:28080, S3 http://127.0.0.1:28333, DB 127.0.0.1:25432".
4. `make migrate`: exit 0, "Running upgrade 0003 -> 0004, DSH migration plan D7".
- The shell had `VIRTUAL_ENV` set to the user's working copy. uv warned and ignored it; I unset it.
- `gitleaks` is not installed. The README marks it "if installed", so I did not run it.

### 2. Acceptance suites
| Command | Exit | Summary |
|---|---|---|
| `uv run ruff check .` / `ruff format --check .` | 0 / 0 | "All checks passed!" / "332 files already formatted" |
| `uv run mypy` | 0 | "Success: no issues found in 118 source files" |
| `uv run .agents/sync_agents.py --check` | 0 | "ok: 3 generated agent file(s) up to date" |
| `uv run .github/scripts/check_plans.py` | 0 | "Validated 4 implementation plan(s); 0 error(s)" |
| `uv run pytest` | 0 | "267 passed, 178 deselected" |
| The 5 DSH integration files listed in overview.md, run with the overview's command | 1 | "4 failed, 51 passed" |
| `uv run --env-file infra/.env pytest -m integration tests/test_runner_conformance.py` (dsh) | 0 | "19 passed, 19 deselected" |
| `uv run --env-file infra/.env pytest -m integration` (all; task 2.5) | 1 | "4 failed, 170 passed, 4 skipped" |
| `make smoke` | 2 | "4 failed, 146 passed, 4 skipped"; "make: *** [Makefile:105: smoke] Error 1" |

The 4 failures are the same in every run:
- `test_dsh_activity.py::test_step_limit_stops_a_runtime_that_does_not_exit`
- `test_dsh_usage.py::test_non_retryable_failure_charges_its_own_unknown_request`
- `test_dsh_usage.py::test_cancelled_attempt_charges_its_own_unknown_request`
- `test_dsh_usage.py::test_retryable_failure_is_charged_once_across_attempts`

Every other R5–R18 test passed, including:
- all 12 `test_outcome_case[...]` cases, plus lost-after-finish and cancel (the 14 R18 cases)
- `test_worker_sigkill_reaps_attempt_and_replacement_recovers` (R10)
- `test_command_isolation_blocks_session_other_attempts_and_reaps_background` (R15)
- `test_forced_stop_is_recorded_as_a_non_retryable_failure` (R9)
- `test_stale_attempt_that_finished_is_fenced[checkpoint|publish|finish]` (R6, R7)
- `test_only_template_capabilities_reach_dsh` (R14)
- `test_tampered_runtime_is_reported_and_refused` (R17)

No test containers or launcher processes were left behind.

### 3. Demo (the phase's Verify steps)
- **1.1 pin refusal: pass.** `tests/test_worker_runner.py -v` shows `test_local_dsh_refuses_a_launcher_that_differs_from_the_lock[report0/1] PASSED`. The live failure case is below.
- **1.1 isolation probe: pass.** I ran the probe command from its header against the DSH image (`docker build -q -f infra/dsh/Dockerfile infra/dsh`). All 13 checks print `"ok":true`, including `{"check":"command_userns_blocked","ok":true}` and `{"check":"cgroup_kill","ok":true,"detail":"alive=0 of 3"}`.
- **1.2 pair starts with no network or credentials: pass.**
  - Command: `docker compose -p pmverify02 --env-file infra/.env -f infra/docker-compose.yml --profile dsh up -d dsh-a worker-dsh-a`.
  - With `VLLM_BASE_URL` empty, the worker refuses: "CapabilityError: VLLM_BASE_URL is not set: template local-dsh@1 needs a model endpoint". This is documented README behaviour.
  - With `VLLM_BASE_URL=http://fake-model:8765` (the `workers-check` pattern) plus the `fake-model` profile, both containers are up and the worker is healthy.
  - `dsh-a` inspection: `NetworkMode=none ReadOnly=true CapAdd=[CAP_SYS_ADMIN] Cgroupns=private`. Its interfaces are `['lo']`, a connect attempt gives "Network is unreachable", and its environment holds only `DSH_SHARED_GID`, `DSH_WORKER_UID` and the base image's variables.
- **1.3 runner choice: pass.** Temporal pollers show `tpl.local-dsh ['bb87b880f041@1/local-dsh']`. The unit tests `test_local_dsh_gets_the_dsh_runner_after_the_pin_check` and `test_local_default_keeps_the_openai_agents_runner` passed.
- **End-to-end DSH task on the pair: pass.**
  - Command: `make task PROFILE=dsh PROMPT="Order 3 units of SKU-1 and write order-summary.md." OUTPUT=order-summary.md`.
  - Result: `"status": "succeeded"`, `"template": "local-dsh"`, `"attempts": 1`, `"tokens_in": 400`, `"usage_known": true`. Checkpoint `session_position: 0`; orders `[{"sku": "SKU-1", "qty": 3}]`.
  - Afterwards `/attempts` holds only `.control.sock`, there are no attempt cgroups, and the only process is `python /opt/dsh/launcher.py`.
- **2.1 migration: pass.** On my populated database (118 tasks, 205 attempts and 205 checkpoints after the tests), `alembic downgrade 0003` then `make migrate` ran "0003 -> 0004" with exit 0. Row counts are unchanged and `usage_ledger` exists. `test_checkpoint_round_trips_a_session_blob` passed. The docs do not say how to make "a copy of the dev database", so I used my disposable database.
- **2.3 / 2.4 conformance: pass**, 19/19 for `dsh`. The `openai_agents` runs are in the unit suite (passed).
- **2.5: fail.** `uv run pytest -m integration` has the 4 failures above.
- **Failure and recovery (R17, live): pass.**
  - Unreachable launcher: I stopped `dsh-a` and restarted the worker. It refuses: "CapabilityError: template local-dsh@1: the DSH launcher is not answering: cannot reach the DSH launcher at /attempts/.control.sock".
  - Pin mismatch at start: I ran `compose run` of `dsh-a` with a tampered `driver.py` mounted. The worker refuses: "DSH runtime sha256:d03ed7b6… does not match the registry lock sha256:a842ed2e…".
  - Pin mismatch at the next attempt: with the worker running, I swapped in the tampered launcher and submitted a DSH task. The worker logged "DSH runtime pin mismatch; attempt refused" and "worker cannot serve its queue", then exited with code 3. The database shows `1 | 1 | refused | dsh_unserviceable`.
  - Recovery: after restoring the real launcher, the same task finished `succeeded` with `"attempts": 1`. Its rows are `refused` then `done`, so the refusal used no attempt.

### Findings
1. **Major: 4 integration tests fail on the documented setup.**
   - Cause: they need `VLLM_BASE_URL` set before they start the fake model. `test_dsh_usage.py`'s three tests never set it, so `build_config` raises "CapabilityError: VLLM_BASE_URL is not set for template local-dsh@1". `test_step_limit…` calls `build_config(...)` before `monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)` (`tests/integration/test_dsh_activity.py` lines 527–542).
   - With `VLLM_BASE_URL=http://127.0.0.1:9` set from the shell, the 3 usage tests pass, but step-limit fails with `RunnerFailure: DshUsageUnknown` (log 08). It passed only when a fake model was answering at `VLLM_BASE_URL` (log 09, diagnostic only). So it depends on a live endpoint, not on its own fake model.
   - Effect: CI's `stack` job copies `.env.example` and leaves `VLLM_BASE_URL` empty (ci.yml line 98), so `make smoke` should fail there too. I did not run CI.
2. **Minor: image tags are shared by every checkout on the host.** `praxismesh-worker:dev` and `praxismesh-dsh:dev` are fixed names in `infra/docker-compose.yml`. Building in one checkout retags them for every other checkout. The DSH start command in overview.md (`up -d dsh-a worker-dsh-a`, no `--build`; `worker-dsh-a` has no build section) would silently run whatever image another checkout built last.
3. **Side effect I caused (please tell the owner).** My compose build moved those two tags. With the containerd snapshotter, the previously tagged images `958cf3075641` (worker) and `981e07124e4c` (dsh) were then deleted, and I could not restore the tags. The other stack (`praxismesh`) is still running on its own image `ee69c2e672c5` and was not stopped or changed. Its next `make workers-up` rebuilds anyway.
4. **Minor:** right after the launcher restarted, `up --wait dsh-a worker-dsh-a` reported "container pmverify02-worker-dsh-a-1 is unhealthy". The worker recovered by restarting (6 restarts), as the compose comment describes.

### Temporary changes, all restored
- I ran a replacement `dsh-a` container (`pmverify02-dsh-tampered`) with `.verify/driver-tampered.py` mounted; it has been removed.
- `docker update --restart=no` on `pmverify02-worker-dsh-a-1` so I could see exit code 3; it is back to `unless-stopped`.
- The downgrade/upgrade of migration 0004 on my own database; it is back at `0004 (head)`.

### Stack left running for the as-built check
- Project `pmverify02`, run from <verify-checkout> with `infra/.env`. Use `make <target>` there, or `docker compose -p pmverify02 --env-file infra/.env -f infra/docker-compose.yml ...`.
- Addresses: Temporal 127.0.0.1:27233, UI http://127.0.0.1:28080, S3 http://127.0.0.1:28333, DB 127.0.0.1:25432.
- Running: db, temporal, temporal-ui, s3, orchestrator, fake-model, dsh-a, worker-dsh-a. The workers were started with `VLLM_BASE_URL=http://fake-model:8765`.
- Images in use: worker `7df049992285`, dsh `73da58e247c5`, also tagged `pmverify02-worker:dev` and `pmverify02-dsh:dev`. Re-run compose with `VLLM_BASE_URL=http://fake-model:8765` and the `dsh`, `workers` and `fake-model` profiles. Without that variable the workers are recreated with no model URL and refuse to start; if another checkout rebuilds the shared tags, `up` without `--build` swaps in its images.

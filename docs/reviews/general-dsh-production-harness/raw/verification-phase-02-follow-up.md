<!-- Verbatim subagent report (verification phase 02, targeted follow-up at 86cfec87bfb1ed83c60150d2104a41b6720b7018, fresh verifier); saved by the coordinator per docs/reviews/README.md rule 1; scratch paths replaced by <verify-checkout-b>. -->

Phase 02 targeted follow-up verification of docs/plans/2026-11-15-dsh-production-harness at 86cfec87bfb1ed83c60150d2104a41b6720b7018, run in <verify-checkout-b>.

**Result:** all four acceptance runs passed with `VLLM_BASE_URL` empty. Of the six as-built claims, 3 are confirmed, 2 are confirmed with a qualification and 1 is partly contradicted. There are 2 Minor findings and 2 Nits.

The checkout is clean apart from `.verify/`, which holds the logs. `infra/.env` was not changed and no source, tests or docs were edited. I did not touch the `praxismesh` stack, and `pmverify02` is still running. I ran four throwaway containers myself, all `--rm`: two probe runs, one `sha256sum` and one `docker compose config` read. I started no services. No images were rebuilt by me; the integration tests ran their own untagged `docker build -q`.

## 1. Acceptance tests

`infra/.env` has `VLLM_BASE_URL` empty, and `VIRTUAL_ENV` was unset.

| Run | Command | Exit | Summary line | Failed |
|---|---|---|---|---|
| 1a | `uv run --env-file infra/.env pytest -m integration tests/integration/test_dsh_launcher.py tests/integration/test_dsh_activity.py tests/integration/test_dsh_usage.py tests/integration/test_dsh_capabilities.py tests/integration/test_dsh_outcomes.py` | 0 | "55 passed in 214.74s (0:03:34)" | none |
| 1b | `uv run --env-file infra/.env pytest -m integration tests/test_runner_conformance.py` | 0 | "19 passed, 19 deselected in 42.78s" | none |
| 2 | `make smoke` | 0 | "150 passed, 4 skipped in 265.36s (0:04:25)" | none |
| 3 | `uv run pytest` | 0 | "267 passed, 178 deselected in 32.51s" | none |

- **1a** is the overview's phase 02 integration command. Log: `.verify/b-integration.log`.
- **1b** is the conformance part of the same documented command. Log: `.verify/b-conformance.log`.
- **2** (`make smoke`) runs `uv run --env-file infra/.env pytest -m integration tests/integration --ignore=tests/integration/test_recovery.py`. All 4 skips are `tests/integration/test_model_endpoints.py:25/31/36/48`, each with "VLLM_BASE_URL is unset or empty; model endpoint not configured". That skip is expected with an empty `VLLM_BASE_URL`. Log: `.verify/b-smoke.log`.
- **3** log: `.verify/b-pytest.log`.

## 2. As-built claims (docs/architecture/overview.md)

### a) Phase 01 › Isolation probe (line 134): confirmed in the DSH image, with a Nit
- **Code:** `infra/dsh/isolation-probe.sh` emits 13 checks. `command_wrapper_runs` (lines 71-81) and the seccomp wrapper only apply when `/opt/dsh/launcher.py` exists, which means inside the DSH image.
- **DSH image:** I ran the header's flags (`--network none --read-only --tmpfs /tmp --tmpfs /mnt --cgroupns=private --cap-add=SYS_ADMIN --security-opt no-new-privileges --security-opt apparmor=unconfined`) in `praxismesh-dsh:dev` with `--entrypoint sh`. That image is the one `pmverify02-dsh-a-1` runs; its `launcher.py` and `pins.py` sha256 prefixes `f43f8503…` and `3fb95fc8…` equal this checkout's. Output: "lines=13 ok=13", including `{"check":"command_userns_blocked","ok":true,"detail":""}`. Log: `.verify/b-isolation-probe.log`.
- **Nit:** the overview says "run command in its header", and the header runs the probe in `<pinned python image>`. Doing that in `python:3.11-slim-bookworm@sha256:a83ba18a…` gives 12 checks, one of them failing: `{"check":"command_userns_blocked","ok":false,"detail":"user namespace allowed"}` (log: `.verify/b-isolation-probe-base.log`). notes.md lines 48-50 correctly say "in the DSH image". The overview line does not name the image, so a reader who follows the header literally does not see "all 13 checks pass".

### b) Phase 02 › Worker pair start command (line 149): confirmed in part, contradicted on `--build` (Minor)
- **Needs `VLLM_BASE_URL`: confirmed.** `workers/main.py:143-148` raises `CapabilityError` when the template's `base_url_env` is empty, and `registry/templates/local-dsh.yaml` sets `base_url_env: VLLM_BASE_URL`. Probe: `METRICS_PORT= uv run --env-file infra/.env python -m workers.main template local-dsh` gave "EXIT=1" and "common.errors.CapabilityError: VLLM_BASE_URL is not set: template local-dsh@1 needs a model endpoint (set it in infra/.env)". Log: `.verify/b-worker-novllm.log`.
- **Command is valid: confirmed.** The read-only `docker compose ... --profile dsh config --services` lists `dsh-a worker-dsh-a`.
- **Container settings: confirmed.** `docker inspect pmverify02-dsh-a-1` shows "net=none ro=true cgroupns=private capadd=[CAP_SYS_ADMIN] secopt=[no-new-privileges:true apparmor:unconfined]".
- **`--build` rationale: contradicted (Minor).** The note justifies `--build` with "the `:dev` image tags are shared". But in `infra/docker-compose.yml` only `dsh-a` (line 187) and `orchestrator` (lines 133-135) have a `build:` section. `worker-dsh-a` (lines 199-214) has `image: praxismesh-worker:dev` and no build. The compose JSON shows "worker-dsh-a praxismesh-worker:dev False" and "orchestrator praxismesh-worker:dev True". So the documented `up -d --build dsh-a worker-dsh-a` rebuilds only `praxismesh-dsh:dev`. It does not rebuild `praxismesh-worker:dev`, which another checkout may have retagged. This conclusion comes from the compose config plus standard Compose `--build` semantics; I did not run a build, as instructed.

### c) Phase 02 › Launcher op list (line 150): confirmed
`infra/dsh/launcher.py:401-428` dispatches exactly `digests` (401), `open` (403), `start` (408), `exec` (410), `freeze`/`thaw` (415), `members` (417), `poll` (419) and `stop` (422). Anything else raises "unknown op".

### d) Phase 02 › Usage accounting (line 157): partly contradicted (Minor)
**Started rows: confirmed.** `start()` at `common/persistence/repositories.py:162-170` inserts without tokens, and 0003 sets server default 0. A read-only DB probe found every started row at the default: "started | 0 | 0 | t | 78".

**Supporting code:** `finish` (`repositories.py:211`), `_ledger_usage_sql` (346-369), `close_unknown` (553-574) and `harness_activity/activity.py:319-320` write NULL for unknown usage. The probe found "closed_null_unknown 53" and "closed_null_but_known 0". Logs: `.verify/b-usage-probe.log`, `.verify/b-usage-probe2.log`, `.verify/b-usage-probe3.log`.

**The "never read 0" part is contradicted.** Some closed rows read 0 while a request up to them was never observed:
- **How it happens:** `start()` (`repositories.py:148-158`) and `record_refusal()` (236-246) mark earlier attempts `lost`, setting `ended_at` but not the tokens. Their usage is fixed only later, by the next attempt's `_open` → `_charge` → `close_unknown` (`activity.py:399` then `403`/`376`, which is a separate transaction) or by `close_unfinished` at task or turn end.
- **Window 1:** between `start` and `close_unknown`, which lasts indefinitely if the worker dies in between.
- **Window 2:** after a refusal, until the task completes.
- **Observed rows:** 3 rows matched (from runs at 14:32, 14:41 and 14:48), for example `task-usage-228754436e6f | 1 | 1 | lost | lost_or_timed_out | 0 | 0 | t`. That row has `ended_at` set, and an unsettled `req-0001` for attempt 1 exists in `usage_ledger`. The task is still "running" and attempt 2 is "started".
- **Source of these rows:** `tests/integration/test_dsh_usage.py::test_stale_attempt_cannot_dispatch` (lines 274-291). That test does not drive a real next Activity, but it shows the state the repository allows.
- **Refusal window:** `test_lost_rows_hold_the_ledger_usage_when_the_task_completes` (lines 389-392) passes through the same state after the refusal. It asserts the row only after `close_unfinished`.
- **Related observation (not counted against the claim):** 3 `refused` rows (`dsh_unserviceable`, `refusing-worker`) read 0/0/known although attempt 1 of the turn has an unsettled request. The comment at `repositories.py:568-570` says every attempt row holds the turn's usage through that attempt, so refused rows do not follow that rule.

**Scope ambiguity:** `openai_agents` writes no ledger; `_ledger_usage_sql`'s docstring excludes it. Its lost or failed rows close at 0 with `usage_known` true; the probe counted 91 lost or failed zero rows with no ledger, though I did not break those down by harness. The sentence is not qualified to DSH.

**A precise version of the claim:** closed rows are corrected to NULL when the next attempt opens, or when the turn or task closes; until then a row marked lost keeps 0.

### e) Phase 02 › Tests (line 164): mostly confirmed, with a Nit
- **`test_dsh_usage.py`: confirmed.** Its docstring (lines 4-6) says "a stub runner … No DSH container is needed". It imports only `make_engine`, `MemoryBlobStore` and `temporalio.testing.ActivityEnvironment`, with no Temporal client, S3 or Docker, and sets `VLLM_BASE_URL` to `http://127.0.0.1:9` (line 49).
- **Activity and outcomes tests: confirmed.** `test_dsh_activity.py:74` and `test_dsh_outcomes.py:169` call `start_container(build_image())` and use `FakeModel`.
- **"No model endpoint needed": confirmed.** Run 1a passed with `VLLM_BASE_URL` empty.
- **Nit, launcher tests:** `test_dsh_launcher.py` builds the DSH image (lines 115-117) and runs its own containers, but does not use the fake model. There is no `FakeModel` import.
- **Nit, capabilities tests:** `test_dsh_capabilities.py` builds the image and starts a container (line 51) and uses `FakeModel` (lines 86-87), but the description leaves it out.
- **Unrelated stale docstring:** `test_dsh_launcher.py:3` says it runs in "the pinned Python base image", while the fixture builds `infra/dsh/Dockerfile`.

### f) Phase 02 › Known limits, shared image tags (line 169): confirmed
- **Code:** compose lines 132, 171, 188, 201, 218 and 231 use the fixed tags `praxismesh-worker:dev` and `praxismesh-dsh:dev`.
- **Runtime:** `docker inspect praxismesh-orchestrator-1` (the other project) shows "praxismesh-worker:dev sha256:ee69c2e672c5…". That tag now resolves to `7df049992285` (built 2026-11-16 09:24), and the other stack's containers list the image as the untagged `ee69c2e672c5`. A build elsewhere retagged it, exactly as stated.

## Findings
1. **Minor (2b):** the documented start command's `--build` does not rebuild `praxismesh-worker:dev`, because `worker-dsh-a` has no `build:` section. It therefore does not do what the note says `--build` is for.
2. **Minor (2d):** "Closed attempt rows never read 0 for unobserved usage" is too strong. A row marked lost by `start` or `record_refusal` reads 0 until the next attempt's `close_unknown` or `close_unfinished` runs. The probe found 3 such rows. The sentence is also not limited to DSH, though `openai_agents` has no ledger.
3. **Nit (2a):** the isolation probe line points to the header's run command (base image), which gives 12 checks with `command_userns_blocked` failing; "all 13 pass" holds only in the DSH image.
4. **Nit (2e):** the tests description says the launcher tests use the fake model (they do not) and leaves out `test_dsh_capabilities.py`, which does use it.

Logs are all in <verify-checkout-b>/.verify/:
- b-integration.log
- b-conformance.log
- b-smoke.log
- b-pytest.log
- b-worker-novllm.log
- b-isolation-probe.log
- b-isolation-probe-base.log
- b-usage-probe.log, b-usage-probe2.log, b-usage-probe3.log
- q.sql, q2.sql

<!-- Verbatim subagent report (verification phase 02, narrow as-built follow-up: docs 7b06ce6 against code 86cfec8, fresh verifier); saved by the coordinator per docs/reviews/README.md rule 1; scratch paths replaced by <verify-checkout-b>. -->

## Targeted re-verification: phase 02 as-built statements in `docs/architecture/overview.md`

I checked four statements from the doc at 7b06ce6 against code frozen at 86cfec8, in `<verify-checkout-b>`. No statement is contradicted. Two can't be fully confirmed: part of statement 1 lacks a runtime check, and statement 4's runtime half can't be run under the brief. Statement 3 has one Nit-level ambiguity. Scratch outputs are in `<verify-checkout-b>/.verify/`.

### 1. Isolation probe (overview.md:134): confirmed from records and code; the runtime part is unverifiable
- **"At phase 01 the user-namespace check failed"** is confirmed.
  - The phase 01 probe (`git show 1f763b7:infra/dsh/isolation-probe.sh`, line 72) already had `command_userns_blocked`.
  - The phase 01 notes (`git show 1f763b7:.../notes.md`, line 44) record "Command cannot create a user namespace | - | **no**".
- **"13 checks in the DSH image"** matches the code.
  - `infra/dsh/isolation-probe.sh` has 13 distinct `report` names. `command_wrapper_runs` (lines 69-80) only runs when `/opt/dsh/launcher.py` exists, and `infra/dsh/Dockerfile:24` copies `launcher.py` there.
  - In the DSH image, commands go through `launcher.install_seccomp()` (`infra/dsh/launcher.py:123`).
  - In the plain base image there is no wrapper, so the userns check (line 86) runs without seccomp.
  - `notes.md` (D3, phase 02 task 1.1) records "all 13 probe checks pass".
- **Unverifiable (Nit):** I could not observe the runtime claims ("passes all 13 checks"; "in the plain base image ... `command_userns_blocked` still fails"). My `docker run --rm` of the probe in `praxismesh-dsh:dev` and in the pinned `python:3.11-slim-bookworm@sha256:a83b…` was denied by the permission classifier. The claims rest only on the recorded notes and the code above.

### 2. Worker pair start instructions (overview.md:149): confirmed
- **Refusal at start:** `workers/main.py:143-148` raises `CapabilityError` when `os.environ.get(loaded.template.base_url_env)` is empty. `registry/templates/local-dsh.yaml:8` sets `base_url_env: VLLM_BASE_URL`.
- **No build of its own:** in `infra/docker-compose.yml`, `worker-dsh-a` (lines 199-201) has only `image: praxismesh-worker:dev`. `orchestrator` (lines 130-135, profile `workers`) builds `praxismesh-worker:dev`.
- **Build command resolves:** `docker compose -p pmverify02 ... --profile dsh build --print orchestrator dsh-a` resolves both targets, even though `orchestrator` is outside the `dsh` profile: `"dsh-a"` gives `tags ["praxismesh-dsh:dev"]` and `"orchestrator"` gives `dockerfile .../workers/Dockerfile`, `tags ["praxismesh-worker:dev"]`.
- **Live stack:** `worker-dsh-a` is "running Up 26 minutes (healthy) praxismesh-worker:dev", and `VLLM_BASE_URL` is set in its environment.

### 3. Usage accounting (overview.md:157): confirmed, with one Nit-level ambiguity
- **"The only ones with ledger rows":** the only `INSERT INTO usage_ledger` is `common/persistence/repositories.py:505`, reached only from the DSH ledger (`harness_activity/dsh/ledger.py:95`). `orchestrator/activities.py:49` says "no ledger rows: openai_agents".
- **Set to NULL when the attempt fails:** `harness_activity/activity.py:310-324` writes `tokens_in=None if own_unknown`.
- **Set to NULL when it "finishes":** a successful attempt cannot have its own unknown usage, because `harness_activity/dsh/policy.py:51-52` turns any unknown usage into `DshUsageUnknown`, which is a failure.
- **Set to NULL when the next attempt opens:** `repositories.py:562-573` (`close_unknown`, plus `_ledger_usage_sql` for lost rows).
- **Set to NULL when the turn or task closes:** `close_unfinished` (`repositories.py:290-301`) is called from `activity.py:271` and `:333` and from `orchestrator/activities.py:130`.
- **Creation default 0:** the live DB `\d task_attempts` shows `tokens_in | bigint | | | '0'::bigint`. `start()` and `record_refusal()` insert without tokens, and marking a row lost does not touch tokens.
- **Live probe on DSH turns** (outcome|usage_known|tokens_in|count): `started|t|0|20`, `refused|t|0|7`, `lost|t|0|12`, `lost|f||16`.
- **Nit (ambiguity):** the statement holds if "unobserved usage" means the attempt's own requests. But a row's usage is cumulative over the turn's attempts. When an earlier attempt's request was never observed, `finish()` writes a number with `usage_known=false`, not NULL: `activity.py:558-568` uses `progress.tokens_in`, and `:319` does the same when `own_unknown` is 0. The close paths write NULL in the same situation (`_ledger_usage_sql`, `repositories.py:355-357`). The live DB has such rows:
  - 18 `done` rows, e.g. `done|2|33168|own_unknown 0|earlier_unknown 1`;
  - 2 `failed` rows, `failed|3|65836|0|2`.

### 4. Tests (overview.md:164): confirmed from code; the runtime claim is unverifiable
- **Fake model or dummy URL:** every model-using test sets `VLLM_BASE_URL` to a `FakeModel` (test_dsh_activity.py:171 and others; test_dsh_capabilities.py:86-87; test_dsh_outcomes.py:274, 326, 360, 412, 452, 536, 651; test_runner_conformance.py:126). test_dsh_usage.py:44-49 sets the dummy `http://127.0.0.1:9` and uses `StubRunner` (line 68).
- **Tests without a model URL never reach `build_config`:** these are test_dsh_activity.py:457 and :694. They fail at the pin check or the preflight.
- **Own image and containers:** test_dsh_launcher.py:111-115 runs `docker build`, and `tests/support/dsh.py:71-78` provides `build_image()`. `start_container` is used in test_dsh_activity.py:74, test_dsh_capabilities.py, test_dsh_outcomes.py:169 and test_runner_conformance.py:60.
- **Unverifiable (Nit):** I did not run the suite, as the brief forbids it. Also, `uv run --env-file infra/.env` loads the developer's `VLLM_BASE_URL` (set in this checkout's `infra/.env`). So no run here could show the tests pass without one; that rests on the code reading above.

### Changes made
None. I wrote only under `.verify/`. The only commands that ran were read-only `docker compose config` / `build --print` / `ps`, `docker inspect`, and SELECT/`\d` queries against `pmverify02`. Nothing touched the `praxismesh` project.

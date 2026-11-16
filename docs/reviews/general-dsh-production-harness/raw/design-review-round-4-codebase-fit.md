<!-- Verbatim subagent report (design-review round 4, codebase fit, targeted follow-up on the phase 02 decision changes); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. The run stopped once on a usage limit and was resumed. -->

Review of docs/plans/2026-11-15-dsh-production-harness at commit 98835319

Phases 01 and 02 are already implemented. Almost all of the plan's claims about their code check out. The real problems are in phase 03, which has not been implemented yet, plus one ADR condition the plan drops.

## Findings

### 1. Major: switching `default` to DSH leaves no way to select `openai_agents`, and breaks CI
**Where:** phase 03, task 2.1; also R3/R4 and the "Why" table row "`openai_agents` stays selectable".

**What is wrong:** Task 2.1 says "point the `default` profile at `dsh`/`local-dsh`". The plan adds no other profile that allows `local-default`.
- Templates are reached only through a profile. `Registry.resolve` refuses any template not in `profile.allowed_templates` (<repo>/registry/loader.py, `resolve`). Requests may not name capabilities (orchestrator/requests.py:3).
- After the switch, `openai_agents` cannot be selected through the API. That conflicts with ADR-0005 condition 5 ("Keep `openai_agents` available and selectable per template until DSH passes its own phase gate"; the phase 03 gate comes after task 2.1) and with decision-log.md:93 ("keep `openai_agents` selectable per template").
- Several CI checks assume `default` resolves to `local-default` on `openai_agents` workers:
  - tests/test_registry.py:26-28 asserts `loaded.template.ref == "local-default@1"`.
  - tests/integration/test_recovery.py:62/65 uses profile `default` with `running_workers` (template `local-default`), and line 70 asserts `result.template == "local-default"`. CI runs it through `make recovery-check` (.github/workflows/ci.yml:119).
  - `make workers-check` (ci.yml:118, Makefile ~126-131) submits a default-profile task through the `workers` Compose profile only (`orchestrator worker-a worker-b`). The DSH pair is in Compose profile `dsh` (infra/docker-compose.yml:186, 200), so no worker would serve `tpl.local-dsh`.
  - tests/integration/test_task_e2e.py:51 and tests/test_submit.py also use `default`.
- `make workers-up` (Makefile:122-123) never starts the DSH pair either.

**Fix:** task 2.1 should add a profile for `openai_agents` (or keep one) and repoint these tests and Make targets. Otherwise the plan should say how CI keeps passing and record the ADR deviation.

### 2. Major: the benchmark task leaves out the DSH container and several hardcoded values
**Where:** phase 03, task 1.1 ("Add `--profile` to `tests/benchmarks/run.py` (`running_workers` already takes a template)"); also R19.

**What is wrong:** `running_workers` (tests/support/workers.py:19-30) builds the template worker in-process. For a `dsh` template, `build_harness` needs a live paired launcher at `DSH_CONTROL` (default `/attempts/.control.sock`) on an attempt volume shared with the worker process, and calls `dsh.check()` at startup (workers/main.py:61, 89-113). Nothing in task 1.1 starts that container. The existing helper for this, `start_container` and `build_image` in tests/support/dsh.py:71 and :176, is not mentioned for reuse.

`tests/benchmarks/run.py` also hardcodes values that `--profile` alone does not change:
- `TEMPLATE = "local-default"` (line 47)
- `"profile": "default"` (line 58)
- `environment()` reporting `openai-agents <version>` as the harness (line 117)
- the output file name `<date>-local-default` (line 186)

As written, the DSH run (task 1.2) would be labelled openai-agents and would overwrite the same day's `default` result files. That conflicts with task 1.2's "both results are recorded".

### 3. Major: ADR-0005 condition 1's licence-notice part is dropped
**Where:** plan "Why" table, row "Pin the DSH release and digests | R17"; ADR-0005 condition 1.

**What is wrong:** ADR-0005 condition 1 reads "Pin an exact DSH release and its digests in the worker image; record its licence notices." The plan maps the condition only to R17 (pinning). No requirement, task or Open question covers licence notices. No file in the repository records them:
- `git ls-files` shows only `LICENSE`.
- infra/dsh/Dockerfile installs `deepseek-harness-runtime-bin==0.2.2rc2` (infra/dsh/requirements.txt) and records no notice.
- ADR-0005 also notes that native-binary provenance is unestablished.

**Fix:** add a task (phase 03 is the natural place) or list the gap under Open questions.

### 4. Nit: phase 03 task 1.1's template edit does nothing
**Where:** phase 03, task 1.1 ("set `local-dsh`'s `turn_timeout` and `max_wall_time_cap` as in `local-default`").

**What is wrong:** they already match. registry/templates/local-dsh.yaml and local-default.yaml both have `turn_timeout: PT10M` and `max_wall_time_cap: PT1H`. Any edit would also need a version bump and `make registry-lock` (template header comment; registry/registry.lock). Drop the clause or say what should actually change.

### 5. Nit: the Compose key in notes.md#d3 is wrong
**Where:** notes.md, D3 ("Compose settings the pair needs: `cgroupns: private`").

**What is wrong:** Compose uses `cgroup: private` (infra/docker-compose.yml:191), and `cgroupns` is not a Compose key. The plan cites this text as the settings to apply (phase 02, task 1.2).

### 6. Nit: the line reference in phase 01 task 2.2 is out of date
**Where:** phase 01, task 2.2 ("`registry/loader.py:101-105`").

**What is wrong:** the resolve-time check is now around line 133 of `resolve`, and the load-time checks are around lines 160-170. The task is done, so this only matters for audit.

## Claims checked and confirmed (no finding)
- **Schemas:** `Harness` includes `dsh` (common/schemas/base.py:10). `SUPPORTED_HARNESSES` is at registry/loader.py:30. The load-time `dsh` check for `concurrency_per_pod`/`context_window` is in registry/loader.py. `usage_known` is on the result schemas (common/schemas/task.py:87, 107, 130, 172).
- **Migration:** common/persistence/migrations/versions/0004_dsh_usage_and_sessions.py exists.
- **Fence:** `pg_advisory_xact_lock(hashtext(...))` is at common/persistence/repositories.py:378. `start`, `finish`, `record_refusal`, `assert_current` and `close_unfinished` are at :137, :172, :222, :259 and :273.
- **Runner and composition:** `_finish` is in harness_activity/activity.py:530. `DSH_MAX_OUTPUT_TOKENS = 2048` is at harness_activity/dsh/ledger.py:17. The disabled composition ids in harness_activity/dsh/composition.py match notes.md#r14.
- **Probe:** the isolation probe has 13 checks, including `command_userns_blocked`, matching the notes' "all 13 probe checks".
- **Compose and registry:** Compose has `network_mode: none`, read-only root, `SYS_ADMIN`, `no-new-privileges`, `apparmor:unconfined` and a tmpfs attempt volume. The registry lock pins `local-dsh@1` and the `dsh` runtime. The `dsh` profile exists.
- **Benchmarks and runbook:** docs/benchmarks/baseline.json is 10/10 on openai-agents. The evidence file docs/spikes/dsh-phase02-r2-evidence.json exists. `docs/operations/runbook.md` does not exist yet, and the plan says it will be created at the path the roadmap standardizes (decision-log.md:68).
- **Rollback:** the claim that running tasks finish on DSH holds. Capabilities and queue are resolved once at workflow start (orchestrator/activities.py:62-74), and wall time is bounded by `deadline` (orchestrator/workflow.py:90).
- **ADR-0006 and decision log:** D3/D4 match ADR-0006. The decision log has entries for D3, D7/D9, R1/R2, `SYS_ADMIN`, AppArmor and D11.

## Files referenced
- <repo>/docs/plans/2026-11-15-dsh-production-harness/phases/03-acceptance.md
- <repo>/tests/benchmarks/run.py
- <repo>/tests/support/workers.py
- <repo>/tests/support/dsh.py
- <repo>/workers/main.py
- <repo>/registry/loader.py
- <repo>/registry/profiles/default.yaml
- <repo>/tests/test_registry.py
- <repo>/tests/integration/test_recovery.py
- <repo>/Makefile
- <repo>/.github/workflows/ci.yml
- <repo>/infra/docker-compose.yml
- <repo>/infra/dsh/Dockerfile
- <repo>/docs/adr/0005-adopt-dsh-as-primary-agent-harness.md
- <repo>/docs/roadmap/decision-log.md

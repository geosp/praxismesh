<!-- Verbatim subagent report (verification-phase-01-acceptance); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## Verification report: DSH migration phase 01 ("Harness seam and registry"), commit 4969d4dbeaddd6fd8f6af777a9b0fdbe50db0bb3

**Verdict: every item passed, each with quoted output. Nothing failed or was blocked.** There are four low-severity findings, all about documentation or test coverage. None of them breaks an acceptance criterion.

Checkout: <verify-checkout> (confirmed `git rev-parse HEAD` = 4969d4d…, clean). Logs: <verify-checkout>/.verify/ (01-setup.log through 15-dsh-worker.log).

### 1. Prerequisites (documented steps only)
1. `uv python install 3.11 && uv sync --locked` (README "Set up"): exit 0.
2. `cp infra/.env.example infra/.env`, then edited it as README "Several checkouts" says:
   - `COMPOSE_PROJECT_NAME=verify-dsh-01`
   - `DB_PORT=15432`, `TEMPORAL_PORT=17233`, `TEMPORAL_UI_PORT=18080`, `S3_PORT=18333`
   - the port inside `PRAXIS_SAMPLE_DB_URL` changed to 15432
   - `VLLM_BASE_URL` left empty
3. `make up`: "stack is up; run 'make status' for addresses and health", exit 0.
4. `make status`: "addresses: Temporal 127.0.0.1:17233, UI http://127.0.0.1:18080, S3 http://127.0.0.1:18333, DB 127.0.0.1:15432 … all services healthy", exit 0.
5. `make migrate`: upgrades 0001 → 0002 → 0003, exit 0.

Nothing undocumented was needed to run. One environment note: the inherited `VIRTUAL_ENV` pointing at <repo>/.venv made uv print "does not match the project environment path… will be ignored". It was harmless, and I ran `unset VIRTUAL_ENV` for the later steps.

### 2. Acceptance suites (AGENTS.md "Checks")
| Command | Exit | Summary |
|---|---|---|
| `uv run ruff check .` | 0 | "All checks passed!" |
| `uv run ruff format --check .` | 0 | "279 files already formatted" |
| `uv run mypy` | 0 | "Success: no issues found in 95 source files" |
| `uv run pytest` | 0 | "174 passed, 101 deselected in 32.90s" (integration tests are deselected by addopts) |
| `uv run .agents/sync_agents.py --check` | 0 | "ok: 3 generated agent file(s) up to date" |
| `uv run .github/scripts/check_plans.py` | 0 | "Validated 4 implementation plan(s); 0 error(s)" |
| `make smoke` | 0 | "92 passed, 4 skipped in 38.71s" (skips: test_model_endpoints, "VLLM_BASE_URL is unset or empty") |
| `make recovery-check` (regression for the moved `run_harness_turn`) | 0 | "5 passed in 58.09s" |
| `make workers-check` (fake model, containers) | 0 | the task reached `"status": "succeeded"` with template local-default, `"tokens_in": 400` |

### 3. Demo: task Verify lines plus R1–R3 Given/When/Then

**0.1 Gate probe: PASS.** I ran the command in the header of infra/dsh/isolation-probe.sh with the image pinned in workers/Dockerfile, `python:3.11-slim-bookworm@sha256:a83ba18a…`.
- Expected: "a probe script freezes and kills a process tree; if freeze fails, SIGSTOP works with its stated limit".
- With `--cap-add=SYS_ADMIN`, observed:
  - `cgroup_join … "members=3"`
  - `cgroup_freeze","ok":true,"detail":"frozen=1 members=3"`
  - `cgroup_kill","ok":true,"detail":"alive=0 of 3"`
  - `sigstop_group … "stopped=3 of 3"`
  - `command_uid` true, `mount_namespace` true ("unshare -m"), escape/mount/caps checks true
  - `command_userns_blocked","ok":false,"detail":"user namespace allowed"`. notes.md#d3 records this exact result and makes the seccomp filter a phase 02 condition, so it matches the document.
- Failure path, run without SYS_ADMIN:
  - `cgroup_remount … "remount refused"`
  - `cgroup_create … "cgroup root not writable"`
  - `sigstop_group","ok":true,"detail":"stopped=3 of 3"`
  - `mount_namespace … "no mount namespace"`
- So when freeze is unavailable the probe names the failure, and the SIGSTOP fallback works, as documented.

**1.1 Seam and fence: PASS.**
- `uv run pytest` passes (above).
- The conformance suite runs through the runner fixture: `tests/test_runner_conformance.py::…[openai_agents]` 19 PASSED (log 07).
- With `pytest -m integration tests/integration/test_persistence_phase1.py tests/integration/test_harness_activity.py -v`, all of these PASSED:
  - `test_session_store_contract` (SQLAlchemySessionStore on Postgres)
  - `test_stale_attempt_cannot_checkpoint_or_finish`
  - `test_older_turn_is_fenced_by_a_newer_turn`
  - `test_fenced_insert_waits_for_a_concurrent_start`
  - `test_start_waits_for_the_task_lock`
  - `test_refusal_fences_older_attempts`
  - `test_late_stale_start_is_refused`
  - `test_fenced_finish_rejects_a_newer_turn`
  - `test_newer_attempt_mid_run_fences_the_finish`
  - `test_newer_attempt_before_publication_blocks_artifacts`
- R3 (local-default passes conformance on the seam): PASS.

**2.1 / R1 (unknown harness rejected): PASS.**
- `test_unknown_harness_value_is_rejected` and `test_unsupported_harness_template_rejected` PASSED.
- Live scenario in a scratch clone (since deleted), with the lock check on, `harness: foo` in local-default gives: `RegistryError: …local-default.yaml: harness: Input should be 'claude_sdk', 'claude_cli', 'openai_agents' or 'dsh'`.
- `harness: claude_sdk` gives: `harness 'claude_sdk' has no runner in this phase (supported: dsh, openai_agents)`.
- `dsh` is present in `Harness` (common/schemas/base.py), `SUPPORTED_HARNESSES`, docs/roadmap/schemas.md, and a decision-log row dated 2026-11-15.

**2.2 / R2 (mismatch fails at load): PASS.**
- `test_harness_mismatch_fails_at_load` and `test_dsh_profile_cannot_allow_an_openai_template` PASSED.
- Exact Given in the scratch clone, dsh.yaml `allowed_templates: [local-default]`, then `load_registry()` gives: `RegistryError: profile 'dsh' harness 'dsh' does not match template 'local-default@1' harness 'openai_agents'`.
- The reverse case (the default profile also allowing local-dsh) gives: `profile 'default' harness 'openai_agents' does not match template 'local-dsh@1' harness 'dsh'`.

**2.3 (registry-lock pins; dsh resolves local-dsh): PASS.**
- `make registry-lock` in the checkout: exit 0, no output, and `git status` shows registry.lock unchanged.
- In the scratch clone I deleted the `local-dsh@1` line. Loading then failed with "template local-dsh@1 is not in registry.lock; bump the version if needed and run `make registry-lock`". Rerunning `make registry-lock` regenerated a lock byte-identical to the committed one (`diff` gave "identical"), and the entry is `local-dsh@1: sha256:54ef665b…`.
- `load_registry().resolve('dsh')` gives `dsh dsh local-dsh@1 1 32768`, meaning the profile has harness dsh, the template has `concurrency_per_pod` 1 and `context_window` 32768.
- The load-time rule for dsh templates is covered: `test_dsh_template_needs_one_attempt_and_a_context_window` (2 cases) PASSED.

**3.1 AgentEvent sink: PASS.**
- `test_events_are_ordered_and_carry_attempt_identity` (seq `[0,1,2,3]`, attempt_id `task-1:2:3`), `test_unknown_event_type_and_fields_are_rejected` and `test_concurrent_emitters_deliver_in_seq_order` (800 events in order) all PASSED.

**Extra check: PASS.** `VLLM_BASE_URL=http://127.0.0.1:1 uv run --env-file infra/.env python -m workers.main template local-dsh` exits 1 with: `CapabilityError: template local-dsh@1 uses harness 'dsh', which this worker cannot run yet`.

### Findings (all low)
1. **Probe image is a placeholder.** The header of infra/dsh/isolation-probe.sh says `<pinned python image>`, and notes.md#d3 says "the pinned Python base image". Neither names the image or where it is pinned; I took it from workers/Dockerfile.
2. **"Pins both" is ambiguous.** Task 2.3 says "lock them … `make registry-lock` pins both", but registry.lock pins only templates. The `dsh` profile is not, and cannot be, in the lock. Either the wording is loose or profile pinning is missing.
3. **A dsh task waits silently.** The `dsh` profile can be selected now, but no worker can serve `tpl.local-dsh` until phase 02. `make task PROFILE=dsh PROMPT=hello` printed no error and was still waiting when my 60 s timeout killed it. The plan seems to intend this, but it is not documented for users.
4. **Worker refusal has no test.** The refusal in workers/main.py for non-openai_agents templates has no unit or integration test; `grep` for "cannot run yet" or local-dsh under tests/ outside test_registry finds nothing. I confirmed it only by hand (extra check above).

Not covered by this phase and not run: R4 (`make benchmark`, phase 03, needs a model); R5–R19 (phases 02–03).

### 4. Teardown
- `make workers-down`, then `make reset` for project verify-dsh-01: containers, volumes `verify-dsh-01_pgdata` and `verify-dsh-01_seaweeddata`, and the network were removed.
- The user's `praxismesh-*` containers are still running and were not touched.
- I deleted infra/.env and the scratch clone; `git status` shows only `?? .verify/`.
- The worker images that `make workers-check` built under project verify-dsh-01 are still in the local Docker image cache.

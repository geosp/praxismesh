<!-- Verbatim verifier report (Phase 3A persistence plan, phase 01 gate verification, acceptance re-run at the logger fix 56c0170); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-acceptance-fix.md per docs/reviews/README.md rule 1. -->

# Phase 3A persistence, phase 01: acceptance verification re-run after the fix

- Plan: docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle, phase 01 (01-index-classes-and-guard.md)
- Checkout: /tmp/claude-1000/-home-geo-develop-praxismesh/5562944e-be36-4ae6-b40e-bb1b87da77f8/scratchpad/verify-phase3a-01
- Commit: `git rev-parse HEAD` -> `56c0170872fd14efa3f7902779284b9a32d382ba` (frozen commit, matches). `git status --short` -> `?? .verify/` only, before and after.
- Date: 2026-11-20
- Logs for this run: `.verify/fix/` (earlier files in `.verify/` were not read or used).
- Demo: not applicable to this phase.

## Environment

- The calling shell had `VIRTUAL_ENV=/home/geo/develop/praxismesh/.venv` and `/home/geo/develop/praxismesh/.venv/bin` on PATH. Every command ran after `unset VIRTUAL_ENV` and removing that PATH entry (`.verify/fix/env.sh`). `uv run which python` -> `.../verify-phase3a-01/.venv/bin/python`.
- `diff infra/.env.example infra/.env`: the only differences are `COMPOSE_PROJECT_NAME=pmverify3a`, `DB_PORT=55432`, `TEMPORAL_PORT=57233`, `TEMPORAL_UI_PORT=58080`, `S3_PORT=58333`, `VLLM_BASE_URL=http://spark-01:8000`, and the port 55432 in `PRAXIS_SAMPLE_DB_URL` and `PRAXIS_COMMS_DB_URL`. That is project name, ports and VLLM_BASE_URL, as stated.
- I did not touch the owner's `praxismesh` Compose project. All `make` targets act on `pmverify3a`, which they read from infra/.env.

## 1. AGENTS.md "Checks" and the unit suite

| Command (AGENTS.md "Checks") | Expected | Observed | Result |
|---|---|---|---|
| `uv sync --locked` | exit 0 | exit 0, `Resolved 90 packages in 1ms` / `Checked 86 packages` | pass |
| `uv run ruff check .` | exit 0 | exit 1, `Found 4 errors.` All 4 are in untracked scratch scripts from earlier checks: `.verify/asbuilt_unindexed.py`, `.verify/guard_live.py` (2), `.verify/m0007/unindexed.py`. `git ls-files .verify` -> 0 files. | see note |
| `uv run ruff format --check .` | exit 0 | exit 1, `3 files would be reformatted, 516 files already formatted`. The 3 files are the same `.verify/` scratch scripts. | see note |
| `uv run ruff check --extend-exclude .verify .` | exit 0 | exit 0, `All checks passed!` | pass |
| `uv run ruff format --check --extend-exclude .verify .` | exit 0 | exit 0, `513 files already formatted` | pass |
| `uv run mypy` | exit 0 | exit 0, `Success: no issues found in 169 source files` | pass |
| `uv run pytest` (unit suite; addopts `-m 'not integration'`) | exit 0 | exit 0, `372 passed, 280 deselected in 57.71s` | pass |
| `uv run .agents/sync_agents.py --check` | exit 0 | exit 0, `ok: 3 generated agent file(s) up to date` | pass |
| `uv run .github/scripts/check_plans.py` | exit 0 | exit 0, `Validated 8 implementation plan(s); 0 error(s)` | pass |
| `uv run .github/scripts/check_dsh_licences.py` | exit 0 | exit 0, `licence notices present for 7 pinned DSH distributions` | pass |
| gitleaks (README "Checks", CI) | - | `which gitleaks` -> `no gitleaks in (...)` | blocked: not installed |
| actionlint (CI) | - | `which actionlint` -> `no actionlint in (...)` | blocked: not installed |
| offline link check (CI) | - | not in the AGENTS.md command list, and not run here | not run |

Note on ruff: the failures come only from verifier scratch files under the untracked `.verify/` directory, which earlier checks wrote in this checkout. Committed content is clean, as the two runs with `--extend-exclude .verify` show. A clean CI checkout would not contain these files. This is not a finding against the project.

## 2. Stack preparation and integration runs

### Steps, in order, with their source

| # | Step | Source | Exit / key output |
|---|---|---|---|
| 1 | `uv sync --locked` | README "Set up"; AGENTS.md "Checks" | 0 |
| 2 | `make up` | README "Local stack" (code block) | 0, `stack is up; run 'make status' for addresses and health` |
| 3 | `make status` | README "Local stack" | 0, `all services healthy`; `model endpoint: http://spark-01:8000 answers /v1/models` |
| 4 | `make migrate` | README "Local stack" and "Running an agent task" | 0; then `alembic current` -> `0007 (head)` |
| 5 | `make workers-down` | README "Local stack": "Run `make smoke`, or `uv run --env-file infra/.env pytest -m integration`, with the worker containers stopped (`make workers-down`)" | 0, all worker, orchestrator and dsh containers `Removed` |
| 6 | `uv run --env-file infra/.env pytest -m integration -rs` | README "Local stack" (the command; I added `-rs` as the brief asks) | see (a) |
| 7 | `make smoke` | README "Local stack" | see (b) |

The README says to stop the workers for the integration runs, so they were not rebuilt before those runs. The worker images are rebuilt from this commit at step 5 below (`make workers-up` uses `--build`). Following the README, I needed no undocumented step.

### (a) Full integration suite

`uv run --env-file infra/.env pytest -m integration -rs` -> exit 0

```
collected 652 items / 372 deselected / 280 selected
...
tests/integration/test_migration_0007.py ...                             [ 75%]
...
tests/integration/test_refs.py .....                                     [ 86%]
...
tests/test_runner_conformance.py .........................               [100%]

=============== 280 passed, 372 deselected in 879.05s (0:14:39) ================
```

`-rs` printed no skip summary, so nothing was skipped. The session-wide `history_payload_guard` fixture in tests/integration/conftest.py runs at session teardown and did not fail the session. The model endpoint tests (`test_model_endpoints.py .....`) ran against `http://spark-01:8000`.

This run also covers the earlier failure. `tests/test_runner_conformance.py` (all 25, including `test_refusals_are_logged_with_ids[dsh]`) ran after `test_migration_0007.py` in the same session and passed.

### (b) `make smoke`

`make smoke` -> exit 0 (runs `pytest -m integration tests/integration --ignore=tests/integration/test_recovery.py`)

```
tests/integration/test_two_agents.py .                                   [ 98%]
tests/integration/test_upload_refs.py ....                               [100%]

======================= 250 passed in 738.59s (0:12:18) ========================
```

## 3. Refusal logging after the migration and reference tests, in one session

`uv run --env-file infra/.env pytest -m integration -v -p no:randomly tests/integration/test_migration_0007.py tests/integration/test_refs.py 'tests/test_runner_conformance.py::test_refusals_are_logged_with_ids[dsh]'` -> exit 0

```
tests/integration/test_migration_0007.py::test_migration_0007_backfills_remaps_and_round_trips PASSED [ 11%]
tests/integration/test_migration_0007.py::test_new_defaults_and_checks PASSED [ 22%]
tests/integration/test_migration_0007.py::test_an_in_process_migration_keeps_existing_loggers PASSED [ 33%]
tests/integration/test_refs.py::test_unindexed_then_reindex_twice PASSED [ 44%]
tests/integration/test_refs.py::test_dangling_references PASSED          [ 55%]
tests/integration/test_refs.py::test_orphans_with_their_age PASSED       [ 66%]
tests/integration/test_refs.py::test_expiry PASSED                       [ 77%]
tests/integration/test_refs.py::test_rowless_uploads_wait_for_the_window PASSED [ 88%]
tests/test_runner_conformance.py::test_refusals_are_logged_with_ids[dsh] PASSED [100%]
============================== 9 passed in 8.13s ===============================
```

Result: pass. The test that failed in the earlier re-run now passes when it runs after the in-process migrations.

I also tried to temporarily revert only `common/persistence/migrations/env.py` to `HEAD~1`, to show that the new regression test fails without the fix. The tool permission layer denied this. I made no change, and the tree is still clean (`git status --short` -> `?? .verify/`). That counter-check is therefore not done (blocked: permission denied). It was not required by the brief.

## 4. Per-task Verify lines and their tests

Integration results come from run 2a. Pytest printed one dot per test, 280 passed and none failed or skipped, so every test listed below passed in that run. Unit results come from the step-1 run (`372 passed`).

| Task | Verify line (summary) | Test(s) | Result |
|---|---|---|---|
| 1.1 | scratch database, migrate to 0006, seed every kind, migrate to 0007, downgrade, upgrade | tests/integration/test_migration_0007.py::test_migration_0007_backfills_remaps_and_round_trips, ::test_new_defaults_and_checks (and the new ::test_an_in_process_migration_keeps_existing_loggers); helper tests/support/scratch_db.py | pass (2a: `test_migration_0007.py ...`) |
| 1.2 | integration test as the app role (no UPDATE or DELETE on audit_log) | tests/integration/test_audit_log.py::test_app_role_cannot_change_audit_rows (parametrized UPDATE and DELETE) | pass (2a: `test_audit_log.py ...`) |
| 1.3 | unit tests, including a repeat `put` over `task` metadata | tests/test_retention.py (test_every_app_table_has_its_d3_class, test_migration_0007_uses_the_same_classes, test_reference_query_matches_the_migration, test_reference_classes_match_d3_blob_table, test_order_and_lifetimes, test_stronger_never_returns_task[*], test_old_payloads_still_decode, test_repeat_put_over_task_metadata, test_task_is_never_written) | pass (unit run: 372 passed; these are unit tests, not part of 2a) |
| 1.4 | seed each case including a bucket object with no row; reindex twice changes nothing the second time | tests/integration/test_refs.py::test_unindexed_then_reindex_twice, ::test_dangling_references, ::test_orphans_with_their_age, ::test_expiry, ::test_rowless_uploads_wait_for_the_window; tests/integration/test_blob_store_s3.py::test_list_objects_names_every_object | pass (2a: `test_refs.py .....`, `test_blob_store_s3.py ..........`) |
| 2.1 | integration test per writer; a refused fenced checkpoint leaves no index row | tests/integration/test_index_writers.py::test_record_task_indexes_instructions_and_inputs, ::test_checkpoint_inserts_index_their_blobs, ::test_refused_fenced_checkpoint_leaves_no_index_row, ::test_event_publish_indexes_attachments, ::test_conflict_keeps_the_stronger_class_and_a_delete_mark, ::test_a_failed_index_write_rolls_back_its_holder_row | pass (2a: `test_index_writers.py ..........`) |
| 2.2 | a submit's uploads are held by its task before `record_task`; mypy passes | tests/integration/test_upload_refs.py::test_submit_uploads_are_held_by_their_task_before_record_task (plus the repeat-put and late-upload tests in the same file); `uv run mypy` | pass (2a: `test_upload_refs.py ....`; mypy `Success: no issues found in 169 source files`) |
| 2.3 | integration test for each terminal status | tests/integration/test_index_writers.py::test_end_task_sets_ended_at_and_indexes_artifacts[succeeded/failed/needs_input], ::test_a_retried_end_task_keeps_a_redaction | pass (2a, same file) |
| 2.4 | a fake-model task reads each class back from rows and `blob_refs` | tests/integration/test_task_e2e.py::test_scripted_task_end_to_end (new row-class and index assertions) | pass (2a: `test_task_e2e.py ...`) |
| 2.5 | integration test of `AuditRepository.append` | tests/integration/test_audit_log.py::test_append_joins_the_callers_transaction | pass (2a) |
| 3.1 | `pytest tests/test_task_workflow.py` | tests/test_task_workflow.py (unit, incl. test_task_workflow_replay) | pass (unit run: 372 passed, no failures) |
| 3.2 | unit test with 21 questions of 600 characters | tests/test_finish_task.py::test_questions_are_truncated, ::test_short_questions_are_unchanged | pass (unit run) |
| 3.3 | a task returning 20 questions of 500 characters passes; a seeded 65 KiB payload fails | tests/integration/test_history_payloads.py::test_twenty_long_questions_stay_under_the_limit (2a: `test_history_payloads.py .`); the session guard in tests/integration/conftest.py::history_payload_guard (did not fail 2a); tests/test_history_guard.py::test_a_seeded_65_kib_payload_fails and the rest of that file (unit run) | pass |
| 4.1 | `check_plans.py` and the link check pass | `uv run .github/scripts/check_plans.py` -> `Validated 8 implementation plan(s); 0 error(s)`; link check (lychee, CI) not run here | check_plans pass; link check not run (not in the AGENTS.md command list) |

## 5. Stack left running

`make workers-up` -> exit 0. The log shows a rebuild from this commit: `Image praxismesh-dsh:dev Built`, `Image praxismesh-worker:dev Built`, and every worker container `Healthy`.

`make status` -> exit 0:

```
orchestrator         Up 3 seconds (healthy)
worker-a             Up 4 seconds (healthy)
worker-b             Up 4 seconds (healthy)
worker-dsh-a         Up 3 seconds (healthy)
worker-dsh-b         Up 3 seconds (healthy)
addresses: Temporal 127.0.0.1:57233, UI http://127.0.0.1:58080, S3 http://127.0.0.1:58333, DB 127.0.0.1:55432
model endpoint: http://spark-01:8000 answers /v1/models
all services healthy
```

## Findings

- None against the committed code or documentation at this commit.
- Observation, not a defect: `uv run ruff check .` and `ruff format --check .` fail in this checkout only because of untracked scratch scripts that earlier checks left under `.verify/`.
- Blocked: gitleaks and actionlint (not installed). Not run: the offline link check. Blocked: the optional revert counter-check of the logger fix (permission denied).

Verdict: PASS. Every runnable check passed at 56c0170: unit 372 passed; integration 280 passed with no skips; make smoke 250 passed; test_refusals_are_logged_with_ids[dsh] passed after the migration and reference tests. gitleaks and actionlint are blocked (not installed) and the link check was not run.

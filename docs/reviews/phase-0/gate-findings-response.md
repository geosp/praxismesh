# Phase 0 gate: response to findings

Response to the [implementation review](implementation-review.md) (FAIL) and the [verification](verification.md) (fail) of `075791a`. Both reports are themselves unchanged. Fixes are on branch `fix/34-phase-0-gate-findings` (issue #34), for a targeted follow-up review under `docs/reviews/README.md` rule 6.

## Majors (implementation review)

| ID | Resolution | Where |
|---|---|---|
| F1 | **Fixed.** `infra/.env` accepts only plain `KEY=value` lines; `check-prereqs.sh` rejects quotes, spaces, `#`, `$`, `\` and backticks in values, naming the line. On that syntax, Make's `include` and Compose's `--env-file` read the same values. Tests: `test_value_syntax_rejected` (quoted `"s3cr#t"`, `a$b`, a space). | `infra/check-prereqs.sh`, `infra/.env.example`, `tests/integration/test_env_check.py`, spec "Configuration without committed secrets" |
| F2 | **Fixed.** The namespace job creates the namespace, or updates a differing retention, and fails, naming the step, if create or update fails (no swallowed error). It exits only once `describe` shows the configured retention. Test: `test_namespace_retention` asserts the TTL equals `TEMPORAL_RETENTION`. Observed: changed 72h to 96h and back, each applied. | `infra/temporal/namespace.sh`, `tests/integration/test_temporal.py`, spec scenario "Changed retention", decision log |
| F3 | **Fixed.** `make unhealthy-check` stops `db`, requires `make status` to exit non-zero naming `db` and the database smoke test to fail naming the database server, then restarts. CI's `stack` job runs it. | `tests/integration/unhealthy_check.py`, `Makefile`, `.github/workflows/ci.yml` |
| F4 | **Fixed.** `make restart-check` snapshots `schema_version` and `schema_update_history` in both Temporal databases plus the namespace config and info before and after a repeat `make up`, and fails if any differ. Observed: a repeated `setup-schema -v 0.0` logs "Skip version upgrade" and changes no rows. "Stopped" stacks are covered by the down/up sequence that follows. | `tests/integration/restart_check.py` |

## Nits (implementation review)

| ID | Resolution |
|---|---|
| F5 | Fixed: the namespace job's start error is no longer discarded; `docker wait` is limited to 120 s with a named timeout message. |
| F6 | Fixed: `try/finally` cleanup in the restart check (a lost object is reported as a FAIL line); the S3 smoke test's cleanup no longer hides the real failure. |
| F7 | Fixed: 30 s Workflow execution timeout and at most 3 Activity attempts. |
| F8 | Fixed: the init marker is a comment on database `postgres`, which only the superuser can change. |
| F9 | Fixed: `make down` and `make reset` work by project name alone, without `infra/.env`. |
| F10 | Fixed: Dependabot groups `temporalio/server` and `temporalio/admin-tools`. |
| F11 | Fixed: `test_migrations_at_head` says "run make migrate" when no migrations are applied. |
| F12 | Fixed: `make status` sends `VLLM_API_KEY` when set. |
| F13 | Fixed: 5 s connect timeout for model calls (120 s overall). |
| F14 | Fixed: spec wording now names the unreachable-endpoint test as the one exception; the test no longer falls back to `spark`, and an empty `VLLM_MODEL` fails with a message (and `check-prereqs.sh` requires it). |
| F15 | Fixed: every variable the stack and tests use must be non-empty in `infra/.env` (`VLLM_*` may be empty except `VLLM_MODEL`). |
| F16 | Fixed: `temporal` refused on `praxismesh` and `postgres` is tested; `CONNECT` on `postgres` is revoked from `PUBLIC`. `template1` keeps the default (nothing connects to it). |
| F17 | Decided, not changed: `0002` stays on the main chain (decision log). Its failure branch is not tested (it needs a database without `pg_search`). |
| F18 | Fixed: `test_ui_reachable` checks the UI on its host port. |
| F19 | Fixed: `test_make_up_runs_the_check` runs `make up` with a missing file. "Docker not running" stays untested (it would stop Docker on the runner). |
| F20 | Contested and aligned: the RFC (table) and task 1.5 define "exits 0" as the one-shot jobs' check; the spec now says so. |
| F21 | Fixed: `test_s3_rejects_wrong_secret`. |
| F22 | Fixed: fixed worker and client identity `phase0-smoke-worker`; fixture re-recorded; no hostname in the repository. |
| F23 | Contested: the RFC accepted replay only for the test fixture Workflow and no model in CI; product Workflows get replay and time-skipping tests from Phase 1. |
| F24 | No action (adequate for Phase 0, as the finding says). |
| F25 | Fixed: `make status` exits 1 when a service is unhealthy. |

## Verification findings

| ID | Resolution |
|---|---|
| V1 | Fixed: `pg_cron` is in `postgres`, not `template1` (overview and decision log). |
| V2 | Fixed: the overview gives all three measurements (275, 368-408 and 349 MiB) with dates instead of one number. |
| V3 | Fixed: the demo record says the script exits 1 and `make` exits 2. |
| V4 | Fixed: README "Trying the services by hand" documents commands for a prompt in each API style and an object put, get and delete; both were run. |
| V5 | Fixed: the full `docker compose -p … --env-file … -f …` command is documented; the case is also automated as `make unhealthy-check`. |
| V6 | Accepted: the UI evidence is the UI's HTTP API; the owner may add a screenshot. |
| V7 | Fixed: `COMPOSE_PROJECT_NAME` in `infra/.env` (default `praxismesh`); README "Several checkouts". |
| V8 | Fixed with F25. A stopped `db` also makes the hello Workflow test time out without naming the database; the database tests and `make status` name it, as the spec requires. |
| V9 | Fixed: the overview names `075791a` and this branch; its merge commit is the one to verify. |
| V10 | Accepted: observed once during implementation (the first init failed on the missing `CASCADE`); not repeatable without breaking init on purpose. |

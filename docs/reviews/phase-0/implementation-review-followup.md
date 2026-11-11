---
review: implementation
phase: 0
change: openspec/changes/phase-0-local-infrastructure
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 61c40ef50b5b062527d953f70eed3689254723be
docs_sha: n/a
diff_base: 075791ab7de4c39b7cd0d21f29fbd7dca7a1d597
session: fresh            # targeted follow-up (docs/reviews/README.md rule 6); the correction list was an explicit input
date: 2026-11-11
verdict: FAIL
reviewers:
  - { lens: contract (impl-reviewer), status: completed }
  - { lens: failure and retry (impl-reviewer), status: completed }
  - { lens: scope and composition (impl-reviewer), status: completed }
---

# Implementation review (targeted follow-up): Phase 0 local infrastructure

Gate mode, light tier, **targeted follow-up** under `docs/reviews/README.md` rule 6. `code_sha` is `61c40ef`, the squash merge of PR #38 on `main`, which fixes the findings of the gate at `075791a`. The diff base is `075791a`. Tracking issue: #34.

Scope:

- re-check every earlier finding (F1-F25, V1-V10) against the fix;
- look for new Blockers and Majors **only in text and code changed in `075791a..61c40ef`**.

## Inputs

Each reviewer (`impl-reviewer` agent, fresh context, read-only) received only the following:

- **Diff:** `git diff 075791ab7de4c39b7cd0d21f29fbd7dca7a1d597 61c40ef`.
- **Contract:**
  - the change's `proposal.md`, `design.md`, `tasks.md` and every file under `specs/`;
  - `docs/rfcs/phase-0-local-infrastructure.md`;
  - `docs/adr/0002-paradedb-as-postgresql-server.md`;
  - the newest (2026-11-11) rows of `docs/plan/decision-log.md`.
- **Guidance:** `AGENTS.md`, `PROJECT_PLAN.md` §2 and §8.
- **Earlier findings and correction list:** `docs/reviews/phase-0/implementation-review.md`, `docs/reviews/phase-0/verification.md`, `docs/reviews/phase-0/gate-findings-response.md`. These are given because this is a labeled targeted follow-up. The reviewers were told to judge every finding on the code and not to take the correction list's word.

`git status --porcelain` was empty on `main` at `61c40ef` when the review started.

The coordinator added one runtime observation, from the verification in this session: an "upgrade" run (R5). It is marked as such below.

## Earlier findings: status at `61c40ef`

Reviewer keys: **C** contract, **F** failure and retry, **S** scope and composition.

| ID | Earlier severity | Status | Evidence |
|---|---|---|---|
| F1 | Major | **partly resolved; residual Major R2** | `check-prereqs.sh:35` rejects quotes, whitespace, `#`, `$`, `\` and backticks in values and names the line. `test_value_syntax_rejected` fails without it. But comment lines are accepted unchecked, and a comment ending in `\` makes Make drop the next line while Compose reads it (C; reproduced in verification). See R2. |
| F2 | Major | **code resolved; test gap is Major R3** | `namespace.sh` creates the namespace, updates a differing retention, fails naming a failed create or update, and waits for the configured TTL. Verification observed 72h to 96h to 72h, and 5d. `test_namespace_retention` would also pass on the old code, because CI always starts fresh. The new spec scenario "Changed retention" has no automated test (C, F, S). |
| F3 | Major | **resolved** | `unhealthy_check.py` requires `make status` to exit non-zero naming `db`, and the database test to fail naming "database server (service db)". CI runs it (`ci.yml:118`). It would fail on either regression (C, S). Residual Nits are in R6. |
| F4 | Major | **resolved for a running stack** | `restart_check.py` snapshots `schema_version` and `schema_update_history` in both Temporal databases plus the namespace config and info around a repeat `make up`, and fails on any difference. Verification saw "Skip version upgrade" and PASS. The stopped-stack case and other gaps are in R7 (Nit). |
| F5 | Nit | resolved | Compose's error is shown; `timeout 120 docker wait`. Misleading message on an empty id: R13. |
| F6 | Nit | partly resolved | `try/finally` is in place, but cleanup suppresses only `ClientError`: R12. |
| F7 | Nit | resolved | 30 s execution timeout, `maximum_attempts=3`; the fixture shows both. Interaction: R15. |
| F8 | Nit | resolved (fresh volumes) | Marker on `postgres`, which only the superuser can change; verification confirmed `must be owner of database postgres` for the app role. Existing volumes: R5. |
| F9 | Nit | resolved, but opens R1 | `down` and `reset` drop `check` and use `-p` only. |
| F10 | Nit | resolved | Dependabot group `temporal`. |
| F11 | Nit | resolved | `to_regclass` hint in `test_migrations_at_head`. |
| F12 | Nit | resolved | `make status` sends the key. The README curl commands do not: R18. |
| F13 | Nit | resolved | `httpx.Timeout(120, connect=5)`. |
| F14 | Nit | resolved | Spec wording, no `spark` fallback, `test_model_name_configured`. |
| F15 | Nit | partly resolved | Required list extended. The new `COMPOSE_PROJECT_NAME` is not required or validated: R9. |
| F16 | Nit | resolved | Both directions tested; `postgres` CONNECT revoked. The `paradedb` database: R19. |
| F17 | Nit | **decided: accepted** | The decision log keeps `0002` on the main chain, with its reason. Residual: ADR-0002 still says "a plain PostgreSQL server can still run everything else", and the failure branch is untested (R16, Nit). |
| F18 | Nit | resolved | `test_ui_reachable` on the host port. |
| F19 | Nit | resolved | `test_make_up_runs_the_check`. "Docker not running" is untested; accepted. |
| F20 | Nit | **contested: accepted** | The RFC table and task 1.5 define "exits 0" as the jobs' check; the spec now says so ("Every long-running service … SHALL define a health check; the one-shot setup jobs count as healthy only by exiting 0"). |
| F21 | Nit | resolved | `test_s3_rejects_wrong_secret`. |
| F22 | Nit | resolved | Fixed identity `phase0-smoke-worker`. The old hostname remains in Git history only; not a credential. |
| F23 | Nit | **contested: accepted** | The RFC accepts replay-only for the fixture Workflow ("no timers, so no time-skipping test applies"), and plan §8 keeps real-model suites off hosted CI. No product Workflow or model caller exists yet. |
| F24 | Nit | no action; accepted | - |
| F25 | Nit | resolved | `make status` fails when a service is unhealthy. Effect on CI's log step: R4. |
| V1 | contradicted claim | resolved in the docs | Overview and decision log fixed; verification confirmed `pg_cron` only in `postgres`. A code comment still says otherwise (R16). |
| V2 | contradicted claim | resolved | Ranges with dates replace the single figure. |
| V3 | Nit | resolved | - |
| V4 | Nit | resolved | README "Trying the services by hand"; verification ran it as written. |
| V5 | Nit | resolved | The full command is documented; the demo record hard-codes `-p praxismesh` (R16). |
| V6 | Nit | accepted | - |
| V7 | Nit | **partly resolved; regression R1** | The project name is configurable, but the fallback and precedence reintroduce the data-loss path. |
| V8 | Nit | resolved | With F25. The hello test still times out without naming the database; accepted. |
| V9 | Nit | resolved | - |
| V10 | Nit | accepted | - |

## New findings in the changed code

Duplicates across reviewers are merged.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| R1 | **Major** | C, F, S | `Makefile:16-21, 61-65`; `infra/.env.example` (`COMPOSE_PROJECT_NAME=praxismesh`) | The project-name override can destroy another checkout's data, which is the hazard V7 raised. **(a)** `down` and `reset` no longer depend on `check`, and `COMPOSE_PROJECT_NAME ?= praxismesh`. In a second checkout with no `infra/.env` (fresh worktree, file moved aside, mistyped `ENV_FILE`), `make reset` runs `docker compose -p praxismesh down --volumes`, with no warning. At `075791a`, `reset: check` refused. **(b)** A Make file assignment overrides the environment, so `COMPOSE_PROJECT_NAME=other make reset` (the way the earlier verification isolated itself) still targets the file's name. Verified by dry run: `make -n reset ENV_FILE=/nonexistent` gives `-p praxismesh`; `COMPOSE_PROJECT_NAME=other make -n reset` gives the file's name. The overview's claim that `down` and `reset` "run even when `infra/.env` is missing" is the behavior that causes it. | Fix: a test that `make -n reset ENV_FILE=<absent>` refuses (or requires an explicit name) and that names the project. Then require an explicit project name when the env file is absent, and echo the project before `down --volumes`. | open |
| R2 | **Major** | C (S, F: Nit-level parser gaps) | `infra/check-prereqs.sh:35` (comments accepted as `#.*`); `Makefile:9-12` | Residual F1. Spec: "`infra/.env`, written as plain `KEY=value` lines that Make and Docker Compose read identically; `make up` SHALL reject any other syntax, naming the line". GNU Make continues a comment that ends in `\` onto the next line; Compose and the check do not. Reproduced in verification: with `# …\` before `TEMPORAL_RETENTION=96h`, the check passes, Make sees the variable as undefined, and Compose applies 96h. Before `COMPOSE_PROJECT_NAME=…`, `make -n reset` resolves to `-p praxismesh` (compounds R1). Related key collisions are accepted too: `ENV_FILE=…`, `SHELL`, `MAKEFLAGS` in `infra/.env` change Make itself. | Fix: add a comment ending in `\` (and a reserved key) to `test_value_syntax_rejected`, which fails today. Then reject such comment lines and restrict keys to the known list. | open |
| R3 | **Major** | S (C, F: test gap noted under F2) | spec `local-stack/spec.md` "Changed retention"; `infra/temporal/namespace.sh` update branch | The scenario added by this diff ("updates the namespace to the configured retention, or exits non-zero naming the failure") has no automated test. `test_namespace_retention` passes on the old code too. The update branch and its named failure are covered only by a manual run, which is the pattern rated Major for F3. The behavior itself works: verification observed 72h to 96h to 72h, 5d, and a named job failure for `1s`. | Fix: in `restart-check` (or a new check), run `make up TEMPORAL_RETENTION=96h`, assert the described TTL, then restore and assert 72h. Optionally assert that a server-rejected value fails naming the update. | open |
| R4 | Nit | C, F, S (S: Major) | `.github/workflows/ci.yml:121` | Stack logs on failure: `make status; docker compose … logs`. GitHub runs bash with `-e`, and `make status` now exits non-zero exactly when the stack is unhealthy, so the logs never print. Reproduced in verification (0 log lines with `db` stopped). Rated Nit: it loses CI diagnostics but breaks no contract promise. The missing `-p` resolves correctly because Compose reads `COMPOSE_PROJECT_NAME` from `--env-file` (observed). | Fix: `make status \|\| true`. | open |
| R5 | Nit | F (F: Major), C, S, confirmed by the coordinator | `infra/db/healthcheck.sh`; `infra/db/init.sh` | A `pgdata` volume initialized at `075791a` carries the marker on `praxismesh`. After updating to `61c40ef` and recreating the containers, `db` never becomes healthy. **Coordinator observation:** a stack started at `075791a` (project `praxismesh-upg`), then the checkout moved to `61c40ef`, `make down`, `make up`: `make up` failed after the 180 s wait with "If database init failed or its passwords changed, run 'make reset'", which deletes data. Neither cause applies. The `postgres` REVOKE is also missing on such volumes. No upgrade note exists. Rated Nit, consistent with F8: Phase 0 data is disposable, the contract makes no cross-version promise, and the owner's main volume already carries the new marker (checked read-only). | Fix: document the one-time step (`COMMENT ON DATABASE postgres …; REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;`) or `make reset`, or accept the legacy marker. | open |
| R6 | Nit | C, F, S | `tests/integration/unhealthy_check.py:55-58, 41-50` | Recovery (`compose start db`, `make up`) ignores exit codes, so a stack that does not come back still prints PASS. The check runs one database test, not `make smoke` as the scenario says. | Fix | open |
| R7 | Nit | C, F, S | `tests/integration/restart_check.py` | "Repeat start … on a running or stopped stack": the stopped case is not snapshot-compared (and `down` removes containers rather than stopping them). Nothing asserts that the jobs actually re-ran. `config_version` is not compared, so a same-value `namespace update` on every start would pass. | Fix | open |
| R8 | Nit | F, verification | `infra/temporal/namespace.sh`; `Makefile:55-57` | `describe` errors are discarded and treated as "absent". A transient failure, or a non-not-found error, gives a misleading message ("creating failed" while the namespace exists, or a 30 s timeout instead of an update), with no retry. `make up` names only the job ("exited with 1; see: make logs"), and `make logs` follows forever. Fails closed. | Fix | open |
| R9 | Nit | C, F, S | `infra/check-prereqs.sh`; `Makefile:16-21`; `unhealthy_check.py:20` | `COMPOSE_PROJECT_NAME=` (empty) passes the check. `?=` does not apply, so `-p` swallows the next token (`--env-file` or `down`). Uppercase names pass the check but Compose rejects them. Renaming orphans the old project's containers and volumes. | Fix | open |
| R10 | Nit | C, S, verification | `Makefile:10` (`include` at parse time) | A line Make cannot parse (`KEY value`) stops every target with Make's "missing separator" before `check-prereqs.sh` runs, including `down` and `reset` (contrary to the Makefile comment and the overview). `KEY http://x` becomes a Make rule and the default goal. Make does name the line; fails safe. | Fix (wording or ordering) | open |
| R11 | Nit | C, S | README "Trying the services by hand" (`set -a; . infra/.env`); `Makefile:18, 21` (`-p` unquoted) | The shell is a further parser. Accepted values with `; & \| < > ( ) ~` are interpreted when sourced, so the snippet can use a different secret than Compose did, and `-p x;cmd` would run `cmd`. | Fix (reject shell metacharacters, or quote) | open |
| R12 | Nit | C, F | `tests/integration/restart_check.py:120-123`; `tests/integration/test_blob_store.py` | Cleanup suppresses only `ClientError`. With the stack down after a failed `make up`, `EndpointConnectionError` from `finally` replaces the real error, and the stack is left down. | Fix | open |
| R13 | Nit | C, F, S | `Makefile:55-56` | An empty container id or a failing `docker wait` is reported as "did not finish within 120 s". `timeout` is GNU coreutils (absent on stock macOS; the host platform is not stated). | Fix | open |
| R14 | Nit | F, S, verification | `infra/check-prereqs.sh` (retention regex) | `1s` or `30m` passes the check but the server rejects it ("A valid retention period is not set on request"), surfacing only after startup as a failed job (observed). Very large values overflow shell arithmetic in `namespace.sh`. | Fix | open |
| R15 | Nit | S | `tests/support/stack.py` (30 s execution timeout); `tests/support/hello.py` (3 attempts × 10 s) | Three attempts plus backoff take about 33 s, so the Workflow timeout ends the run before the third attempt. Harmless, but the two documented bounds disagree. | Fix | open |
| R16 | Nit | C, F, S | `tasks.md` 1.4 and 6.1; RFC line 80; ADR-0002 line 34; `infra/db/init.sh:8-9`; overview "One Docker Compose project, `praxismesh`"; `docs/demos/phase-0.md` (`-p praxismesh`) | Contract and comment text still describe the old behavior: an existing namespace left unchanged; README documents `temporal operator namespace update`; a changed retention not applied; plain PostgreSQL can run everything (F17); `pg_cron` in `template1` (V1 residue in a changed file); a fixed project name; a hard-coded `-p` that would stop another checkout's `db` if copied. The decision log supersedes the behavior items. | Fix (docs) | open |
| R17 | Nit | C, S | `tests/integration/test_env_check.py` | The syntax tests call the script, not `make up`. They don't assert the line number, and each case is caught by an earlier character, so dropping `#` or `\` from the class would go unnoticed. | Fix | open |
| R18 | Nit | S, verification | README "Trying the services by hand" | The curl commands send no `Authorization` header, so they fail against a key-protected endpoint (the DGX Spark endpoint needs none). | Fix | open |
| R19 | Nit | verification (as-built) | `infra/db/init.sh` (REVOKE list) | ParadeDB's bootstrap database `paradedb` keeps PUBLIC CONNECT, and both application roles can connect to it (observed). The isolation section does not mention it. Holds no PraxisMesh data. | Fix (revoke, or document) | open |

## Reviewer status

| Reviewer | Status |
|---|---|
| Contract | completed |
| Failure and retry | completed |
| Scope and composition | completed |

## Verdict

**FAIL.** No Blockers, and all three reviewers ran. Of the earlier Majors:

- F3 is resolved.
- F4 is resolved for the scenario it raised.
- F2's code is resolved, but its new scenario is untested (R3).
- F1 leaves a residual parser divergence (R2).

The diff also introduces a new Major, R1 (project-name fallback and precedence). Per `docs/reviews/README.md` rule 5, every Major must be fixed or contested with evidence before a PASS. Under rule 6 the findings go back to the implementer.

## Open items

- **Majors:** R1, R2, R3. Fix or contest, then re-check in a new session (targeted, as here).
- **Nits:** R4-R19, 16 in all. They do not block; the implementer decides.
- **Accepted or contested-accepted:** F17, F20, F23, F24, V6, V10.

---
review: implementation
phase: 0
change: openspec/changes/phase-0-local-infrastructure
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: f0337f1cdde68c104fecbf748739ca9b4cb72125
docs_sha: n/a
diff_base: a6e0629
session: fresh            # final narrow follow-up (docs/reviews/README.md rule 6); the correction list was an explicit input
date: 2026-11-11
verdict: FAIL
reviewers:
  - { lens: contract (impl-reviewer), status: completed }
  - { lens: failure and retry (impl-reviewer), status: completed }
  - { lens: scope and composition (impl-reviewer), status: completed }
---

# Implementation review (final narrow follow-up): Phase 0 local infrastructure

This is a gate-mode, light-tier review, run as the **final narrow follow-up** under `docs/reviews/README.md` rule 6.

- **Code reviewed:** `code_sha` `f0337f1`, the squash merge of PR #40 on `main`. PR #40 fixes the findings of the follow-up at `61c40ef`.
- **Diff:** `a6e0629..f0337f1`.
- **Tracking issue:** #34.

The owner fixed the scope:

- **Re-check only these findings:**
  - R1 / VF2: `make down` and `make reset` act on the wrong project.
  - R2 / VF1: Make and Compose read `infra/.env` differently.
  - R3: no test for "Changed retention".
  - R4 / VF3: the CI failure step prints no logs.
  - R5 / VF10: a volume from before PR #38 never becomes healthy.
- **Look for new Blockers and Majors only in the code paths those fixes changed:**
  - `Makefile`;
  - `infra/check-prereqs.sh`, `infra/db/healthcheck.sh` and `infra/temporal/namespace.sh`;
  - `tests/support/status.py`;
  - `tests/integration/restart_check.py`, `unhealthy_check.py` and `test_env_check.py`;
  - the CI step "Stack logs on failure".
- **Report Nits only about R1-R5 themselves.**
- **Accept the owner's decisions in the decision log.**

## Inputs

Each reviewer was an `impl-reviewer` agent with a fresh, read-only context. Each received only the following:

- **Diff:** `git diff a6e0629 f0337f1`.
- **Contract:**
  - the change's `proposal.md`, `design.md`, `tasks.md` and every file under `specs/`;
  - `docs/rfcs/phase-0-local-infrastructure.md`;
  - `docs/adr/0002-paradedb-as-postgresql-server.md`;
  - the two newest (2026-11-11) rows of `docs/plan/decision-log.md`, as owner decisions.
- **Guidance:** `AGENTS.md`; `PROJECT_PLAN.md` §2 and §8.
- **Earlier findings and correction list:** `implementation-review-followup.md`, `verification-followup.md` and `followup-findings-response.md`. These were given because this run is labeled a targeted follow-up. The reviewers were told to judge each finding on the code.
- **The scope above.**

`git status --porcelain` was empty on `main` at `f0337f1` when the review started.

The coordinator re-ran two reviewer claims that rested on reader behaviour the reviewers could not observe read-only (N2, N3). The re-runs used the disposable verification checkout (see `verification-followup-2.md`) and are marked "confirmed by run" below.

## Earlier findings: status at `f0337f1`

Reviewer keys: **C** contract, **F** failure and retry, **S** scope and composition.

| ID | Earlier severity | Status | Evidence |
|---|---|---|---|
| R1 / VF2 | Major | **Resolved as raised. New Major N1 arises from the fix.** | `Makefile:37` resolves the name with `check-prereqs.sh --project-only`. `Makefile:66, 69-70` run `name=$(PROJECT) && … docker compose -p "$name" …`, so a failed lookup never reaches Docker. `check-prereqs.sh:31-44` takes the name from the shell, else from the file. It refuses an empty name and checks it against `^[a-z0-9][a-z0-9_-]*$`. The `praxismesh` fallback is gone, and `reset` echoes the project before deleting. Tests: `test_reset_refuses_without_project_name`, `test_bad_project_name_rejected` and `test_shell_project_name_wins`. Verification observed the refusal with `make reset ENV_FILE=/nonexistent.env` (C, F, S). |
| R2 / VF1 | Major | **Resolved as raised. Residual Major N2.** | Make no longer `include`s the file (`Makefile:4-12`). Compose reads it with `--env-file`; tests, migrations and status read it with `uv run --env-file`. `check-prereqs.sh:74` rejects any line ending in `\`, comments included. `:78` accepts only known keys, so `MAKEFLAGS`, `SHELL` and `ENV_FILE` are refused. `:81` restricts values to `A-Za-z0-9._:/@%+,=-`. The tests run through `make up` and assert the line number: `test_comment_continuation_rejected`, `test_unknown_key_rejected` and `test_value_character_rejected` (12 characters). Duplicate keys are still accepted and read differently (N2) (C, F, S). |
| R3 | Major | **Resolved.** Nits in N9. | `restart_check.py:136-142` runs `make up` with `TEMPORAL_RETENTION=96h` and requires DescribeNamespace to show 345600 s. A second `make up` must restore the configured value. Without the update branch (`namespace.sh:57-62`) the first assertion fails. CI runs it (`ci.yml:117`). Verification: `restart-check: PASS (… retention change applied and restored …)` (C, F, S). |
| R4 / VF3 | Nit | **Resolved.** | `ci.yml:121-123` runs `make status \|\| true` and then the logs command. Verification ran the step under `bash -e` with `db` stopped: exit 0, `unhealthy or stopped: db`, and 676 log lines (C, F, S). |
| R5 / VF10 | Nit | **Resolved for health. Residual Nits N10 and N11.** | `healthcheck.sh:11-15` accepts the marker on `postgres` or `praxismesh`. Verification: a `db` volume created at `075791a` became healthy at `f0337f1` after its container was recreated. However, `make smoke` then fails two isolation tests on that volume (N11) (C, F, S). |

## New findings in the changed code

Duplicates across reviewers are merged.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| N1 | **Major** | C (F: noted as R1-d) | `infra/check-prereqs.sh:32` (shell value first); `Makefile:37, 66-70`; README "Trying the services by hand" (`set -a; . infra/.env; set +a`) and "Several checkouts" ("or set in the shell") | The fix made a shell `COMPOSE_PROJECT_NAME` win over the file. The README tells users to source `infra/.env` into their interactive shell, which exports `COMPOSE_PROJECT_NAME`. Scenario: the user sources checkout A's file (`praxismesh`), then runs `make reset` in checkout B from the same shell. Checkout B's file says `praxismesh-b`, but the command runs `docker compose -p praxismesh down --volumes` and deletes A's data. `make up` in B likewise reuses A's project and volumes. B's file passes the check, which validates only the file. The only guard is an echo. At `61c40ef` the file won, so this sequence was safe. **Confirmed by run:** `COMPOSE_PROJECT_NAME=praxismesh sh infra/check-prereqs.sh --project-only <B's env>` prints `praxismesh`, and the full check exits 0. This is the data-loss class of R1 and V7, reached through a documented step. | Fix. Test: a shell value that differs from the file's value must make `--project-only` (and `make reset`) refuse, naming both values, unless an explicit override is given. Optionally run the README snippet in a subshell. | open |
| N2 | **Major** | S (F: Major if confirmed; confirmed by run) | `infra/check-prereqs.sh:70-85` (no duplicate check) and `value()` (last occurrence); `Makefile:11-12`; `tests/support/status.py`; `restart_check.py` (nested `make down`/`up`) | Spec, Configuration: `infra/.env` holds "plain `KEY=value` lines that every reader (Docker Compose, `uv run --env-file`) reads identically; `make up` SHALL reject any other syntax, naming the line". A repeated key passes the check, but the readers disagree: Compose takes the **last** value, and `uv run --env-file` takes the **first**. **Confirmed by run:** an env file with a second `DB_PORT=45432` and `TEMPORAL_RETENTION=96h` passes the check. Compose publishes `db` on 45432 and gives the namespace job 96h, while uv gives `35432 72h`. With a second `COMPOSE_PROJECT_NAME=praxismesh-dup`, Compose and `--project-only` resolve `praxismesh-dup`, but uv, and Compose run under uv (as `make status` runs it), resolve the first name. Consequences: migrations and smoke tests connect to another port, which may be another checkout's database. `make status` reports another project. `restart-check`'s nested `make down`/`make up` inherit the uv-loaded name and act on another project, which reopens R1. | Fix. Test: append a repeated key to the example in `test_env_check.py` and require `make up` to fail, naming the repeated line. Optionally pass one resolved `-p` everywhere. | open |
| N3 | Nit | C, F, S (confirmed by run) | `check-prereqs.sh:32-33`; `Makefile:11` (no `-p` for `up`) | A variable that is exported but empty, `COMPOSE_PROJECT_NAME=`, makes `--project-only` fall back to the file's name, and the full check passes. Compose ignores the empty value and falls back to the compose directory's name, `infra`. **Run:** `--project-only` gives `praxismesh-v2`, while `docker compose config` gives name `infra`. So `make up` would start project `infra`, which every checkout shares, while `make down` and `make reset` act on another name. Rated Nit: an empty exported variable is unusual, and `reset` does not delete another checkout's named project. | Fix: treat set-but-empty as an error, or pass `-p` everywhere | open |
| N4 | Nit | C, F | `check-prereqs.sh` (validates the file only); `Makefile:7` comment | Shell overrides, which win for Compose and uv, are never validated. `TEMPORAL_RETENTION=30m make up` bypasses the one-day rule and fails later as a job error. Fails closed; shell precedence is by design. | Fix or accept | open |
| N5 | Nit | S | `Makefile:9` (`ENV_FILE ?=`), `:36` comment | `ENV_FILE` exported in the shell, pointing at another project's env file, makes `make reset` act on that project, which contradicts the comment "they never act on another checkout's stack". | Fix (wording) or accept | open |
| N6 | Nit | C, F, S | `test_env_check.py` (`test_reset_refuses_without_project_name` and the `make up` negative tests) | The tests run a real `make reset` and `make up`. Under `make smoke`, uv has loaded the developer's `COMPOSE_PROJECT_NAME` into the environment. If the refusal or the check regressed, the test itself would run `down --volumes` or `up` on the developer's stack. | Fix: `DOCKER_HOST=unix:///nonexistent`, or a docker stub on `PATH` | open |
| N7 | Nit | C, F, S | `test_env_check.py:136-145`; `restart_check.py` | No test checks that `make up` and `make down`/`reset` resolve the same project. `test_shell_project_name_wins` calls the script only. `restart-check`'s `make down` would pass even if it acted on another project. | Fix | open |
| N8 | Nit | C, F, S | `infra/docker-compose.yml:8` | The comment still says "The project name comes from the Makefile (COMPOSE_PROJECT_NAME, default praxismesh)", which contradicts the R1 fix. The file is outside the diff, but the comment concerns R1. | Fix (comment) | open |
| N9 | Nit | C, F, S | `restart_check.py:43, 136` | R3 residuals: (a) if the configured retention is already `96h` or `4d`, no update runs and the check still passes; (b) the scenario's "or exits non-zero naming the failure" branch is untested; (c) the change comes from the shell, not from `infra/.env` as the scenario says (equivalent for Compose). | Fix (a); (b) optional | open |
| N10 | Nit | C, F, S | `infra/db/healthcheck.sh:11-15` | The legacy marker is accepted on `praxismesh` for **every** volume. The app role owns `praxismesh` and can set that comment. On a volume whose init failed partway, it could make `db` report healthy. This is what F8's move to `postgres` prevented. The overview's "only the superuser can change it" now overstates the guarantee. | Fix (accept the legacy marker only when `postgres` carries no marker and the volume predates the move) or document | open |
| N11 | Nit | F, S, C (confirmed by run) | `infra/db/healthcheck.sh`; README "When things go wrong" ("no reset is needed after updating") | A volume created at `075791a` lacks `REVOKE CONNECT` on `postgres` (and every volume created before `f0337f1` lacks it on `paradedb`). **Run:** after the upgrade, `db` was healthy and `make migrate` applied, but `make smoke` gave `2 failed, 41 passed, 4 skipped`: `test_app_role_refused_elsewhere[postgres]` and `test_temporal_role_refused_elsewhere[postgres]`. The README claim is therefore wrong for such volumes. | Fix: document the one-time `REVOKE CONNECT ON DATABASE postgres, paradedb FROM PUBLIC;`, or narrow the claim | open |
| N12 | Nit | C, F, S | `ci.yml:121-123`; `healthcheck.sh` | R4 and R5 have no automated regression test. Both were reproduced by hand in verification. | Accept or fix | open |

One reviewer assumption was checked and closed. `uv run --env-file` does not override a variable already set in the environment: `TEMPORAL_RETENTION=96h uv run --env-file infra/.env` printed `96h`. R3's "configured" value therefore reads correctly.

## Reviewer status

| Reviewer | Status |
|---|---|
| Contract | completed |
| Failure and retry | completed |
| Scope and composition | completed |

## Verdict

**FAIL.** All three reviewers ran, and no Blocker was found. R1-R5 are each resolved as raised. Two new Majors remain open in the fixes' own code paths:

- **N1:** a shell project name, exported by the README's own snippet, sends `make reset` to another checkout.
- **N2:** a repeated key is read differently by Compose and uv, which breaks the spec's "every reader reads identically" and reopens R1.

Per `docs/reviews/README.md` rule 5, every Major must be fixed or contested with evidence before a PASS.

## Open items

- **Majors:** N1 and N2.
- **Nits:** N3-N12, 10 in all. They do not block.

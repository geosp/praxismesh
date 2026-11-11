---
review: design
phase: 0
change: openspec/changes/phase-0-local-infrastructure
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 7da1b8b2bc1390a735427751458cceea1e859de8
docs_sha: n/a
diff_base: n/a
session: fresh            # targeted follow-up (docs/reviews/README.md rule 6) of docs/reviews/phase-0/design-review.md
date: 2026-11-11
verdict: FAIL
reviewers:
  - { lens: follow-up F1-F13 (design-reviewer), status: completed }
  - { lens: follow-up F14-F25 (design-reviewer), status: completed }
  - { lens: new issues introduced or missed (design-reviewer), status: completed }
---

# Design review (targeted follow-up): Phase 0 local infrastructure

**This is a targeted follow-up** under `docs/reviews/README.md` rule 6. It is not a full independent re-review. The reviewers received the original report, `docs/reviews/phase-0/design-review.md` (gate mode, commit `83e0ae3`, verdict FAIL), as their correction list. They checked each of F1-F25 against the revised design and then looked for new Blockers and Majors.

## Inputs

Revision `7da1b8b2bc1390a735427751458cceea1e859de8` (branch `docs/phase-0-design`). The working tree was clean (`git status --porcelain` empty). All paths below are under `/home/geo/develop/praxismesh`.

- **Change files:** `openspec/changes/phase-0-local-infrastructure/` (`proposal.md`, `design.md`, `tasks.md`, `specs/dev-environment/local-stack/spec.md`, `specs/persistence/app-database/spec.md`, `specs/storage/blob-store/spec.md`, `specs/inference/model-endpoints/spec.md`)
- **Design docs:** `docs/rfcs/phase-0-local-infrastructure.md`, `docs/adr/0002-paradedb-as-postgresql-server.md`
- **Correction list:** `docs/reviews/phase-0/design-review.md`, given only because this is a targeted follow-up
- **Guidance and plan files:** `AGENTS.md`, `PROJECT_PLAN.md`, `docs/plan/phases/phase-0.md`, `docs/plan/design-decisions.md`, `docs/plan/decision-log.md`, `docs/plan/schemas.md`
- **Repository files the reviewers read:** `pyproject.toml`, `.github/workflows/ci.yml`, `.github/scripts/ci_gate.py`, `tests/test_ci_gate.py`, `.github/dependabot.yml`, `docs/spikes/harness-vllm.md`, `README.md`, `docs/release.md`, and `git diff 83e0ae3 7da1b8b`

All three lenses ran as `design-reviewer` agents.

`openspec validate phase-0-local-infrastructure --strict` passes: "Change 'phase-0-local-infrastructure' is valid".

The coordinator checked the new Majors directly against the repository (`ci.yml:246-248`, `ci_gate.py:31-32`, `PROJECT_PLAN.md:156`, RFC:58).

## Fresh reader paraphrase

Not part of this targeted follow-up. The fresh-reader lens ran in the original review, and that paraphrase stands. A full gate re-review would run it again.

## Status of the original findings

RFC = `docs/rfcs/phase-0-local-infrastructure.md`. Paths for tasks, specs and the proposal are relative to `openspec/changes/phase-0-local-infrastructure/`.

| ID | Orig. sev. | Status | Evidence | What remains |
|---|---|---|---|---|
| F1 | Major | Resolved | RFC:61 adds a `temporal-namespace` job. RFC:80: "creates namespace `TEMPORAL_NAMESPACE` … retention `TEMPORAL_RETENTION` (default `72h`) … If the namespace already exists, it succeeds without changes". RFC:83: "**Requirement: `make up` succeeds when run twice in a row.**" Also tasks 1.3, 1.4 and 1.6, and local-stack spec "Repeat start". | Nit: see N7 (namespace readiness, retention drift). |
| F2 | Major | Partly resolved (remainder Nit) | RFC:75: "`CREATE EXTENSION IF NOT EXISTS pg_search` in `praxismesh` only, as the superuser". RFC:88: the migration "only **checks** … Downgrading it is a no-op". | Privileges are fixed. The template half is still open. Nothing records whether the image's own bootstrap creates extensions in `template1`, and so in Temporal's databases. Task 4.5 checks only `praxismesh`. |
| F3 | Major | Resolved | RFC:120-128 adds `make restart-check`: "`down`, then `up`; `migrate`, which must make no changes … assert that the Workflow is still listed … and the object reads back the same". The CI job runs it (RFC:132). Also tasks 4.7 and 5.1. | — |
| F4 | Major | **Partly resolved; race still open (Major)** | RFC:58: "`pg_isready` **and** a query proving the three databases and two roles exist". RFC:71: "`set -e` and `psql -v ON_ERROR_STOP=1`". RFC:77: "a half-failed init or a changed password needs `make reset`". | The init-once half is resolved. The health-check race is not. The check still does not use TCP. The databases and roles it looks for are created first, before REVOKE, `CREATE EXTENSION` and the entrypoint's restart from the socket-only temporary server to the real one. The check can therefore pass while `db:5432` refuses TCP connections. `temporal-schema` then fails intermittently on a clean volume, which is CI's case. Merged with N3 from this round. |
| F5 | Major | Resolved | RFC:161: "If it is **set but unreachable**, they **fail**, naming the endpoint. Phase 0 closes only with a recorded run in which the model tests passed against the Sparks." Also model-endpoints spec and task 4.4. | Nit: "unset" against "empty" (see N5). |
| F6 | Major | Partly resolved (remainder Nit) | RFC:175, demo: "`docker compose stop db`, then `make status` names `db` as unhealthy and `make smoke` fails naming the database as unreachable". The local-stack spec was rewritten to match. | The demo now has a working failure case. The "Unhealthy service" scenario still has no automated test. The traceability table (RFC:143) maps it only to the `make status` command. |
| F7 | Major | Resolved | RFC:99 adds `VLLM_MODEL` ("must not contain a `/`") and `VLLM_API_KEY`. RFC:67 explains the model registry and points to the launch flags in `docs/spikes/harness-vllm.md`. `vllm-local` is deferred and recorded as a deviation (task 6.3). | — |
| F8 | Major | Resolved | RFC:113-117: runtime and dev groups, `boto3-stubs[s3]`, "`addopts = -m "not integration"` … `make smoke` runs `pytest -m integration`". Tasks 0.1 and 0.2 come before section 3. | The dependency list brings in a new Major (N1, psycopg license). Nit: replacing `addopts` drops the existing `-ra` (N6). |
| F9 | Major | Resolved | RFC:137-148: a plan → OpenSpec → acceptance-test table covering phase-0.md:9-15. | Nit: gaps in the table (N8). |
| F10 | Major | Resolved | RFC:88: "Alembic in `common/persistence/migrations/`, per plan §6". Tests are in `tests/integration/` (RFC:117). | Nit: the location of `alembic.ini` is unstated. |
| F11 | Major | Resolved | RFC:118: "an **in-process Temporal worker** on a unique task queue per run … Phase 0 has no worker container". | — |
| F12 | Major | Resolved | RFC:103: "CI copies `.env.example` to `.env`. The placeholder passwords are local to the runner and are not secrets." | — |
| F13 | Major | Resolved | RFC:29-31 adds glosses for §4.16 and for the DGX Spark pair ("one base URL … served name `spark`"). | — |
| F14 | Nit | Resolved | RFC:135: "Dependabot gets a `docker-compose` ecosystem entry". Task 5.3. | — |
| F15 | Nit | Resolved | RFC:74: "`REVOKE CONNECT ON DATABASE … FROM PUBLIC` on all three". Task 1.2 and the app-database spec. | — |
| F16 | Nit | Partly resolved | The app-database spec now cites "Plan decision log 2026-11-11, ParadeDB; ADR-0002". | ADR-0002 is still `status: proposed` with `issue: null`. Nothing states that approving this design accepts the ADR. |
| F17 | Nit | Resolved | Task 6.1: "…and the ParadeDB AGPL-3.0 note". | — |
| F18 | Nit | Resolved | RFC:94: "`.env` lives at the **repository root** … `docker compose --env-file .env -f infra/docker-compose.yml`". | The fix moves `.env.example` away from the plan's layout without a recorded decision (N2). |
| F19 | Nit | Partly resolved | RFC:118: "a replay test against a history recorded in the test, which runs with the unit tests". Task 4.2. | There is no time-skipping test and no exemption from it (§8). The replay test's placement contradicts the task heading (N6). |
| F20 | Nit | Resolved | RFC:63 names `chrislusf/seaweedfs:4.53`. RFC:60 gives a gRPC probe fallback. RFC:83 uses `--wait --wait-timeout 180` and has a fallback. | Verification at implementation is still pending (plan §2). |
| F21 | Nit | Resolved | RFC front matter `issue: "#34"`. Issue #34 is open. | — |
| F22 | Nit | Resolved | RFC:89 uses "a uniquely named bucket per run". RFC:118 uses a unique task queue and Workflow ID. | — |
| F23 | Nit | Partly resolved | RFC:160: "under **6 GB** … `docker stats` is recorded in `docs/demos/phase-0.md`. Rethink trigger: over 6 GB at idle". | The §7.1 review-cost trigger is not restated. Demo step 6 does not say the reading is taken at idle. |
| F24 | Nit | Resolved | RFC:133 names both edits (`REQUIRED_JOBS`, `needs:`). RFC:134 states the cost. | The fallback it states conflicts with the gate (N4). |
| F25 | Nit | Partly resolved | RFC:99 now reads "must not contain a `/`". RFC:65 names the volumes. Glosses added. | proposal.md:13 still lists only `make up`, `make down` and `make migrate`, while RFC:107 has eight targets. `tier`/`size`, `pg_search` and "documentation skill" still have no gloss in the RFC. |

Summary: of the 13 original Majors, 10 are resolved and 3 partly resolved. F2 and F6 now hold only Nits, but F4's health-check race is still open at Major level. None of F1-F25 was contested.

## Findings (new in this round)

Reviewer: NI = the new-issues lens. Where a lens raised a remainder of an original finding, it is merged into the table above (N3 into F4).

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| N1 | Major | NI (coordinator confirmed) | RFC:114; tasks.md:5 (0.1); proposal.md:40 | **The new dependency fails a required CI check.** The design adds `psycopg[binary]` 3 as a runtime dependency. psycopg 3 and psycopg-binary are licensed LGPL-3.0-only. The `licenses` job's dependency review allows only "Apache-2.0, MIT, MIT-0, BSD-2-Clause, BSD-3-Clause, ISC, PSF-2.0, Python-2.0, MPL-2.0, Unlicense, 0BSD, CC0-1.0, Zlib" (`.github/workflows/ci.yml:246-248`). `licenses` is in `REQUIRED_JOBS` (`.github/scripts/ci_gate.py:31`), so the PR for task 0.1 turns `ci-ok` red. The original design (83e0ae3 RFC:71) already listed `psycopg` 3, so this was missed in the first round rather than introduced by the revision. | Fix, either: (a) use a permissively licensed driver that SQLAlchemy and Alembic support (`pg8000`, BSD-3-Clause; or `asyncpg`, Apache-2.0); or (b) keep psycopg with an owner decision in the decision log, a justified allowlist entry in `ci.yml` and a note in `docs/release.md`. Check the license tree of the new lock at implementation. | open |
| N2 | Major | NI (coordinator confirmed) | RFC:94; tasks.md:19 (2.1); local-stack spec:39 | **Unrecorded layout deviation.** Plan §6 places the file in `infra/`: "`/infra  docker-compose.yml (…), .env.example`" (`PROJECT_PLAN.md:156`). The F18 fix moves `.env.example` to the repository root. Neither the RFC nor task 6.3 (which does record the vLLM deviation) records the move, and the decision log has no entry for it. This is the same class of issue as F10: §4.16 lets the plan govern until it is changed by a reviewed PR with a decision-log entry. The fix is cheap. | Fix, either: (a) keep `.env.example` and `.env` in `infra/`, with the Makefile using `--env-file infra/.env`; or (b) add a decision-log entry and update plan §6, and list the move alongside the vLLM deviation in task 6.3. | open |
| N4 | Nit | NI | RFC:134; tasks.md 5.2 | The fallback "the job runs only on PRs that touch `infra/` …" would make `ci-ok` fail on every other PR. `ci_gate.py` treats a skipped job as a failure unless it is in `PR_ONLY_JOBS`, and `tests/test_ci_gate.py` enforces this. | Fix: filter inside the job (a no-op step that exits 0), or name the `ci_gate.py` and test changes the fallback needs. | open |
| N5 | Nit | NI | RFC:94, 99, 132, 161; model-endpoints spec:24; task 4.4 | Nothing says how `.env` values reach pytest; `--env-file` goes only to `docker compose`. The skip condition says "unset", but CI's copied `.env.example` sets `VLLM_BASE_URL` to an empty string. Taken literally, an empty value would try to reach `""` and fail the `stack` job. | Fix: `make smoke` exports `.env`, or the tests load it from the root. Define the skip condition as "unset or empty" everywhere. | open |
| N6 | Nit | NI | tasks.md:28-32 (4.2); RFC:117-118 | The replay test is to "run with the unit tests", but it sits under the `tests/integration/` heading, and the integration marker is deselected by default. "A history recorded in the test" needs a Temporal server, which the unit job doesn't have. The new `addopts` drops the existing `-ra` (`pyproject.toml:29`). | Fix: put the replay test outside `tests/integration/`, unmarked, replaying a committed JSON history. Say where `HelloWorkflow` lives. Keep `-ra`. | open |
| N7 | Nit | NI | RFC:80; tasks 1.4, 4.1, 4.7 | A new namespace may not be usable at once (the frontend's namespace cache), and visibility writes are asynchronous, so the "listed by the visibility API" assertions can flake. "Already exists → no change" silently ignores a changed `TEMPORAL_RETENTION`. | Fix: wait until the namespace is usable, poll the visibility checks with a timeout, and either update retention or document that changing it needs `make reset`. | open |
| N8 | Nit | NI | RFC:137-148; model-endpoints spec:27-29; phase-0.md:43 | Gaps in the traceability table: `test_model_config` checks only the `.env` string, not that `/v1/models` lists `VLLM_MODEL`. "Endpoint unreachable" has no automated test. The replay test is missing from the table. The demo item "healthy … vLLM services" is not covered, because `make status` shows only Compose services. | Fix: assert `VLLM_MODEL` in `/v1/models`, add the unreachable-endpoint test, add the replay row, and add a vLLM reachability line to `make status` or to demo step 1. | open |
| N9 | Nit | NI | app-database spec:19-21 | "Clean volume … the baseline revision is applied and recorded as current" is wrong now that a second revision follows the baseline (RFC:88, task 3.1). | Fix: "all revisions up to head are applied and head is recorded as current". | open |

N3 (health-check race) is merged into F4.

## Verdict

**FAIL.**

`docs/reviews/README.md` rule 5 decides it: "Every Major must be fixed or contested with evidence before a PASS."

Three Majors are open, and none is fixed or contested:
- **F4:** the health-check race.
- **N1:** psycopg's LGPL license fails the required `licenses` check.
- **N2:** `.env.example` moves away from the plan §6 layout with no decision-log entry.

No Blocker was raised, and every reviewer in this follow-up's scope completed.

The revision fixed most of the original findings: 10 of 13 Majors are resolved, and F2 and F6 hold only Nits now. All three open Majors are small fixes.

## Open items

- **Majors to fix or contest:**
  - F4: probe over TCP (`pg_isready -h 127.0.0.1`), and check the last thing init creates, for example `pg_search` in `praxismesh`.
  - N1: change the PostgreSQL driver, or record an owner decision and add an allowlist entry.
  - N2: keep `.env.example` in `infra/`, or record the move in the decision log and plan §6.
- **Nits**, which do not block: the remainders of F2, F6, F16, F19, F23 and F25, plus N4-N9.
- **Still to verify against live images and docs at implementation** (plan §2):
  - whether the `temporal` CLI ships in `temporalio/server`;
  - how `--wait` handles one-shot jobs;
  - whether `temporal-sql-tool` setup is idempotent;
  - whether the ParadeDB image creates extensions in `template1`;
  - the versions the RFC cites.
- **Next step:** after the author fixes, a re-check runs in another new session (rule 6).

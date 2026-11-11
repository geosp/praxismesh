---
review: design
phase: 0
change: openspec/changes/phase-0-local-infrastructure
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 7659389ef18a4c6a4010e78ffefeb1d976b40ffc
docs_sha: n/a
diff_base: n/a
session: fresh            # second targeted follow-up (docs/reviews/README.md rule 6) of docs/reviews/phase-0/design-review-followup.md
date: 2026-11-11
verdict: PASS
reviewers:
  - { lens: follow-up F4, N1, N2, N4-N9 and new issues in the changed text (design-reviewer), status: completed }
---

# Design review (second targeted follow-up): Phase 0 local infrastructure

**This is a targeted follow-up** under `docs/reviews/README.md` rule 6. It is not a full independent re-review. Its correction list is the previous follow-up, `docs/reviews/phase-0/design-review-followup.md` (commit `7da1b8b`, verdict FAIL with three open Majors: F4, N1 and N2). The reviewer checked those Majors and Nits N4-N9 against the revision. It then looked for new Blockers and Majors **only in the text that changed** between `7da1b8b` and `7659389`.

## Inputs

Revision `7659389ef18a4c6a4010e78ffefeb1d976b40ffc` (branch `docs/phase-0-design`). `git status --porcelain` was empty. All paths below are under `/home/geo/develop/praxismesh`.

- **Change files:** `openspec/changes/phase-0-local-infrastructure/` (`proposal.md`, `design.md`, `tasks.md`, `specs/**`)
- **Design docs:** `docs/rfcs/phase-0-local-infrastructure.md`, `docs/adr/0002-paradedb-as-postgresql-server.md`
- **Changes reviewed:** `git diff 7da1b8b 7659389 -- openspec docs/rfcs`
- **Correction list:** `docs/reviews/phase-0/design-review-followup.md`, given only because this is a targeted follow-up
- **Repository files for evidence:** `.github/workflows/ci.yml`, `.github/scripts/ci_gate.py`, `tests/test_ci_gate.py`, `.gitignore`, `pyproject.toml`, `PROJECT_PLAN.md`, `docs/plan/phases/phase-0.md`, `docs/plan/decision-log.md`

The single lens ran as a `design-reviewer` agent. The coordinator spot-checked the cited lines: RFC:58, 75, 77, 94, 107, 114, 117, 118, 133, 142, 144 and 161, and `ci.yml:246-258`.

`openspec validate phase-0-local-infrastructure --strict` passes: "Change 'phase-0-local-infrastructure' is valid".

## Fresh reader paraphrase

This targeted follow-up does not include one. The paraphrase from the original review (`design-review.md`) still applies.

## Status of the open Majors

RFC = `docs/rfcs/phase-0-local-infrastructure.md`. Paths for tasks, specs and the proposal are relative to `openspec/changes/phase-0-local-infrastructure/`.

| ID | Orig. sev. | Status | Evidence | What remains |
|---|---|---|---|---|
| F4 | Major | **Resolved** | RFC:58: "script over TCP: `pg_isready -h 127.0.0.1`, then `psql -h 127.0.0.1` checking that `pg_search` exists in `praxismesh`, the last thing init creates, so it passes only once init has finished and the server accepts network connections". Task 1.5 (tasks.md:15) matches. While the postgres entrypoint runs `/docker-entrypoint-initdb.d`, its temporary server listens on the Unix socket only. A TCP probe to 127.0.0.1 therefore cannot pass until init has finished and the real server is up. This closes the race. The default `pg_hba.conf` trusts `127.0.0.1/32`, so the in-container probe needs no password. | Nit F4a below. |
| N1 | Major | **Resolved** | RFC:114: "`sqlalchemy[asyncio]` (2.1, MIT) with the `asyncpg` driver (0.32, Apache-2.0) … Not `psycopg` 3: it is LGPL-3.0, which CI's license allow-list does not include (N1)". Also proposal.md:40 and task 0.1 (tasks.md:5, "confirm the `licenses` job passes"). The allow-list at `ci.yml:246-248` is "Apache-2.0, MIT, MIT-0, BSD-2-Clause, BSD-3-Clause, ISC, PSF-2.0, Python-2.0, MPL-2.0, Unlicense, 0BSD, CC0-1.0, Zlib". The licenses below are expected values from package metadata; the reviewer did not check them against a lock. The new driver path is SQLAlchemy MIT, greenlet MIT/PSF-2.0 and asyncpg Apache-2.0. asyncpg's `async-timeout` dependency applies only below Python 3.11, so it is not installed. The rest of the set is on the list too: alembic, Mako, temporalio, nexus-rpc, jmespath, six, urllib3, h11, anyio and the boto3 stubs are MIT. protobuf, MarkupSafe, httpx, httpcore and idna are BSD-3-Clause. boto3, botocore, s3transfer and types-protobuf are Apache-2.0. python-dateutil is Apache-2.0/BSD-3-Clause and certifi MPL-2.0. | GitHub's license detection can disagree with package metadata, as it already did for typing-extensions. Task 0.1's license-job check covers this. Nit N1a below. |
| N2 | Major | **Resolved** | RFC:94: "The template is **`infra/.env.example`**, where plan §6 puts it (N2). The developer copies it to `infra/.env` (git-ignored). The Makefile passes it with `docker compose --env-file infra/.env …`". Also local-stack spec:39, tasks.md:19 (2.1) and proposal.md:39. This matches `PROJECT_PLAN.md:156`, so no decision-log entry is needed. A grep found no root-level `.env` references left. `.gitignore:2` (`.env`) ignores `infra/.env`, and `.gitignore:4` (`!.env.example`) keeps `infra/.env.example` tracked. | — |

## Status of the Nits from the previous follow-up

| ID | Status | Evidence |
|---|---|---|
| N4 | Resolved | RFC:133 and task 5.2: "the job still always runs, but its steps skip … (a skipped *job* would fail `ci-ok`; N4)". This is consistent with `ci_gate.py:33` (`PR_ONLY_JOBS`). |
| N5 | Resolved | RFC:94 says "`make smoke` and `make restart-check` export the same file into the test environment". "Unset or empty" appears at RFC:161, model-endpoints spec:24 and task 4.4. |
| N6 | Mostly resolved | RFC:117 has `addopts = "-ra -m 'not integration'"`. RFC:118 and task 4.2 add a unit test, `tests/test_hello_replay.py`, against a history committed under `tests/fixtures/`. The design still doesn't name the module that holds `HelloWorkflow`. |
| N7 | Resolved | RFC:80: the job exits only once `temporal operator namespace describe` succeeds, and the README documents `namespace update` for a changed retention. RFC:118 and task 4.1: visibility is "polled up to 10 s". |
| N8 | Resolved | RFC:142 adds `test_model_listed`. RFC:144 adds `test_hello_replay` and `test_unreachable_endpoint_fails`. RFC:107 adds endpoint reachability to `make status`. |
| N9 | Resolved | app-database spec:21: "all revisions up to head are applied and head is recorded as current". |

## Findings (new in this round, changed text only)

No new Blocker or Major.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| F4a | Nit | design-reviewer | RFC:58, 75, 77; task 1.5 | RFC:75 now allows that the ParadeDB image's own bootstrap may add `pg_search` to `template1`. In that case `pg_search` exists in `praxismesh` as soon as the database is created, so it is not "the last thing init creates". The TCP probe still closes the race. The marker matters only if a container restarts on a half-initialised volume, and the design names no restart policy. | Have `init.sh` write an explicit final marker (for example `COMMENT ON DATABASE praxismesh IS 'init-complete'`) and check that marker, or state that `db` has no restart policy. Drop the "last thing" wording if task 1.5 finds `pg_search` in `template1`. | open |
| N1a | Nit | design-reviewer (coordinator confirmed) | `ci.yml:251-253`; task 0.1 | The new runtime dependencies (temporalio, sqlalchemy) make typing-extensions a runtime transitive dependency. The justification for its allow-list exception ("Dev-only (pulled in by mypy), never shipped") becomes false. Nothing fails, because the exception matches by package name. | In task 0.1, update the comment's justification. | open |
| M1 | Nit | design-reviewer | RFC:114-115; tasks.md:5-6 | asyncpg is added without type stubs, and strict mypy is extended to the new packages. Any module that imports `asyncpg` directly would fail `uv run mypy`. | Access the database only through SQLAlchemy, or add `asyncpg-stubs` (check its license) or a narrow mypy override. Verify at task 0.1. | open |
| M2 | Nit | design-reviewer | RFC:107; tasks.md:20, 33 | The design doesn't say what `make status` reports when `VLLM_BASE_URL` is empty, which is CI's case (RFC:103). `test_unreachable_endpoint_fails` must use its own deliberately unreachable URL. If it used the configured URL, it would be skipped in CI and contradict the passing run against the Sparks. | State both: `make status` reports "not configured" and does not fail, and the test uses a fixed unreachable address. | open |
| M3 | Nit | design-reviewer | model-endpoints spec; RFC:142 | `test_model_listed` is mapped to "External model endpoint by configuration", but no spec scenario says that `VLLM_MODEL` is listed by `/v1/models`. | Add that scenario to the spec. | open |

## Verdict

**PASS.**

`docs/reviews/README.md` rule 5 decides it:
- No Blocker is open, and every reviewer ran.
- The three Majors open after the previous follow-up, F4, N1 and N2, are fixed in `7659389`.
- The changed text introduces no new Blocker or Major.
- The remaining items are Nits, which do not block.

## Open items

- **Nits, which do not block:**
  - from this round: F4a, N1a, M1, M2 and M3;
  - from the previous follow-up: the N6 remainder (where `HelloWorkflow` lives);
  - from the earlier reviews: the remainders of F2, F6, F16, F19, F23 and F25.
- **Still to verify against live images, packages and docs at implementation** (plan §2):
  - whether the ParadeDB image creates extensions in `template1`, and whether it keeps the postgres `pg_hba.conf` defaults;
  - whether the `temporal` CLI ships in `temporalio/server`;
  - how `--wait` handles one-shot jobs;
  - whether `temporal-sql-tool` setup is idempotent;
  - the cited versions, including sqlalchemy 2.1 and asyncpg 0.32;
  - whether the `licenses` job passes on the new lock.
- **ADR-0002** is still `status: proposed`. The coordinator should accept it together with this design (remainder of F16).

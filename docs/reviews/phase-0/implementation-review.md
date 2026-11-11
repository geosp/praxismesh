---
review: implementation
phase: 0
change: openspec/changes/phase-0-local-infrastructure
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 075791ab7de4c39b7cd0d21f29fbd7dca7a1d597
docs_sha: n/a
diff_base: bb2ed35df31ed304f688d2c5e92c3d70f2094c17
session: fresh
date: 2026-11-11
verdict: FAIL
reviewers:
  - { lens: contract (impl-reviewer), status: completed }
  - { lens: failure and retry (impl-reviewer), status: completed }
  - { lens: scope and composition (impl-reviewer), status: completed }
---

# Implementation review: Phase 0 local infrastructure

Gate mode, light tier. `code_sha` is `075791a`, the squash merge of PR #36 on `main`. The diff base `bb2ed35` is its parent (the Phase 0 design merge). Tracking issue: #34.

## Inputs

Each reviewer (`impl-reviewer` agent, fresh context) received only the following:

- **Diff:** `git -C <repo> diff bb2ed35df31ed304f688d2c5e92c3d70f2094c17 075791ab7de4c39b7cd0d21f29fbd7dca7a1d597`
- **Contract:**
  - `openspec/changes/phase-0-local-infrastructure/proposal.md`
  - `openspec/changes/phase-0-local-infrastructure/design.md`
  - `openspec/changes/phase-0-local-infrastructure/tasks.md`
  - `openspec/changes/phase-0-local-infrastructure/specs/dev-environment/local-stack/spec.md`
  - `openspec/changes/phase-0-local-infrastructure/specs/inference/model-endpoints/spec.md`
  - `openspec/changes/phase-0-local-infrastructure/specs/persistence/app-database/spec.md`
  - `openspec/changes/phase-0-local-infrastructure/specs/storage/blob-store/spec.md`
  - `docs/rfcs/phase-0-local-infrastructure.md`
  - `docs/adr/0002-paradedb-as-postgresql-server.md`
- **Guidance:** `AGENTS.md` (no nested `AGENTS.md` exists in the touched packages) and `PROJECT_PLAN.md` (§2, §8).

`git status --porcelain` was empty on `main` at `075791a` when the review started. All three reviewers read the code and contract read-only; none ran the stack.

## Findings

Duplicates across reviewers are merged. Reviewer keys: **C** contract, **F** failure and retry, **S** scope and composition.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| F1 | Major | C, F, S | `Makefile:10-14` (`include` + `export`), `infra/check-prereqs.sh` (`sed`), Compose `--env-file` | `infra/.env` is read by three parsers that disagree on quotes, `#` and `$`. With `APP_DB_PASSWORD="s3cr#t"` or a value containing `$`, Compose gives init.sh one password while Make exports another to `make migrate`, the tests and restart-check. Authentication then fails with no named diagnostic, and the likely "fix" (`make reset`) deletes data. Spec: "All endpoints, ports and credentials SHALL come from `infra/.env`" and the clear-diagnostics requirement. | Fix: an env-check test with a quoted value and values containing `#` and `$` that asserts `docker compose --env-file … config` and the Make-exported environment agree (fails today); then restrict the allowed syntax in `.env.example` and reject other values in `check-prereqs.sh`, or read the file one way everywhere. | open |
| F2 | Major | C, S | `infra/temporal/namespace.sh:12-17`; `tests/support/stack.py` | The spec's Hello Workflow runs "in the namespace the stack creates with its configured retention" (§4.13). If `default` already exists (a prior run with another `TEMPORAL_RETENTION`, or created by the server image), the job prints "already exists" and exits 0. A failed `create` is swallowed (`|| echo …`), so an invalid retention surfaces only as "not usable after 30 s". No test, demo step or as-built line checks retention. | Fix: an integration test that calls `DescribeNamespace` and asserts `workflow_execution_retention_ttl` equals the parsed `TEMPORAL_RETENTION`; then make the job compare (or update) the retention of an existing namespace and stop swallowing the create error. | open |
| F3 | Major | C (S: N10) | `Makefile` `status` target; `tests/integration/test_database.py:26-32` | Spec scenario "Unhealthy service": with `db` stopped, `make status` names `db` and `make smoke` fails naming the database. Only a manual demo run (`docs/demos/phase-0.md`) shows it. A regression in `status` or in the `except OSError` mapping leaves CI green. | Fix: a CI `stack` step that stops `db`, asserts `make status` names `db` and `make smoke -k database` exits non-zero naming the database, then restarts `db`. | open |
| F4 | Major | C (S: N1, rated Nit) | `infra/temporal/schema.sh:4-14`; `tests/integration/restart_check.py` | Spec scenario "Repeat start": "the schema and namespace jobs make no changes". Only the exit code of a second `make up` is checked. Both reviewers doubt that `setup-schema -v 0.0` is a no-op on an existing database (it may rewrite `schema_version` and log a history row on each run); neither could confirm it read-only. "Stopped" (`compose stop`) is also not exercised. | Fix: in restart-check, snapshot `schema_version` and `schema_update_history` in both Temporal databases plus the namespace description before and after the repeat `make up`, and assert equality. | open |
| F5 | Nit | C, F, S | `Makefile:37-42` | `up -d temporal-namespace >/dev/null 2>&1` discards Compose's error, so a failure there shows only `make: *** Error 1`; `docker wait` on the jobs has no time limit (only CI's 20-minute job timeout bounds it). Spec: "exit non-zero naming the unhealthy service". The `--wait` step relies on Compose's own output to name the service. | Fix | open |
| F6 | Nit | F, S | `tests/integration/restart_check.py:47-69`; `tests/integration/test_blob_store.py:17-23` | No `try/finally` in restart-check: a lost object raises `NoSuchKey` instead of `FAIL …`, skips cleanup and leaves a `phase0-restart-*` bucket (and possibly a stopped stack). In the S3 smoke test, `delete_bucket` in `finally` on a non-empty bucket replaces the real failure. Exit code stays non-zero; CI resets. | Fix | open |
| F7 | Nit | F | `tests/support/stack.py:44-47`; `tests/support/hello.py` | `execute_workflow` has no `execution_timeout` and the Activity retries forever. A smoke run killed mid-Workflow leaves a Running Workflow on an unpolled task queue that retention never removes. | Fix | open |
| F8 | Nit | F | `infra/db/init.sh:40-42`; `infra/db/healthcheck.sh:7-10` | The init marker is a comment on database `praxismesh`, which the app role owns. A future app migration that changes the comment makes `db` permanently unhealthy after the next restart, and the advised `make reset` deletes data. | Fix | open |
| F9 | Nit | F | `Makefile` `down`/`reset` depend on `check` | With `infra/.env` missing or incomplete, `make down` and `make reset` refuse to run, blocking the documented recovery path. | Fix | open |
| F10 | Nit | F | `.github/dependabot.yml` | `temporalio/server` and `temporalio/admin-tools` can be bumped in separate PRs to mismatched versions. The CI `stack` job would catch it. Not verified. | Fix: group `temporalio/*`. | open |
| F11 | Nit | F | `tests/integration/test_database.py:45-47`; `Makefile` `smoke` | `make smoke` on a fresh stack without `make migrate` fails with `UndefinedTableError` on `alembic_version`, not a hint to run `make migrate`. | Fix | open |
| F12 | Nit | C, S | `Makefile` `status` (`curl … /v1/models`) | `make status` sends no `VLLM_API_KEY`, so a key-protected endpoint shows as "unreachable" while the tests (which send the key) pass. The Sparks need no key. | Fix | open |
| F13 | Nit | S | `tests/support/models.py:20` | A single 120 s timeout also covers connect, so a black-holed `VLLM_BASE_URL` costs about 6 minutes across three tests before "unreachable". | Fix | open |
| F14 | Nit | C, S | `tests/integration/test_model_endpoints.py` | Spec: "the model smoke tests call that endpoint and no other", but `test_unreachable_endpoint_fails` calls `http://127.0.0.1:9` at helper scope. tasks.md 4.4 (design follow-up M2) explicitly accepts this; the spec text should be aligned. `VLLM_MODEL` also has a hard-coded `"spark"` fallback in the test, and an empty `VLLM_MODEL` gives no clear message (spec: model name "never hard-coded"). | Fix (spec wording and fallback) | open |
| F15 | Nit | S | `tests/support/stack.py:22-25`; `common/persistence/settings.py` | An empty optional variable (`TEMPORAL_PORT=`) makes Compose use its default, while the tests raise "not set" or `int("")` ValueError. `check-prereqs.sh` does not flag it. | Fix | open |
| F16 | Nit | C, S | `tests/integration/test_database.py:35-37`; `infra/db/init.sh` | Role isolation is tested in one direction only (app role refused on the Temporal databases; nothing checks `temporal` refused on `praxismesh`). `postgres` and `template1` keep PUBLIC CONNECT. | Fix | open |
| F17 | Nit | C | `common/persistence/migrations/versions/0002_require_pg_search.py` | The failure branch (no `pg_search`) is untested. With 0002 on the main chain, plain PostgreSQL cannot reach later migrations, which is in tension with ADR-0002 ("a plain PostgreSQL server can still run everything else"). The spec mandates the check, so this is a contract tension to decide, not an implementation error. | Fix (test) / record decision | open |
| F18 | Nit | C | `infra/docker-compose.yml` (temporal-ui health check) | "UI reachable on its documented port" is checked only inside the container; a wrong host port mapping still reports healthy. | Fix | open |
| F19 | Nit | C | `tests/integration/test_env_check.py:16-19` | The missing-env test runs `check-prereqs.sh` directly, not `make up`, so dropping `check` from `up` would go unnoticed. "Docker not running" has no test. | Fix | open |
| F20 | Nit | C | `infra/docker-compose.yml` one-shot jobs; `infra/db/healthcheck.sh` | Spec: "Every service … SHALL define a health check"; the one-shot jobs have none (the RFC defines "exits 0" as their check, enforced in the Makefile). The `db` check proves roles and `pg_search` only via the init marker. | Contest candidate: RFC table and task 1.5 accepted this; align spec wording. | open |
| F21 | Nit | C | `infra/docker-compose.yml` (s3) | No test shows SeaweedFS rejects a wrong S3 secret, so credential enforcement is not observed. | Fix | open |
| F22 | Nit | C | `tests/fixtures/hello_history.json` | The recorded replay fixture contains the recording worker's identity, which includes a workstation hostname. Not a credential. | Fix: re-record with a fixed `identity`. | open |
| F23 | Nit | C, S | `tests/test_hello_replay.py`; `.github/workflows/ci.yml` | Plan §8 asks for replay and time-skipping tests per Workflow and a tiny model or stubs in CI. HelloWorkflow (a test fixture) has replay only, and CI skips the model tests. The RFC accepts both; recorded so the deviation is explicit. | Contest candidate: RFC accepted. | open |
| F24 | Nit | C | `tests/integration/restart_check.py` | Only `alembic_version` stands in for application data across the restart (plus Temporal history and the S3 object). Adequate for Phase 0. | none | open |
| F25 | Nit | S | `Makefile` `status` | `make status` exits 0 when services are unhealthy, so scripts cannot rely on it. | Fix | open |

## Reviewer status

| Reviewer | Status |
|---|---|
| Contract | completed |
| Failure and retry | completed |
| Scope and composition | completed |

## Verdict

**FAIL.** No Blockers, and all three reviewers ran, but four Majors (F1-F4) are open. Per `docs/reviews/README.md` rule 5, every Major must be fixed or contested with evidence before a PASS. Gate mode does not fix findings in the reviewing session (rule 6): they go back to the implementer, and a re-check runs in a new session.

## Open items

- F1-F4 (Major): fix, or contest with evidence, then re-check in a new session.
- F5-F25 (Nit): do not block; the implementer decides.
- Reviewer notes that could not be confirmed read-only: whether `setup-schema -v 0.0` rewrites version rows on an existing database (F4), whether the Temporal server image registers `default` itself (F2), and whether SeaweedFS rejects a wrong S3 secret (F21).

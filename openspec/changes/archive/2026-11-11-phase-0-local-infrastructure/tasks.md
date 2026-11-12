# Tasks

## 0. Project setup

- [x] 0.1 Add runtime dependencies (`temporalio`, `alembic`, `sqlalchemy[asyncio]`, `asyncpg`, `boto3`, `httpx`) and dev `boto3-stubs[s3]`; lock with `uv`; confirm the `licenses` job passes; update the `typing-extensions` allow-list comment in `ci.yml` (it becomes a runtime dependency); type asyncpg access through SQLAlchemy only, or add stubs or a narrow mypy override (follow-up 2: N1a, M1)
- [x] 0.2 Register the `integration` pytest marker and exclude it from the default run while keeping `-ra`; extend mypy `files` to the new packages

## 1. Compose stack

- [x] 1.1 `infra/docker-compose.yml`: ParadeDB `0.26.6-pg16`, Temporal Server and admin tools 1.32.2, Temporal UI 2.58.1, `chrislusf/seaweedfs:4.53`; tags pinned and digests recorded; ports bound to 127.0.0.1; volumes `pgdata`, `seaweeddata`
- [x] 1.2 `infra/db/init.sh` (`set -e`, `ON_ERROR_STOP`): roles, three databases, `REVOKE CONNECT ... FROM PUBLIC` and grants, `CREATE EXTENSION IF NOT EXISTS pg_search` in `praxismesh` only
- [x] 1.3 `temporal-schema` job (`temporal-sql-tool --plugin postgres12`, setup and update for both databases), safe to repeat
- [x] 1.4 `temporal-namespace` job: create `TEMPORAL_NAMESPACE` with `TEMPORAL_RETENTION`; "already exists" is success; exit only once `namespace describe` succeeds (since the gate fixes: a differing retention is updated, not left unchanged; decision log)
- [x] 1.5 Health checks for every service; the database check runs over TCP and checks that `pg_search` exists in `praxismesh`; verify the Temporal CLI is in the server image or use a gRPC probe; check whether the image adds extensions to its template database; have `init.sh` finish with a marker the health check reads (for example `COMMENT ON DATABASE praxismesh`), or give `db` no restart policy (follow-up 2: F4a)
- [x] 1.6 Verify `docker compose up --wait` with completed one-shot jobs; `make up` twice in a row succeeds

## 2. Developer commands and configuration

- [x] 2.1 `infra/.env.example` (plan §6) with every variable (database, Temporal, S3, `VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`); `infra/.env` git-ignored
- [x] 2.2 `Makefile`: `up`, `down`, `reset`, `status` (including model endpoint reachability, shown as "not configured" when `VLLM_BASE_URL` is empty), `migrate`, `smoke`, `restart-check`, `logs`, all using `infra/.env`; `smoke` and `restart-check` export it to the tests
- [x] 2.3 Prerequisite checks with named diagnostics: Docker not running, `infra/.env` missing, required variable unset

## 3. Application database

- [x] 3.1 Alembic (async environment, SQLAlchemy with asyncpg) in `common/persistence/migrations/`: empty baseline revision, then a revision that checks `pg_search` is installed (downgrade is a no-op)
- [x] 3.2 `make migrate` applies from a clean volume and is a no-op after restart

## 4. Integration tests (`tests/integration/`, marker `integration`)

- [x] 4.1 Hello Workflow and Activity with an in-process worker, unique task queue and Workflow ID per run; result checked; listed by the visibility API (polled up to 10 s)
- [x] 4.2 Replay test `tests/test_hello_replay.py` (unit run) against a history file committed under `tests/fixtures/`, recorded once from the stack
- [x] 4.3 S3 put, get and delete in a unique bucket per run
- [x] 4.4 Model endpoints: skipped when `VLLM_BASE_URL` is unset or empty, failing (endpoint named) when set but unreachable (`test_unreachable_endpoint_fails`, using its own unreachable URL, not the configured one; follow-up 2: M2); `VLLM_MODEL` contains no `/` and appears in `/v1/models`
- [x] 4.5 Application role refused on Temporal's databases; `pg_search` installed
- [x] 4.6 `infra/.env` check: missing file and unset variable produce named diagnostics
- [x] 4.7 `make restart-check`: up, migrate, seed, down, up, migrate (no-op), assert Workflow and object survive

## 5. CI

- [x] 5.1 `stack` job running `make up`, `make migrate`, `make smoke`, `make restart-check` (model tests skipped), with `infra/.env` copied from `infra/.env.example`
- [x] 5.2 Add `stack` to `REQUIRED_JOBS` in `.github/scripts/ci_gate.py` and to `ci-ok`'s `needs:`; if Docker Hub pulls prove flaky, skip its steps (never the job) on PRs that touch none of the stack paths
- [x] 5.3 Dependabot `docker-compose` ecosystem entry

## 6. Documentation and demo

- [x] 6.1 README: running the stack, `make reset` for a failed init or changed passwords, a changed retention (applied by `make up` since the gate fixes; originally `temporal operator namespace update`), optional GCS and Ceph settings, and the ParadeDB AGPL-3.0 note
- [x] 6.2 Run the demo, including a passing model run against the Sparks and `docker stats` (under 6 GB), and record `docs/demos/phase-0.md`
- [x] 6.3 As-built section in `docs/architecture/overview.md`; record the Phase 0 deviation (no Compose vLLM profile) in the decision log

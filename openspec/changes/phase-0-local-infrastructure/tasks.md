# Tasks

## 0. Project setup

- [ ] 0.1 Add runtime dependencies (`temporalio`, `alembic`, `psycopg[binary]`, `boto3`, `httpx`) and dev `boto3-stubs[s3]`; lock with `uv`
- [ ] 0.2 Register the `integration` pytest marker and exclude it from the default run; extend mypy `files` to the new packages

## 1. Compose stack

- [ ] 1.1 `infra/docker-compose.yml`: ParadeDB `0.26.6-pg16`, Temporal Server and admin tools 1.32.2, Temporal UI 2.58.1, `chrislusf/seaweedfs:4.53`; tags pinned and digests recorded; ports bound to 127.0.0.1; volumes `pgdata`, `seaweeddata`
- [ ] 1.2 `infra/db/init.sh` (`set -e`, `ON_ERROR_STOP`): roles, three databases, `REVOKE CONNECT ... FROM PUBLIC` and grants, `CREATE EXTENSION IF NOT EXISTS pg_search` in `praxismesh` only
- [ ] 1.3 `temporal-schema` job (`temporal-sql-tool --plugin postgres12`, setup and update for both databases), safe to repeat
- [ ] 1.4 `temporal-namespace` job: create `TEMPORAL_NAMESPACE` with `TEMPORAL_RETENTION`; "already exists" is success
- [ ] 1.5 Health checks for every service, the database check proving databases and roles exist; verify the Temporal CLI is in the server image or use a gRPC probe
- [ ] 1.6 Verify `docker compose up --wait` with completed one-shot jobs; `make up` twice in a row succeeds

## 2. Developer commands and configuration

- [ ] 2.1 `.env.example` at the repository root with every variable (database, Temporal, S3, `VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`); `.env` git-ignored
- [ ] 2.2 `Makefile`: `up`, `down`, `reset`, `status`, `migrate`, `smoke`, `restart-check`, `logs`, all passing `--env-file .env`
- [ ] 2.3 Prerequisite checks with named diagnostics: Docker not running, `.env` missing, required variable unset

## 3. Application database

- [ ] 3.1 Alembic in `common/persistence/migrations/`: empty baseline revision, then a revision that checks `pg_search` is installed (downgrade is a no-op)
- [ ] 3.2 `make migrate` applies from a clean volume and is a no-op after restart

## 4. Integration tests (`tests/integration/`, marker `integration`)

- [ ] 4.1 Hello Workflow and Activity with an in-process worker, unique task queue and Workflow ID per run; result checked; listed by the visibility API
- [ ] 4.2 Replay test for the hello Workflow, run with the unit tests
- [ ] 4.3 S3 put, get and delete in a unique bucket per run
- [ ] 4.4 Model endpoints: skipped when `VLLM_BASE_URL` is unset, failing (endpoint named) when set but unreachable; `VLLM_MODEL` contains no `/`
- [ ] 4.5 Application role refused on Temporal's databases; `pg_search` installed
- [ ] 4.6 `.env` check: missing file and unset variable produce named diagnostics
- [ ] 4.7 `make restart-check`: up, migrate, seed, down, up, migrate (no-op), assert Workflow and object survive

## 5. CI

- [ ] 5.1 `stack` job running `make up`, `make migrate`, `make smoke`, `make restart-check` (model tests skipped), with `.env` copied from `.env.example`
- [ ] 5.2 Add `stack` to `REQUIRED_JOBS` in `.github/scripts/ci_gate.py` and to `ci-ok`'s `needs:`; path-filter it only if Docker Hub pulls prove flaky
- [ ] 5.3 Dependabot `docker-compose` ecosystem entry

## 6. Documentation and demo

- [ ] 6.1 README: running the stack, `make reset` for a failed init or changed passwords, optional GCS and Ceph settings, and the ParadeDB AGPL-3.0 note
- [ ] 6.2 Run the demo, including a passing model run against the Sparks and `docker stats` (under 6 GB), and record `docs/demos/phase-0.md`
- [ ] 6.3 As-built section in `docs/architecture/overview.md`; record the Phase 0 deviation (no Compose vLLM profile) in the decision log

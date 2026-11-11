# Tasks

## 1. Compose stack

- [ ] 1.1 `infra/docker-compose.yml`: ParadeDB `0.26.6-pg16`, Temporal Server and admin tools 1.32.2, Temporal UI 2.58.1, SeaweedFS 4.53; images pinned by tag and digest; ports bound to 127.0.0.1
- [ ] 1.2 Database init: Temporal persistence and visibility databases plus the application database, each with its own role
- [ ] 1.3 Temporal schema setup as a one-shot admin-tools job (`temporal-sql-tool`, plugin `postgres12`) that the server waits for
- [ ] 1.4 SeaweedFS S3 endpoint with credentials from `.env`
- [ ] 1.5 Health checks for every service; named volumes
- [ ] 1.6 Optional `vllm-local` profile, off by default

## 2. Developer commands and configuration

- [ ] 2.1 `.env.example` with placeholders; `.env` git-ignored
- [ ] 2.2 `Makefile`: `up` (checks prerequisites, waits for health), `down`, `migrate`, `smoke`, `logs`, `reset`
- [ ] 2.3 Clear diagnostics: Docker not running, `.env` missing, required variable unset, model endpoint unreachable

## 3. Application database

- [ ] 3.1 Alembic setup with an empty baseline revision and a revision that creates `pg_search`
- [ ] 3.2 `make migrate` applies from a clean volume and is a no-op after restart

## 4. Smoke tests (`tests/smoke/`)

- [ ] 4.1 Hello-world Temporal Workflow and Activity; result checked and visible through the visibility API
- [ ] 4.2 S3 put, get and delete against SeaweedFS
- [ ] 4.3 vLLM `/v1/messages` and `/v1/chat/completions` against `VLLM_BASE_URL`; skipped with the reason when unset or unreachable
- [ ] 4.4 Application role cannot connect to Temporal's databases; `pg_search` installed

## 5. CI

- [ ] 5.1 A `stack` job that runs `make up`, `make migrate` and `make smoke` on GitHub's runners (model tests skipped there), included in `ci-ok`

## 6. Documentation and demo

- [ ] 6.1 README: running the stack; optional GCS and Ceph settings documented
- [ ] 6.2 Run the demo and record `docs/demos/phase-0.md`
- [ ] 6.3 As-built section in `docs/architecture/overview.md`

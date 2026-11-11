# As-built architecture overview

Cumulative, one section per phase (plan §4.17, §7.0 light tier). Each section records the `code_sha` it describes and states only observed behavior. Design intent lives in `docs/rfcs/`.

## Phase 0: local infrastructure

**Describes:** `main` at `075791a` (PR #36), updated for the gate findings by the branch `fix/34-phase-0-gate-findings` (issue #34); the commit that merges it is the one to verify. **Design:** [RFC](../rfcs/phase-0-local-infrastructure.md), [ADR-0002](../adr/0002-paradedb-as-postgresql-server.md). **Evidence:** [docs/demos/phase-0.md](../demos/phase-0.md).

### Components

One Docker Compose project, `praxismesh` (`infra/docker-compose.yml`). Host ports bind to `127.0.0.1`.

| Service | Image (tag and digest pinned in Compose) | Role | Health check |
|---|---|---|---|
| `db` | `paradedb/paradedb:0.26.6-pg16` | PostgreSQL 16.15 server for Temporal and the application | `infra/db/healthcheck.sh`: `pg_isready` and `psql` over TCP to `127.0.0.1`, then requires the init-complete marker on database `postgres` |
| `temporal-schema` | `temporalio/admin-tools:1.32.2` | One-shot: `temporal-sql-tool --plugin postgres12` `setup-schema -v 0.0` and `update-schema` on both Temporal databases | exit code 0 |
| `temporal` | `temporalio/server:1.32.2` | Temporal frontend, history, matching and worker services in one process | HTTP GET `127.0.0.1:7243/api/v1/cluster-info` (the image has no `temporal` CLI) |
| `temporal-namespace` | `temporalio/admin-tools:1.32.2` | One-shot: creates `TEMPORAL_NAMESPACE` with `TEMPORAL_RETENTION` if absent, updates the retention if it differs, fails naming a failed create or update; exits once `namespace describe` shows the configured retention | exit code 0 |
| `temporal-ui` | `temporalio/ui:2.58.1` | Web UI | HTTP GET `/` |
| `s3` | `chrislusf/seaweedfs:4.53` | `weed server -s3`: master, volume, filer and S3 gateway in one process; credentials from the fallback environment variables | HTTP GET `/healthz` on the S3 port |

Volumes: `pgdata`, `seaweeddata`, prefixed with the Compose project name. The project name comes from `COMPOSE_PROJECT_NAME` (default `praxismesh`), so separate checkouts can run separate stacks. Long-running services restart `unless-stopped`.

The model server is external: `VLLM_BASE_URL` in `infra/.env`. There is no vLLM service in Compose (decision log, 2026-11-11).

### Data and isolation

- **Databases**, created by `infra/db/init.sh` on a fresh volume, all from `template0`: `temporal` and `temporal_visibility` (owner role `temporal`), `praxismesh` (owner role `praxismesh`). `CONNECT` on these three and on `postgres` is revoked from `PUBLIC` and granted only to the owning role. Observed: role `praxismesh` gets "permission denied for database" on `temporal`, `temporal_visibility` and `postgres`; role `temporal` gets it on `praxismesh` and `postgres`.
- **Extensions.** ParadeDB's own bootstrap installs extensions (including `pg_search`, `vector` and `postgis`) into `template1`, and `pg_cron` into `postgres`; creating from `template0` keeps them out. Observed extensions: `temporal` has `plpgsql` only; `temporal_visibility` has `plpgsql` and `btree_gin` (added by Temporal's visibility schema); `praxismesh` has `plpgsql`, `vector` and `pg_search` (`pg_search` 0.26 requires `vector`, so it is created with `CASCADE`).
- **Init marker.** The last statement of `init.sh` sets `COMMENT ON DATABASE postgres` to `praxismesh-init-complete`; the health check requires it. Only the superuser can change it, so application migrations cannot break the health check. Observed during implementation: when init failed partway, Docker restarted `db`, the entrypoint skipped init on the existing volume, and `db` stayed unhealthy rather than reporting healthy.
- **Tuning.** `PDB_TUNE=false` turns off ParadeDB's auto-tuning, which would set `shared_buffers` to 25% of host RAM.
- **Application schema.** Alembic, async environment, SQLAlchemy 2.1 with asyncpg, in `common/persistence/migrations/`. Revisions: `0001` (empty baseline) and `0002` (checks `pg_search` is installed; downgrade is a no-op). Connection settings come from the environment (`common/persistence/settings.py`).

### Commands

`make up` first runs `infra/check-prereqs.sh`: Docker running, Compose plugin present, `infra/.env` present, every line plain `KEY=value` (no quotes, spaces, `#`, `$`, `\` or backticks, which Make and Compose would read differently), required variables set and non-empty, `VLLM_MODEL` without `/`, `TEMPORAL_RETENTION` as `<number><s|m|h|d>`. It then runs `docker compose up -d --wait` on the long-running services only, because Compose v5.7 reports a one-shot job that exited 0 as a `--wait` failure. It then starts `temporal-namespace` and checks both jobs' exit codes with `docker wait`, limited to 120 s. Observed: `make up` succeeds twice in a row; from a clean volume it takes about 15 s once images are pulled.

`make status` lists each service, reports the model endpoint as not configured, answering `/v1/models` (sending `VLLM_API_KEY` when set), or unreachable, and names any unhealthy or stopped service with exit status 1. `make down` and `make reset` work by project name alone, so they run even when `infra/.env` is missing or invalid. `make smoke` runs `pytest -m integration tests/integration`. `make restart-check` runs `tests/integration/restart_check.py`; `make unhealthy-check` runs `tests/integration/unhealthy_check.py`.

### Tests

- **Unit run** (`uv run pytest`, CI job `tests`): excludes the `integration` marker. Includes `tests/test_hello_replay.py`, which replays `tests/fixtures/hello_history.json` (recorded from the stack) against `HelloWorkflow` with no server.
- **Integration** (`tests/integration/`, CI job `stack`):
  - hello Workflow with an in-process worker on a unique task queue (30 s execution timeout, at most 3 Activity attempts), listed by visibility within 10 s; the namespace's retention equals `TEMPORAL_RETENTION`; the UI answers on its host port;
  - S3 put, get and delete in a unique bucket; a wrong secret is rejected;
  - role isolation in both directions, `pg_search` installed, migrations at head (with a hint to run `make migrate` when none are applied);
  - `make up`'s prerequisite diagnostics, including rejected `.env` syntax;
  - model endpoints: skipped when `VLLM_BASE_URL` is empty; `test_unreachable_endpoint_fails` always runs against its own unreachable address.
- **Restart check:** snapshots both Temporal databases' `schema_version` and `schema_update_history` and the namespace description before and after a repeat `make up` and requires them equal; then seeds a Workflow and an object, runs `make down` and `make up`, and checks they survive and the migration revision is unchanged. Observed: a repeated `setup-schema -v 0.0` logs "Skip version upgrade" and changes no rows.
- **Unhealthy check:** stops `db`; `make status` must exit non-zero naming `db`, and the database smoke test must fail naming the database server; then restarts the stack.
- `HelloWorkflow` and `say_hello` live in `tests/support/hello.py`; they are test fixtures, not product code. The worker and client use the fixed identity `phase0-smoke-worker`, so recorded histories carry no hostname.
- **CI:** job `stack` copies `infra/.env.example` to `infra/.env` and runs `make up`, `make migrate`, `make smoke`, `make restart-check` and `make unhealthy-check`; it is required by `ci-ok`.

### Resource use

Observed idle memory for the four long-running services (`docker stats`, sum of the services): 275 MiB in the implementer's run, 368-408 MiB in the verification run, 349 MiB in three samples after the gate fixes (2026-11-11). It varies with activity; all are far under the 6 GB budget.

### Known limitations

- Single node, no TLS, no authentication on Temporal or the UI; placeholder passwords in `infra/.env.example`. Ports bind to `127.0.0.1` only.
- Database init runs only on a fresh volume; changed passwords or a failed init need `make reset`.
- GCS and Ceph RGW are documented in the README, not run or tested.
- Model tests run only where `VLLM_BASE_URL` is set; CI skips them.

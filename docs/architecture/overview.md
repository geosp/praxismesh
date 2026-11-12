# As-built architecture overview

Cumulative, one section per phase (plan §4.17, §7.0 light tier). Each section records the `code_sha` it describes and states only observed behavior. Design intent lives in `docs/rfcs/`.

## Phase 0: local infrastructure

**Describes:** `130f3d4` on `main` (PR #42), the commit at which Phase 0 closed (issue #34). **Design:** [RFC](../rfcs/phase-0-local-infrastructure.md), [ADR-0002](../adr/0002-paradedb-as-postgresql-server.md). **Evidence:** [docs/demos/phase-0.md](../demos/phase-0.md).

### Components

One Docker Compose project per checkout (`infra/docker-compose.yml`), named by `COMPOSE_PROJECT_NAME`. Host ports bind to `127.0.0.1`.

| Service | Image (tag and digest pinned in Compose) | Role | Health check |
|---|---|---|---|
| `db` | `paradedb/paradedb:0.26.6-pg16` | PostgreSQL 16.15 server for Temporal and the application | `infra/db/healthcheck.sh`: `pg_isready` and `psql` over TCP to `127.0.0.1`, then requires the init-complete marker on database `postgres` |
| `temporal-schema` | `temporalio/admin-tools:1.32.2` | One-shot: `temporal-sql-tool --plugin postgres12` `setup-schema -v 0.0` and `update-schema` on both Temporal databases | exit code 0 |
| `temporal` | `temporalio/server:1.32.2` | Temporal frontend, history, matching and worker services in one process | HTTP GET `127.0.0.1:7243/api/v1/cluster-info` (the image has no `temporal` CLI) |
| `temporal-namespace` | `temporalio/admin-tools:1.32.2` | One-shot: creates `TEMPORAL_NAMESPACE` with `TEMPORAL_RETENTION` if absent, updates the retention if it differs, fails naming a failed create or update; exits once `namespace describe` shows the configured retention | exit code 0 |
| `temporal-ui` | `temporalio/ui:2.58.1` | Web UI | HTTP GET `/` |
| `s3` | `chrislusf/seaweedfs:4.53` | `weed server -s3`: master, volume, filer and S3 gateway in one process; credentials from the fallback environment variables | HTTP GET `/healthz` on the S3 port |

Volumes: `pgdata`, `seaweeddata`, prefixed with the Compose project name. The Makefile reads `COMPOSE_PROJECT_NAME` from `infra/.env` only, passes it to Compose with `-p` and exports it to every command it runs, replacing any value in the shell; with no valid name every target refuses.env.example` sets `praxismesh`. Separate checkouts with separate names (and ports) run separate stacks. Long-running services restart `unless-stopped`.

The model server is external: `VLLM_BASE_URL` in `infra/.env`. There is no vLLM service in Compose (decision log, 2026-11-11).

### Data and isolation

- **Databases**, created by `infra/db/init.sh` on a fresh volume, all from `template0`: `temporal` and `temporal_visibility` (owner role `temporal`), `praxismesh` (owner role `praxismesh`). `CONNECT` on these three, `postgres` and ParadeDB's own `paradedb` database is revoked from `PUBLIC` and granted only to the owning role. Observed: role `praxismesh` gets "permission denied for database" on `temporal`, `temporal_visibility` and `postgres`; role `temporal` gets it on `praxismesh` and `postgres` (tested); on a fresh volume both are also refused on `paradedb`.
- **Extensions.** ParadeDB's own bootstrap installs extensions (including `pg_search`, `vector` and `postgis`) into `template1`, and `pg_cron` into `postgres`; creating from `template0` keeps them out. Observed extensions: `temporal` has `plpgsql` only; `temporal_visibility` has `plpgsql` and `btree_gin` (added by Temporal's visibility schema); `praxismesh` has `plpgsql`, `vector` and `pg_search` (`pg_search` 0.26 requires `vector`, so it is created with `CASCADE`).
- **Init marker.** The last statement of `init.sh` sets `COMMENT ON DATABASE postgres` to `praxismesh-init-complete`; the health check requires it, and only the superuser can change it. **Upgrade of older volumes:** when the marker is absent but `praxismesh` has both `vector` and `pg_search` (created together by init's last step; `vector` needs the superuser, so the app role cannot fake it), the health check applies the current `REVOKE CONNECT` statements and writes the marker once. Observed: a volume without the marker and with `CONNECT` granted to `PUBLIC` on `postgres` and `paradedb` was upgraded and became healthy; with the two extensions dropped, it stayed unhealthy.
- **Tuning.** `PDB_TUNE=false` turns off ParadeDB's auto-tuning, which would set `shared_buffers` to 25% of host RAM.
- **Application schema.** Alembic, async environment, SQLAlchemy 2.1 with asyncpg, in `common/persistence/migrations/`. Revisions: `0001` (empty baseline) and `0002` (checks `pg_search` is installed; downgrade is a no-op). Connection settings come from the environment (`common/persistence/settings.py`).

### Commands

Make never reads `infra/.env`. Compose reads it with `--env-file`; the tests, migrations and `make status` get it through `uv run --env-file`. `make up` first runs `infra/check-prereqs.sh`: Docker running, Compose plugin present, `infra/.env` present; every line a comment, blank, or `KEY=value` with a known key and a value of `A-Z a-z 0-9 . _ : / @ % + , = -` only, and no line ending in `\`; every variable except `VLLM_BASE_URL` and `VLLM_API_KEY` non-empty; each key at most once; a valid lowercase `COMPOSE_PROJECT_NAME`; `VLLM_MODEL` without `/`; `TEMPORAL_RETENTION` as `<number><s|m|h|d>`, at least one day. Each problem is named, with its line number where it has one.
`make status` (`tests/support/status.py`) lists each service and the host addresses, reports the model endpoint as not configured, answering `/v1/models` (sending `VLLM_API_KEY` when set), or failing, and names any unhealthy or stopped service; it then fails, so `make` exits non-zero (2). `make down` and `make reset` use the project name from `infra/.env` with `docker compose -p <name> down`, so they work when other settings are invalid; with no valid name they refuse instead of using a default. `make smoke` runs `pytest -m integration tests/integration`. `make restart-check` runs `tests/integration/restart_check.py`; `make unhealthy-check` runs `tests/integration/unhealthy_check.py`.

### Tests

- **Unit run** (`uv run pytest`, CI job `tests`): excludes the `integration` marker. Includes `tests/test_hello_replay.py`, which replays `tests/fixtures/hello_history.json` (recorded from the stack) against `HelloWorkflow` with no server.
- **Integration** (`tests/integration/`, CI job `stack`):
  - hello Workflow with an in-process worker on a unique task queue (60 s execution timeout, at most 3 Activity attempts), listed by visibility within 10 s; the namespace's retention equals `TEMPORAL_RETENTION`; the UI answers on its host port;
  - S3 put, get and delete in a unique bucket; a wrong secret is rejected;
  - role isolation in both directions, `pg_search` installed, migrations at head (with a hint to run `make migrate` when none are applied);
  - `make up`'s and `make reset`'s prerequisite diagnostics, through `make`: each rejected character, a comment ending in `\`, unknown keys, bad retention and project names, and `make reset` refusing without a project name;
  - model endpoints: skipped when `VLLM_BASE_URL` is empty; `test_unreachable_endpoint_fails` always runs against its own unreachable address.
- **Restart check:** snapshots both Temporal databases' `schema_version` and `schema_update_history` and the namespace description, then requires them unchanged after a repeat `make up` on the running stack and after `compose stop` plus `make up`; requires the namespace job's log to show it ran without updating. Runs `make up` with a different `TEMPORAL_RETENTION` from the shell (96h, or 120h if 96h is configured) and requires the namespace to show it, then `make up` again and requires the configured retention back. Then seeds a Workflow and an object, runs `make down` and `make up`, and checks they survive and the migration revision is unchanged. Observed: a repeated `setup-schema -v 0.0` logs "Skip version upgrade" and changes no rows.
- **Unhealthy check:** stops `db`; `make status` must fail naming `db`, and `make smoke` must fail naming the database server; then starts `db` and runs `make up`, which must succeed.
- `HelloWorkflow` and `say_hello` live in `tests/support/hello.py`; they are test fixtures, not product code. The worker and client use the fixed identity `phase0-smoke-worker`, so recorded histories carry no hostname.
- **CI:** job `stack` copies `infra/.env.example` to `infra/.env` and runs `make up`, `make migrate`, `make smoke`, `make restart-check` and `make unhealthy-check`; it is required by `ci-ok`.

### Resource use

Observed idle memory for the four long-running services (`docker stats`, sum of the services): 275 MiB in the implementer's run, 368-408 MiB in the verification run, 349 MiB in three samples after the gate fixes (2026-11-11). It varies with activity; all are far under the 6 GB budget.

### Known limitations

- Single node, no TLS, no authentication on Temporal or the UI; placeholder passwords in `infra/.env.example`. Ports bind to `127.0.0.1` only.
- Database init runs only on a fresh volume; changed passwords or a failed init need `make reset`.
- GCS and Ceph RGW are documented in the README, not run or tested.
- Model tests run only where `VLLM_BASE_URL` is set; CI skips them.

## Phase 1: harness-in-Activity, single agent

**Describes:** branch `feat/44-evidence` (issue #44), the last of four implementation PRs (#46 foundations, #47 harness, #48 durability, this one). **Design:** [RFC](../rfcs/phase-1-single-agent.md) (accepted, with as-built notes), OpenSpec change `phase-1-single-agent`. **Evidence:** [docs/demos/phase-1.md](../demos/phase-1.md), [docs/benchmarks/](../benchmarks/), [docs/security/threat-model.md](../security/threat-model.md).

### Components

| Component | Where | What it does |
|---|---|---|
| Registry | `registry/` | Profile `default`, template `local-default@1` with its system prompt, MCP entry `sample-shop`, skill `order-desk`; `registry.lock` pins each template's hash. `PRAXIS_REGISTRY` points to another directory (the recovery tests) |
| CLI | `python -m orchestrator.cli task submit\|status\|output`; `make task`, `task-status` (the task, its attempts, its latest checkpoint and orders), `task-output`; `make demo-worker-loss` | Validates a request (capability fields rejected by name), mints task and request IDs, stores instructions and inputs as `task` blobs, starts `TaskWorkflow` with `REJECT_DUPLICATE` inside a `praxis.task.submit` span; `--request FILE` submits a raw JSON request |
| `TaskWorkflow` | `orchestrator/workflow.py`, queue `orchestration` | `resolve_capabilities` (template, effective budget = min of profile and template cap, template queue), `record_task` (the lasting duplicate guard), then harness turns until `done`, `needs_input`, a failure or an exhausted turn, token or wall-time budget; `complete_task` writes the `TaskResult` |
| `run_harness_turn` | `harness_activity/activity.py`, queue `tpl.local-default` | Refuses another template version (retryable, not counted); records the attempt; restores the newest checkpoint (turn, attempt, seq), truncating the session, or starts fresh; runs the harness; finishes with outputs as `audit` artifacts |
| Runner | `harness_activity/runner.py` (`OpenAIAgentsRunner`, the only runner; the Claude runner is deferred) | Template-only configuration; workspace tools, allow-listed `run_command`, read-only skills listed in the instructions, the sample MCP server (stdio, `tool_filter`); ends on `finish_task`; refused tools are returned to the model; spans for each model and tool call |
| Sample MCP server | `sample_mcp/` | Four read-only shop tools; `record_order` idempotent per task in one transaction; a test-only pause after an effect (`SAMPLE_MCP_PAUSE_FILE`) |
| Workers | `workers/main.py`, `workers/Dockerfile` (built locally, never published, non-root) | `make workers-up`: orchestrator, `worker-a`, `worker-b`. A template worker without a model URL refuses to start |
| Observability | `common/observability/`; profile `observability` | JSON logs with request, task, workflow, turn, attempt and worker IDs, from the CLI, the orchestrator and the harness (IDs attached when a record is created); OpenTelemetry through Temporal's interceptor, exported over OTLP only when configured; openai-agents tracing off; Prometheus metrics on port 9100: Activity duration, heartbeat lag, tokens, tool calls and tool errors per tool, checkpoint size and time; Prometheus v3.16.0 and Jaeger 2.23.0 |

### Durability as built

- **Checkpoints:** before every model call (seq 0 holds the instructions), and a final one carrying the `finish_task` report. Each holds a deterministic workspace snapshot (content-addressed, so an unchanged workspace adds no blob) and the session's item count. Observed positions for a two-step task: 1, 3, 5.
- **Heartbeats:** from the attempt row to the outcome, every `heartbeat_timeout / 3`, carrying the turn's live, cumulative usage (lost attempts included) and the latest checkpoint ID.
- **Recovery:** a lost worker's attempt times out after `heartbeat_timeout` (30 s; 5 s in the recovery tests), and the next attempt runs on any worker of the template queue. Observed on the Sparks: a killed `worker-b` container's task finished on `worker-a`, with each order recorded once and the conversation continued (4 session items at the stop, 40 at the end).
- **Fencing:** an attempt checks for a newer attempt before every model call and stops without writing anything; Temporal also cancels a resumed attempt whose heartbeat timed out.
- **Budgets:** the in-turn token check counts lost attempts' heartbeated usage, so a turn overruns by at most one model call.
- **Attempts:** at most 5 real attempts per turn, checked by the Activity; template-version refusals are not counted. A turn that fails for good (attempts exhausted, a capability or input error) closes its open attempt rows and reports its usage and real attempts in the error's details, which the `TaskResult` counts; `complete_task` closes rows still open (for example after `schedule_to_close`). Temporal's own attempts are unlimited within `schedule_to_close` (6 x `turn_timeout`).
- **Idempotency:** `record_order`'s key is the task ID, the tool and the canonical arguments; the `tasks` table rejects a reused task ID after Temporal's retention.

### Tests

| Suite | Where | Runs in |
|---|---|---|
| Unit (141) | `tests/test_*.py`: schemas and registry, `BlobStore` fake, observability, runner conformance with the real MCP subprocess and the fake model, `TaskWorkflow` time-skipping and replay | every PR (`tests`) |
| Integration | `tests/integration/`: `BlobStore` contract on SeaweedFS, persistence, traces down to model and tool calls, end-to-end tasks with in-process workers, `run_harness_turn` restore, budget, heartbeat and fencing tests | every PR (`stack`, `make smoke`) |
| Recovery (5) | `tests/integration/test_recovery.py`: SIGKILL or SIGSTOP of worker processes | every PR (`stack`, `make recovery-check`) |
| Containers | `make workers-check`: a scripted task through the worker containers | every PR (`stack`) |
| Benchmark (10 tasks) | `tests/benchmarks/`, `make benchmark` | on request, real model; baseline 10 of 10 (2026-11-12, re-recorded with inner turns) |

### Deviations from the RFC

| RFC | As built | Record |
|---|---|---|
| Both harness runners | `openai_agents` only; the Claude runner is deferred | decision log 2026-11-11 |
| Structured `output_type` ends a turn | the `finish_task` tool ends it (0 of 3 against 3 of 3 on the Sparks) | decision log 2026-11-11 |
| Recovery check kills worker containers | kills worker processes (SIGKILL or SIGSTOP); the demo kills a container with `docker kill` | decision log 2026-11-12 |
| A template queue named in Workflow code | the queue (with `PRAXIS_QUEUE_PREFIX`) is resolved by `resolve_capabilities` into `ResolvedTask` | this section |
| Up to 5 Temporal attempts per turn | unlimited within `schedule_to_close`, with 5 real attempts enforced by the Activity | informal durability review, F7 |

### Resource use

`docker stats` on 2026-11-12, with the stack, three workers, Prometheus and Jaeger running: about 940 MiB in total. Each worker uses 165-180 MiB.

### Known limitations

- No sandbox or egress control for `run_command`: it checks only a command's first word, then runs it with `sh -c`, so with `sh` allowed any command runs, including reads outside the workspace (threat model C5, R1, R2; Phase 5).
- `needs_input` is terminal; answering questions arrives in Phase 2.
- Metrics counters reset when a worker restarts.
- The Claude Agent SDK runner is not implemented.

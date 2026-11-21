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

**Describes:** tested code `9472d20d3b5e5d7cee1542ffedf9c25335defadd`, delivered by PR #53 at `45366585cdf15a253be6767965731039e6d0c97d` (issue #44). Independent review and verification passed; [coordinator closure](../reviews/phase-1/closure.md) links the assessed docs and merged evidence. **Design:** [RFC](../rfcs/phase-1-single-agent.md) (accepted, with as-built notes), archived OpenSpec change `2026-11-13-phase-1-single-agent`. **Evidence:** [original demo](../demos/phase-1.md), [independent model demo](../demos/phase-1-model-pr53.md), [combined verification](../reviews/phase-1/model-verification-pr53.md), [benchmarks](../benchmarks/), [threat model](../security/threat-model.md).

### Components

| Component | Where | What it does |
|---|---|---|
| Registry | `registry/` | Profile `default`, template `local-default@1` with its system prompt, MCP entry `sample-shop`, skill `order-desk`; `registry.lock` pins each template's hash. `PRAXIS_REGISTRY` points to another directory (the recovery tests) |
| CLI | `python -m orchestrator.cli task submit\|status\|output`; `make task`, `task-status` (the task, its attempts, its latest checkpoint and orders), `task-output`; `make demo-worker-loss` | Validates a request (capability fields rejected by name), mints task and request IDs, stores instructions and inputs as `task` blobs, starts `TaskWorkflow` with `REJECT_DUPLICATE` inside a `praxis.task.submit` span; `--request FILE` submits a raw JSON request |
| `TaskWorkflow` | `orchestrator/workflow.py`, queue `orchestration` | `resolve_capabilities` (template, effective budget = min of profile and template cap, template queue), `record_task` (the lasting duplicate guard), then harness turns until `done`, `needs_input`, a failure or an exhausted turn, token or wall-time budget; `complete_task` writes the `TaskResult` |
| `run_harness_turn` | `harness_activity/activity.py`, queue `tpl.local-default` | Refuses another template version (retryable, not counted); records the attempt; restores the newest checkpoint (turn, attempt, seq), truncating the session, or starts fresh; runs the harness; finishes with outputs as `artifact`-class artifacts (`audit` before migration 0007) |
| Runner | `harness_activity/runner.py` (`OpenAIAgentsRunner`, the only runner; the Claude runner is deferred) | Template-only configuration; workspace tools, allow-listed `run_command`, read-only skills listed in the instructions, the sample MCP server (stdio, `tool_filter`); ends on `finish_task`; refused tools are returned to the model; spans for each model and tool call |
| Sample MCP server | `sample_mcp/` | Four read-only shop tools; `record_order` idempotent per task in one transaction; a test-only pause after an effect (`SAMPLE_MCP_PAUSE_FILE`) |
| Workers | `workers/main.py`, `workers/Dockerfile` (built locally, never published, non-root) | `make workers-up`: orchestrator, `worker-a`, `worker-b`. A template worker without a model URL refuses to start |
| Observability | `common/observability/`; profile `observability` | JSON logs with request, task, workflow, turn, attempt and worker IDs, from the CLI, the orchestrator and the harness (IDs attached when a record is created); OpenTelemetry through Temporal's interceptor, exported over OTLP only when configured; openai-agents tracing off; Prometheus metrics on port 9100: Activity duration, heartbeat lag, tokens, tool calls and tool errors per tool, checkpoint size and time; Prometheus v3.16.0 and Jaeger 2.23.0 |

### Durability as built

- **Checkpoints:** before every model call (seq 0 holds the instructions), and a final one carrying the `finish_task` report. Each holds a deterministic workspace snapshot (content-addressed, so an unchanged workspace adds no blob) and the session's item count. Observed positions for a two-step task: 1, 3, 5.
- **Heartbeats:** from the attempt row to the outcome, every `heartbeat_timeout / 3`, carrying the turn's live, cumulative usage (lost attempts included) and the latest checkpoint ID.
- **Recovery:** a lost worker's attempt times out after `heartbeat_timeout` (30 s; 5 s in the recovery tests), and the next attempt runs on any worker of the template queue. Observed on the Sparks: a killed `worker-b` container's task finished on `worker-a`, with each order recorded once and the conversation continued (4 session items at the stop, 40 at the end).
- **Fencing:** an attempt checks for a newer attempt before every model call and stops without writing anything; Temporal also cancels a resumed attempt whose heartbeat timed out. Since DSH migration phase 01 the writes themselves are fenced; see that section.
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

## DSH migration phase 01: harness seam and registry

Plan: [docs/plans/2026-11-15-dsh-production-harness](../plans/2026-11-15-dsh-production-harness/plan.md), phase 01. As of phase 01 production ran only `openai_agents`; phase 02 (below) adds the DSH runner and supersedes the statements here about what phase 02 would add.

### Components

| Component | Where | As built |
|---|---|---|
| Session store | `harness_activity/session_store.py` | `SessionStore` protocol: `session`, `load(checkpoint | None)` (truncate to the checkpoint's position, or clear), `capture()` returning a `SessionSnapshot` (position, optional session blob ref). `SQLAlchemySessionStore` wraps `SQLAlchemySession`; `run_harness_turn` uses only the store. A snapshot with a session ref raises until the DSH migration's phase 02 adds checkpoint columns. |
| Fence | `common/persistence/repositories.py` | `start`, the fenced checkpoint insert, the fenced finish and `assert_current` each take `pg_advisory_xact_lock(hashtext(task_id))`, then check in the same transaction that no newer (turn, attempt) row exists. A stale write raises `FenceRejected`; the Activity raises `Superseded`, writing nothing. A template-version refusal takes the same lock and inserts an `outcome = 'refused'` row (no newer-attempt check), so it fences older attempts. Artifact blobs are uploaded after `assert_current` and referenced only through the fenced finish. |
| Registry | `registry/loader.py`, `registry/templates/local-dsh.yaml`, `registry/profiles/dsh.yaml` | `dsh` is a `Harness` value. Profile and template harness must match at load. `dsh` templates need `concurrency_per_pod: 1` and `context_window`. `local-dsh@1` is locked. Workers refuse non-`openai_agents` templates, so no worker serves `tpl.local-dsh` until phase 02: a `dsh` task's turn waits and then fails at `schedule_to_close` (6 x `turn_timeout`, 1 h). |
| Events | `common/schemas/events.py`, `harness_activity/events.py` | `AgentEvent` schema; `EventSink` with `NoOpSink` and `MemorySink`; `AttemptEvents` numbers one attempt's events and delivers them in `seq` order under a lock. No runner emits events yet. |
| Isolation probe | `infra/dsh/isolation-probe.sh` | Manual probe (run command in its header); results in the plan's notes.md#d3. Per-attempt cgroup freeze/kill and mount namespaces need `SYS_ADMIN`. At phase 01 the user-namespace check failed. Since phase 02, running the header's flags in the DSH image (`praxismesh-dsh:dev`, which has the launcher's seccomp wrapper) passes all 13 checks; in the plain base image the header names, `command_userns_blocked` still fails. |

### Tests

- Unit: `uv run pytest` (registry, events, the conformance suite through a session store fixture).
- Integration (Postgres, stack up): `uv run --env-file infra/.env pytest -m integration tests/integration/test_persistence_phase1.py tests/integration/test_harness_activity.py` (fence concurrency, refusal rows, Activity-level fencing, store contract).

## DSH migration phase 02: DSH runner and worker pair

Plan: [docs/plans/2026-11-15-dsh-production-harness](../plans/2026-11-15-dsh-production-harness/plan.md), phase 02 (requirements R5-R18). `local-dsh` turns run on `DshRunner`; the `default` profile still runs `openai_agents` until phase 03. Phase 03 (below) switches `default` and supersedes the statements here about what phase 03 would add.

### Components

| Component | Where | As built |
|---|---|---|
| Worker pair | `infra/docker-compose.yml` (Compose profile `dsh`: `dsh-a`, `worker-dsh-a`, volume `dsh-attempts-a`) | `dsh-a` has no network, a read-only root, no credentials, `cgroup: private`, `SYS_ADMIN` and `apparmor:unconfined`; `worker-dsh-a` serves `tpl.local-dsh` and reaches the launcher at `DSH_CONTROL` on the shared tmpfs volume. Start (needs a model endpoint in `VLLM_BASE_URL`, or the worker refuses at start). The `:dev` image tags are shared by every checkout on a host, and `worker-dsh-a` has no build of its own (the `orchestrator` service builds `praxismesh-worker:dev`), so build both images first: `docker compose -p <project> --env-file infra/.env -f infra/docker-compose.yml --profile dsh build orchestrator dsh-a`, then `... --profile dsh up -d dsh-a worker-dsh-a`. |
| Launcher | `infra/dsh/launcher.py` | Root in the DSH container. One control connection per attempt (newline JSON: `digests`, `open`, `start`, `exec`, `freeze`, `thaw`, `members`, `poll`, `stop`); a closed connection destroys the attempt. Each attempt gets a cgroup; its runtime (UID 1000) and commands (UID 4242, no capabilities, `no_new_privs`, seccomp blocking user namespaces) run in their own mount and IPC namespaces with private `/tmp`, `/run` and `/dev/shm`, seeing only their attempt. `stop` thaws, sends SIGTERM, kills the cgroup after the grace and removes the tree (`keep_tree` keeps it after a step-limit stop). Reaps leftovers at start; remembers attempts it could not clean (`dirty`, reported with `digests`). |
| Runtime pin | `infra/dsh/pins.py`, `harness_activity/dsh/pins.py`, `registry/registry.lock` | The runtime digest covers the hash-pinned requirements and the launcher, driver, bridge and pins code; the launcher computes its report at start-up. The worker checks it at start and before every attempt (`DshRunner.check`). |
| Runner | `harness_activity/dsh/runner.py` | Opens the attempt tree (`workspace`, `home`, `ipc`, `config`, `tmp`), starts the DSH driver through the launcher, polls it and stops it at the deadline, on cancel, on abort, or 2 s after a step-limit denial. Classifies the end (`harness_activity/dsh/policy.py`) into a result or a `RunnerFailure`. Refuses attempts (`Unserviceable`) when the pin differs or the container is dirty or unreachable. |
| Gateway and ledger | `harness_activity/dsh/gateway.py`, `ledger.py`; `usage_ledger` table | A Unix-socket HTTP gateway in the attempt tree. Checks the attempt key, model and exact tool catalog; runs the barrier before every request after the first; writes a fenced `usage_ledger` row before dispatch and settles it with the response's usage; caps `max_tokens` at 2048; emits `token` events. |
| Barrier | `harness_activity/dsh/barrier.py` | Before a request: the newest tool-call ID must be in the session files; freeze, capture workspace and session blobs, commit through the fence, thaw. |
| Executor and tools | `harness_activity/dsh/executor.py`, `harness_activity/tools.py`, `infra/dsh/mcp_bridge.py` | The worker runs the granted file, shop and MCP tool bodies for DSH's MCP client; `run_command` runs in the attempt cgroup through the launcher. File tools never follow a symbolic link. Emits `tool_call`/`tool_result` events. |
| Session store | `harness_activity/dsh/session.py` | The DSH home is a separate session blob (`session_ref`, `session_digest` on `checkpoints`); a restore replaces the whole home; `session_position` stays 0. |
| Usage accounting | `harness_activity/activity.py`, `common/persistence/repositories.py`, `orchestrator/activities.py` | Turn usage is cumulative over attempts and rebuilt from the ledger. Each unsettled request is charged `context_window` + 2048 and makes usage unknown (`usage_known = false`), when the next attempt opens, when the turn fails or is cancelled, and in `complete_task`. For DSH turns (the only ones with ledger rows), an attempt row's unobserved usage is set to NULL when the attempt finishes or fails, when the next attempt opens, or when the turn or task is closed. Until then a row still `started`, or one a newer start or refusal marked `lost`, holds its creation default 0; refused rows carry no usage. |
| Worker start | `workers/main.py` | Chooses the runner from `template.harness`. A DSH worker that cannot serve (pin, dirty or unreachable container) refuses at start (exit 1, `CapabilityError`) or, during a turn, records an uncounted `refused` row and shuts down (exit 3). |
| Workflow | `orchestrator/workflow.py` | A cancelled turn waits for its Activity to record the attempt (`WAIT_CANCELLATION_COMPLETED`); a turn that fails for good keeps `usage_known`. |

### Tests

- Unit: `uv run pytest`.
- Integration (stack up, Docker, `infra/.env`): `uv run --env-file infra/.env pytest -m integration tests/integration/test_dsh_launcher.py tests/integration/test_dsh_activity.py tests/integration/test_dsh_usage.py tests/integration/test_dsh_capabilities.py tests/integration/test_dsh_outcomes.py`, and `tests/test_runner_conformance.py` with `-m integration` for the `dsh` runner. They need no model endpoint. The launcher, activity, capability and outcome tests build the DSH image and start their own DSH containers; the activity, capability and outcome tests also use the deterministic fake model. `test_dsh_usage.py` uses a stub runner and the database only.

### Known limits

- At phase 02, `default` still ran `openai_agents`; phase 03 (below) added the switch, the `openai` profile and the second DSH pair.
- `praxismesh-worker:dev` and `praxismesh-dsh:dev` are fixed tags: building in one checkout retags them for every other checkout on the host.
- Deferred review items (plan notes.md#rollout): an `unresolved usage` denial starts no exit timer; a stale attempt's usage charge is unfenced; launcher `poll` replies have no timeout.

## DSH migration phase 03: acceptance and default switch

Plan: [docs/plans/2026-11-15-dsh-production-harness](../plans/2026-11-15-dsh-production-harness/plan.md), phase 03 (requirements R4, R19, R20). `default` runs on DSH; `openai_agents` stays selectable through `openai`. Operations: [docs/operations/runbook.md](../operations/runbook.md).

### Components

| Component | Where | As built |
|---|---|---|
| Profiles | `registry/profiles/` | `default` and `dsh` resolve to `local-dsh` (`harness: dsh`); `openai` resolves to `local-default` (`harness: openai_agents`). The registry lock pins templates and the DSH runtime digest, not profiles, so a profile switch leaves it unchanged. |
| Worker pairs | `infra/docker-compose.yml` (Compose profile `dsh`) | Two pairs, `dsh-a`/`worker-dsh-a` and `dsh-b`/`worker-dsh-b`, each with its own attempt volume (`dsh-attempts-a`, `dsh-attempts-b`) that no other service mounts. `make workers-up` builds and starts the orchestrator, `worker-a`, `worker-b` and both pairs; `make workers-check` submits on `openai` against the fake model. |
| Benchmark | `tests/benchmarks/run.py`, `tests/support/dsh_container.py` | `--profile` (default `default`) takes the template from the profile; for a `dsh` template it builds the DSH image and starts its own paired container. Results go to `docs/benchmarks/<date>-<profile>.{md,json}`, rewritten as each task finishes; `--out` writes elsewhere and is not judged against the baseline. An unknown `--only` ID is refused, and a subset must use `--out`; `--baseline` takes an `openai_agents` profile only. If the worker stops serving, the run terminates the waiting task and stops, unjudged. Containers it starts carry the label `praxismesh.dsh-test`. Same-day results (2026-11-17, [demo record](../demos/general-dsh-production-harness-03.md)): `dsh` and `default` (then `openai_agents`) each passed 10 of 10. |
| Licence notices | `docs/licences/dsh/`, `.github/scripts/check_dsh_licences.py` | The licence files of each distribution pinned in `infra/dsh/requirements.txt`. The CI `lint` job fails on a pin with no notices, an empty notice directory, or notices for a distribution no longer pinned; `export` refreshes them from the DSH image. The offline link check skips `docs/licences`. |

### Tests

- Unit: `uv run pytest` (profiles, the Compose pairs, the benchmark report, the licence check).
- Benchmark (real model, Docker): `make benchmark ARGS="--profile dsh"` and `make benchmark ARGS="--profile openai"`.
- `make demo-worker-loss` submits on `openai` (override with `PROFILE=`), so the Phase 1 demo still exercises `openai_agents`.

### Known limits

- Rebuilding the worker image restarts the DSH workers too: an attempt in flight is lost and retried, and that task reports `usage_known: false`.
- The deferred review items of phase 02 remain (see above).

## Phase 2 events: the event table and `agentctl tail`

Plan: [docs/plans/2026-11-18-phase-2-agent-events](../plans/2026-11-18-phase-2-agent-events/plan.md) (requirements R1-R9). Decision: [ADR-0009](../adr/0009-use-a-postgresql-event-table-for-agent-events.md). Operations: [runbook, Agent events](../operations/runbook.md#agent-events).

### Components

| Component | Where | As built |
|---|---|---|
| Event tables | `common/persistence/migrations/versions/0005_agent_events.py` | `event_logs` (per workflow: next offset, retained base), `agent_events` (keyed by workflow and offset; columns mirror `AgentEvent`), `event_batches` (batch IDs seen in the last 600 s). All are listed in `APP_TABLES`; since migration 0007 `event_logs` and `agent_events` carry retention class `transcript` and `event_batches` `ephemeral` (`task` before). |
| Fence | `common/persistence/fence.py` | ADR-0007's per-task advisory lock, newer-turn-or-attempt check and `FenceRejected`, used by every fenced write in `repositories.py` and by the event table. |
| Transport | `common/events/` | The interface (`publish`, `read`, `latest`, `prune`), the reader rule (`Expired` before pruned offsets, on a jump during a read; a repeat raises), the in-memory reference and `TableTransport`. A publish takes the task lock and fence check, then the workflow's `event_logs` row lock, dedupes the batch ID, inserts, advances the offset and `NOTIFY`s `agent_events`. A following reader `LISTEN`s on its own autocommit connection and polls every 1 s. |
| Publisher | `harness_activity/events.py` (`BatchingPublisher`) | One per attempt. Cuts batches of at most 64 when full, 200 ms after the oldest buffered event's emit time, or at close; one publish at a time in `seq` order; a cut batch is frozen and re-sent unchanged after a database error (backoff 0.25, 0.5, 1 s once per batch, then one try per trigger, also while closing); a refusal stops it. `close()` runs once, is shielded from its caller's cancellation, and bounds the final flush at 10 s (`CLOSE_TIMEOUT_S`) in a task of its own. |
| Activity | `harness_activity/activity.py` | `run_harness_turn` creates the attempt's `AttemptEvents` over the publisher and passes it to `HarnessRunner.run`. It emits `reset` first, right after the checkpoint lookup and before opening the attempt (a failure before then still stores a `reset`), and `status` before the final flush. Both success paths, the normal one and the restore short-circuit, reach `_finish`, which flushes first: a refusal raises `Superseded` before the finish checkpoint, artifacts and outcome; a flush that fails for good raises the retryable `EventsUnavailable`. Failure and cancel paths store their events and re-raise the original error. Workers publish to `TableTransport`; without a transport (unit tests) events go nowhere. |
| Runners | `harness_activity/runner.py`, `harness_activity/dsh/` | `openai_agents` emits `token`, `tool_call` and `tool_result` through its run hooks (parallel calls to one tool keep their own call numbers) and `refused` pairs for tools the template does not grant, as DSH does from its gateway and executor; `DshRunner` no longer takes a sink. Payloads hold counts, names (refused names capped at 64 characters), IDs and statuses only. |
| CLI | `agentctl`, `orchestrator/cli.py` | `./agentctl tail TASK [--after N] [--no-follow]` and `./agentctl events prune --task T (--below N \| --older-than 7d)`. Each line is flushed. `tail --follow` stops after one more read once Temporal reports the Workflow closed or not found; other Temporal errors are logged and it keeps following. `--no-follow` reads the table only. |

### Data flow

```text
runner (DSH / openai_agents) --emit--> AttemptEvents --> BatchingPublisher
    --publish (fence, event_logs row lock, batch dedup, NOTIFY)--> agent_events
agentctl tail --LISTEN agent_events + 1 s poll--> reads offsets above N (reader rule)
```

### Failure and recovery

- A superseded attempt's publish is refused; the attempt stores nothing more and raises `Superseded` at its final flush (or earlier at its next model call).
- A lost reply re-sends the same batch ID, which is stored once (within 600 s).
- A worker killed mid-turn loses its buffered events (up to 64, or 200 ms worth); the retried attempt opens with a `reset` naming the checkpoint it restored from.
- A reader asking below the retained base gets `Expired(base)` first, then continues from the base.

### Tests

- Unit: `uv run pytest` (`tests/test_event_publisher.py`, `tests/test_event_transport.py`, the CLI tail and prune tests, and the runner conformance event test for `openai_agents`; its `dsh` case is an integration test, `uv run pytest -m integration tests/test_runner_conformance.py`, which CI's stack job does not run).
- Integration: `tests/integration/test_event_table.py` (the spike's shared suite on the table and the in-memory reference, the fence, lock order, the horizon, `older_than`, a notify during a fetch); `tests/integration/test_harness_activity.py` (reset and status, a retried attempt, refused final flushes on both success paths, a runner failure, a cancellation); `tests/integration/test_dsh_activity.py` (the DSH event stream).
- Load: `python -m tests.benchmarks.event_load` (results in `docs/benchmarks/2026-11-18-event-load.json`: at 499eb63: display p95 0.209 s, publish p95 10 ms, database CPU 2.9-3.5% fenced against 3.4% unfenced, both at noise level).
- Demo: `sh infra/demo/phase-2-events.sh` ([demo record](../demos/phase-2-events.md)).

### Known limits

- Pruning is manual (`events prune`) until Phase 3A's retention; a finished workflow keeps its last 600 s of batch rows until then.
- A stale attempt still running after its task completed can publish after `tail`'s final read; the fence refuses only when a newer attempt exists.
- `status` reports the runner's result, not the recorded outcome: an attempt refused at its finish writes may have stored `status: done`.
- One global `NOTIFY` channel; every follower's connection receives every workflow's notification (ADR-0009).

## Phase 2 messaging: the inbox, the comms MCP server and waiting tasks

Plan: [docs/plans/2026-11-18-phase-2-events-and-comms](../plans/2026-11-18-phase-2-events-and-comms/plan.md) (requirements R10-R33). Operations: [runbook, Messaging between tasks](../operations/runbook.md#messaging-between-tasks).

### Components

| Component | Where | As built |
|---|---|---|
| Message tables | `common/persistence/migrations/versions/0006_task_messages.py` | `task_messages` (one row per message, question or reply, with its status, `claimed_turn` and `notice_turn`; body at most 16,384 characters; unique idempotency key), `task_inbox` (per task: `sleeping`) and `message_wakes` (at most one pending wake per recipient Workflow). |
| Comms role | `infra/db/roles.sh`, `make db-roles` | `praxis_comms` gets `SELECT, INSERT, UPDATE` on `task_messages`, `SELECT, INSERT` on `message_wakes`, and `SELECT` on `tasks`, `task_attempts` and `task_inbox`, besides `CONNECT` on the database and `USAGE` on `public`; it holds no other table grant of its own (it can read what PostgreSQL grants to `PUBLIC`, such as catalog tables). `init.sh` runs `roles.sh` on a fresh volume when `PRAXIS_COMMS_DB_PASSWORD` is set. |
| Inbox repository | `common/persistence/messages.py` (`MessageRepository`) | `send`, `ask`, `read_claimed` and `blocking_finish` are attempt writes: the task lock and ADR-0007's fence check, then a per-request advisory lock. `claim` and `end_task` are the orchestrator's: the request lock only. Messages go only to tasks of the sender's request that have not ended; a refusal is stored as a `rejected` row with its reason; an identical repeat (same task, turn, tool and arguments) stores nothing. A reply must answer an open question addressed to the replier and go to its asker. A send to a sleeping recipient adds a wake row and `NOTIFY message_wakes`. |
| Comms MCP server | `comms_mcp/`, `registry/mcp/comms.yaml` | `send_to_agent`, `ask_agent` (`deadline_seconds` at least 1, default 300; a longer deadline is cut to the profile's `max_ask_wait`, default 10 min), `post_status` (a stage and an optional 0-100 progress) and `get_task_context` (the request's tasks and the caller's undelivered messages). It runs as a stdio subprocess per attempt, started by the worker, and takes its identity from `PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT`, never from arguments. The worker sets them after the catalog entry's `env` and `secret_env`, and the registry loader refuses an entry that names them or `PRAXIS_MAX_ASK_WAIT` (issue #89). Refusals return MCP errors. Granted by `local-dsh` v2 and `local-default` v2. |
| Dispatcher | `orchestrator/dispatcher.py`, started by `workers/main.py` beside the orchestrator worker | `LISTEN`s on `message_wakes` and polls every 1 s. For each row, in that row's own transaction, it deletes the row and then sends the `inbox` Signal (5 s RPC timeout); a failed Signal rolls the delete back, so the row waits for the next poll, and for a closed or missing Workflow the row is dropped (logged). Its connection is retried until it is cancelled. |
| Waiting Workflow | `orchestrator/workflow.py` (`TaskWorkflow`, patch `phase2-wait`) | After a `waiting` turn it claims its inbox (`claim_inbox`): with rows it runs a woken turn at once; with none it sleeps until an `inbox` Signal, its earliest open question's deadline, its idle timeout (only with no open question) or its wall-time deadline. After a Signal or a question's deadline it claims again; at the idle timeout it ends `succeeded` without a claim; `end_task` then marks its unread messages `undelivered` and cancels unanswered questions to it, waking their askers. Woken turns count against `max_wakes`, other turns against `max_turns`. At the wall-time deadline one last claim decides the ending: `succeeded` with no open question, `failed` ("wall-time budget exhausted") with one. A run continues as new when Temporal suggests it or past 1,000 events, carrying its state in `TaskStart.carried`. Every ending after the task is recorded runs `complete_task`, retried until it succeeds (except for the non-retryable error types) and run once more if a cancel interrupts it; a failure or cancel during `resolve_capabilities` or `record_task`, before the task is recorded, ends the Workflow without it. |
| Harness | `harness_activity/activity.py`, `tools.py`, `runner.py`, `dsh/executor.py` | A woken turn's input lists what its claim assigned (`render_inbox`), read once. `finish_task("done" \| "needs_input")` is refused while the task has an open question or an unread reply (R19), on both runners; after the run the Activity checks again, so a finish beside a same-step `ask_agent` becomes `continue`. A `waiting` turn keeps its outputs. `post_status` results become `status` events (`source: agent`). |
| CLI | `orchestrator/cli.py` | `./agentctl task submit --join REQ ...` adds a task to request `REQ`, which must already have a task. |

### Data flow

```text
agent tool call --stdio--> comms_mcp --praxis_comms--> task_messages (+ message_wakes, NOTIFY)
dispatcher --LISTEN / 1 s poll--> delete wake row, Signal `inbox` --> TaskWorkflow wakes
TaskWorkflow --claim_inbox--> rows assigned to the next turn --> run_harness_turn reads them
any ending --complete_task--> end_task: questions cancelled, unread rows undelivered, askers woken
```

### Failure and recovery

- An attempt lost after a send reruns the same step; the identical send stores nothing (`tests/integration/test_messaging_failures.py`, a SIGKILLed DSH worker).
- A recipient attempt lost after its claim reruns the same turn and reads the same rows; no later turn gets them.
- The dispatcher down: wake rows wait in `message_wakes`; question deadlines, idle timeouts and wall time still fire. A crash before a row's commit keeps the row.
- The database down: claims retry until the wall-time deadline; `complete_task` retries until it succeeds, so the task's messages are closed once the database returns.
- A cancelled task runs `complete_task`; its open questions are cancelled and their askers are woken and told.

### Tests

- Unit: `uv run pytest` (`tests/test_task_workflow_waiting.py` in Temporal's time-skipping server; `tests/test_message_schemas.py`; `tests/test_fake_model_scripts.py`; `tests/test_dispatcher_supervision.py`; the runner conformance tests for the refused finish and MCP status results).
- Integration: `tests/integration/test_messages.py` (the repository), `test_comms_mcp.py` and `test_comms_role.py` (the server and its role), `test_dispatcher.py`, `test_harness_activity.py` (woken turns, the finish checks), and the acceptance suites on DSH: `test_two_agents.py` (A asks B, B wakes and replies, A resumes), `test_messaging_failures.py` (timeout, cross-request refusal, killed worker, cancelled recipient), `test_messaging_endings.py` (refused finish, undelivered message) and `test_messaging_history.py` (100 back-to-back wakes, 50 messages in one turn).
- Demo: [demo record](../demos/phase-2.md).

### Deviations from the plan

- The carried state of a continued run travels in `TaskStart.carried`, not as a second `run` argument (plan decision log, D11), because Temporal drops type hints when a start passes fewer arguments than `run` declares.
- The test fake model also fills tool arguments from the task's input (`${input:REGEX}`, plan decision log, D16), because a woken recipient learns a question's ID from its input.
- `finish_task` is checked again after the run, beside its in-tool check (R19, implementation review F97), because parallel tool calls on `openai_agents` can run it before a same-step `ask_agent` commits.
- The dispatcher commits each wake row on its own rather than per batch (D6, implementation review F99 and F136), so a send is never dropped or held for a whole batch.
- The body limit is 16,384 characters, not bytes (D6 says 16 KB; accepted in implementation review F118).

### Known limits

- The body limit counts characters, not bytes.
- A Workflow that is terminated (not cancelled) never runs `complete_task`; its task stays `running`.
- Sends during one sleep can add several wakes before the next claim; each is only a hint.
- A refusal is replayed for an identical call in the same turn, even if its cause has cleared.
- Rows a woken turn read stay `read` if that turn then fails for good.
- On `openai_agents`, `sh` runs in the worker container and can read the comms database URL from its environment; DSH runs commands in its isolated container.

## Phase 3A persistence: blob references, retention and removal (draft)

Draft: phases 01 and 02 of the [Phase 3A persistence plan](../plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md). Phase 03 adds backup, restore and `reconcile`, and completes this section. Operations: [runbook, Removing data](../operations/runbook.md#removing-data).

### Components

| Component | Where | As built |
|---|---|---|
| Reference index | `common/persistence/refs.py`, migration 0007 | `blob_refs`: one row per holder and blob (a row's table, key and column, or a task's own upload), with its task, request, class and a removal mark. Each writer indexes in the holder's transaction (`index_refs`); `RecordingBlobStore.put` writes the upload reference. Marked rows are never deleted. Expiry is computed from the class and the task's `ended_at`, never stored. |
| Classes and lifetimes | `common/persistence/retention.py` | `ephemeral` 1 day from the write; `checkpoint` 7, `transcript` 30 and `artifact` 90 days from the task's end; `audit` kept. Each table's class is `TABLE_CLASS`; each blob's class comes from where it is named (`REFERENCE_CLASS`). |
| Audit log | `audit_log`, `common/persistence/audit.py` | Append-only (a trigger refuses `UPDATE` and `DELETE`); removal tombstones, actor `cli:<OS user>`. |
| Removal engine | `common/persistence/removal.py` | One transaction per batch: task locks (taken without waiting), `blob_objects` row locks in key order, the row changes, references marked, blobs left with no live reference marked, the tombstone. Then, per marked blob, the bucket step: under its row lock, delete the object only if the mark still stands, then set `bucket_deleted_at`. A run first finishes blobs an earlier run left marked. A dry run is one transaction, rolled back. `run_lock` holds `pg_advisory_lock(3, 0)` for a whole run and fails at once if another holds it. |
| Removals | `orchestrator/lifecycle.py`, `orchestrator/cli.py` | `agentctl gc`, `agentctl request delete REQ [--force]` and `agentctl events prune`, each with `--dry-run`. `gc` refuses while any stored reference is unindexed; it asks Temporal before expiring the uploads of a task with no row. `request delete` holds the request lock (session form) for its run, fixes its task list in its first tombstone, fences each task with a `deleted` attempt row, marks its uploads under the task locks, then deletes checkpoints and task rows, prunes events and redacts content (notes.md#redact). |
| Expired reads | `RecordingBlobStore.get`, `stream`, `stat` | Raise `BlobExpired`, naming the removal date, when `blob_objects.removed_at` is set; `agentctl task output` reads through it. |
| Events | `common/events/table.py` | `prune` takes the caller's connection, a row limit and the operation that marks the pruned events' references; events leave only through it, so `tail` reports *expired*, not a gap. |

### Failure and recovery

- A run killed inside a batch leaves nothing of that batch; one killed after a commit leaves the batch and its tombstone, and the next run deletes its marked objects first (`tests/integration/test_removal_kills.py`).
- A `put` of removed bytes clears the mark before the bucket step, which then keeps the object; after the bucket step it uploads them again. A deleted task's late upload revives nothing.
- An attempt writing a message holds its task lock and then waits for the request lock a delete holds; the delete's first batch takes task locks without waiting, so it releases the request lock and retries instead of deadlocking.

### Tests

- Integration, each on a scratch database with an in-memory bucket: `test_removal_engine.py`, `test_revive.py`, `test_event_prune.py`, `test_gc.py`, `test_request_delete.py`, `test_removal_kills.py`; `test_blob_expired.py` on the stack database. Session IDs on both runners: `test_task_e2e.py`, `test_dsh_outcomes.py`.
- Unit: `tests/test_cli.py` (`gc`, `request delete`).

### Known limits

- Temporal keeps each turn's summary, questions and outcome for `TEMPORAL_RETENTION` (72 hours) after a delete, and in backups taken before.
- Removal is manual; nothing schedules `gc`.

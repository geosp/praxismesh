# Phase 0 demo evidence

Evidence for the Phase 0 demo in [docs/plan/phases/phase-0.md](../roadmap/phases/phase-0.md), following the demo steps in the [RFC](../rfcs/phase-0-local-infrastructure.md#testing-and-demo). Items are marked pass only with observed output. **Status: all six steps pass in the implementer's run; independent verification (`verify-phase`) is still to come.**

## Environment

| Item | Value |
|---|---|
| Code | `aa3889b` on `feat/34-local-stack` (issue #34) |
| Date | 2026-11-11 |
| Workstation | x86_64, about 15 GB RAM, no GPU; Docker 29.9.2, Compose v5.7.0 |
| Images | ParadeDB `0.26.6-pg16`, Temporal Server and admin tools `1.32.2`, Temporal UI `2.58.1`, SeaweedFS `4.53` (digests in `infra/docker-compose.yml`) |
| Model endpoint | vLLM 0.32.0 on the DGX Spark pair, served names `qwen3.8-flash-next` and `spark`; the URL is in the git-ignored `.env` only |
| Run by | coding agent, in the implementation session |

## Steps

| # | Step | Expected | Observed | Result |
|---|---|---|---|---|
| 1 | `make reset`, `make up` from a clean volume; `make status`; `make up` again | All services healthy, both jobs exit 0; the second `make up` succeeds | `stack is up: Temporal 127.0.0.1:7233, UI http://127.0.0.1:8080, S3 http://127.0.0.1:8333, DB 127.0.0.1:5432` twice. `make status`: `db`, `s3`, `temporal`, `temporal-ui` `Up (healthy)`; `temporal-schema` and `temporal-namespace` `Exited (0)`; `all services healthy` | Pass |
| 2 | `make migrate`, `make smoke`; the hello Workflow in the Temporal UI | Migrations reach head; the hello Workflow completes and is visible | `Running upgrade -> 0001`, `0001 -> 0002`; second `make migrate` applies nothing. `make smoke`: `15 passed` (with the model endpoint set, step 3). The UI's API (`/api/v1/namespaces/default/workflows`, query `WorkflowType="HelloWorkflow"`) lists the executions with status `WORKFLOW_EXECUTION_STATUS_COMPLETED` | Pass |
| 3 | A real prompt to each vLLM endpoint | Both API styles answer | `/v1/models`: `['qwen3.8-flash-next', 'spark']`. `/v1/messages` (`stop_reason` `end_turn`): "Temporal is an open-source workflow orchestration platform used to build, run, and scale reliable applications and services by making complex distributed workflows fault-tolerant, observable, and easy to maintain." `/v1/chat/completions` (`finish_reason` `stop`): "Temporal is an open-source platform for building reliable, fault-tolerant applications by durably executing long-running workflows, ensuring they can recover and continue from their exact state after crashes, restarts, or infrastructure failures." The model tests (`test_model_listed`, `test_messages_endpoint`, `test_chat_endpoint`) passed against the same endpoint | Pass |
| 4 | Workflow and object survive `make down` / `make up` | Same Workflow and object after restart; migrations unchanged | `make restart-check`: `seeded Workflow phase0-restart-b6df50dbc325 and s3://phase0-restart-b6df50dbc325/seed.txt` ... `PASS (revision 0002, Workflow and object survived)`, 33 s | Pass |
| 5 | Failure cases | Each names what is wrong | See below | Pass |
| 6 | `docker stats`; clean up | Under 6 GB | `temporal-ui` 12.6 MiB, `temporal` 110 MiB, `db` 70.9 MiB, `s3` 81.5 MiB: about 275 MiB in total (other runs: 349-408 MiB; see the as-built overview) | Pass |

### Step 5: failure cases

| Case | Command | Observed |
|---|---|---|
| `infra/.env` missing | `make up ENV_FILE=infra/.env.absent` | `error: infra/.env.absent is missing; create it with: cp infra/.env.example infra/.env.absent`; the script exits 1 and `make` exits 2 |
| Database stopped | `docker compose --env-file infra/.env -f infra/docker-compose.yml stop db` (the project name comes from `infra/.env`), then `make status` and `make smoke`. Automated since the gate fixes as `make unhealthy-check` | `make status`: `unhealthy or stopped: db`. `make smoke`: `RuntimeError: database server (service db) at 127.0.0.1:5432 is unreachable; check make status: [Errno 111] Connect call failed ('127.0.0.1', 5432)` |
| Model endpoint unreachable | `make smoke VLLM_BASE_URL=http://127.0.0.1:9` | `EndpointUnreachableError: model endpoint http://127.0.0.1:9 is unreachable: ConnectError('[Errno 111] Connection refused')` for each model test; `3 failed, 12 passed` |

Also covered by tests (`tests/integration/test_env_check.py`): an unset required variable (`error: APP_DB_PASSWORD is not set in ...`) and a model name containing `/`.

Steps 3 and 4 were run with ad hoc commands; the README's "Trying the services by hand" now documents equivalent ones. The Temporal UI evidence in step 2 is the UI's own HTTP API, not a screenshot.

The [verification run](../reviews/phase-0/verification.md) at `075791a` repeated every step with its own observed output.

## Findings during implementation

Recorded in the [as-built overview](../architecture/overview.md#phase-0-local-infrastructure) and the decision log:

- `pg_search` 0.26 requires the `vector` extension, so init creates it with `CASCADE`. The first attempt failed; the init marker kept `db` unhealthy after Docker restarted it on the half-initialised volume, as designed (follow-up 2, Nit F4a).
- ParadeDB's bootstrap installs eight extensions into `template1`; all PraxisMesh databases are created from `template0`.
- The Temporal server image has no `temporal` CLI; its health check uses the frontend's HTTP API.
- Compose v5.7's `up --wait` treats a one-shot job that exited 0 as a failure; `make up` waits on the long-running services and checks job exit codes itself.

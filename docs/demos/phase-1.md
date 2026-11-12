# Phase 1 demo evidence

Evidence for the Phase 1 demo checklist in [docs/plan/phases/phase-1.md](../plan/phases/phase-1.md), following the demo in the [RFC](../rfcs/phase-1-single-agent.md#testing-and-demo). Items are marked pass only with observed output. **Status: all demo items pass in the implementer's run; independent verification (`verify-phase`) is still to come.**

## Environment

| Item | Value |
|---|---|
| Code | branch `feat/44-evidence` (issue #44), after PRs #46, #47 and #48 |
| Date | 2026-11-12 |
| Workstation | x86_64, about 15 GB RAM, no GPU; Docker 29.9.3, Compose v5.7.1 |
| Model | the DGX Spark endpoint: vLLM 0.32.0, served model `spark` (qwen3.8-flash-next); the URL is only in a git-ignored `.env` |
| Template | `local-default@1` (`sha256:6122e8de…`), harness `openai-agents` 0.24.0 |
| Workers | `make workers-up`: the orchestrator and two template workers (`worker-a`, `worker-b`) as containers |
| Observability | `make observability-up`: Prometheus v3.16.0 and Jaeger 2.23.0; `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318` for the CLI |
| Run by | coding agent, in the implementation session |

## Checklist

| # | Demo item (phase-1.md) | Result |
|---|---|---|
| 1 | A documented sample task uses its approved skill and MCP tool and produces a visible file plus a validated `TaskResult` | **Pass** (step 1) |
| 2 | During a second task, after an acknowledged checkpoint, the worker is terminated; a replacement resumes and finishes without losing edits or conversation context | **Pass** (step 2 with a container; edits: automated test) |
| 3 | A side-effect step is not duplicated on retry; an unauthorized skill or tool request is explicitly rejected | **Pass** (steps 2 and 3) |
| 4 | The completed output and the same logical task reference before and after worker replacement | **Pass** (step 2) |
| 5 | Evidence and reproduction steps saved here | **Pass** |

## Step 1: the sample task

```bash
make task PROMPT="We need to order 3 units of SKU-1 and 2 units of SKU-2. Use the order-desk skill: look up prices and stock, record each order, and write order-summary.md." OUTPUT=order-summary.md
make task-output ID=task-0cf188e1-6af6-41b5-9dd5-60ac4d6b3023 FILE=order-summary.md
```

Observed:
- **Result:** `TaskResult` status `succeeded`, 1 turn, 1 attempt, 10,958 tokens in and 1,036 out, one artifact `order-summary.md`.
- **The file**, in the `order-desk` skill's format:

  ```
  | SKU-1 | 3 | 12.50 | 37.50 |
  | SKU-2 | 2 | 7.25 | 14.50 |
  Total: 52.00
  ```

- **Temporal UI** (through its API): `TaskWorkflow WORKFLOW_EXECUTION_STATUS_COMPLETED` for this task ID.

## Step 2: losing a worker container

The script submits a task that orders four SKUs. It polls `checkpoints` until the task has two, which means one after the first model call. It finds the container that holds the attempt (the hostname part of `task_attempts.worker_identity`) and stops it **abruptly** with `docker kill`.

`docker stop` (SIGTERM, then a 10 s grace period) was tried first. The Temporal worker shut down gracefully and let its attempt finish (`done`, attempt 1), so it did not show a lost worker. An abrupt stop is what a crashed container looks like.

| | Observed |
|---|---|
| Task | `task-12faaa11-b809-4b49-9836-52eca4b044e2` (Workflow ID the same) |
| At the stop | 2 checkpoints, 4 session items; holder `praxismesh-worker-b-1`, killed at 11:34:28 |
| Attempts | turn 1 attempt 1 `lost` (on worker-b), turn 1 attempt 2 `done` (on worker-a, a different container) |
| Result | `succeeded`, 1 turn, 2 attempts |
| Side effects | `sample_orders`: SKU-4 x 2, SKU-5 x 1, SKU-2 x 3, SKU-1 x 1, each recorded once |
| Conversation | the session grew from 4 items at the stop to 40 at the end: it was continued, not restarted |

**What this run did not show:** the stop came before the model's first file edit, so no workspace edit was at risk. Recovery **after workspace edits** is shown by the automated test `tests/integration/test_recovery.py::test_recovery_after_workspace_edits` (`make recovery-check`). It kills the worker at a held-open point after a checkpoint that contains the edit. The edit is present after recovery, and the resumed model request carries the instructions and the earlier tool call. `test_recovery_in_a_later_turn_with_edit_and_effect` does the same in turn 2, with an edit and an order. Both pass in CI's `stack` job.

## Step 3: no duplicated side effect; rejected capability request

**Side effect.** In step 2, every order was recorded once. The case where a worker dies **between** an effect and the next checkpoint, so that the resumed attempt calls the tool again, is automated as `test_side_effect_not_repeated_after_crash`. There, the resumed `record_order` returned `"repeated": true`, and `sample_orders` held one row.

**Rejection.** A request that names capabilities:

```bash
echo '{"profile": "default", "instructions": "Order SKU-1.", "skills": ["rogue-skill"], "mcp_servers": ["rogue-mcp"]}' > rogue.json
uv run --env-file infra/.env python -m orchestrator.cli task submit --request rogue.json
```

Observed: `error: a task request may not set mcp_servers, skills: capabilities come only from the worker template`. The exit status was 2, and no task row was created.

## Step 4: one trace from submission to result

Jaeger (v3 API, service `praxis-cli`, attribute `praxis.task_id` = step 1's task) returned **one trace with 24 spans across `praxis-cli`, `praxis-orchestrator` and `praxis-template`**:

| Span | Count |
|---|---|
| `praxis.task.submit` | 1 |
| `StartWorkflow:TaskWorkflow` | 1 |
| `RunWorkflow:TaskWorkflow` | 1 |
| `RunActivity:resolve_capabilities` | 1 |
| `RunActivity:record_task` | 1 |
| `RunActivity:run_harness_turn` | 1 |
| `model call` | 5 |
| `tool call` | 7 |
| `RunActivity:complete_task` | 1 |

Open the UI at <http://127.0.0.1:16686> and search service `praxis-cli`. Automated: `tests/integration/test_tracing.py::test_task_trace_reaches_model_and_tool_calls`.

**Metrics.** Prometheus (<http://127.0.0.1:9090>) scrapes `orchestrator:9100`, `worker-a:9100` and `worker-b:9100`, all `up`, and `praxis_tokens_total` is reported. The counters reset when a container restarts.

## Benchmark and resources

- **Benchmark baseline:** 10 of 10 tasks passed, each in one turn, in about 4 minutes in total ([docs/benchmarks/2026-11-12-local-default.md](../benchmarks/2026-11-12-local-default.md)).
- **Memory:** `docker stats` with the stack, three workers, Prometheus and Jaeger running came to about 940 MiB in total.

## Cleanup

```bash
make workers-down && make observability-down   # or: make reset (deletes all data)
```

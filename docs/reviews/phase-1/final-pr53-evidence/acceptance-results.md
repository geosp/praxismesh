# Phase 1 acceptance and demo verification

Proposed verdict: **BLOCKED**. All executed deterministic acceptance suites passed; the real-model sample, benchmark comparison and live worker-container-loss demo cannot run because documented prerequisites provide no model endpoint. No mocks are claimed as real-model gate evidence. Frozen checkout: `/tmp/praxismesh-pr53-final-verify`, code `9472d20d3b5e5d7cee1542ffedf9c25335defadd`. Date: 2026-11-13. Requirements read: AGENTS.md, PROJECT_PLAN.md, phase-1.md tasks/Accept/Demo, phase RFC testing/demo, README setup, Makefile, infra/.env.example, and only reproduction instructions from the earlier demo evidence.

## Environment and prerequisites

No working-copy configuration or secrets were read/copied. `.verify/acceptance.env` was copied from `infra/.env.example`; example placeholder credentials remain unchanged. Project changed to `praxismesh-pr53-finalverify`; host ports: DB 25432, Temporal 27233, Temporal UI 28080, S3 28333; sample DB URL changed to its 25432 host port. Tracing endpoint `http://127.0.0.1:24318`. `VLLM_BASE_URL` and `VLLM_API_KEY` remain empty, model name remains example `spark`. No relevant model endpoint was present in the shell (`env | rg '^(VLLM_BASE_URL|VLLM_MODEL|OTEL_EXPORTER_OTLP_ENDPOINT)='`, exit 1, no output).

Observability shell overrides: `PROMETHEUS_PORT=29090 JAEGER_UI_PORT=26686 OTLP_HTTP_PORT=24318`. These Compose-supported names are rejected if placed in ENV_FILE, so they were removed from the scratch env after an initial `make up` prerequisite rejection. README permits shell overrides. No source/test/docs edits or failure-path changes were made. Stack and workers are **left running** for the next verifier, with workers still pointing to the labeled fake model as documented after workers-check. No unrelated services were changed.

Versions: uv 0.13.5; Python 3.11.17; Docker Engine/client 29.9.3; Docker Compose v5.7.1; openai-agents 0.24.0; temporalio 1.36.0; pytest 9.2.0; opentelemetry-sdk 1.45.2. Evidence: acceptance-versions.log and acceptance-docker-version-escalated.log. Initial sandbox network/Docker restrictions were resolved with tool escalation; these are environment restrictions, not application failures.

All commands below ran from the frozen checkout. Python commands used `UV_CACHE_DIR=/tmp/praxismesh-pr53-final-verify/.verify/uv-cache`; commands involving stack sockets/network used escalation. Output redirected to the named .verify evidence file. Exit codes are actual command exits (Make may wrap its child exit).

## Checks

| Command/step | Expected | Observed (quoted) | Exit/result | Evidence under .verify |
|---|---|---|---|---|
| `git rev-parse HEAD` | Frozen code SHA | `9472d20d3b5e5d7cee1542ffedf9c25335defadd` | 0 / PASS | acceptance-revision.txt |
| `uv sync --locked` | Install locked environment | `Resolved 90 packages in 1ms`; `Installed 86 packages in 18ms` | 0 / PASS after escalation | acceptance-uv-sync-escalated.log |
| `make up ENV_FILE=.verify/acceptance.env` (with observability shell overrides above) | Healthy isolated stack | `stack is up; run 'make status' for addresses and health` | 0 / PASS | acceptance-make-up-retry.log |
| `make migrate ENV_FILE=.verify/acceptance.env` | Apply Phase 1 migration | `Running upgrade 0002 -> 0003, Phase 1 tables: tasks, attempts, checkpoints, idempotency, blob metadata, sample orders, and the openai-agents session store` | 0 / PASS | acceptance-migrate.log |
| `uv run pytest` | Unit, replay and time-skipping suites pass | `157 passed, 91 deselected in 34.25s` | 0 / PASS | acceptance-unit-replay.log |
| `make smoke ENV_FILE=.verify/acceptance.env` | Stack suites pass (real endpoint tests skip if unconfigured) | `82 passed, 4 skipped in 31.77s`; four explicit `VLLM_BASE_URL is unset or empty; model endpoint not configured` skips | 0 / PASS deterministic suites; model items BLOCKED | acceptance-smoke.log |
| Included smoke metric regression: `tests/integration/test_harness_activity.py::test_activity_metrics_are_recorded` | Record Activity duration and heartbeat lag | `tests/integration/test_harness_activity.py ................ [76%]` (all 16 tests in file passed; test is included in file) | Included in exit 0 smoke / PASS | acceptance-smoke.log |
| `make observability-up ENV_FILE=.verify/acceptance.env` (with independent port overrides) | Start Prometheus/Jaeger | `praxismesh-pr53-finalverify-prometheus-1 Started`; `praxismesh-pr53-finalverify-jaeger-1 Started` | 0 / PASS | acceptance-observability-up.log |
| `make workers-check ENV_FILE=.verify/acceptance.env` | Scripted task through worker containers, explicitly fake model | `status: succeeded` (JSON), `Ordered 3 x SKU-1.`, turns 1, attempts 1, tokens 400 in/40 out, inner_turns 4 | 0 / PASS simulated | acceptance-workers-check.log |
| `make task-output ENV_FILE=.verify/acceptance.env ID=task-0403d014-d086-4264-9207-859372e12408 FILE=order-summary.md` | Visible output artifact from simulated task | `# Order summary` and `| SKU-1 | 3 | 12.50 | 37.50 |` | 0 / PASS simulated | acceptance-fake-task-output.log |
| `make task-status ENV_FILE=.verify/acceptance.env ID=task-0403d014-d086-4264-9207-859372e12408` | Completed same workflow/task, checkpoint and order | `"workflow": "COMPLETED"`, `"status": "succeeded"`, `"orders": [{"sku": "SKU-1", "qty": 3}]`, 5 checkpoints | 0 / PASS simulated | acceptance-fake-task-status.json |
| `make recovery-check ENV_FILE=.verify/acceptance.env` | Recovery after workspace edits, effect idempotency, checkpoint/session consistency, stale attempt fencing, later-turn recovery | All named tests `PASSED`; `5 passed in 58.50s` | 0 / PASS simulated process crash | acceptance-recovery.log |
| `uv run --env-file .verify/acceptance.env python -m orchestrator.cli task submit --request .verify/rogue.json` | Explicit rejection of requested MCP/skill overrides | `error: a task request may not set mcp_servers, skills: capabilities come only from the worker template` | 2 / PASS expected rejection | acceptance-rejection-escalated.log; rogue.json |
| `make benchmark ENV_FILE=.verify/acceptance.env` | Real model benchmark; baseline 10/10, regression at most one lost | `error: VLLM_BASE_URL is not set; the benchmark needs a real model`; `make: *** [Makefile:141: benchmark] Error 2` | 2 / BLOCKED missing endpoint | acceptance-benchmark.log |

The rogue request was created with `printf '%s\n' '{"profile":"default","instructions":"Order SKU-1.","skills":["rogue-skill"],"mcp_servers":["rogue-mcp"]}' > .verify/rogue.json`.

Recovery suite observed passes: `test_recovery_after_workspace_edits`, `test_side_effect_not_repeated_after_crash`, `test_checkpoint_matches_session_position`, `test_superseded_attempt_comes_back_and_writes_nothing`, `test_recovery_in_a_later_turn_with_edit_and_effect`. These are documented deterministic HTTP fake-model/process-SIGKILL checks, not evidence of real-model behavior or a live container-loss demo.

## Independent observability observations

Exact read-only API commands, all curl exit 0:

```sh
curl -fsS 'http://127.0.0.1:29090/api/v1/query?query=up' > .verify/acceptance-prometheus-up.json
curl -fsS 'http://127.0.0.1:29090/api/v1/query?query=praxis_tokens_total' > .verify/acceptance-prometheus-tokens.json
curl -fsS 'http://127.0.0.1:26686/api/v3/traces?query.service_name=praxis-cli&query.start_time_min=2026-11-13T14:00:00Z&query.start_time_max=2026-11-13T15:00:00Z' > .verify/acceptance-jaeger-v3.json
```

Expected: all three worker scrape targets up; token counters; one trace follows submission through Workflow and Activity into model/tool calls and result. Observed: `orchestrator:9100`, `worker-a:9100`, `worker-b:9100` all value `1`; `praxis_tokens_total` 400 in and 40 out. One trace `b4bb71b0cde997d5854308f92d106a5f`, 20 spans across `praxis-cli`, `praxis-orchestrator`, `praxis-template`, task `task-0403d014-d086-4264-9207-859372e12408`. Includes `praxis.task.submit`, `StartWorkflow:TaskWorkflow`, `RunWorkflow:TaskWorkflow`, `RunActivity:run_harness_turn`, four `model call`, four `tool call`, `RunActivity:complete_task`, `CompleteWorkflow:TaskWorkflow`. PASS for simulated task observability. Raw JSON and derived acceptance-observability-summary.log saved. Initial attempt at legacy `/api/traces?service=praxis-cli&limit=20` returned HTTP 404/exit 22; corrected to the v3 API named by docs, successfully.

Simulated task Workflow ID equals task ID; Temporal run ID `01a1d552-a25d-7eb6-9694-e07b75d9229c`; request `req-90e39822-9804-4856-8fb0-d4ff998faf7f`; latest checkpoint `task-0403d014-d086-4264-9207-859372e12408:1:1:4` session_position 9; visible artifact `order-summary.md`, 105 bytes, checksum `sha256:fa7034119c3338fc83da4e49d68dc45df4fab7e66569092749898d9263513bac`. Template `local-default@1`, hash `sha256:6122e8de71a551797b991d7ce87c701c366623076a63135b2f40e3f4b6e7f7ee`.

## Required demo items still blocked

- Real-model documented sample (`make workers-up`, then documented `make task PROMPT=... OUTPUT=order-summary.md` and `make task-output`): BLOCKED because no documented endpoint/credentials are available. Not executed against fake as a substitute.
- Real-model worker-container loss (`make workers-up`, `make demo-worker-loss`), same task/workflow before/after replacement, edits/conversation preserved and order effects exactly once: BLOCKED by same endpoint dependency. Deterministic process-loss suite passed, but does not close this live demo item.
- Real-model benchmark comparison to recorded baseline: BLOCKED by endpoint; runner diagnostic reproduced. No baseline or benchmark documents were rewritten.
- Real-model trace/metrics: BLOCKED for real-model task; the independent simulated trace and actual worker scrape observations above pass.

No product failure was observed in executed acceptance suites. Operational note: optional observability port keys are absent from env example and rejected in ENV_FILE despite Compose supporting them; shell overrides allowed by README permit isolation. Initial sandbox DNS failure, Docker socket denial, legacy Jaeger API 404 and the scratch env validation rejection are retained as diagnostic attempts, not acceptance failures. The first sandboxed rejection request also stalled during tracing export; authoritative rejection evidence is the escalated retry.

Cleanup is deliberately deferred at coordinator request. Only this isolated project should later be stopped using documented `make workers-down ENV_FILE=.verify/acceptance.env`, observability teardown with matching shell overrides, and `make down ENV_FILE=.verify/acceptance.env` (or reset only if deleting this verification project's data is intended).

Final handoff checks: `make status ENV_FILE=.verify/acceptance.env` exited 0, printed `all services healthy` and `model endpoint: not configured (VLLM_BASE_URL is empty)` (acceptance-final-status.log). `docker compose -p praxismesh-pr53-finalverify --env-file .verify/acceptance.env -f infra/docker-compose.yml --profile workers --profile fake-model --profile observability ps` exited 0 and showed the isolated platform, both workers, orchestrator, fake model, Prometheus and Jaeger up (acceptance-final-compose-ps.log). `docker compose -p praxismesh-pr53-finalverify --env-file .verify/acceptance.env -f infra/docker-compose.yml exec -T worker-a printenv VLLM_BASE_URL` exited 0 and printed `http://fake-model:8765` (acceptance-worker-model.log). The configured external endpoint and the active worker fake override are deliberately distinguished.

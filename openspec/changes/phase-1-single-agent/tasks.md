# Tasks

## 1. Foundations (PR 1)

- [ ] 1.1 Dependencies: `openai-agents`, `pydantic`, `pyyaml` (runtime), `mcp`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp` and `prometheus-client`; `claude-agent-sdk` as the optional extra `claude`. Confirm that CI's `licenses` job passes.
- [ ] 1.2 `common/schemas/`: `AgentProfile`, `WorkerTemplate`, `McpServer`, `BlobRef`, `TaskRequest`, `TaskResult`, `TurnInput`, `TurnOutcome` and `ExecutionAttempt`, each with `schema_version`. The profile and request schemas forbid extra fields.
- [ ] 1.3 `registry/` loaders and `registry/registry.lock` (template hashes, checked in CI); the committed `default` profile, `local-default@1` template and `sample-shop` MCP entry; harness-precedence and template-choice rules. Negative tests for profiles and requests.
- [ ] 1.4 `common/blob_store/`: protocol, typed errors, in-memory fake, S3 adapter, and the shared contract suite (fake in unit tests, SeaweedFS in `stack`).
- [ ] 1.5 Migration `0003` (including `sample_orders`, and `DEFAULT 'task'` on the SDK and sample tables) and `common/persistence/retention.py`; repositories with the stated upsert keys; a test that every row and blob has a retention class.
- [ ] 1.6 `common/observability/`: JSON logging with context IDs, OpenTelemetry setup with `TracingInterceptor`, Prometheus metrics, SDK tracing disabled; unit tests with an in-memory exporter and `test_no_sdk_trace_export`.
- [ ] 1.7 CLI (`python -m orchestrator.cli task submit|status`): validates requests, mints `task_id`, uploads instructions and inputs as blobs, starts with `REJECT_DUPLICATE`; `test_duplicate_task_id_rejected`.
- [ ] 1.8 Tooling: new `infra/.env` keys (`S3_BUCKET`, `PRAXIS_SAMPLE_DB_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`) in `.env.example` and `check-prereqs.sh`; mypy `files` gains the new packages.

## 2. Harness (PR 2)

- [ ] 2.1 `HarnessRunner` interface; `OpenAIAgentsRunner` (`tool_not_found_behavior="return_error_to_model"`, tracing off); `ClaudeSdkRunner` behind the optional extra (`tools`, exact `allowed_tools`, `dontAsk`, local plugin for skills, `effort`, clean-environment `cli_path` wrapper).
- [ ] 2.1a `tests/support/fake_model/`: deterministic OpenAI and Anthropic endpoints that answer from the message history, with a pause point and a request log.
- [ ] 2.2 Built-in workspace tools and `run_command` (allow-list, credential-free environment, timeout, output cap).
- [ ] 2.3 `sample_mcp` server and the `order-desk` skill bundle; MCP tool filter; skills mounted read-only and listed.
- [ ] 2.4 `run_harness_turn` (without mid-turn recovery) and `TaskWorkflow` with turn and budget accounting and the retry policy; replay and time-skipping tests.
- [ ] 2.5 `workers/Dockerfile`, Compose profile `workers` (orchestrator, worker-a, worker-b), `make workers-up`, `workers-down`, `task`, `task-status`; a scripted end-to-end test, `test_prohibited_tool_returns_error` and `test_claude_runner_isolation` in the `stack` job.

## 3. Durability (PR 3)

- [ ] 3.1 Mid-turn checkpoints at the next `on_llm_start` and after the run (deterministic tar, off the event loop), heartbeat details with usage, attempt rows at start, restore preferring the highest attempt, truncation to the session position; `test_checkpoint_matches_session_position`.
- [ ] 3.2 `SQLAlchemySession` on the app database for `openai_agents`; the Claude `SessionStore` adapter, and verification that a Claude session resumes on another worker (or the recorded fallback).
- [ ] 3.3 Idempotency keys and `record_order`; the kill-between-effect-and-checkpoint test.
- [ ] 3.4 `make recovery-check` with the fake model's pause point (stop the worker holding the attempt after an acknowledged checkpoint; the other finishes with the full history), run in the `stack` job.

## 4. Evidence (PR 4)

- [ ] 4.1 Benchmark suite in `tests/benchmarks/agent_tasks/`, `make benchmark`, the baseline on the Sparks in `docs/benchmarks/`, and the regression check.
- [ ] 4.2 `docs/security/threat-model.md` with controls mapped to tests.
- [ ] 4.3 Compose profile `observability` (Prometheus, Jaeger, pinned by digest); the trace demo.
- [ ] 4.4 Run the demo against the Sparks and record `docs/demos/phase-1.md`.
- [ ] 4.5 The Phase 1 section of `docs/architecture/overview.md`; decision-log rows for any deviations.

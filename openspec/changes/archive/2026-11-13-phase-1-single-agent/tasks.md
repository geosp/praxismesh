# Tasks

## 1. Foundations (PR 1)

- [x] 1.1 Dependencies: `openai-agents`, `pydantic`, `pyyaml` (runtime), `mcp`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp` and `prometheus-client`. Confirm that CI's `licenses` job passes.
- [x] 1.2 `common/schemas/`: `AgentProfile`, `WorkerTemplate`, `McpServer`, `BlobRef`, `TaskRequest`, `TaskResult`, `TurnInput`, `TurnOutcome` and `ExecutionAttempt`, each with `schema_version`. The profile and request schemas forbid extra fields.
- [x] 1.3 `registry/` loaders and `registry/registry.lock` (template hashes, checked in CI); the committed `default` profile, `local-default@1` template and `sample-shop` MCP entry; harness-precedence and template-choice rules. Negative tests for profiles and requests.
- [x] 1.4 `common/blob_store/`: protocol, typed errors, in-memory fake, S3 adapter, and the shared contract suite (fake in unit tests, SeaweedFS in `stack`).
- [x] 1.5 Migration `0003` (including `sample_orders`, and `DEFAULT 'task'` on the SDK and sample tables) and `common/persistence/retention.py`; repositories with the stated upsert keys; a test that every row and blob has a retention class.
- [x] 1.6 `common/observability/`: JSON logging with context IDs, OpenTelemetry setup with `TracingInterceptor`, Prometheus metrics, SDK tracing disabled; unit tests with an in-memory exporter and `test_no_sdk_trace_export`.
- [x] 1.7 CLI (`python -m orchestrator.cli task submit|status`): validates requests, mints `task_id`, uploads instructions and inputs as blobs, starts with `REJECT_DUPLICATE` (its duplicate test lands in PR 2).
- [x] 1.8 Tooling: new `infra/.env` keys (`S3_BUCKET`, `PRAXIS_SAMPLE_DB_URL`, and the optional `OTEL_EXPORTER_OTLP_ENDPOINT`) in `.env.example` and `check-prereqs.sh`; `make registry-lock`; mypy `files` gains the new packages.

## 2. Harness (PR 2)

- [x] 2.1 `HarnessRunner` interface and its conformance suite; `OpenAIAgentsRunner` (`tool_not_found_behavior="return_error_to_model"`, tracing and trace processors off, the `finish_task` tool with `stop_at_tool_names`, `MaxTurnsExceeded` mapped to `continue`, `ModelBehaviorError` mapped to `continue`).
- [x] 2.1a `tests/support/fake_model/`: a deterministic OpenAI-compatible endpoint that answers from the message history (scripts end by calling `finish_task`), with a one-shot pause point and a request log.
- [x] 2.2 Built-in workspace tools and `run_command` (allow-list, credential-free environment, timeout, output cap).
- [x] 2.3 `sample_mcp` server and the `order-desk` skill bundle; MCP tool filter; skills mounted read-only and listed.
- [x] 2.4 `run_harness_turn` (without mid-turn recovery) and `TaskWorkflow` with turn and budget accounting and the retry policy; replay and time-skipping tests.
- [x] 2.5 `workers/Dockerfile`, Compose profile `workers` (orchestrator, worker-a, worker-b), `make workers-up`, `workers-down`, `task`, `task-status`, `task-output`; a scripted end-to-end test, `test_prohibited_tool_returns_error`, `test_runner_conformance` and `test_duplicate_task_id_rejected` (Temporal and `tasks`) in the `stack` job.

## 3. Durability (PR 3)

- [x] 3.1 Checkpoints at every `on_llm_start` (including the first) and after the run (deterministic tar, off the event loop), heartbeat details with usage, attempt rows at start, restore ordered by turn, attempt and seq (or a fresh start when none exists), truncation to the session position; `test_checkpoint_matches_session_position`, `test_restore_prefers_latest_turn`, `test_restore_without_checkpoint`.
- [x] 3.2 `SQLAlchemySession` on the app database; truncation to the session position; self-fencing of overlapping attempts; cumulative usage and `lost` attempt rows.
- [x] 3.3 Idempotency keys and `record_order`; the sample server's test-only pause after the effect; `test_side_effect_not_repeated_after_crash`.
- [x] 3.4 `make recovery-check` with the fake model's pause point (SIGKILL the worker process holding the attempt after an acknowledged checkpoint; the other finishes with the full history), run in the `stack` job. *(Worker processes rather than containers: decision log 2026-11-12.)*

## Carried from the design review

Nits from `docs/reviews/phase-1/design-review-followup-3.md` to resolve in the PR that touches them. J1, J3, J7, J10, J11 and J13 are already applied to the RFC.

- [x] D.1 J2: name the `McpServer` field and the test catalog entry for the sample server's timeout and pause flag (PR 3). *(`McpServer.client_session_timeout_seconds` and literal `env.SAMPLE_MCP_PAUSE_FILE`, set in the generated test registry, `tests/support/worker_procs.py`.)*
- [x] D.2 J4, J5, J6, J8, J9, J14, J16: wording and field-list alignment in the RFC and specs (PR 1). *(J4: no "both runners" wording remains.)*
- [x] D.3 J12: state the status when a sibling tool call in the same step fails alongside `finish_task` (PR 2).
- [x] D.4 J15: assert the `seq` 0 checkpoint in `test_checkpoint_matches_session_position` (PR 3).
- [x] D.5 J17: add the unit check named in the report to task 2.5 (PR 2).
- [x] D.6 J18: link the `finish_task`/`output_type` run from the RFC, add its decision-log row and a Risks row (PR 2).

## Carried from the informal durability review (PR 3)

- [x] R.1 F10: when a harness turn fails for good, add its last heartbeated tokens and attempts to the `TaskResult` (PR 4).
- [x] R.2 F12: close the last attempt's row on a terminal failure, with its real category (PR 4).
- [x] R.3 F15: a recovery case with an edit and an effect in one task, and a loss in turn 2 or later (PR 4).

## 4. Evidence (PR 4)

- [x] 4.1 Benchmark suite in `tests/benchmarks/agent_tasks/`, `make benchmark`, the baseline on the Sparks in `docs/benchmarks/`, and the regression check.
- [x] 4.2 `docs/security/threat-model.md` with controls mapped to tests.
- [x] 4.3 Compose profile `observability` (Prometheus, Jaeger, pinned by digest); the trace demo.
- [x] 4.4 Run the demo against the Sparks and record `docs/demos/phase-1.md`.
- [x] 4.5 The Phase 1 section of `docs/architecture/overview.md`; decision-log rows for any deviations.

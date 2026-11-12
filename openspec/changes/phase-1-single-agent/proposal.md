# Proposal

## Why

Phase 0 built the local platform stack. Phase 1 adds the first product code: one agent, on the local model, completes useful work as a durable Temporal task and recovers when its worker is destroyed (plan Phase 1; §4.1, §4.2, §4.10, §4.13). Later phases build on its capability model, `BlobStore`, persistence, observability and benchmark baseline.

## What Changes

- **Capability model:** versioned `AgentProfile`, `WorkerTemplate` and `McpServer` schemas with YAML loaders. Harness configuration comes from templates only, and requests or profiles that name skills, MCP servers or tools are rejected.
- **`BlobStore`:** a minimal contract (`put`, `get`/`stream`, `stat`, `delete`, typed errors), with a SeaweedFS S3 adapter and contract tests.
- **Persistence:** migration `0003` (tasks, attempts, checkpoints, idempotency keys, blob metadata, sample orders, session stores), with a retention class on every row and blob from the first write.
- **Execution:**
  - `run_harness_turn`: a bounded harness invocation behind `HarnessRunner`, with the `openai_agents` runner (the Claude Agent SDK runner is deferred to its own change, after the licensing decision);
  - `TaskWorkflow`: turn and budget accounting, retrying infrastructure failures only;
  - mid-turn checkpoints of session and workspace, so a task recovers on another worker;
  - idempotency keys on side-effecting tools.
- **A sample skill and a sample MCP server**, plus a generic worker image and a `workers` Compose profile with two workers.
- **Observability baseline:** JSON logs with context IDs, OpenTelemetry tracing from submission to Activity, Prometheus metrics, and an optional `observability` profile (Prometheus and Jaeger).
- **Agent benchmark suite:** seeded from the spike's 10 tasks, with a recorded baseline and a regression limit of at most 1 task lost out of 10.
- **Threat model, first version.**

Not in scope:
- live messaging and streaming, or `comms_mcp` beyond a stub (Phase 2);
- Ceph and GCS adapters, presigned URLs, retention enforcement and garbage collection (Phase 3A);
- worker affinity queues;
- a sandbox for untrusted code and egress control (Phase 5);
- the Claude Agent SDK runner (its own change, after the licensing decision);
- Kubernetes (Phase 7).

## Capabilities

### New Capabilities
- `agents/capability-model`: profiles, templates, the MCP catalog, loaders and template-only capability.
- `execution/harness-turn`: the bounded harness Activity and its runners.
- `execution/task-workflow`: the durable task, turn and budget accounting, and retries.
- `execution/durability`: checkpoints, recovery on another worker, and idempotent side effects.
- `observability/baseline`: logs, traces and metrics.
- `quality/agent-benchmarks`: the benchmark suite and its regression rule.
- `security/threat-model`: the threat model and its controls-to-tests mapping.

### Modified Capabilities
- `storage/blob-store`: adds the `BlobStore` contract and its typed errors.
- `persistence/app-database`: adds the Phase 1 tables and retention classes.

## Impact

- **New code:**
  - `common/schemas/`, `common/blob_store/`, `common/observability/`;
  - `registry/`, `orchestrator/`, `harness_activity/`;
  - `sample_mcp/`, the `comms_mcp/` stub, `workers/`;
  - `tests/benchmarks/`.
- **New docs:** `docs/benchmarks/` and `docs/security/threat-model.md`.
- **Compose:** new profiles `workers` and `observability`.
- **Make targets:**
  - `workers-up`, `workers-down`;
  - `task`, `task-status`;
  - `recovery-check`, `benchmark`.
- **New runtime dependencies:** `openai-agents`, `pydantic`, `pyyaml`, `mcp`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp` and `prometheus-client`.
- **Tracking issue:** #44. Design: [docs/rfcs/phase-1-single-agent.md](../../../docs/rfcs/phase-1-single-agent.md).

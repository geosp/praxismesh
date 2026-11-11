# PraxisMesh plan: Phase 1

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 1: Harness-in-Activity, single agent

**Read first:** `PROJECT_PLAN.md`, then §4.1, §4.2, §4.10, §4.13; schemas.

- [ ] Implement versioned `AgentProfile`, `WorkerTemplate`, `McpServer`, dev YAML loaders and a generic worker polling `tpl.{template}`.
- [ ] Implement the **minimal `BlobStore` contract** (`put`, `get/stream`, `stat`, `delete`, typed errors) with the SeaweedFS S3 adapter and contract tests, and add the first application-DB migrations this phase needs (session/checkpoint references, task attempts, idempotency keys). Ceph/GCS adapters, presigned access, retention/GC and Claim Check stay in Phase 3A. *(Moved forward in rev 2.9: this phase's workspace snapshots depend on it.)*
- [ ] Write a retention class on every blob and stored record from the first write (§4.13). Garbage collection and deletion arrive in Phase 3A; the metadata must exist now.
- [ ] **Baseline observability (moved forward in rev 2.10):** structured logs carrying request, conversation, workflow, task and attempt IDs; distributed tracing from client call through Workflow to Activity using the SDK's verified tracing support; a metrics endpoint on workers (Activity duration, heartbeat lag, tokens, tool-call counts and errors, checkpoint size and time); and Prometheus as an optional Compose profile. Later phases add signals to this base instead of starting it in Phase 8.
- [ ] **Agent benchmark suite (rev 2.10):** create `tests/benchmarks/agent_tasks/`, seeded from the Pre-0 spike tasks: a small fixed set of representative tasks (start near 10; grow toward 30 by Phase 3B) with deterministic pass/fail checks. Record pass rate, turns, tokens and wall time per model, template and prompt version in `docs/benchmarks/`. Re-run on any change to a model, `WorkerTemplate`, harness version or system prompt; a drop beyond the owner's limit blocks phase closure.
- [ ] **Threat model, first version (rev 2.10):** write `docs/security/threat-model.md` covering what exists so far: assets, trust boundaries, actors (hostile prompt, hostile file content, compromised worker, over-privileged profile) and the capability-isolation controls, each mapped to a test. Every later phase that adds a trust boundary extends it.
- [ ] Verify SDK compatibility; implement `run_harness_turn` Activity with template-configured local model, MCP, skill mounts, bounded inner turns/timeouts, heartbeat, structured `TaskResult` and session ID/ref capture.
- [ ] Implement **durable session persistence or equivalent verified adapter**, and **separate workspace snapshots through `BlobStore`**. Recover on a different worker after pod loss. Worker-affinity queue is optional acceleration only.
- [ ] Implement `TaskWorkflow` on stable orchestration queue with clear turn/budget accounting and infrastructure retry semantics.
- [ ] Add a sample skill and sample MCP tool, plus a negative capability test proving profiles/requests cannot inject MCP/skills or invoke prohibited tools.
- [ ] Phase 1 may use a stub for `comms_mcp` and plain structured logs; live messaging/streaming belongs to Phase 2.
- **Accept:** one local-model task uses the template-provided skill and MCP tool; a worker crash resumes; deleting a pod **after workspace edits** still restores and finishes on a replacement; no duplicated external side effects; forbidden MCP/skill overrides fail; one trace follows a task from submission to result; the benchmark suite runs and its baseline is recorded.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** A single agent completes useful work and recovers even when its worker is destroyed.

- [ ] Run a documented sample task that uses its approved skill and MCP tool to produce a visible file plus a validated `TaskResult`.
- [ ] During a second task, wait for an acknowledged session/workspace checkpoint, terminate the worker, and demonstrate a replacement resumes and finishes without losing edits or conversation context.
- [ ] Replay or retry a side-effect step and show it is not duplicated; request an unauthorized skill/tool and show explicit rejection.
- [ ] Show the completed output and the same logical task reference before and after worker replacement.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-1.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

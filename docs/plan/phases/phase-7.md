# PraxisMesh plan: Phase 7

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 7: Kubernetes deployment

**Read first:** `PROJECT_PLAN.md`, then §4.7, §4.10, §4.11; schemas.

- [ ] **Operator language decision (design gate):** Default to Python with Kopf. During Phase 7 design review, evaluate Python/Kopf against Go/Kubebuilder/controller-runtime for the actual controller scope, CRD reconciliation complexity, Kubernetes API compatibility, performance, reliability, operational tooling and maintenance cost. Record benchmark/evidence-based rationale and the selected language before implementation of the custom operator. Adopt Go only if its benefits materially justify the additional language, build and support burden; reuse the Temporal Worker Controller rather than duplicating its responsibilities.

- [ ] **Worker Versioning strategy (moved from Phase 9 in rev 2.9):** the Worker Controller's rollouts depend on versioned worker deployments, so decide this here. Define deployment/build version naming, pinned versus auto-upgrade behavior for long-running entity Workflows (`OrchestratorWorkflow`, `RepoStewardWorkflow`), the patching policy for changed Workflow code, the drain/sunset rule for old versions, and a replay test in CI against recorded histories. Record it as an ADR before rollout work.

- [ ] Build Helm chart for Temporal OSS + PostgreSQL, SeaweedFS default, vLLM (GPU requests per model), gateway, webhook bridge, control plane, operator, KEDA, Prometheus stack, DCGM exporter where GPU exists. Provide kind/k3d CPU-only model/stub profile.
- [ ] Generate `WorkerTemplate` and `McpServer` OpenAPI CRDs from a single versioned Pydantic schema source; add schemas for references and template status.
- [ ] Verify current Temporal Worker Controller version (v1.7.0 or later, see §4.11) and `WorkerDeployment` CRD; confirm that `ScaledObject` is an allowed kind for `WorkerResourceTemplate` in that release. Adapter/operator renders configuration and appropriate Worker Controller resource(s); **do not concurrently own Controller-managed Deployments**. Document fallback plain Deployment adapter if incompatible.
- [ ] Configure version-scoped KEDA `ScaledObject`s on harness Activity backlog, including Controller `allowedResources` and RBAC. Keep orchestration workers always on and appropriately replicated. Test scale-from-zero caveats and selected external-metrics adapter conflicts.
- [ ] Enforce model/vLLM GPU capacity on maximum worker replicas and in-flight Activity concurrency; set node scheduling/resource policies.
- [ ] Version templates, roll out and roll back without killing useful work; drain then terminate with grace periods, Activity heartbeat cancellation and independent workspace/session restore after pod loss.
- [ ] Render `stdio` MCP in worker, `sidecar` MCP in pod, `service` MCP as cluster Deployment+Service; startup validates tools and MCP health, failing readiness if absent.
- [ ] NetworkPolicies for worker egress, Kubernetes Secret refs, RBAC, local PVCs, object-store backend selection and opt-in GCS configuration. Avoid cloud-provider assumptions.
- [ ] Observe pod/queue capacity, rolling versions, backlogs, worker failure and readiness.
- **Accept:** on kind/k3d a template CRD creates workers that take Activities; backlog scales 0→N→0 on eligible harness queues; stable orchestration continues functioning; template updates roll safely and rollback works; deliberate pod deletion resumes state; broken MCP prevents readiness; deployment works entirely locally with SeaweedFS.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** A Kubernetes installation scales workers on demand and survives replacement.

- [ ] Install on documented kind/k3d (CPU-only profile allowed), create a worker-template CRD, and show an actual queued Activity runs on its worker.
- [ ] Show harness-worker replicas grow with a backlog and later return to zero while always-on orchestration continues accepting work.
- [ ] Change a template version, watch a safe rollout/drain and rollback, and demonstrate an in-flight task remains recoverable.
- [ ] Delete an active worker pod and show a replacement restores its session/workspace; show readiness rejects a broken MCP configuration and scaling obeys configured model capacity.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-7.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

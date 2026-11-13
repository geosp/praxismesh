# PraxisMesh plan: Phase 8

Part of the PraxisMesh project plan, revision 2.11. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 8: Platform administration UI and API

Accepted sequencing: [Phase 4A](phase-4a.md) supplies the Compose task UI first;
this phase extends that frontend after Phase 7 Kubernetes deployment and
Phase 6B verified-workflow capabilities exist. See
[ADR-0003](../../adr/0003-early-compose-task-ui.md). No Phase 8 functionality is
claimed implemented. Existing requirements are allocated as follows: initial
task/conversation interaction and supported question/approval actions move to
4A; the tasks below retain administration and later integrations.

**Read first:** `PROJECT_PLAN.md`, then §4.10, §4.12; schemas.

- [ ] **API (FastAPI):** CRUD for versioned templates (clone/diff/rollback), MCP catalog, agent profiles; schema validation; Kubernetes CRD writes; audit; live fleet reads; Temporal visibility/streams; Prometheus queries; OIDC or local auth and API-enforced `admin`/`operator`/`viewer` RBAC.
- [ ] **Templates UI:** live status, ready/desired pods/version/backlog, YAML and form editor, validation, clone, diff, rollout, rollback, pause/scale.
- [ ] **MCP catalog UI:** server transports, health, template use, connection/tool-list test without exposing secrets.
- [ ] **Profiles UI:** profile create/edit and preview of permitted template routing and expected capabilities.
- [ ] **Fleet UI:** pods, nodes, GPU placement, current task, logs links and drain/restart.
- [ ] **Dashboard:** task backlog and queue delay, turn p50/p95, throughput, success/failure/escalation, tokens/s and per task, vLLM TTFT and KV cache, GPU use, predicted/actual tier and delivery accuracy; time range and refresh. Builds on the Phase 1 metrics and traces.
- [ ] **Workflows UI extensions:** reuse Phase 4A's task graph, live progress, attempts/offsets, Temporal links and cancellation; add fleet/tier filters and authorized retry controls supported by later server APIs. Preserve the existing Compose task experience.
- [ ] **Approvals inbox extensions:** build on Phase 4A's input/approval inbox for plan/tool/merge and Phase 6B stage context, with audited signals; no ability for viewer to change approvals. Reuses the Phase 3B approval API and Phase 5/6B policies; the CLI stays supported.
- [ ] **Verified workflow views:** display chosen template/version, stage graph, pinned spec and commit, independent reviewer findings, required evidence, blocked/failing gates and authorized retry/approval actions. A workflow editor is explicitly deferred; do not allow UI bypass of policy.
- [ ] **Audit UI**, including external `kubectl` changes reflected by live cluster reads; SSE reuses Phase 2/4 event transport.
- [ ] Integrate app PostgreSQL queryable records (requests, plan revisions, attempts, messages, budgets, GitHub deliveries), not only Temporal visibility.
- **Accept:** admin edits template from UI and watches pods run work; live dashboard tracks load; operator resolves approval; viewer cannot mutate via API; externally changed CRD is reflected; no secrets leak.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** An operator can manage the platform from the UI without shell access.

- [ ] Sign in as an admin; create or clone a template in the UI, validate it, deploy it, and watch worker status and an example task change live.
- [ ] Open a workflow graph and dashboard; show current task state, backlog, latency, events, and a link to the execution details.
- [ ] As an operator, resolve a pending approval and show the resulting workflow transition and audit record.
- [ ] Sign in as a viewer and demonstrate mutation is denied by the API; update a CRD outside the UI and show the displayed state reconciles.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-8.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

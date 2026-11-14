# Project Plan: PraxisMesh — Durable Agent Platform on Temporal

**Revision:** 2.12
**Updated:** 2026-11-14
**Product / project name:** PraxisMesh  
**Tagline:** Durable orchestration for autonomous AI agents  
**GitHub repository:** https://github.com/geosp/praxismesh (public; clone URL `https://github.com/geosp/praxismesh.git`)  
**Distribution:** Open source under the Apache License 2.0 (`LICENSE`)  
**Status:** Phases 0 and 1 implemented and closed; Phase 1 independently reviewed and verified. Phase 2 has not started. See [Phase 1 closure](docs/reviews/phase-1/closure.md).
**Development workflow (rev 2.12):** New work uses the Skill Central implementation-planning suite and `docs/plans/`. OpenSpec is retired from the active development workflow; existing records remain historical and their guarantees are explicitly incorporated by `docs/requirements/baseline.md`. The phase gate and evidence rules remain mandatory. See `docs/development/planning.md`. Proposed [ADR-0004](docs/adr/0004-use-implementation-plans-for-development.md) reconciles ADR-0003’s Phase 4A artifact requirement while carrying forward all its other decisions.

**Audience:** Claude Code or another implementation agent. Read the full plan before writing code. Implement phase by phase; do not check a task until its tests, acceptance criteria, and phase demo all pass. Make small, reviewable commits. Record discoveries, substitutions, and deviations in the decision log.

> This document incorporates the approved architectural review of Phases 0–7, the demonstration requirement for **every Phase 0–9**, a proposed repository/OpenSpec/custom-skill bootstrap prerequisite, and a planning-only independent session/review protocol for Phase 0, and a proposed reusable, independently verified workflow capability for runtime agents. Revision 2.9 resequences work without changing the architecture: a pre-bootstrap feasibility spike is added, Phase 3 is split into 3A and 3B, the reusable verified-workflow capability moves to a new Phase 6B, minimal persistence moves forward to Phases 0-2, and early phases use a lighter process tier (§7.0). Phase numbers 0–9 are otherwise preserved. Revision 2.10 adds project CI, an agent benchmark suite, early observability, an approval CLI, cost units, a gateway compatibility matrix, a threat model, retention and backup, release hygiene and a risk register, and splits the plan into a core file plus per-topic files (see the document map). An unchecked task is not evidence of failure: it simply has not yet been completed and validated.

## Document map

Revision 2.11 schedules a Compose task UI in Phase 4A before GitHub delivery,
while retaining Kubernetes administration in Phase 8. This owner-accepted sequencing decision
is tracked in [ADR-0003](docs/adr/0003-early-compose-task-ui.md) and issue #56;
it does not implement a UI or waive any phase gate.

This file is the core plan. Detail lives in `docs/roadmap/`. Section numbers are stable across files, so a reference such as §4.16 means that numbered section in the file shown here. Load only what a session needs (§9, item 7).

| Section | File |
|---|---|
| Pre-0 feasibility spike and open inputs; §0 bootstrap | [docs/roadmap/bootstrap.md](docs/roadmap/bootstrap.md) |
| §1 What we are building; §2 Hard constraints; §3 Architecture | this file |
| §4 Core design decisions (4.1–4.17) | [docs/roadmap/design-decisions.md](docs/roadmap/design-decisions.md) |
| §5 Schemas and persistence model | [docs/roadmap/schemas.md](docs/roadmap/schemas.md) |
| §6 Repository layout; §7 phase order, process tiers, risk register, phase index | this file |
| §7 Phase task lists, acceptance criteria and demos | `docs/roadmap/phases/phase-*.md` (index in §7.2) |
| §8 Testing rules; §9 Working agreement | this file |
| §10 Decision log | [docs/roadmap/decision-log.md](docs/roadmap/decision-log.md) |
| §11 External references | [docs/roadmap/references.md](docs/roadmap/references.md) |
| Revision history | [docs/roadmap/revision-history.md](docs/roadmap/revision-history.md) |

## 1. What we are building

**PraxisMesh** is an open-source, self-hosted agent-management and execution platform exposing an **OpenAI-compatible API**. Requests become durable Temporal workflows when orchestration is required. The platform:

1. **Triages** incoming requests with a cheap, plain model call to decide complexity, risks, capabilities, and delivery mode (`inline`, `artifact`, `repo`). Client overrides are subject to authorization.
2. **Plans** nontrivial work as a validated task DAG using a stronger model; simple inline requests bypass planning and harness creation.
3. **Dispatches** harness Activities to matching worker templates and task queues by tier, tool/skill capabilities, profile restrictions, and model capacity. **Orchestration Workflows run on a separate stable queue**, not on scale-to-zero harness queues.
4. **Verifies**, retries, escalates, and optionally replans with hard limits. Infrastructure retries are distinct from quality-related retries and escalation.
5. **Persists** structured, queryable application records in PostgreSQL and large data in a pluggable object store. Temporal retains durable control flow and small, versioned references, rather than large prompt or result blobs.
6. **Delivers** repository work through an integrated GitHub pull request, current-commit CI verification, and an approval/merge gate.
7. **Executes reusable, governed workflow templates** (initially a software-engineering lifecycle): requirements/specification -> independent design review -> implementation -> independent implementation review -> independent verification -> approval/delivery. Every stage has a bounded role, evidence, and policy gates; it can target an existing or explicitly authorized new repository.
8. **Maintains** repositories through GitHub webhooks, reviews, issues, CI events, and versioned schedules, managed by a per-repository steward coordinator.
9. **Operates** through a Kubernetes control plane: versioned worker templates, an MCP catalog, deployment lifecycle, authorization, approvals, observability, and fleet management.

### Deployment principles

- Default deployment is **fully self-hosted**: OSS Temporal, PostgreSQL, local vLLM, SeaweedFS object storage, Kubernetes, and the platform's services. GitHub is an allowed external repository service; Anthropic API is optional for a model tier.
- **Google Cloud Storage (GCS) is an expressly optional external object-storage backend**, enabled only when an installation opts into that exception. A local deployment cannot depend on GCS.
- **Ceph RGW/S3 is another supported alternative**. Implement object storage behind one `BlobStore` contract; do not embed vendor-specific calls into workflows or harness logic.
- MCP servers and MCP tools run **only on worker nodes**. Orchestrator-side model calls have no MCP or harness tools.

### First-release scope and non-goals (rev 2.11)

- **First release (MVP):** Phases 0, 1, 2, 3A, 3B, 4, 4A and 5 on Docker Compose. The MVP outcome is: an unmodified OpenAI client or the task UI submits a request, the platform triages, plans, executes and verifies it durably, and repository work arrives as one reviewable GitHub pull request. Phase 4A adds live browser interaction after the gateway; Phase 5 remains the MVP completion point.
- **Post-MVP increments, in order:** Phase 6 (steward), Phase 6B (reusable verified workflows, §4.15), Phase 7 (Kubernetes), Phase 8 (platform administration UI/API and later capability views), Phase 9 (hardening). Items 7, 8 and 9 in the list above are post-MVP. Phase 8 extends the Phase 4A frontend instead of creating a second task UI.
- **Non-goals for the first release:** a hosted service; hard multi-tenant isolation between mutually untrusted organizations; a UI workflow builder; source forges other than GitHub; worker runtimes other than Python; high-availability Temporal operations guidance; model training or fine-tuning; billing.
- **Sizing:** This plan carries no effort estimates. Each phase implementation plan must state a relative size (S/M/L), the hardware it needs, and the external inputs from Pre-0.2 it depends on, so the owner can sequence work with real numbers.

## 2. Hard constraints

- **Languages:** Python 3.11+ for workers, workflows, gateway, control-plane API and tools; use `uv`. Phase 7 operator defaults to Python with Kopf, subject to a documented Python-versus-Go design review; Go with Kubebuilder/controller-runtime is permitted only if approved based on controller requirements. UI: TypeScript, React, Vite.
- **Runtime:** Kubernetes for production workers/services. Docker Compose is for fast development in Phases 0–6. Use `kind` or `k3d` for local Kubernetes tests; avoid assumptions about cloud load balancers or identity services.
- **Local models:** vLLM, with Anthropic Messages-compatible endpoint for Claude harnesses and OpenAI-compatible endpoint for framework/plain-model calls. Configure model, `base_url`, API style, limits, and allowed overrides per worker template, never hard-code them.
- **Deterministic Workflows:** no direct network, database, filesystem, subprocess, git, or LLM calls from Workflow code. All external I/O occurs in Activities. No nondeterministic time/randomness in Workflow code.
- **Keep histories bounded:** Workflow and Activity parameters/results carry small references plus necessary deterministic decisions; large payloads are stored in the application database and `BlobStore`. Also bound the number of events, Signals, Updates and children; use Continue-As-New deliberately. Offloading bytes does not eliminate history events.
- **Treat shared state as versioned:** a Workflow may consume immutable/versioned records returned by an Activity; it must not consult mutable PostgreSQL state directly during replay. All write Activities are idempotent and use stable operation IDs.
- **No implicit privilege escalation:** agent profiles and requests cannot inject MCP servers, skills, secrets, or arbitrary templates; policy checks still apply when a client forces `delivery` or selects a repository.
- **Verify live APIs before implementing:** `temporalio`, Temporal Workflow Streams, SDK session persistence/resume behavior, `claude-agent-sdk`, `temporalio-mcp`, vLLM Anthropic endpoint/tool parser, `github/github-mcp-server`, Temporal Worker Controller (including currently named CRDs and KEDA integration), KEDA Temporal scaler, and `kopf`. Record verified versions, references, limitations and any interfaces/fallbacks in §10. Do not claim an untested SDK capability works.
- **Do not commit secrets**. Restrict credentials, resource access, egress, execution budgets, and untrusted repository code.
- **Named models, tiers and hardware:** The local model for each tier, the meaning of each tier and the development GPU are required inputs (Pre-0.2). Do not start Phase 1 with an unnamed model or Phase 3A with undefined tiers.
- **Named sandbox for untrusted code:** Before Phase 5, select by ADR the mechanism that runs untrusted repository code and tests (for example a sandboxed container runtime class on Kubernetes, and a rootless, credential-free, egress-restricted container under Compose). The mechanism, its limits and its test are part of the Phase 5 gate.
- **Tenancy (proposed default, owner to confirm):** The first release is a single-organization installation. Where schemas say `tenant`, read it as the authenticated client/principal plus repository scope. Isolation between mutually untrusted organizations is a non-goal for the first release.
- **Third-party harness licensing and branding (rev 2.10):** As checked on 2026-11-10 (re-verify): the Claude Agent SDK is governed by Anthropic's Commercial Terms of Service; its Python package bundles the Claude Code CLI; and Anthropic's branding guidance says a product built on it must keep its own branding and not present itself as Claude Code. Pointing the harness at an Anthropic-format gateway through `ANTHROPIC_BASE_URL` is a documented configuration. Whether the terms permit the intended use with non-Anthropic local models, and redistribution inside published images, is **not established here** and is an owner decision (Pre-0.2). Until it is resolved: publish Dockerfiles, not prebuilt images that contain the harness; install the harness at image build time on the installer's machine; and keep the `openai_agents` harness able to serve as the default.

## 3. Architecture

```text
OpenAI SDK client
  | /v1/models, /v1/chat/completions, /v1/responses, background/cancel
  v
FastAPI Gateway -- request/turn identity + auth/idempotency --> PostgreSQL app DB
  | Update-with-Start / Signals / queries
  v
Temporal Server (OSS, PostgreSQL persistence)
  |
  +--> stable orchestration queue (always-on OrchestratorWorkflow,
  |    TaskWorkflow, RepoStewardWorkflow, delivery coordinator)
  |      |
  |      +--> triage / plan / verify / inline calls as ordinary Activities
  |      +--> validated DAG + capability/tier dispatcher
  |      +--> GitHub integration/CI approval Activities
  |      +--> versioned app state & inbox/outbox via DB Activities
  |
  +--> harness Activity queues tpl.{template} (scale independently)
  |      +--> affinity queues tpl.{template}.{pod}, best-effort only
  |      +--> Claude SDK/CLI or OpenAI agent framework, skills, CLI, MCP
  |      +--> comms_mcp on worker nodes -> scoped Temporal interaction
  |
  +--> Workflow Streams -> gateway SSE / agentctl / UI
  |
  +--> Signals/Updates -> durable correlated agent messaging
  |
  +--> Continue-As-New with explicitly transferred state/child ownership

PostgreSQL app DB: requests, conversations/turns, plan revisions, tasks,
                    attempts, messages, webhook inbox/outbox, approvals,
                    budgets, event index, GitHub delivery ledger, audit
BlobStore: default SeaweedFS S3; optional Ceph S3 or opt-in GCS
           sessions, workspace checkpoints, transcripts, tool output, artifacts
GitHub: repo-scoped App tokens, issue/review/CI webhooks, PRs

Kubernetes control plane:
React UI -> FastAPI control-plane API -> WorkerTemplate/McpServer CRDs
                               -> template/operator adapter (Python default)
                               -> Temporal Worker Controller WorkerDeployment
                                  + version-scoped KEDA ScaledObjects
                               -> worker pods, MCP sidecars/services
Metrics: Prometheus + vLLM + GPU exporters + Temporal visibility
```

### Component responsibilities

| Component | Responsibility | Build/reuse |
|---|---|---|
| Temporal OSS + its PostgreSQL store | Durable orchestration, timers, retries, history | Reuse |
| PostgreSQL **application** DB/schema | Indexed/versioned business state, inboxes, delivery ledger, audit | Build schema/repositories; separate logical DB/schema from Temporal internal tables |
| vLLM | Local inference: Anthropic-style and OpenAI endpoints | Reuse |
| `common/blob_store/` | Pluggable large-object abstraction; session/workspace/artifact storage | Build adapters for SeaweedFS S3, Ceph S3, GCS |
| SeaweedFS | Self-hosted default blob storage | Reuse; **replaces MinIO** |
| `gateway/` | OpenAI API compatibility; auth, request identity, SSE adapters | Build |
| `orchestrator/` | Triage, DAG planning, scheduling, verification, escalation, reusable stage-gated workflows | Build |
| `workflow_catalog/` | Versioned workflow templates, review policies, stage/evidence contracts; initially `verified_software_delivery` | Build as configuration and schemas, not a separate orchestration engine (Phase 6B) |
| `harness_activity/` | Bounded, heartbeating harness call; session/workspace recovery | Build |
| `comms_mcp/` | Scoped agent messaging tools, on worker nodes only | Build |
| `registry/` | Profiles/templates, dev YAML loading, policy checking | Build |
| Worker template + MCP catalog CRDs | Versioned system-wide execution capabilities | Build |
| `operator/` | Project templates into current Worker Controller resources; reconcile MCP services | Build |
| Temporal Worker Controller + KEDA | Versioned worker rollouts and backlog scaling | Reuse if verified in selected versions; fallback to Deployments behind adapter |
| `github_integration/` | GitHub App, worktrees, integration branch, PR/CI/approval | Build |
| `steward/` | Per-repo coordination, durable webhook intake, schedule triggers | Build |
| `control_plane/` | Admin API/UI, live cluster state, fleet, audit, metrics | Build |
| `common/persistence/` | Pydantic repositories, SQL migrations, immutable records, transaction boundaries | Build |
| Payload codec | Encryption, compression as appropriate, and large-payload offload | Build and evaluate SDK external storage features, without depending on preview APIs |

## 4. Core design decisions

See [docs/roadmap/design-decisions.md](docs/roadmap/design-decisions.md).

## 5. Versioned schemas and persistence model

See [docs/roadmap/schemas.md](docs/roadmap/schemas.md).

## 6. Repository layout

```text
/infra                 docker-compose.yml (Temporal, Postgres, UI, SeaweedFS, vLLM), .env.example
/common                schemas, config, blob_store, persistence, codec, logging, metrics
/registry              profiles/*.yaml, templates/*.yaml, catalog, loaders
/orchestrator          stable-queue workflows + triage, plan, verify and dispatch Activities
/workflow_catalog     versioned workflow definitions/review policies (one initial template)
/harness_activity      runners, workspace snapshots, session restore, heartbeat
/comms_mcp             worker-local scoped messaging MCP server
/gateway               FastAPI OpenAI API, SSE format adapters, auth, request registry
/github_integration    GitHub App auth, worktrees, integration, PR/CI, webhook ingress
/steward               RepoStewardWorkflow, inbox/outbox, schedule triggers
/workers               generic activity workers, startup validation, Dockerfiles
/operator              Python/Kopf operator by default (Go only if approved) and Worker Controller adapters
/control_plane         api/ FastAPI + web/ React/Vite
/deploy                Helm, CRDs, kind/k3d bootstrap, NetworkPolicies
/tests                 unit, replay/time-skipping, integration, e2e, failure/chaos
/docs                  README.md, rfcs/, adr/, architecture/, templates/, roadmap/, reviews/, demos/, spikes/, benchmarks/, security/, api/, operations/, release.md
/docs/plans            reviewed implementation contracts for new work
/openspec              historical specs/ and archived changes/; no active workflow
/.agents               the one real copy for coding harnesses: skills/<name>/SKILL.md (reviewed specialist
                       skills and Phase 0 documentation skill, when installed), agents/*.md, templates/,
                       sync_agents.py (see .agents/README.md)
/.claude               skills -> ../.agents/skills (symlink, also read by Copilot); agents/ generated
/.codex                agents/*.toml generated for Codex CLI (Codex reads .agents/skills natively)
/AGENTS.md, /CLAUDE.md shared agent instructions; CLAUDE.md imports AGENTS.md
/.github               CI workflows, issue/PR templates, CODEOWNERS; agents/*.agent.md generated for Copilot
/Makefile
/PROJECT_PLAN.md       core plan; detail lives in /docs/roadmap (see the document map)
```

## 7. Implementation phases

**Entry requirement:** Record the Pre-0 spike decision, then complete the repository, OpenSpec, and specialist-skills bootstrap in §0 before starting Phase 0. This is a project-process dependency, not a new runtime component.

### 7.0 Process tiers and phase order (rev 2.11)

**Order:** Pre-0 -> §0 -> 0 -> 1 -> 2 -> 3A -> 3B -> 4 -> 4A -> 5 (MVP complete) -> 6 -> 6B -> 7 -> 8 -> 9. Sub-phases 3A, 3B, 4A and 6B are gated like phases, each with its own acceptance criteria, demo and evidence file. [ADR-0003](docs/adr/0003-early-compose-task-ui.md) records the owner-accepted split between Compose task interaction in 4A and Kubernetes administration in 8, after independent planning design review PASS. Each phase still requires its own implementation design approval.

The review protocol should cost roughly what the phase is worth. Two tiers apply:

| | Light tier (Phases 0, 1, 2) | Full tier (Phase 3A onward) |
|---|---|---|
| Specification | One implementation plan tracing to project-plan requirements | Same |
| Design | Readable plan with design decisions; one independent design review | Plan with full design depth and independent design review (§4.17) |
| Implementation review and verification | **One** fresh independent session that runs the implementation-review skill and then the verification skill against the same `code_sha` | Separate fresh sessions, neither seeing the other's verdict |
| As-built documentation | A section added to `docs/architecture/overview.md` | Cumulative as-built update, independently validated |
| Evidence linkage | `code_sha` and final `head_sha` in the PR record; `docs_sha` only if docs land in a separate commit | Full `code_sha` / `docs_sha` / `head_sha` protocol (§4.17) |
| Documentation skill | May be created at any point; must exist before Phase 3A | Used |

Both tiers keep the non-negotiables: reviewers never share the implementation session, reviews target an immutable commit, required checks pass on the latest head, and the phase demo is run and recorded. In the light tier, independence **between** review and verification is knowingly waived; independence **from the implementer** is not. A design reviewer may move a light-tier phase to the full tier by recording the reason.

### 7.1 Risk register and rethink triggers (rev 2.10)

Each phase implementation plan restates the risks it meets and the measurable signal that means "stop and rethink". Thresholds are owner-set (Pre-0.2) before the phase runs. Hitting a trigger opens a decision-log entry; it does not fail the phase by itself.

| Risk | First exposed | Rethink trigger | Fallback |
|---|---|---|---|
| A local model cannot drive the Claude harness reliably | Pre-0.1, Phase 1 | Spike or benchmark pass rate below the owner's threshold | `openai_agents` harness as default; adapter; optional hosted tier |
| Harness licensing does not permit the intended use or distribution | §0, Phase 1 | Owner or counsel says no | `openai_agents` harness as default; harness installed by the user, never shipped |
| SDK session state cannot be restored on a different worker | Phase 1 | Pod-loss recovery test cannot pass with the SDK's own interface | Adapter that stores transcripts; restart the task from the last workspace checkpoint |
| Workflow Streams (preview) changes or bloats history | Phase 2 | Breaking API change, or history per busy run above the set bound | Offset-based transport behind the event interface |
| Planner output is too poor at the local tier | Phase 3A | Plan validity or routing accuracy on the evaluation set below threshold | Simpler linear plans; stronger planner tier |
| One GPU cannot serve two tiers at once | Phase 3A | Two models cannot be served concurrently within memory | One model with two profiles; hosted top tier |
| Entity-workflow history or Continue-As-New proves fragile | Phase 3B | History bound exceeded, or an orphaned child found in tests | More child workflows; fewer Signals; shorter runs |
| No workable sandbox under Compose | Phase 5 | Sandbox test cannot pass locally | Restrict `repo` mode to Kubernetes; run untrusted tests only in the repository's own CI |
| GitHub App cannot create repositories | Phase 5 | Permission test fails | `new_repo_policy=never`; require pre-created repositories |
| Worker Controller and KEDA cannot meet acceptance | Phase 7 | Scale-to-zero or rollout acceptance fails on the pinned versions | Plain Deployments behind the operator adapter |
| Review process costs more than it returns | Any | A light-tier phase spends more time in review than in implementation | Owner adjusts the tier for that phase and records why |

### 7.2 Phase index

| Phase | Title | Process tier | In MVP | File |
|---|---|---|---|---|
| 0 | Local infrastructure | Light | Yes | [docs/roadmap/phases/phase-0.md](docs/roadmap/phases/phase-0.md) |
| 1 | Harness-in-Activity, single agent | Light | Yes | [docs/roadmap/phases/phase-1.md](docs/roadmap/phases/phase-1.md) |
| 2 | Real-time events and the comms MCP | Light | Yes | [docs/roadmap/phases/phase-2.md](docs/roadmap/phases/phase-2.md) |
| 3A | Persistence, triage, routing and DAG dispatch | Full | Yes | [docs/roadmap/phases/phase-3a.md](docs/roadmap/phases/phase-3a.md) |
| 3B | Verification, escalation, replanning and bounded execution | Full | Yes | [docs/roadmap/phases/phase-3b.md](docs/roadmap/phases/phase-3b.md) |
| 4 | OpenAI-compatible gateway | Full | Yes | [docs/roadmap/phases/phase-4.md](docs/roadmap/phases/phase-4.md) |
| 4A | Live task interaction UI on Compose | Full | Yes | [docs/roadmap/phases/phase-4a.md](docs/roadmap/phases/phase-4a.md) |
| 5 | GitHub delivery | Full | Yes | [docs/roadmap/phases/phase-5.md](docs/roadmap/phases/phase-5.md) |
| 6 | Agent maintenance (steward) | Full | Post-MVP | [docs/roadmap/phases/phase-6.md](docs/roadmap/phases/phase-6.md) |
| 6B | Reusable, independently verified workflows | Full | Post-MVP | [docs/roadmap/phases/phase-6b.md](docs/roadmap/phases/phase-6b.md) |
| 7 | Kubernetes deployment | Full | Post-MVP | [docs/roadmap/phases/phase-7.md](docs/roadmap/phases/phase-7.md) |
| 8 | Platform administration UI and API | Full | Post-MVP | [docs/roadmap/phases/phase-8.md](docs/roadmap/phases/phase-8.md) |
| 9 | Hardening | Full | Post-MVP | [docs/roadmap/phases/phase-9.md](docs/roadmap/phases/phase-9.md) |

## 8. Testing rules

- **Pre-Phase-0 gate:** Verify the repository/OpenSpec/custom-skill bootstrap against the §0 acceptance test and demonstration. Do not treat missing external skill sources as completed work.

- Every Workflow: deterministic replay and time-skipping tests with mocked Activities. Catch direct I/O, wall-clock/randomness and non-versioned breaking changes in Workflow code.
- Unit tests cover Pydantic validation, DAG correctness, template capability matching, BlobStore contracts, authorization, idempotent persistence and event protocols.
- Reusable workflow tests (Phase 6B onward) cover stage dependency ordering, template version pinning, fresh reviewer contexts, exact-SHA/digest evidence, mandatory gates, failed/revised review invalidation and bounded fix/review loops. Phase 5 and later tests exercise authorized/denied new-repository creation and idempotency under retry.
- Integration tests use `make up`, vLLM tiny model, SeaweedFS and application PostgreSQL (or deterministic stubs when model is too large for CI).
- End-to-end GitHub tests use a throwaway test repo configured by env var; skip when absent. Never merge or push directly to the default branch in tests.
- Failure tests inject pod deletion, process crash, dropped/doubled webhook, expired credential, missing blob, AI quality failure, update/stream reconnect and Continue-As-New while children/messages remain active.
- Report measured inline TTFT overhead, end-to-end latency, queue backlog, history event count/size, DB/object-store I/O, and success/escalation rate. A target is not passed until measured.
- Separate unit/integration/e2e/chaos suites; record environment versions and test results before checking items.
- **CI split (rev 2.10):** every PR runs lint, types, unit and replay tests on hosted runners with deterministic model stubs. Integration, end-to-end and benchmark suites that need a real model or GPU run on a schedule or on request against a self-hosted runner, and their latest result is linked from the phase evidence. A phase cannot close on stubbed results alone.
- **Benchmark rule (rev 2.10):** the agent benchmark suite is re-run whenever a model, template, harness version or system prompt changes, and at every phase closure from Phase 1 onward. Results are compared with the recorded baseline.


### Phase demo gate (applies to Phases 0–9)

- Before implementation, independently approve the phase implementation plan against project requirements; record material decisions in ADRs as they arise. After implementing and preliminarily testing a phase, draft its **cumulative as-built architecture overview**, then independently verify the claims before closure. Reference the approved `code_sha`, documentation revision `docs_sha`, implementation-contract revision, demo evidence and ADRs; attach final `head_sha` linkage externally or through a non-self-referential record and require latest-head checks. The reviewed docs must describe observed behavior, not just plans.
- A phase is **not complete** until its implementation tasks, automated acceptance suite, **and** hands-on demo checklist all pass. A test suite alone is insufficient; demonstration alone does not substitute for tests.
- Each demo must be **runnable from documented prerequisites**, with a named entry point (command, API request, or UI navigation), realistic input, clearly visible outcome, and a cleanup/reset method. Prefer a short 3–10 minute presentation with a repeatable script.
- Demonstrate the new phase **integrated with all prior completed phases**, not a disconnected mock. Any stub or simulated failure must be labeled; never silently replace an essential capability with a mock. In Phase 7, the documented CPU-only profile is an allowed demonstration profile, not evidence of GPU behavior.
- Document both a **happy path and a meaningful failure/recovery or permission check** when applicable. Capture evidence under `docs/demos/phase-N.md`; include environment versions, test run/link, commands, expected versus observed output, task/workflow/PR identifiers, and demo pass/fail.
- No demo boxes should be checked before the actual demo has been executed and verified. If a dependency is unavailable (such as a GitHub test repo), record the demo as **blocked**, not passed.
- Sub-phases 3A, 3B, 4A and 6B are each gated as a phase, with evidence in `docs/demos/phase-3a.md`, `phase-3b.md`, `phase-4a.md` and `phase-6b.md`. The Pre-0 spike is gated by its write-up, not by a demo.

## 9. Working agreement for Claude Code

1. Begin only after the §0 repository and specialist-skills bootstrap has passed and the Pre-0 spike decision is recorded. Start each phase by summarizing tasks, dependencies, open decisions and API versions requiring verification. Ask before a materially irreversible choice; otherwise follow these decisions.
2. Implement small, reviewable commits per logical task, starting from an independently reviewed human-readable implementation plan. Record significant decisions as ADRs; after implementation and preliminary tests, draft the cumulative as-built architecture and independently verify it. Preserve distinct tested source, docs and final delivery-head references under §4.17 (or the §7.0 light-tier equivalent for Phases 0–2); run required checks on the latest head and record evidence before checking off work.
3. Check official current docs/PyPI/repositories for SDK APIs. When claims differ, follow the actual API, provide a compatible adapter, and record the deviation and consequence.
4. No new hosted dependencies beyond GitHub, optional Anthropic API, and **optional explicitly opted-in GCS storage**. Always keep the default deployment local.
5. No secrets committed/logged. Prompt content, repository files, tool output and webhook bodies are untrusted; tool/capability privileges come from validated system configuration.
6. Keep this plan as the source of truth for scope, sequencing, constraints and gates (see the §4.16 precedence rule); update task checkboxes only after verified completion, and update the Decision log whenever constraints, APIs, architecture, or acceptance criteria change.
7. **Context loading (rev 2.10):** a session reads `PROJECT_PLAN.md`, the file for its phase, the design sections that file lists under *Read first*, and `docs/roadmap/schemas.md` when it touches schemas. It reads the decision log and revision history only to check why something was decided. Do not load the whole set by default.

## 10. Decision log

See [docs/roadmap/decision-log.md](docs/roadmap/decision-log.md).

## 11. External references to verify at implementation

See [docs/roadmap/references.md](docs/roadmap/references.md). Revision history: [docs/roadmap/revision-history.md](docs/roadmap/revision-history.md).

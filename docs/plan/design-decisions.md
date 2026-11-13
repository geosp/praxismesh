# PraxisMesh plan: core design decisions (§4)

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## 4. Core design decisions

### 4.1 Harness-in-Activity

- One harness Activity is **one bounded harness invocation**, potentially involving multiple internal model/tool exchanges. Define precisely the distinction between SDK `max_turns`, task-level `max_turns`, total execution attempts, timeout, and token budget.
- Use Claude Agent SDK if verified compatible with vLLM; fallback to `claude -p --output-format stream-json` or an adapter behind a stable `HarnessRunner` interface. For OpenAI agents, use their appropriate local endpoint.
- Template injects `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` when applicable, and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. Validate actual current environment settings before implementation.
- Generate MCP configuration and skills mounts **only** from the template. Mount trusted config read-only. Disable or constrain implicit repo/user skill discovery and unauthorized tools. Verify allowed **and prohibited** capabilities.
- Heartbeat with bounded progress metadata; store session ID/checkpoint ref durably. Instrument streamed events and tool usage, but batching/stream transport belongs to Phase 2.
- `TaskResult` is structured; large results are referenced rather than embedded.

### 4.2 Session/workspace durability and worker affinity

- Workers have shared queue `tpl.{template}` and optional pod queue `tpl.{template}.{pod}`.
- Affinity is an **optimization**, never a correctness prerequisite. Pod loss must recover on another worker.
- Persist or reconstruct session state using the SDK's *verified* session-storage interface where suitable; otherwise implement an adapter to save necessary session metadata/records in object storage.
- Separately checkpoint filesystem changes/workspace to `BlobStore`; for repo work, reconstruct from git plus stored uncommitted changes if applicable. A session transcript alone cannot restore filesystem changes.
- A retry must not repeat side effects: use task/turn/attempt IDs, git commit/PR identifiers, and idempotency keys. Explicitly test pod termination between side effect and checkpoint.

### 4.3 Entity Workflows and bounded history

- `OrchestratorWorkflow`, `TaskWorkflow`, and `RepoStewardWorkflow` run on stable orchestration queues with always-on capacity (multiple replicas in production).
- Carry compact deterministic state across Continue-As-New, including stream offset/state, pending message identifiers, and ownership of unfinished children. **Do not assume live children automatically transfer to the new run.** Define lifecycle, tracking and reconciliation.
- Use PostgreSQL for durable, queryable application records and `BlobStore` for large bytes. Use versioned references in Workflow history and Activities; keep Activities deterministic with respect to recorded return values and write idempotency.

### 4.4 Real-time agent communications

- Prefer Temporal Python Workflow Streams where supported and stable enough; verify the exact SDK version (experimental/preview status) and provide a narrow fallback behind an event-transport interface. As checked on 2026-11-10 (re-verify): the module is `temporalio.contrib.workflow_streams`, in Public Preview, built on Signals and polling Updates, so each durable batch still adds history events. Temporal's OpenAI Agents SDK plugin can publish model events to a stream; evaluate it for the `openai_agents` harness before writing custom plumbing.
- **Streams are for progress and observation**, not agent-to-agent request/response commands. Batch token deltas and noisy tool events; avoid one Temporal history event per token.
- `comms_mcp` on worker pods offers `post_status`, `send_to_agent`, `ask_agent`, and `get_task_context`. It talks through a scoped service/client, not arbitrary Temporal admin APIs.
- Agent-to-agent messages use a **durable PostgreSQL inbox**, unique message/correlation IDs, a reply route, bounded blocking timeout, dedupe keys, and a trigger to wake/schedule the recipient agent. Implement cycle/deadlock prevention (time limits, bounded waits, optional dependency detection).
- Store resumable event offsets and attempt IDs. A reconnect returns every **retained** event in order without duplicate display; explicitly report truncation or retention expiry. Continue-As-New must preserve offset continuity when the SDK supports it.

### 4.5 Planning, dispatch and verification

- Validated DAG tasks carry tier, requirements, acceptance checks, risk and optionally estimated token/time budget.
- Schedule **each ready task** as soon as all dependencies pass, not only in synchronized DAG levels. Bound graph size/depth, active children, and outstanding Activity count; keep stable ordering for equally eligible tasks.
- Planner sees the available capability catalog, tier costs/limits and policy restrictions (names/descriptions only; no secrets).
- Match template by tier, capabilities, profile restrictions, model override allowance, model capacity and cost; within eligible tier choose lowest permitted cost. Escalate only when suitable and authorized. If capability is genuinely unavailable, return `needs_input` rather than silently removing the requirement.
- Distinguish retries: transport/pod/vLLM failures use bounded Temporal Activity retries; schema validation uses bounded correction attempts; quality/acceptance failures use a same-tier improvement attempt then tier escalation. Top-tier quality failure may trigger bounded replan.
- All budgets are global and per-task: total time, tokens, turn count, retry count, escalation count, replan count, concurrency, and spending policy. Replans version the plan and preserve verified outputs. **Units (rev 2.10, proposed default):** meter input tokens, output tokens, wall-clock seconds and GPU-seconds per Activity attempt. A template's `cost_weight` is a dimensionless multiplier applied to its tokens to give *cost units*, which is what budgets and the cheapest-eligible-template rule compare. For the optional hosted tier, also derive currency from a configured price table. Spending policy is expressed in cost units, with an optional currency cap for hosted tiers.
- Verifier runs explicit tests/checks when possible, otherwise uses an independent reviewer model; no tool or git I/O in Workflow code.

### 4.6 Delivery mode routing

- `inline`: cheap, low-latency plain model Activity; no plan/harness/workspace/git; stream as it is produced. Target gateway-added TTFT overhead under 2 seconds **as a measured goal**, not a guaranteed property.
- `artifact`: scratch workspace, optional plan, files uploaded via `BlobStore`, and access-controlled artifact refs/links.
- `repo`: resolve target repo; plan/worktrees/integration/PR/CI/merge gate.
- Repo resolution priority: explicit request `metadata.repo` or authorized profile default; explicit URL or `owner/name` from prompt; otherwise `needs_input` unless `new_repo_policy=auto` explicitly allows creation. Default policy is `ask`.
- Client `metadata.delivery` can force mode only within authorization policy; mode upgrades mid-run are durable, auditable events.

### 4.7 Concurrency and capacity

- Cap harness Activities per pod to vLLM's effective capacity; let backlog live in Temporal queues.
- For each template, cap replicas and throughput based on GPU/model capacity, concurrent active requests, memory/KV cache and deployment policy. KEDA backlog alone is not a capacity oracle.
- Separate long-running orchestration queue scaling from short-lived or scale-to-zero Activity queues.

### 4.8 GitHub delivery and safety

- GitHub App private key stays in trusted credential service/secret boundary; issue short-lived repo-scoped installation tokens to the least-privileged execution environment. Do not place private keys in worker pods.
- Each task works on its own worktree/branch. A **dedicated integration coordinator** combines branches, detects overlaps/conflicts, builds one delivery branch, and creates/updates one PR. Conflicts become resolution tasks; never overwrite other task output.
- Persist branch names, commit SHA, PR identity, CI run SHA, and delivery operation IDs in PostgreSQL. Repeated Activities must check existing state and GitHub before creating another branch/comment/PR.
- CI is webhook-driven plus reconciliation/poll fallback. A PR is considered verified only if required checks apply to the **latest head SHA**.
- Default merging requires human approval Signal; profile auto-merge is opt-in and still obeys branch protection, CI, and org/repo policy. Agents never push to default branch.
- Run untrusted repository code in isolated execution environments without privileged GitHub App secrets. The sandbox mechanism is selected by ADR before Phase 5 (§2).

### 4.9 Gateway request/conversation identity and API compatibility

- `conversation_id` can span many turns; each submitted user turn has a unique `response_id` and idempotency key. Store mapping in application PostgreSQL, not inferred exclusively from Temporal Workflow ID.
- `/v1/chat/completions` and `/v1/responses` have **distinct** streaming schemas. Use one internal event model with separate protocol adapters. Avoid leaking private reasoning or internal progress into normal assistant text; expose operational status through a separate endpoint/extension.
- Background jobs support submit, retrieve, and cancel. HTTP disconnect must **not** cancel a durable job unless the caller explicitly requests cancellation. A `needs_input` follow-up resumes the correct logical conversation/job via a new turn.
- Authn and authz are both required: per-client repository access, delivery permissions, rate limits, budget limits, and approval policies. Test with official synchronous and asynchronous OpenAI Python clients.
- **Compatibility matrix (rev 2.10):** publish `docs/api/compatibility.md` in the Phase 4 RFC, listing for each endpoint every request parameter as *honored*, *ignored (documented)* or *rejected*. Proposed starting position, to be confirmed in that RFC: honor `model` (as agent profile), `messages`/`input`, `stream`, `metadata`, `previous_response_id`, `background`, `user` and an output-token cap (applied as a budget ceiling); pass sampling parameters through on the `inline` path and ignore them, documented, on orchestrated paths; reject client-defined `tools`/function calling, `n` greater than 1, log probabilities, audio and image/file inputs in the first release; allow structured-output requests on the `inline` path only when the configured model supports them. Rejected parameters return an OpenAI-style error object with a clear message; nothing is dropped silently. Map errors consistently (401, 403, 404, 409 for idempotency conflicts, 429, 5xx) and report aggregate token usage.

### 4.10 Worker templates as the unit of capability

- `WorkerTemplate`: tier, image, model, API style/endpoint, resources, MCP refs, skills, CLI tools, concurrency, scaling, cost, authorization and secrets refs. Per-pod MCP configuration is from **templates only**.
- `McpServer` catalog entry: `stdio`, `sidecar`, or shared HTTP `service`, plus command/image/url, environment and secret references, health checks and capabilities. `comms_mcp` is baseline; repo-capable templates also include GitHub MCP when configured.
- Template edits create immutable versions and deployment rollouts; preserve in-flight work and restore across pod replacement.
- Operator owns declarative template/capability projection, not the same underlying Deployments that the Temporal Worker Controller manages.

### 4.11 Kubernetes realization

- CRDs: `WorkerTemplate`, `McpServer` with OpenAPI validation generated from versioned Pydantic schemas.
- Prefer the current Temporal Worker Controller's **`WorkerDeployment` CRD** for versioned rollout; confirm exact release and required configuration. Older docs may use `TemporalWorkerDeployment`: do not blindly use a stale name. As checked on 2026-11-10 (re-verify): the rename from `TemporalWorkerDeployment`/`TemporalConnection` to `WorkerDeployment`/`Connection` landed in controller app version v1.7.0 (the upstream docs cite the Helm chart version inconsistently, so confirm it); pin v1.7.0 or later. Per-version resources such as autoscalers attach through a separate `WorkerResourceTemplate` object that references the deployment via `spec.workerDeploymentRef`.
- Configure Worker Controller to own versioned Deployment resources and version-scoped KEDA `ScaledObject`s, if verified. **Explicitly allow `ScaledObject` in Worker Controller resource templates and verify RBAC/admission settings**. If integration cannot meet the acceptance criteria, use plain Deployments behind an operator adapter and record the deviation.
- KEDA scales **harness Activity** workers according to compatible Temporal metrics/queue version. Orchestration workers remain available. Choose one supported external-metrics adapter strategy and avoid HPA/KEDA API-provider conflicts.
- Support SeaweedFS for default local storage; optional Ceph S3/GCS adapters do not change business workflows. Secrets remain Kubernetes references. Enforce ingress, egress, RBAC, quotas and readiness checks.

### 4.12 Control plane is the authoritative configuration writer

- **Task interaction (Phase 4A, proposed in ADR-0003):** the Compose-hosted UI uses Phase 4 gateway/task APIs and Phase 3B input/approval actions, with Phase 2/4 event transport. Reads and writes are authenticated and authorized server-side; the browser has no direct database, Temporal admin, object-store admin or Kubernetes access. It does not grant capabilities or run a second orchestrator.
- **Platform administration (Phase 8):** the UI speaks only to the control-plane API for configuration; that API validates and updates CRDs/profiles with audit trails. Direct `kubectl` edits may occur; the UI reads live Kubernetes state through the API and presents those changes. Phase 8 extends the Phase 4A frontend after the Phase 7 cluster contracts exist.
- Separate `admin`/`operator`/`viewer` capabilities; enforce permissions server-side.

### 4.13 Application data and large-payload persistence

- Use a **separate application schema/database** in PostgreSQL, not Temporal's private persistence tables.
- Implement `BlobStore` operations for `put`, `get`, `delete`, `stat`, and access-controlled retrieval/presign where backend supports it. Adapter selection by environment/configuration: `seaweedfs` default (S3), `ceph_s3`, optional `gcs`.
- Data integrity: immutable content keys or version IDs, checksums, encryption strategy, retention/GC, tenant/repo isolation, and audit metadata. Store object refs in PostgreSQL; do not put sensitive large values in Temporal history.
- Use a transactionally committed PostgreSQL **outbox** and deduplication for external side effects/events where atomic DB+Temporal/GitHub commits are impossible. Repair inconsistencies by reconciliation.
- For storage failures, retry idempotently and distinguish missing, expired, unauthorized and corrupt blobs. Ensure artifact references remain valid across workflow retries and Continue-As-New.
- **Retention classes (rev 2.10, proposed defaults, all configurable):** every `BlobRef` and stored record carries a retention class from the first write. Proposed defaults: workspace and session checkpoints 7 days after the task reaches a terminal state; transcripts and tool output 30 days; delivered artifacts 90 days; audit, approval and delivery-ledger records kept until explicitly purged. Align Temporal namespace retention so history never outlives the blobs it references without the reference resolving to a clear *expired* error.
- **Deletion:** provide delete-by-conversation and delete-by-request operations that remove blobs, redact prompt and transcript content in PostgreSQL, and leave an audit tombstone. Deletion never rewrites Temporal history, which is one more reason content stays out of it.
- **Backup and restore:** define one procedure covering Temporal's database, the application database and the object store, with a stated recovery point. Because the three cannot be snapshotted atomically, restore includes a reconciliation pass that reports dangling references and orphaned blobs. The procedure is exercised as a drill in Phase 3A and hardened in Phase 9.

### 4.14 Steward: event-driven repo management

- Exactly one logical `RepoStewardWorkflow` per managed repository coordinates events, schedules, outstanding work, and reconciliation; it does not run coding models directly.
- Webhook bridge validates signature, persists raw event and delivery ID in a PostgreSQL inbox transaction, acknowledges promptly, and asynchronously forwards work to Temporal. Deduplicate and periodically reconcile missed events.
- Filter self-generated GitHub events and coalesce related reviews/CI notifications to avoid automation loops. Treat issue text, reviews and repository instructions as untrusted.
- Per-repo integration/delivery operations are serialized or locked; unrelated analysis can proceed concurrently. Maintain versioned schedule configs; a schedule starts a trigger workflow that signals the existing steward.
- Agents maintain `AGENTS.md`, `CLAUDE.md`, and `.claude/skills/` only through normal PR policy; repo instructions cannot override platform security.

### 4.15 Reusable, independently verified workflows (planned platform capability)

**Goal:** The fresh-session design/review/verification protocol used to **build this platform** can later be offered to users **of this platform**. This is a reusable, versioned policy-driven workflow, **not** an additional orchestration engine and **not** a requirement to run the exported Claude Code development skills in production. The first packaged workflow is `verified_software_delivery`; the same framework can support other multi-stage work with different roles and checks.

- **Definition:** A versioned `WorkflowTemplate` describes named stages, dependencies, allowed `WorkerTemplate` capabilities, artifact contracts, review policy, max attempts/budgets, timeout, approval requirements and final delivery. Example stages: `requirements/spec -> design -> independent_design_review -> implement -> independent_code_review -> independent_verification -> approval/delivery`. For a *new* repository, insert `authorize_and_provision_repository` **before** implementation; existing repositories skip that step. OpenSpec may be a configured specification adapter, but is not mandatory for all runtime workloads.
- **Independence:** Each reviewer/verifier runs as a separate harness invocation with fresh session/workspace, minimum required inputs, an immutable spec/design revision and a precise tested code snapshot/commit or artifact digest. For its **initial independent verdict**, it must **not** receive prior reviewers' reports, verdicts, conclusions, the implementation session's transcript, or anyone's private reasoning. Approved design artifacts and authoritative requirements are permitted inputs. A coordinator may route actionable findings to the implementer; a later targeted remediation check may see the fix list only after a fresh, recorded independent assessment. An implementation agent cannot approve its own output; reviewers must not modify inspected code. Reviewer and author identities/roles must be recorded; distinct model providers are optional, not the definition of independence.
- **Evidence and gates:** Each stage produces structured, immutable results (`pass`, `fail`, `blocked`, `needs_input`), checks run, tested SHA/digest, tool/skill/policy version and cited artifact refs. Temporal determines transitions from recorded, versioned results via Activities; PostgreSQL indexes stage executions and verdicts; `BlobStore` stores large logs, transcripts and test artifacts. A failure opens a bounded fix-and-rereview loop; changed code invalidates reviews/verification for prior SHAs. Quality-review verdicts and GitHub CI/branch protection are **both** required where policy specifies them.
- **Security and scope:** Tenant/repository allowlists, role permissions, required human approvals, budgets, max iterations and escalation limits apply to every stage. Repository creation is default-deny or approval-required unless a trusted profile explicitly permits it. Untrusted specifications, generated skill files and repository instructions cannot grant additional tools, alter policy or bypass gates. Keep credentials out of review agents and sandbox all untrusted tests.
- **Delivery (resequenced in rev 2.9):** This capability is **outside the first-release MVP** and is delivered in **Phase 6B**, after the orchestrator (3A/3B), gateway (4), GitHub delivery (5) and steward (6) are verified. Phase 6B supplies the stage/gate runner with a local artifact demonstration, binds it to commit-pinned GitHub review, CI and PR delivery, exposes authorized template selection at the gateway, and makes the approved policy available to issue/review/scheduled stewardship. Phase 8 surfaces stage verdicts, evidence, retries and human approvals. Phase 9 tests policy bypass, tampering and recovery. Earlier phases must not build partial versions of the runner.
- **Incremental scope:** Keep the fast `inline` path unchanged. Do not make every task run the full software-delivery process. No separate runtime workflow engine, hosted service or UI workflow builder is required for the first release; start with one declarative template and a small extensible registry.

### 4.16 Specification, execution, and state ownership

**Objective:** Make the source of truth for requirements, durable control flow, indexed business state, and large artifacts explicit. Avoid duplicated authority and mutable state that could change an in-flight execution.

**Sequencing note (rev 2.9):** The `WorkflowTemplate`-related items in this section take effect in Phase 6B. The specification-pinning, idempotency and reconciliation items apply from Phase 3A.

#### Ownership boundaries

| Component | Authoritative responsibility |
|---|---|
| Git + OpenSpec | Approved project or managed-repository specifications, designs, change proposals, development task definitions and revision history |
| Temporal | Durable orchestration, execution history, timers, retries, stage transitions and workflow progression |
| Application PostgreSQL | Queryable application records: requests, task/attempt metadata, immutable revision references, review results, approval provenance, audit and budget records |
| Temporal's PostgreSQL persistence | Temporal's internal service data and event history; never directly queried or modified by PraxisMesh application code |
| `BlobStore` (default SeaweedFS) | Large immutable/referenced evidence, logs, transcripts, workspace/session checkpoints, test output and artifacts |

The Git repository holds canonical specification content. The versioned `workflow_catalog/` defines available review/gate policies; once published, application PostgreSQL may hold immutable approved/deployed template snapshots and version references for discovery and audit. Neither mutable PostgreSQL rows nor agent-supplied repository content can silently replace a pinned specification or an authorized execution policy. A `WorkflowTemplate` describes **how** work is governed; OpenSpec describes **what** to build. OpenSpec is an optional specification source for managed user repositories, not the runtime workflow engine.

**Build-time precedence rule (rev 2.9).** For building PraxisMesh itself: (1) `PROJECT_PLAN.md` is authoritative for scope, phase sequencing, hard constraints and acceptance gates. (2) An approved OpenSpec spec is authoritative for the detailed requirement text of the phase it covers and must trace to plan requirements. (3) If the two conflict, the plan governs until the plan is changed by a reviewed PR with a decision-log entry; an OpenSpec change never overrides the plan silently. (4) RFCs and ADRs record design and rationale and are not requirement sources. (5) As-built documentation describes what exists and never creates requirements. This supersedes earlier wording that OpenSpec alone is canonical for requirements.

#### Versioning, consistency and reconciliation

- [ ] At execution admission, resolve an approved specification Git SHA plus the relevant OpenSpec revision/path or content digest, the approved `WorkflowTemplate` ID/version, and any approved design revision. Persist these immutable references with the run.
- [ ] A later spec or policy change must not silently modify a running workflow. Use an explicit approved transition, restart, or new execution, with an auditable migration decision where necessary.
- [ ] Store only the small immutable references and replay-safe decisions needed by Temporal. Never read Git, mutable PostgreSQL, object storage, network endpoints, or wall-clock state directly inside Workflow code; external I/O runs in Activities, whose results are recorded.
- [ ] Use stable idempotency/operation IDs, transactional inbox/outbox where applicable, and reconciliation across GitHub, PostgreSQL and Temporal. Never assume a distributed transaction across these systems.
- [ ] Database read models and operational dashboards must reflect workflow results, not independently advance a Temporal workflow or override its approval gates. Detect and repair projection lag and interrupted writes.

#### Independent reviews and evidence scope

For `verified_software_delivery`, the accepted specification states the deliverables and tests; the pinned `WorkflowTemplate` defines review sequence, allowed capabilities, separation of duties, and approval rules; Temporal enforces transitions; PostgreSQL indexes stage verdicts/approvals; `BlobStore` preserves supporting evidence; Git identifies the exact inspected commit.

- [ ] Bind each design review, implementation review, verification verdict, and CI result to the approved specification/design revision, workflow policy version and tested Git commit or artifact digest.
- [ ] Treat evidence for a superseded commit, changed design, expired policy requirement or mismatched spec revision as stale. Re-run only the affected checks according to the approved policy, never automatically carry forward a prior pass.
- [ ] Do not grant runtime agents authority from OpenSpec files, issue bodies, repo-defined skills, or prior session transcripts; capability/approval enforcement stays in trusted server-side policy.

#### Build-time and runtime separation

The external Claude Code sessions and project-level OpenSpec artifacts used **to build PraxisMesh** are not themselves the production execution system. PraxisMesh may later consume each managed repository's own approved specifications through a scoped adapter; it must also support non-OpenSpec workflows. The two environments must not share mutable execution state or automatically inherit credentials and permissions.

**Accept:** A demonstrated trace connects approved spec SHA/revision -> pinned template version -> Temporal workflow/run -> PostgreSQL records -> evidence digest. Tests prove that mid-run spec changes do not drift execution, stale reviews cannot pass gates, crash/retry reconciliation does not duplicate effects, and no direct access to Temporal's persistence tables is required. These are future implementation acceptance criteria, not completed checks.

### 4.17 Human-readable design and as-built documentation lifecycle

**Intent:** Maintain readable, cohesive engineering documentation alongside the formal OpenSpec requirements. These are complementary forms of evidence, not competing specification or execution engines. The outputs are: an RFC before construction; an ADR for significant decisions whenever they occur; and a cumulative as-built architecture reference after verified implementation.

| Artifact | When | Purpose | Location |
|---|---|---|---|
| **RFC (Request for Comments)** | Prior to implementing each phase or material change | Proposed design, goals/non-goals, alternatives, diagrams, contracts, data flows, failure modes, tradeoffs, risks and acceptance tests | `docs/rfcs/phase-N-<topic>.md` |
| **ADR (Architecture Decision Record)** | When a consequential architectural decision is approved or superseded | Why an option was chosen, alternatives considered, consequences, status and relevant source links | `docs/adr/NNNN-<decision>.md` |
| **As-built architecture** | Draft after implementation and preliminary testing; independently validate during final verification and correct before phase closure | What actually runs: components, APIs, Temporal Workflows/Activities, application PostgreSQL data models, storage, deployment, operational behavior, diagrams and known limitations | `docs/architecture/overview.md` and topic pages as needed |

- [ ] For each phase, create or update a concise RFC referencing the relevant approved OpenSpec spec/change version and project-plan requirements. Independently review and approve the RFC before implementation. An RFC documents intent, not proof of completion.
- [ ] For material decisions, write an ADR with context, decision, considered alternatives, consequences, status (`proposed`, `accepted`, `superseded`) and links to affected requirements/RFCs. Do not generate perfunctory ADRs for trivial implementation details. When a decision changes an approved requirement, update OpenSpec and the master plan through their normal change processes.
- [ ] Following implementation and preliminary tests, draft or update the **cumulative** as-built architecture overview **before final independent verification**, including code paths, observed integrations, failure/recovery behavior, supported deployment configuration and deviations from the RFC. Include meaningful diagrams. Reference the frozen **tested implementation commit** (`code_sha`) or immutable source-tree digest, plus specification/decision revisions; do not require a tracked document to contain the SHA of the commit that will later contain that same document.
- [ ] Make documentation a phase gate: design review checks the RFC against requirements; independent implementation review checks code versus the approved RFC and applicable ADRs; independent verification checks that **drafted as-built claims and diagrams** match observed behavior of the frozen implementation snapshot. Commit the documentation as a separate revision (`docs_sha`); verify the documentation as it exists at that revision. Record the mapping of `code_sha` -> `docs_sha` -> validation evidence in a separate phase handoff/PR check or evidence record, **never by asking a tracked file to name its own final SHA**. A code change requires affected reviews/tests and documentation to be refreshed; a documentation-only correction requires renewed documentation review/checks, but need not repeat unaffected code tests if the verified source tree is unchanged.
- [ ] Maintain a navigable `docs/README.md` or architecture index, with links between phase RFCs, ADRs, the current architecture overview, OpenSpec revisions and demo evidence. A new engineer should understand the system without reconstructing it from individual specs.
- [ ] Keep templates and automation lightweight: a documentation skill may scaffold, update and lint these files, but cannot approve its own work or treat generated text as verified design or observed implementation.

**Commit and evidence closure protocol (applies to every full-tier phase; Phases 0–2 use the §7.0 light tier):**

1. **Freeze implementation:** Record `code_sha` (the last implementation commit examined) and, when helpful, the content/tree digest for relevant source/configuration paths. Run initial implementation review and executable acceptance tests against this immutable snapshot.
2. **Draft, commit, and validate docs:** Write the as-built account using the tested implementation, record its `code_sha` reference, and commit RFC/ADR/as-built/evidence changes. Record `docs_sha` (the documentation revision under review). An independent verifier checks observable behavior against the source snapshot and compares the documentation **as committed at `docs_sha`** against those observations. If necessary, correct and re-review the docs.
3. **Close on the actual delivery head:** Let `head_sha` be the PR/delivery head after any documentation, demos or review-record commits. Enforce all required branch checks/CI on **that latest `head_sha`** and verify that the relevant source/configuration tree is unchanged from the reviewed `code_sha`. If the source tree differs, repeat affected code reviews and functional tests; if only docs/evidence changed, repeat affected documentation validation and latest-head checks. No stale status check can approve a newer head.
4. **Link without self-reference:** Record `{spec_revision, code_sha, docs_sha, head_sha, tests, review IDs, evidence digests}` in an immutable PR/check-run, release/approval record or other **separately versioned** evidence ledger after the checked head is known. Repository-stored evidence may reference a **prior tested commit** and its own content digest, but must never be required to contain the SHA of the commit that contains that evidence. If a new evidence commit moves the head, re-evaluate latest-head checks before closing.

The coordinator verifies the linkage and closes the phase only when implementation, independent assessments, documentation, demonstrations, and required latest-head checks all pass. This protocol is a **build-time handoff convention**; Phase 5 runtime GitHub delivery separately enforces its existing latest-head-SHA rules.

**Phase 0 bootstrapping:** Phase 0's initial RFC is authored using a simple template and reviewed normally. *After* that first approved design, a fresh implementation session creates the project-scoped documentation skill (for example `.claude/skills/praxismesh-documentation/SKILL.md`) and templates. The skill is reviewed using the existing specialist review process and demonstrated in a fresh session. The skill then assists with Phase 0's as-built documentation and later phases. **The skill is a light-tier deliverable (Phases 0–2, due before Phase 3A), not a pre-Phase-0 prerequisite**, avoiding a circular dependency; the skill is never a runtime privilege of PraxisMesh agents by default.

**Accept:** A new developer can follow approved requirements through the RFC/ADRs to a code snapshot, the independently validated as-built architecture and evidence record with distinct `code_sha`, `docs_sha` and final `head_sha`. A seeded stale design or invented as-built claim must fail independent review or verification; a documentation-only commit must not cause an impossible self-reference requirement or bypass latest-head CI. No additional hosted service or documentation framework is required.

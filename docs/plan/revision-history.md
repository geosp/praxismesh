# PraxisMesh plan: revision history

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

### Revision summary

**Revision 2.10:** Planning-only additions and a file split; no architecture change and no resequencing. Adds project CI and open-source project files to bootstrap; an agent benchmark suite, baseline observability, retention metadata and a first threat model in Phase 1; cost metering, retention enforcement, deletion and a backup drill in Phase 3A; an approval and input CLI in Phase 3B; a gateway compatibility matrix in Phase 4; a completed threat model and the first tagged release in Phase 5; a risk register (§7.1); and harness licensing as an open owner decision. Splits the document into a core plan and `docs/plan/` files with a document map and per-phase reading lists. Numeric defaults introduced here are proposals. **No repository, code, infrastructure or skills were created; all tasks remain unchecked.**

**Revision 2.9:** Planning-only resequencing after an external review; no architecture change. Adds a Pre-0 feasibility spike and open-inputs table; moves minimal persistence into Phases 0–2; splits Phase 3 into 3A and 3B; collects the reusable verified-workflow capability into a post-MVP Phase 6B; defines the first-release MVP (Phases 0–5) and non-goals; adds light and full process tiers; states one build-time precedence rule between this plan and OpenSpec; moves the Worker Versioning strategy to Phase 7 and a security baseline to Phase 5; names sandbox and tenancy as required decisions; adds a fallback for the specialist skills; records web-checked facts and completes the reference list. No task was dropped; moved tasks keep their wording except where a stub note no longer applied. Statements in older revision summaries and decision-log rows about Phase 3, 4, 5 and 6 carrying workflow-template work are superseded by this revision. **No repository, code, infrastructure or skills were created; all tasks remain unchecked.**

**Revision 2.8:** Planning-only closure of the final sanity-check findings. Replaces self-referential "same final commit" requirements with distinct tested source (`code_sha`), reviewed documentation (`docs_sha`) and final delivery head (`head_sha`), including source-tree checks and latest-head CI. Drafts as-built documentation before final independent verification; restricts fresh first-pass reviewers from prior verdicts/transcripts; standardizes the runbook at `docs/operations/runbook.md`. No new application phases, technology changes or implementation. All existing tasks remain unchecked.

**Revision 2.7:** Planning-only addition of a human-readable RFC/ADR/as-built architecture lifecycle alongside OpenSpec. Establishes review and final-SHA documentation gates for every phase, a cumulative architecture overview, and a project-scoped documentation skill to be created during Phase 0 after an initial manually authored and reviewed RFC. Adds repository paths, decision-log guidance and skill verification. Earlier specifications, phases and prerequisites remain intact; no repository, skills or code have been created and no implementation tasks checked.

**Revision 2.6:** Planning-only consolidation of three approved additions: (1) a pre-Phase-0 evaluation of a custom OpenSpec workflow schema and independent-session handoffs; (2) §4.16 specification/execution/state ownership, immutable specification and policy pinning, evidence invalidation and reconciliation; (3) Phase 7 Python/Kopf-versus-Go/Kubebuilder operator design gate. Clarifies the existing Python default without selecting or implementing Go. Existing phase boundaries and previous acceptance criteria are preserved. **No GitHub repository, code, infrastructure, skills or workflows were created or installed. All implementation and demonstration tasks remain unchecked.**

**Revision 2.5:** Adopted **PraxisMesh** as the official project/product name and designated `praxismesh` as the intended GitHub repository slug. Added the tagline and open-source intent; clarified that availability, ownership, license, and repository creation remain pending. Updated project overview and bootstrap instructions. **Planning only: no repository, software, infrastructure, or skills created or installed, and no implementation tasks marked complete.**

**Revision 2.4:** Planning-only addition of a **reusable, independently verified workflow capability**, with an initial `verified_software_delivery` template. Adds versioned stage/review evidence contracts and incremental Phase 3/4/5/6/8/9 acceptance tests for policy-gated execution, optionally authorized new GitHub repository creation, independent commit-pinned review, verification, approvals and stewardship. No new phase or runtime engine. **Phase 0 and build-time specialist-skill bootstrap remain unchanged; no code, repository or infrastructure was created and no tasks were marked complete.**

**Revision 2.3:** Expanded **Phase 0 only** with a proposed skill-specialized session workflow: approved OpenSpec/plan alignment, sanitized/versioned exports from the other Claude Code account, independent design and implementation reviews, independent verification of the same commit, and final demo/approval gate. Bootstrap and Phases 1–9 remain unchanged. **Planning update only; no repository, skills, infrastructure, or tests were created or run.**

**Revision 2.2:** Added the §0 GitHub repository naming/creation, OpenSpec initialization, external specialist-skill installation, isolated-session readiness and bootstrap demo gate. The repository name is a proposal; external skill sources are pending. No installation or GitHub repository creation has occurred. Preserves the ten application phases and all uncompleted checkboxes.

**Revision 2.1:** Added live, reproducible demo checklists and evidence requirements to all ten phases (0–9). All implementation and demo checkboxes remain unchecked.

| Phase | Incorporated review changes |
|---|---|
| 0 | SeaweedFS replaces MinIO, app DB separated, blob smoke test and optional backends |
| 1 | Durable sessions + independent workspace checkpoints, bounded harness turns, capability isolation, lost-pod recovery |
| 2 | Workflow Streams/retention, durable correlated inbox, idle-agent wake-up, timeout/cycle protection, batched events |
| 3 | PostgreSQL app state + Claim Check, stable orchestrator queues, incremental DAG, bounded budgets/replans and explicit retry categories |
| 4 | Persistent conversation identity, separate SSE schemas, background lifecycle, idempotency, authorization and SDK compatibility |
| 5 | Integrated delivery branch/PR, token scope, crash-safe delivery, latest-SHA CI and merge protections |
| 6 | Steward coordination, webhook inbox/reconciliation, loop prevention, versioned schedules, per-repo delivery locks |
| 7 | Current Worker Controller CRDs, KEDA version-aware scaling, GPU capacity, recovery, safer operator/controller ownership |
| 8 | Original UI/control-plane requirements retained; reads updated application persistence and storage/worker architecture |
| 9 | Original hardening requirements retained; encryption, retention and chaos testing updated for `BlobStore`/PostgreSQL |

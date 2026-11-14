# PraxisMesh plan: Phase 3A

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 3A: Persistence, triage, routing and DAG dispatch

**Read first:** `PROJECT_PLAN.md`, then §4.5, §4.6, §4.7, §4.13, §4.16; schemas.

*Split from the former Phase 3 in rev 2.9. Full process tier starts here.*

- [ ] Extend the Phase 0–2 **application PostgreSQL schema/migrations** to cover plans/revisions, tasks, attempts, messages, budgets, requests, blob refs, event index and audit metadata. Implement idempotent repositories and optional outbox patterns for cross-service operations.
- [ ] Complete the `BlobStore` contract begun in Phase 1 (optional Ceph S3 and GCS adapters, access-controlled retrieval/presign, retention metadata) and add Claim Check reference passing for large prompts, context, results, transcripts and artifacts. Avoid large Activity parameters/results and unnecessary history events.
- [ ] Triage and plan Activities produce validated `TriageResult` and `PlanSchema`; bounded structured-output retries. Build ~50 prompt evaluation set for delivery-mode and tier routing.
- [ ] Support `inline` (ordinary no-tools model call), `artifact` (scratch + `BlobStore`) and `repo` (local-git stub until Phase 5). Handle client mode override with authorization and auditable mid-run upgrades.
- [ ] Implement incremental DAG scheduling of **ready tasks** through child `TaskWorkflow`s on a **stable orchestration queue**. Route only harness Activities to `tpl.{template}` or affinity queues.
- [ ] Implement tier/capability matching, allowed model overrides, cheapest eligible template, planner capability catalog, pod concurrency and vLLM capacity bounds.
- [ ] Record predicted vs actual successful tier and measured first-token overhead for inline path.
- [ ] Meter cost units per §4.5 and write them to the budget ledger; show them in the phase demo.
- [ ] Implement retention enforcement (garbage collection by class) and the delete-by-conversation and delete-by-request operations from §4.13, with audit tombstones.
- [ ] Add `make backup` and `make restore` for the Compose stack and run the §4.13 drill: restore into a clean stack, run reconciliation, and report dangling references and orphaned blobs.
- **Accept:** simple question produces no plan/workspace/git; artifact is retrievable; DAG tasks start as dependencies finish and run on two tiers; capability policy holds; routing accuracy on the evaluation set is measured and reported; large artifacts do not inflate Workflow history; a delete request removes a conversation's blobs and redacts its rows; a backup restores into a clean stack with reconciliation reporting no unexplained dangling references.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** A quick question stays fast; a complex request is planned and delegated across tiers.

- [ ] Ask a simple question and show the answer with no DAG, workspace, or git creation; display measured first-token overhead.
- [ ] Submit a multi-step artifact request and show a live dependency graph where independent tasks overlap; retrieve the completed artifact via its `BlobStore` reference.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-3a.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

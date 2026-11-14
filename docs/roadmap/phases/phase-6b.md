# PraxisMesh plan: Phase 6B

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 6B: Reusable, independently verified workflows

**Read first:** `PROJECT_PLAN.md`, then §4.15, §4.16; schemas.

*New in rev 2.9. Collects the §4.15 work formerly spread across Phases 3, 4, 5 and 6. Post-MVP. Depends on Phases 3B, 4, 5 and 6.*

- [ ] Add a **declarative, versioned `WorkflowTemplate` stage/gate runner** on top of existing `OrchestratorWorkflow`/`TaskWorkflow` (no second engine). Persist stage input/output refs, actor role, independent review verdicts, policy version and budget ledger. Provide initial `verified_software_delivery` definition; run it first against a local artifact, then against real GitHub commits through the Phase 5 delivery path.
- [ ] Enforce fresh independent reviewer contexts, immutable artifact/SHA binding, evidence-required gate transitions, no self-approval, and invalidation/re-review after revision. A failed stage can request bounded correction without bypassing its policy. OpenSpec is an optional source of requirements/specifications, not a mandatory harness dependency.
- [ ] Allow an **optional authorized workflow template/profile selection** through validated request metadata or a documented extension; default remains the current triage path. Reject caller-supplied stage/tool/policy definitions that bypass the server-side workflow registry. Do not compromise OpenAI-compatible wire semantics.
- [ ] Bind `verified_software_delivery` to real GitHub commits: optional approved repository provisioning; independent design review, implementation review, repeatable verification (all pinned to correct spec/commit), CI on final SHA, then PR and final approval. A failed or stale review blocks delivery; a changed commit reopens the necessary checks. Store workflow-stage evidence and link it from the PR.
- [ ] Allow each managed repository to pin an approved, versioned **review/verification workflow policy** from the same workflow catalog. Issue, PR-review and scheduled work follow its stage gates before Phase 5 delivery, without granting privileges via untrusted repository files.
- **Accept:** a policy-driven multi-stage local artifact run blocks on a failing independent review and resumes only after a corrected artifact is re-verified; on GitHub, a failed or stale review blocks delivery and a changed commit reopens the necessary checks; an authorized new-repository request completes the same review/verification/PR policy; caller-supplied stage, tool or policy definitions are rejected; the configured review policy cannot be bypassed by a webhook or agent-generated issue; the `inline` path is unchanged.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** A governed, multi-stage delivery where no stage can approve its own work.

- [ ] Run the initial workflow template with a local artifact: an isolated reviewer rejects a seeded defect, the implementation stage corrects it, and independent verification permits progression; show commit/digest and evidence refs for each gate.
- [ ] On a throwaway repository, walk through design review -> implementation -> independent review -> verification -> PR approval. Inject a reviewer rejection and prove the gate cannot be skipped; change the commit after review and show the affected checks reopen. If the GitHub test owner is unavailable, record this item as blocked, not passed.
- [ ] Trigger the same policy from a labeled issue through the steward and show the stage gates still apply.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-6b.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

# PraxisMesh plan: Phase 6

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 6: Agent maintenance (steward)

**Read first:** `PROJECT_PLAN.md`, then §4.8, §4.14; schemas.

- [ ] Webhook ingestion validates signatures, transactionally saves delivery IDs/payload refs in PostgreSQL inbox, acknowledges rapidly and asynchronously signals/starts one logical `RepoStewardWorkflow` per repository.
- [ ] Steward is a coordinator: dispatch events via Phase 3A/3B workflows and deliver via Phase 5, never acting as a model-powered coder itself.
- [ ] Handle issue label `agent`, review comments on agent PRs, default-branch CI failures, deduplication, self-generated event filtering, event coalescing and missed-webhook reconciliation.
- [ ] Version per-repo Temporal schedule configs and overlap policies; schedule trigger Workflows signal the existing steward rather than assuming schedules can directly Signal it.
- [ ] Repository-scoped concurrency/locks for integration/delivery, with parallel independent analysis, recoverable lock leases and explicit conflict policy.
- [ ] Treat repository instructions/issues/comments as untrusted; read and propose changes to `AGENTS.md`, `CLAUDE.md`, `.claude/skills/` via PRs only, without privilege escalation.
- [ ] Preserve durable repo event ledger, pending work and maintenance state across Continue-As-New.
- **Accept:** issue label opens linked PR; review comment produces update; schedule opens upkeep PR; duplicate/missed webhook cases recover; concurrent requests don't overwrite; no agent-generated event loop; bad repository instructions cannot trigger privileged actions.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** Repository events create controlled, recoverable maintenance work.

- [ ] Label a test GitHub issue `agent`, then show the steward create a tracked orchestration job and open a linked maintenance PR through Phase 5.
- [ ] Post a PR review comment and show the existing work is updated rather than launching an unrelated duplicate.
- [ ] Redeliver the same webhook and simulate one missed webhook; demonstrate deduplication and reconciliation, with no self-triggered agent loop.
- [ ] Trigger a configured scheduled upkeep task and show the repo lock prevents conflicting delivery while independent analysis can continue.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-6.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

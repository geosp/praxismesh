---
id: ADR-0003
title: Deliver a Compose task UI after the Phase 4 gateway
status: accepted
date: 2026-11-13
issue: "#56"
related: [PROJECT_PLAN.md sections 7.0 and 7.2, docs/plan/phases/phase-4.md, docs/plan/phases/phase-8.md, docs/plan/design-decisions.md section 4.12]
supersedes: null
superseded_by: null
---

# ADR-0003: Deliver a Compose task UI after the Phase 4 gateway

Accepted by the owner on 2026-11-13 for [issue #56](https://github.com/geosp/praxismesh/issues/56),
after the independent [planning design review passed](../reviews/general-early-task-ui/design-review-80c2dc2.md).
This acceptance records the phase sequence; it does not approve a UI implementation design.

## Context and problem statement

The owner wants a browser interface for live interaction with tasks earlier than
Phase 8. The current Phase 8 combines task interaction with Kubernetes-dependent
administration, so the UI waits for deployment and fleet work in Phase 7.
Phases 2, 3B and 4 already plan resumable progress, durable task controls,
questions/approvals, conversation identity, authentication and authorization.
The project defaults to a local, self-hosted deployment with Docker Compose
through Phase 6B. An early UI must reuse these contracts rather than create a
second execution or authorization path.

## Considered options

- Keep the entire UI in Phase 8: smallest change to sequencing, but delays live
  browser interaction until Kubernetes deployment is complete.
- Move all of Phase 8 before Phase 7: creates unmet CRD, pod/node, scaling and
  rollout dependencies, or requires a second Compose fleet-management backend.
- Split task interaction into Phase 4A; retain Kubernetes administration and
  later capability views in Phase 8.

## Decision outcome

Chosen option: split out Phase 4A, after Phase 4 and before Phase 5, because live
task interaction can reuse the gateway without waiting for cluster administration. It is part
of the MVP and follows the [full process tier](../../PROJECT_PLAN.md#70-process-tiers-and-phase-order-rev-211), like Phase 4. Phase 5 remains the
MVP completion point. This ADR is a sequencing decision, not the implementation
RFC or a claim that any UI is available today.

Phase 4A uses the planned TypeScript/React/Vite stack and runs in Docker Compose.
It provides:

- Authenticated conversation and task submission using Phase 4's supported
  input types; no new file-upload or tool capability is implied.
- A stable, visible request/task ID and a task list for returning to background
  work after closing the browser.
- Live status, output and tool events, plus plan/dependency progress where
  provided by the server. Operational events remain distinct from assistant
  output and do not expose private model reasoning.
- Retrieval of completed results and existing artifact references.
- Resumable observation with duplicate suppression and explicit retention-gap
  indication, using the Phase 2/4 event contracts.
- Questions and approval actions using Phase 3B's authenticated, audited API;
  conversation continuation follows Phase 4 identity semantics.
- Explicit cancellation. Browser disconnect never cancels durable work.
- A minimal task summary for existing status, attempts and budget fields;
  broader fleet and performance dashboards stay in Phase 8.

The UI calls trusted server APIs. It gets no direct database, Temporal admin,
object-store credential or Kubernetes access. It cannot grant tools, bypass
approval gates or change template capabilities. Authentication and authorization
are enforced on the API; a hidden button is not an access control.

[Phase 8](../plan/phases/phase-8.md) retains template/profile/MCP administration, cluster/fleet management,
deployment/rollout/scale controls, GPU placement, full operational dashboards,
external kubectl reconciliation and [verified-workflow views](../plan/design-decisions.md#415-reusable-independently-verified-workflows-planned-platform-capability) introduced by
Phase 6B. It extends the same frontend and shared event/identity contracts.
GitHub delivery views cannot imply Phase 5 capabilities in Phase 4A.

### Consequences

- Good: live browser interaction becomes available on Compose before the
  Kubernetes phase, while relying on the already tested gateway and controls.
- Bad: the MVP gains an additional gated phase and frontend testing/maintenance
  work before GitHub delivery. Phase 5 arrives later in the sequence.
- Bad: Phase 4A cannot provide future administration features or unsupported
  request types; the UI must accurately represent the available backend.
- Follow-up: update the core phase order, phase index, MVP statement, decision
  log and revision history; add phase-4a.md; split the overlapping Phase 8 tasks;
  clarify section 4.12's task/API versus Kubernetes administration boundary.
- Follow-up: write an independently reviewed Phase 4A RFC and OpenSpec change
  after Phase 4's contracts are established. Preserve full-tier gates.
- Unknown: exact browser auth mechanism, served UI/API topology, event endpoint
  shapes and thresholds. Resolve in the Phase 4/4A designs, without inventing
  unverified API capabilities here.

### Confirmation

The independent planning design review passed at `80c2dc2`, checking sequencing,
ownership, preserved requirements and the scope moved out of Phase 8. All three
reviewers completed; the report discloses the fresh reader's automatic project
instructions. The two optional navigation nits were addressed without changing
the planning contract. The owner explicitly accepted ADR-0003 on 2026-11-13.

The later Phase 4A acceptance/demo must show: submit a background task in the
browser; watch real progress; close/reopen and retrieve it by the same identity;
disconnect/reconnect without duplicate retained events and display gaps
explicitly; answer a needs_input question; resolve an authorized approval;
cancel a separate task; retrieve a result; and reject unauthorized API actions.
It must run locally with Compose, with no Kubernetes prerequisite, and save
evidence in docs/demos/phase-4a.md. Phase 8 subsequently verifies cluster-specific
administration without rebuilding task orchestration.

## Links

- [Core plan](../../PROJECT_PLAN.md): sections 2, 7.0, 7.2 and 8.
- [Phase 2](../plan/phases/phase-2.md): event observation and reconnect.
- [Phase 3B](../plan/phases/phase-3b.md): questions, approval and cancellation.
- [Phase 4](../plan/phases/phase-4.md): gateway and conversation identity.
- [Phase 4A](../plan/phases/phase-4a.md): task UI acceptance and demo.
- [Phase 8](../plan/phases/phase-8.md): remaining administration scope.
- [Design decisions](../plan/design-decisions.md): sections 4.9 and 4.12.

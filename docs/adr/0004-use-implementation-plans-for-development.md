---
id: ADR-0004
title: Use implementation plans for development contracts
status: proposed
date: 2026-11-14
issue: "#58"
related: [docs/plans/2026-11-13-skill-central-migration/plan.md, PROJECT_PLAN.md sections 4.16 and 7.0]
supersedes: ADR-0003
superseded_by: null
---

# ADR-0004: Use implementation plans for development contracts

## Context and problem statement

The owner approved replacing active OpenSpec and project-local planning/review
skills with the canonical Skill Central suite. That suite uses docs/plans for
requirements and design. Accepted ADR-0003 explicitly requires a Phase 4A RFC
and OpenSpec change, which conflicts with retiring active OpenSpec. This decision
reconciles the artifact requirement without changing the accepted task UI design
boundaries or claiming its implementation design is approved.

## Considered options

- Retain mandatory separate RFC/OpenSpec artifacts: preserves the former format,
  but requires the retired tooling and duplicates the new plan contract.
- Use reviewed implementation plans for future contracts, preserving existing
  runtime requirements, evidence, sequencing and phase gates.

## Decision outcome

Chosen option: use reviewed implementation plans, because migration requirements
R1, R3 and R4 require central skills while retaining existing guarantees and gates.
New development requirements and detailed designs live in docs/plans; separate
RFCs are optional and durable decisions remain ADRs.

This ADR supersedes ADR-0003 only to replace its mandatory Phase 4A RFC/OpenSpec
follow-up with an independently reviewed Phase 4A implementation plan after
Phase 4's contracts are established. It carries forward **every other ADR-0003
decision and acceptance/demo requirement by reference**, including the Compose
UI scope, phase order, full process tier, security boundaries, Phase 8 split and
MVP completion at Phase 5. Read the preserved ADR-0003 for those binding details.
The supersession link does not discard them. Existing ADR-0003 text is unchanged.

Historical OpenSpec and completed-phase evidence remain preserved and binding
through the incorporated baseline. This decision concerns repository development
artifacts, not planned production specification-adapter capabilities. It takes
effect only after owner acceptance and merge following independent review.

### Consequences

- Good: future contracts use the selected canonical suite without duplicate formats.
- Bad: readers must follow historical incorporation and supersession references;
  public structural checks cannot prove execution or human approval.
- Follow-up: link this reconciliation from Phase 4A guidance and the project plan;
  retain fresh frozen reviews, verification, tests, demos and latest-head gates.

### Confirmation

Independent design review must check that only the artifact requirement changes
and all ADR-0003 guarantees survive. The later Phase 4A plan and phase gate must
trace those guarantees and reproduce its required acceptance/demo; this tooling
cutover neither starts nor closes that runtime phase. Public plan validation,
link checks and coordinator evidence inspection check the documentation wiring.

## Links

- [Migration plan](../plans/2026-11-13-skill-central-migration/plan.md)
- [Carried-forward ADR-0003](0003-early-compose-task-ui.md)
- [Project plan](../../PROJECT_PLAN.md)
- [Incorporated baseline](../requirements/baseline.md)
- [Issue #58](https://github.com/geosp/praxismesh/issues/58)

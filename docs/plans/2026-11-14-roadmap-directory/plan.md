---
title: Rename the project roadmap directory
status: in-progress
created: 2026-11-14
updated: 2026-11-14
design_review: { status: passed, rounds: 2, last: 2026-11-14 }
approved: 2026-11-14
adr_review: null
---

# Rename the project roadmap directory

## Summary

Rename docs/plan to docs/roadmap so the project roadmap is clearly distinct from
the implementation contracts in docs/plans. Keep PROJECT_PLAN.md as the roadmap's
entry point. Update live references and historical navigation destinations,
preserving the recorded decisions, evidence and runtime requirements. The main
risks are broken links and changing the scope of a path-specific secret-scan
exception; link checks, historical comparisons and scan canaries verify both.

## Why

The [Skill Central migration](../../development/planning.md) introduced docs/plans
for implementation contracts using centrally installed planning and review skills.
The older docs/plan directory holds the long-term roadmap and architectural
constraints. Their nearly identical names obscure the distinction. The owner
selected docs/roadmap and authorized navigation-only maintenance in historical
records on 2026-11-14.

## What changes

- Move the 19 tracked roadmap files to docs/roadmap without changing their roles.
- Update active documentation, agent instructions, local skills and path consumers.
- Update historical Markdown navigation destinations under the owner's exception.
- Maintain the schema prose scan exception at its new path and its historical path.
- Record reviews, verification and the maintenance exception with the change.

### Non-goals

- Change the implementation-contract format or the externally maintained suite.
- Change runtime behavior, roadmap requirements, phase order or acceptance criteria.
- Rewrite historical decisions, findings, recorded input paths, SHAs or archives.
- Change security policy, repository settings or runtime phase completion states.
- Finalize lifecycle metadata from the earlier skill migration.

## Terms

- **Roadmap**: PROJECT_PLAN.md and its detailed architectural and phase documents.
- **Implementation contract**: a dated docs/plans folder with plan.md, phase tasks
  and reviews.md, discovered by Skill Central's `impl-plan/plan-tool.py`.
- **Validation tools**: the external `impl-plan/plan-tool.py` and project-owned
  `.github/scripts/check_plans.py`; [invocations and boundaries](../../development/planning.md#public-validation)
  are documented in the planning workflow.
- **Skill Central suite**: the externally maintained `impl-plan`, `design-review`
  and `impl-review` skills, helper and reviewers installed in user discovery roots.
- **OpenSpec**: the former specification/change-artifact workflow, now retired
  from active development while its historical records are preserved.
- **Prior migration metadata**: lifecycle fields in the earlier
  [skill-central-migration plan](../2026-11-13-skill-central-migration/plan.md),
  which tracked replacement of active OpenSpec and local review skills.
- **Historical record**: an existing ADR, archived specification, saved review,
  verification report, closed-phase RFC or demo evidence.
- **Navigation destination**: the target of a Markdown link, distinct from its
  visible label and any recorded input-path text.
- **Scan canary**: a check using generated dummy values to prove the scanner's
  narrow exception still allows only its intended content.

## Requirements

### R1 · Roadmap location is unambiguous

The roadmap detail must live in docs/roadmap with PROJECT_PLAN.md as its entry point.
- **Given** the current roadmap inventory, **when** the rename is applied, **then** all 19 files exist at corresponding new paths and docs/plan is absent.

### R2 · Implementation-plan discovery is unchanged

The shared helper and public validator must continue to discover implementation contracts only under docs/plans.
- **Given** the renamed roadmap and existing contracts, **when** discovery and validation run, **then** no roadmap file is treated as an implementation contract.

### R3 · Navigation resolves after the move

Repository navigation and active path consumers must resolve to the renamed files.
- **Given** a current documentation link, **when** it is followed, **then** its new destination and intended anchor resolve.
- **Given** an active path consumer, **when** its documented check runs, **then** its behavior is preserved at the renamed path.

### R4 · Historical content is preserved

Historical records must retain their contents apart from authorized Markdown navigation destinations.
- **Given** an existing historical record, **when** its navigation is maintained, **then** its text, labels, decisions, findings, recorded paths and SHAs are otherwise unchanged.
- **Given** maintained historical navigation, **when** preservation is verified against the baseline in [notes](notes.md#preservation-baseline), **then** the affected-record inventory and destination changes are recorded separately.

### R5 · Roadmap meaning is preserved

The directory move must preserve roadmap requirements, task states, acceptance criteria and phase order.
- **Given** a moved roadmap file, **when** its diff is audited, **then** those properties remain unchanged.

Permitted edits are path maintenance and the directory-organization entry in
docs/roadmap/decision-log.md; the entry does not change runtime requirements.

### R6 · Secret scanning remains narrowly scoped

The reviewed schema prose exception must preserve the exact rule, allowlist line-matching expression
and two paths specified in the [scanner contract](notes.md#scanner-contract).
- **Given** historical and current schema prose, **when** scanning runs, **then** that reviewed phrase remains allowed at both exact paths.
- **Given** unallowlisted dummy content at either schema path or an ordinary file, **when** scanning runs, **then** it is detected without exposing raw values in evidence.

## Decisions

### D1 · Separate the roadmap by directory name

Move docs/plan to docs/roadmap and update the document map. Retain the filename
PROJECT_PLAN.md and the docs/plans discovery root. Maintain navigation in the root
document and implementation-contract files under R3/R4. Rejected: putting the
roadmap inside docs/plans, because its role and format differ from the contracts.
Details: notes.md#d1

### D2 · Preserve historical prose and repair navigation only

Use the owner's navigation-maintenance exception to satisfy R4 through the
[preservation procedure](notes.md#preservation-baseline), its designated baseline
and affected-record inventory. Rejected: compatibility pages at docs/plan, because
they retain the confusing directory and require maintenance.

### D3 · Preserve historical scan compatibility

Apply the R6 scanner contract and verify it with canaries covering allowed and
unallowlisted content.
Rejected: replacing the old exception or ignoring the whole roadmap directory,
because either changes scanning beyond the move. Details: notes.md#scanner-contract

## Assumptions

- This is documentation/tooling maintenance, not a runtime phase closure.
- Existing ADRs need no new architectural decision for a directory rename; the
  ordinary decision log records its documentation impact.
- Source ZIPs, user installations and the Skill Central suite require no edits.

## Risks

- Relative links break: inventory link destinations and run the offline link check.
- A bulk replacement affects evidence: enforce the byte comparison in the
  preservation procedure before accepting R4.
- History scanning regresses: preserve both exact exception paths and execute R6.
- Runtime requirements drift: audit moved-file diffs before independent review.

## Rollout & rollback

Review this contract independently before implementation. Track the work in a
GitHub issue and a feature branch based on main. Move files and update consumers
in one PR, then run independent implementation review and the documented checks.
The owner merges after latest-head CI passes; agents never merge.

Reverting the PR restores the former directory, navigation and scan configuration
together. No deployment, application data migration or user-installation change
is needed. Use the [verification procedure](notes.md#verification-procedure) for concrete
entry points, expected outcomes and preservation comparisons.

## Open questions

- None

## Impact

- Packages / directories: docs/plan to docs/roadmap, docs/plans (this contract),
  root documentation, .agents/skills, .github/workflows, .gitleaks.toml and
  documentation references under spikes; historical destinations as authorized.
- Data: no application data changes.
- Jobs / APIs: existing CI canary paths change; no job identities, required-check
  rules or runtime APIs change.

## Links

- [Issue #60](https://github.com/geosp/praxismesh/issues/60): rename tracking and acceptance.
- [Project plan](../../../PROJECT_PLAN.md): authoritative scope and phase gates.
- [Planning workflow](../../development/planning.md): canonical skills and frozen reviews.
- [Review protocol](../../reviews/README.md): independence and saved verdicts.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | Rename and verify roadmap navigation | impl-reviewed | 0/3 |

## Decision log

2026-11-14: Owner chose docs/roadmap and authorized navigation-destination updates
in historical records while preserving substantive text and recorded provenance.

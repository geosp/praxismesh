---
title: Rename the project roadmap directory
status: draft
created: 2026-11-14
updated: 2026-11-14
design_review: { status: none, rounds: 0, last: null }
approved: null
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

The Skill Central migration introduced docs/plans for implementation contracts.
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

- Rename PROJECT_PLAN.md or change docs/plans and the shared Skill Central suite.
- Change runtime behavior, roadmap requirements, phase order or acceptance criteria.
- Rewrite historical decisions, findings, recorded input paths, SHAs or archives.
- Change security policy, repository settings or runtime phase completion states.
- Finalize lifecycle metadata from the earlier skill migration.

## Terms

- **Roadmap**: PROJECT_PLAN.md and its detailed architectural and phase documents.
- **Implementation contract**: a dated docs/plans folder with plan.md, phase tasks
  and reviews.md, discovered by the shared impl-plan helper.
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
- **Given** a current documentation link or active path consumer, **when** it is followed or checked, **then** it uses a valid new path and preserves its intended anchor or behavior.

### R4 · Historical content is preserved

Historical records must retain their contents apart from authorized Markdown navigation destinations.
- **Given** an existing historical record, **when** its navigation is maintained, **then** its text, labels, decisions, findings, recorded paths and SHAs are otherwise unchanged, with the maintenance recorded separately.

### R5 · Roadmap meaning is preserved

The directory move must preserve roadmap requirements, task states, acceptance criteria and phase order.
- **Given** a moved roadmap file, **when** its diff is audited, **then** changes consist only of path maintenance and an identified directory-organization decision entry.

### R6 · Secret scanning remains narrowly scoped

The reviewed schema prose exception must preserve its rule-and-line restrictions at the exact old and new schema paths.
- **Given** historical and current schema prose, **when** scanning runs, **then** that reviewed phrase remains allowed at both exact paths.
- **Given** unallowlisted dummy content at either schema path or an ordinary file, **when** scanning runs, **then** it is detected without exposing raw values in evidence.

## Decisions

### D1 · Separate the roadmap by directory name

Move docs/plan to docs/roadmap and update the document map. Keep PROJECT_PLAN.md
and docs/plans unchanged. Rejected: putting the roadmap inside docs/plans, because
it has a different role and format from the implementation contracts discovered there.
Details: notes.md#d1

### D2 · Preserve historical prose and repair navigation only

Use the owner's explicit exception to update Markdown destinations in historical
records, retaining labels and recorded inputs. Record the maintenance in this plan's
notes, with an inventory of affected records. Rejected: compatibility pages at
docs/plan, because they retain the confusing directory and require maintenance.

### D3 · Preserve historical scan compatibility

Retain the existing exact old schema path for history scans and add the exact new
path to the same rule-and-line restriction. Exercise both paths with canaries.
Rejected: replacing the old exception or ignoring the whole roadmap directory,
because either changes scanning beyond the move. Details: notes.md#d2

## Assumptions

- This is documentation/tooling maintenance, not a runtime phase closure.
- Existing ADRs need no new architectural decision for a directory rename; the
  ordinary decision log records its documentation impact.
- Source ZIPs, user installations and the private suite require no edits.

## Risks

- Relative links break: inventory link destinations and run the offline link check.
- A bulk replacement rewrites evidence: isolate historical navigation edits and
  compare all other bytes against the frozen baseline.
- History scanning regresses: preserve both exact exception paths and execute R6.
- Runtime requirements drift: audit moved-file diffs before independent review.

## Rollout & rollback

Review this contract independently before implementation. Track the work in a
GitHub issue and a feature branch based on main. Move files and update consumers
in one PR, then run independent implementation review and the documented checks.
The owner merges after latest-head CI passes; agents never merge.

Reverting the PR restores the former directory, navigation and scan configuration
together. No deployment, application data migration or user-installation change
is needed. See notes.md for the verification outline.

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

- [Project plan](../../../PROJECT_PLAN.md): authoritative scope and phase gates.
- [Planning workflow](../../development/planning.md): canonical skills and frozen reviews.
- [Review protocol](../../reviews/README.md): independence and saved verdicts.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | Rename and verify roadmap navigation | draft | 0/3 |

## Decision log

2026-11-14: Owner chose docs/roadmap and authorized navigation-destination updates
in historical records while preserving substantive text and recorded provenance.

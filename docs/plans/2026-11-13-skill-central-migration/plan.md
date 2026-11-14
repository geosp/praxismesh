---
title: Centralize planning skills and retire active OpenSpec
status: draft
created: 2026-11-13
updated: 2026-11-14
design_review: { status: none, rounds: 0, last: null }
approved: null
adr_review: null
---

# Centralize planning skills and retire active OpenSpec

## Summary

Use the owner's Skill Central suite through a user-wide installation for
implementation plans in docs/plans and independent reviews, after its Codex and
bundled-export prerequisites are merged and verified. Replace OpenSpec CI with
public local contract validation. Retire active OpenSpec development tooling
while retaining completed phase records and guarantees. The main risk is losing
discovery or weakening phase gates; R2 defines the cutover gate. Owner acceptance
of ADR-0004 reconciles the Phase 4A artifact requirement.

## Why

The owner selected three replacement ZIP exports and approved central management
on 2026-11-13. Project-local copies would duplicate reusable skills. There are no
active OpenSpec changes; Phases 0 and 1 are closed and Phase 2 has not started.

## What changes

- Skill Central gains Codex and bundled-export intake support, then the planning suite.
- New detailed contracts and designs use docs/plans, with durable decisions in docs/adr.
- PraxisMesh removes superseded local skills/agents and OpenSpec generation/validation CI.
- Public CI validates project plan contracts without accessing the private suite.

### Non-goals

- Runtime code, production specification adapters, completed phase evidence and merges.
- Deleting ZIP exports or historical requirement texts; activating unmerged skills.

## Terms

- **Suite**: impl-plan, design-review and impl-review plus their helper and reviewer agents.
- **Bundled-export prerequisites**: Skill Central support for importing the chosen
  ZIP exports and their explicit harness variants before suite installation.
- **OpenSpec**: the former repository requirements/change format and its generated
  development skills and CI checks; existing records remain historical.
- **Cutover**: switching new PraxisMesh work to the verified canonical suite.
- **Baseline**: existing Phase 0/1 guarantees incorporated by reference.
- **Harness variant**: a native agent configuration for one supported coding tool.
- **Owned installation**: links or Codex references tracked by Skill Central;
  unmanaged destinations are refused rather than overwritten.
- **Protected review**: required review and CI before owner merge to protected main.
- **Doctor**: Skill Central's installation health check; not a model invocation test.
- **Coordinator**: the session checking immutable evidence and refusing closure
  when gates are incomplete, under docs/reviews/README.md.
- **Latest-head approval**: the owner approves delivery only after required checks
  and evidence linkage cover the current PR head. Operational rules are in
  [the workflow](../../development/planning.md) and [review protocol](../../reviews/README.md).

## Requirements

### R1 · Canonical skills remain central

Reusable suite skills and reviewer agents must live in Skill Central.
- **Given** the suite is installed, **when** PraxisMesh is opened, **then** it discovers the canonical suite without local copies.

### R2 · Activation follows protected review

The cutover must follow protected suite merge and fresh-session discovery checks.
- **Given** only a candidate suite exists, **when** cutover is considered, **then** activation and final merge remain blocked.

### R3 · Existing guarantees remain binding

Retiring OpenSpec must preserve completed evidence and explicitly incorporate existing guarantees.
- **Given** a historical spec or phase report, **when** cutover is prepared, **then** its contents and links remain available.

### R4 · Phase gates remain mandatory

The coordinator refuses closure unless every independently traceable gate below
passes under the linked review protocol.

- **Given** a missing reviewer, **when** closure is requested, **then** the coordinator refuses completion (R4.a).
- **Given** failed acceptance tests or verification, **when** closure is requested, **then** the coordinator refuses completion (R4.b).
- **Given** an unrun demo, **when** closure is requested, **then** the coordinator refuses completion (R4.c).
- **Given** mismatched evidence SHAs or stale-head checks, **when** delivery approval is requested, **then** the coordinator refuses completion (R4.d).

Gate definitions:

- **R4.a Reviews:** fresh-session reviews use frozen commits; a missing reviewer
  prevents completion.
- **R4.b Execution:** acceptance tests and independent verification must pass.
- **R4.c Demo:** the required demo must actually run and pass before completion.
- **R4.d Delivery:** evidence SHAs must match their inputs, and required checks and
  owner approval must cover the latest head.

### R5 · Public CI has no private dependency

Public CI must validate local implementation contracts without fetching Skill Central.
- **Given** a fork without private credentials, **when** the plans check runs, **then** it validates local files with project dependencies only.

## Decisions

### D1 · Share the suite through owned user installations

Keep one portable canonical suite and explicit harness variants. Skills and most
agent variants use owned links. Codex reviewer variants use owned config_file
references to canonical regular TOML files. This avoids the symlinked role
configuration that Codex refuses. Rejected: copying
skills into PraxisMesh, because project copies drift. Details: notes.md#d1

### D2 · Use implementation plans for future requirements and designs

Retain the master plan's scope/gate authority; an approved implementation plan
carries detailed contracts and design. Rejected: maintaining parallel RFC/OpenSpec
requirements for every new phase, because the selected suite already owns those contracts.
Phase 4A is the Compose task-interaction UI. ADR-0003 currently requires separate
Phase 4A RFC/OpenSpec artifacts. Proposed
[ADR-0004](../../adr/0004-use-implementation-plans-for-development.md) supersedes
that artifact requirement while carrying forward every other ADR-0003 decision.
The owner must accept that reconciliation with this cutover; it does not approve
Phase 4A's future implementation design.

### D3 · Validate repository contracts locally in CI

Use a small project-owned validator for requirement coverage and scenarios,
phase status, task Verify steps and completion evidence references. See
[public validation](../../development/planning.md#public-validation) for its
commands and boundary. Rejected: fetching a private helper in public fork CI, because it would
require new credentials and exclude contributors. It does not prove execution evidence.

## Assumptions

- The owner-selected ZIPs are authoritative for this migration; legacy adaptations remain recoverable in Git.
- Owner approval covers scope, not an independent design-review verdict or phase closure.

## Risks

- Discovery fails or duplicates persist: enforce R2 and record activation results.
- Shared defaults weaken gates: document mandatory repository overrides and check evidence.
- Private suite unavailable to a contributor: allow direct contract authoring and public checks.

## Rollout & rollback

Review/merge Skill Central prerequisites, then the suite. Install the protected
revision and satisfy R2 using doctor and fresh-session Linux/macOS checks. Record
the protected suite SHA in the cutover PR before owner merge.

A repository revert restores prior project definitions and CI. It leaves the
canonical Skill Central checkout and owned user installation intact; use the
restored project skill names explicitly. If a shared registration conflicts with
a restored project reviewer, stop and preview the manager's owned uninstall for
that harness before choosing recovery. That operation affects the user-wide
installation and other repositories, so it is a separate owner decision; never
force-remove destinations. Preserve source exports and ownership records. See
[installation and recovery](../../development/planning.md#installation-and-cutover).

## Open questions

- None

## Impact

- Packages / directories: .agents, .codex/agents, .claude/agents, .github, docs, tests.
- Data: no application data migration; user link ownership stays in Skill Central state.
- Jobs / APIs: replace CI openspec job with plans; no runtime API changes.

## Links

- [Project plan](../../../PROJECT_PLAN.md) — scope, sequencing and acceptance gates (§4.16, §7.0, §8).
- [Planning workflow](../../development/planning.md) — installation and repository overrides.
- [Regression baseline](../../requirements/baseline.md) — incorporated existing guarantees.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | Skill Central prerequisites | draft | 0/1 |
| 02 | Canonical planning suite | draft | 0/1 |
| 03 | PraxisMesh cutover | draft | 0/1 |

## Decision log

2026-11-13: Owner approved migration scope and retiring active OpenSpec. Independent
review, protected CI and activation evidence are still pending.

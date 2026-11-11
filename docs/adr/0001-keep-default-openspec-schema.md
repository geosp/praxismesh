---
id: ADR-0001
title: Keep OpenSpec's default spec-driven schema; review gates live in the review skills and CI
status: proposed
date: 2026-11-11
issue: null
related: ["docs/plan/bootstrap.md §0.2.1", "docs/reviews/README.md", "plan §4.16", "plan §4.17"]
supersedes: null
superseded_by: null
---

# ADR-0001: Keep OpenSpec's default spec-driven schema; review gates live in the review skills and CI

## Context and problem statement

Plan §0.2.1 asks whether an OpenSpec custom workflow schema should express the project's handoffs: specification, design, independent design review, implementation, independent implementation review and independent verification. It also asks how gates that OpenSpec cannot enforce are enforced instead. The evaluation was timeboxed; this ADR records the result, tested on OpenSpec 1.17.0.

The test forked the default schema into a project schema, `gated`. It added three artifacts, `design-review`, `implementation-review` and `verification`, each requiring the one before it, and set `apply.requires: [tasks, design-review]`. `openspec schema validate gated` passed. A dummy change was then walked through it in a throwaway worktree:

- `openspec status` tracked the reviews in order: "4/7 artifacts complete", with implementation review and verification shown "blocked by" their predecessors.
- `openspec instructions apply` returned `state: ready` with **no** design review, and also with a design review whose content said FAIL. `apply.requires` did not block implementation.
- `openspec archive` archived the change with **all three reviews missing**.
- OpenSpec judges artifacts by file presence only. It cannot read a verdict, a commit SHA or a session's isolation.

## Considered options

- **Adopt the custom `gated` schema:** visibility of the review steps in `openspec status`, but no enforcement.
- **Keep the default `spec-driven` schema:** reviews and gates stay in the review skills, the gate protocol and CI.
- **Minimal extension:** a single `review-record` artifact pointing to the saved reports.

## Decision outcome

Chosen option: "Keep the default `spec-driven` schema", because a custom schema adds visibility but no enforcement, and it brings costs:

- A review artifact that an agent is asked to "complete" invites a session to write the review itself, the opposite of independent review.
- The reports would be duplicated: they already belong in `docs/reviews/phase-N/`.
- A forked copy of the default schema's long instructions has to be re-forked whenever OpenSpec updates them, and schema commands are marked experimental.

The handoffs are carried and enforced as follows:

| Plan §0.2.1 point | Where it lives |
|---|---|
| Ordering of specification, design and tasks | OpenSpec `spec-driven` (proposal, specs, design, tasks) |
| Independent design review, implementation review, verification | Skills `review-design`, `review-implementation`, `verify-phase`; protocol in `docs/reviews/README.md` |
| Traceability: requirement -> spec -> RFC/ADR -> tests -> evidence -> commit | Specs trace to plan sections (§4.16, checked by `review-design`). The contract lens of `review-implementation` maps each requirement to its enforcing code and test. Reports record `commit_sha`/`code_sha`/`docs_sha`; the coordinator gate records `head_sha` in the PR |
| Fresh sessions with only their required inputs | The skills' gate mode (fresh session, inputs only, no transcripts), agent tool lists, and `.claude/settings.json`; shown in bootstrap demo item 3 |
| Enforcement | `ci-ok` and ruleset `protect-main` block merges; the coordinator approval gate checks verdicts, SHAs and latest-head CI before a phase is ticked. A review verdict alone never authorizes a merge |

### Consequences

- Good, because OpenSpec stays on its default schema, so `openspec update` keeps working with no fork to maintain, and CI's drift check stays simple.
- Good, because review reports have one home (`docs/reviews/`) and are only ever written by review sessions.
- Bad, because `openspec status` does not show whether a change has been reviewed; the coordinator gate and the reports do.
- Bad, because review verdicts are not machine-enforced yet: the coordinator gate is a documented procedure, not a CI check.
- Follow-up: when the first phase reports exist (Phase 0), consider a CI check that a phase-closing PR carries review and verification reports with PASS for the same `code_sha`.

### Confirmation

- CI's `openspec` job keeps running `openspec validate --all` and the drift check against the default schema; no `openspec/schemas/` directory exists.
- At each phase gate, the coordinator approval gate in `docs/reviews/README.md` is followed and its result recorded in the PR.
- Revisit this ADR if OpenSpec starts enforcing `apply.requires` or artifact content, or if the follow-up CI check is built.

## Links

- Plan: `docs/plan/bootstrap.md` §0.2.1; `PROJECT_PLAN.md` §4.16, §4.17
- Gate protocol: `docs/reviews/README.md`
- OpenSpec version evaluated: 1.17.0 (`openspec schema fork|validate`, `openspec status`, `openspec instructions apply --json`, `openspec archive`)

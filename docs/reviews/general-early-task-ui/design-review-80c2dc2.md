---
review: design
phase: general-early-task-ui
change: n/a
rfc: n/a
adrs: [docs/adr/0003-early-compose-task-ui.md]
commit_sha: 80c2dc2637840de4ebc5ab4bdd60059ab3f3db24
docs_sha: n/a
diff_base: 79fa2c9ab99a3daf5cc0c5a71ebe9d69cdd976e1
session: fresh
date: 2026-11-13
verdict: PASS
reviewers:
  - { lens: fresh-reader, status: completed }
  - { lens: codebase-fit, status: completed }
  - { lens: zoom-out, status: completed }
---

# Design review: ADR-0003 and the Phase 4A / Phase 8 split

## Inputs

Gate-mode planning review for issue #56 and draft PR #57, using the
`review-design` skill. This fresh coordinating session did not author or discuss
the design before the review request. All three reviewers started with no parent
conversation history; none received another reviewer's findings or verdict.

Review target: committed diff
`79fa2c9ab99a3daf5cc0c5a71ebe9d69cdd976e1..80c2dc2637840de4ebc5ab4bdd60059ab3f3db24`.
Read-only GitHub metadata confirmed PR #57 is open and draft, its head is the
pinned commit, and its base is `main` at the recorded diff base. Local
`git merge-base origin/main <commit_sha>` agreed. `git rev-parse HEAD` matched
the pin; `git status --porcelain -- <reviewed paths>` was empty before review.
The diff includes both PR commits, not only the final commit's changes.

Repository root for all paths below: `/home/geo/develop/praxismesh`.

The ADR and coordinated plan changes are the planning contract. There is no
Phase 4A implementation RFC or OpenSpec change. Per the requested scope, the
skill's phase-RFC prerequisite, implementation task coverage and delta-spec
checks do not apply to this sequencing decision. Their absence does not approve
implementation: Phase 4A still requires its own full-tier design gate later.

Fresh reader input (only this file was opened):

- `docs/adr/0003-early-compose-task-ui.md`

Codebase-fit and zoom-out reviewers received these change/design files:

- `PROJECT_PLAN.md`
- `docs/adr/0003-early-compose-task-ui.md`
- `docs/adr/README.md`
- `docs/plan/decision-log.md`
- `docs/plan/design-decisions.md`
- `docs/plan/phases/phase-4.md`
- `docs/plan/phases/phase-4a.md`
- `docs/plan/phases/phase-8.md`
- `docs/plan/revision-history.md`

Their guidance and context inputs were:

- `AGENTS.md`
- `PROJECT_PLAN.md`
- `docs/reviews/README.md`
- `docs/plan/phases/phase-2.md`
- `docs/plan/phases/phase-3a.md`
- `docs/plan/phases/phase-3b.md`
- `docs/plan/phases/phase-4.md`
- `docs/plan/phases/phase-4a.md`
- `docs/plan/phases/phase-5.md`
- `docs/plan/phases/phase-6b.md`
- `docs/plan/phases/phase-7.md`
- `docs/plan/phases/phase-8.md`
- The sections in `docs/plan/design-decisions.md` named by those phases'
  **Read first** lines; `docs/plan/schemas.md` if needed.
- Nested package `AGENTS.md` files if applicable, and repository code as needed.

They also received the pinned commit, main-branch diff base, read-only boundary
and their respective skill briefs adapted to this planning-only contract. No
author transcript or coordinator conclusions were provided. Codex automatically
supplied project instructions to the fresh reader, including `AGENTS.md`; it
could not be fully isolated from project instructions. Its paraphrase is
therefore less independent in that respect, as the skill requires us to record.

Individual assessments are preserved in
[fresh-reader-80c2dc2.md](fresh-reader-80c2dc2.md),
[codebase-fit-80c2dc2.md](codebase-fit-80c2dc2.md) and
[zoom-out-80c2dc2.md](zoom-out-80c2dc2.md).

## Fresh reader paraphrase

The following two sections are reproduced word for word.

### What this proposes

Split the UI work into an earlier Phase 4A for browser-based task interaction and a later Phase 8 for Kubernetes administration and other advanced views. Phase 4A would run locally in Docker Compose after the Phase 4 gateway, reuse existing server contracts, and support submitting, observing, resuming, controlling and retrieving tasks. This brings browser interaction into the MVP, while adding a gated phase before Phase 5 completes it.

### How the existing system works, per this document

The current plan places the UI in Phase 8, where task interaction is combined with administration that depends on Phase 7’s Kubernetes deployment work. Earlier phases already plan event observation, durable controls, questions, approvals, identity and API authorization. Docker Compose is the default deployment through Phase 6B; the document does not establish which of these capabilities are implemented today.

## Findings

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| N1 | Nit | Fresh reader | ADR-0003, Decision outcome / Consequences | “Full process tier” and “full-tier gates” are not defined locally; a standalone reader cannot identify the required reviews/evidence. The linked plan supplies the meaning. | Fix: link the first use to `PROJECT_PLAN.md` §7.0 or briefly name the gates. | Open; nonblocking. |
| N2 | Nit | Fresh reader | ADR-0003, Decision outcome | “Template/profile/MCP administration” and “verified-workflow views” rely on the linked plan for their functional meaning. Phase placement is understandable. | Fix: add direct links to the Phase 8 plan and §4.15 at the retained-capability paragraph, or a brief gloss. | Open; nonblocking. |

No Blocker or Major was raised. Codebase-fit and zoom-out completed with no
findings. The coordinator retained both standalone-readability nits without
editing the reviewed design.

## Scope and requirement assessment

| Requested check | Assessment and evidence at the pinned commit |
|---|---|
| Live task interaction on Compose after Phase 4 | Covered by Phase 4A prerequisites and tasks, acceptance and demo (`phase-4a.md`, Prerequisites, Accept and Demo checklist). Submission, stable IDs, real events, closing/reopening, retained-event reconnect/gaps, input, approvals, cancellation, results and permission checks are required. Kubernetes is explicitly excluded as a prerequisite. |
| Dependencies and API ownership | Phase 2 supplies observation/reconnect; Phase 3A supplies records and artifact access; Phase 3B supplies authenticated, idempotent, audited input/approval controls; Phase 4 owns server identity, authorization, supported inputs and event/reconnect contracts (`phase-4.md`, opening paragraph; §4.12). Phase 4A consumes these APIs and must document topology in its later design. |
| Authorization boundaries | Every read/mutation requires API authorization, including direct requests; no browser access to privileged DB, Temporal admin, object-store admin or Kubernetes interfaces. No UI capability grants, approval bypass or second orchestrator. Browser threat-model work and hostile-content tests are required (`phase-4a.md`, tasks 6–8). |
| Phase 8 retained scope | Original API/RBAC, templates, MCP, profiles, fleet/GPU, full dashboards, audit and external kubectl reconciliation remain. Workflows extensions retain filters/tier and authorized retry; approvals extensions retain plan/tool/merge context and CLI support; verified-workflow views retain template/version, pinned spec/commit, findings, evidence and blocked gates (`phase-8.md`, task list). |
| Requirement preservation | Compared the full committed diff with base Phase 8. Initial task observation/controls move to 4A; later integrations remain in 8. No original Phase 8 requirement was found dropped or weakened. No existing `openspec/` file is changed; the later implementation contract is expressly deferred. |
| MVP, sequence and documentation | Core MVP statement, §7.0 order, §7.2 index, §8 sub-phase gates, §4.12 ownership, ADR index, decision-log entry, revision summary and both phase plans agree: 4 → 4A → 5, full tier, MVP completes at 5; administration remains post-7 and verified-workflow views post-6B. |
| Appropriate implementation deferral | Browser auth/session mechanism, serving topology, endpoint shapes and measurable UI thresholds remain for independently reviewed Phase 4/4A designs (ADR Consequences; `phase-4a.md`, task 8). Those future designs must establish actual APIs and relevant §7.1 risks/thresholds before implementation. No untested runtime capability is approved by this review. |

Current code is a Phase 1 foundation, not an implemented browser/gateway/event
stack. Reviewers compared future capability claims to the plan rather than
treating them as existing code. No UI implementation, functional testing or live
demo was performed. `git diff --check <base>..<commit_sha>` passed. No phase
tasks or demo boxes were checked.

## Verdict

**PASS for the planning-only ADR and coordinated plan revision at the pinned
commit.** All three reviewers completed; there are no open Blockers or Majors.
The two open Nits do not block under `docs/reviews/README.md`, gate rule 5.

This verdict does not accept ADR-0003, approve a Phase 4A implementation design,
close any phase or authorize merging. ADR status remains `proposed`.

## Open items and exact next steps

1. Return N1 and N2 to the author as optional clarity edits. This reviewing
   session makes no fixes. Any subsequent assessment of changed design text
   runs in a new session, or is explicitly labeled a targeted follow-up.
2. The author/coordinator records the planning decision and ADR acceptance in
   a separate session after owner approval. Keep the Phase 4A implementation
   RFC/OpenSpec work deferred until Phase 4 contracts are established.
3. Before owner merge of PR #57, commit the review evidence on the feature
   branch and require the repository's checks on the resulting latest head.
   Reassess affected design changes if the planning contract changes; this
   report remains pinned to `80c2dc2637840de4ebc5ab4bdd60059ab3f3db24`.
4. After Phase 4, author the Phase 4A full RFC and OpenSpec change, freeze
   browser/API contracts, auth/session/topology and measurable acceptance/risk
   thresholds, and obtain a fresh full-tier design review before UI
   implementation. Later implementation review, verification and the Compose
   demo remain mandatory.

Reports were saved locally without overwriting existing reports. This session
does not commit, push, write to GitHub, implement, fix findings, merge or mark
the ADR accepted.

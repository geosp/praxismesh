---
name: docs-design
description: >-
  Guides a conversation that produces a PraxisMesh design document - a full RFC,
  a short (light-tier) RFC, or an ADR - as Markdown in docs/rfcs or docs/adr from
  the templates in docs/templates, developed in the open on a draft GitHub pull
  request. Use when the user wants to write, start, continue or review an RFC,
  design doc, design proposal, tech note, architecture decision record (ADR),
  decision rationale, trade-off analysis or consequences; supersede an earlier
  decision; or asks how to design a phase or material change before implementing it.
---

# Design documents (RFC / ADR)

For new phase planning, use Skill Central `impl-plan`; its reviewed plan replaces a mandatory separate phase RFC. Use this skill for standalone RFCs and ADRs when requested.

Design docs live in the repository as Markdown and are reviewed on a **draft GitHub pull request**. Merging the PR records the approved revision. This follows plan §4.17 (documentation lifecycle) and §7.0 (process tiers). Follow the branch, commit and attribution rules in `AGENTS.md`.

> **Provisional:** this skill and its templates were brought forward from the Phase 0 documentation-skill task and are pending review (see the decision log). It covers RFCs and ADRs only, not as-built architecture.

## Which document

| Type | When | Template | Path |
|---|---|---|---|
| **Full RFC** | A requested standalone design for a material change with real alternatives or a need for team agreement | `docs/templates/rfc.md` | `docs/rfcs/phase-N-<topic>.md` |
| **Short RFC** | A requested standalone design when the solution is already clear and needs recording more than debating | `docs/templates/rfc-short.md` | `docs/rfcs/phase-N-<topic>.md` |
| **ADR** | One consequential decision is being made or superseded (not a whole design) | `docs/templates/adr.md` | `docs/adr/NNNN-<decision>.md` |

For a change not tied to a phase, use `general` in place of `phase-N` (`docs/rfcs/general-<topic>.md`).

## ADR rules

An ADR captures **one** architecturally significant decision, its rationale, trade-offs and consequences, for a future reader reconstructing why the system is the way it is.

- **One decision per ADR.** If several decisions are bundled, split them into separate ADRs.
- **Significant only.** The decision affects structure, quality attributes, constraints or evolution. No transient implementation details, meeting notes or trivial choices (plan §4.17). If significance is unclear, ask what a future maintainer will need to know.
- **Known facts only.** Capture context, requirements, constraints, options, rationale and consequences as they are. Write `Unknown`, or ask one focused question, rather than inventing context, options or quality attributes.
- **No sales pitch.** List at least two considered options, including the rejected one and why it lost, and write real downsides as well as benefits.
- **Rationale tied to requirements** (project plan, implementation plan, RFC), not preference.
- **Confirmation is required:** say how compliance will be checked (a test, CI check, review item or demo step).
- **Too little evidence?** Do not draft an ADR headed for acceptance. Record the open questions on the issue or PR and come back when the facts are in.

**Statuses** (plan §4.17): `proposed` (under review), `accepted` (merged after a passing independent review), `superseded` (replaced by a later ADR). There is no `rejected` status: a rejected proposal is a PR closed without merging, with a comment giving the reason.

**Supersession:** the new ADR sets `supersedes: ADR-NNNN`. Never edit the existing ADR. Determine supersession by the new ADR's `supersedes` link.

**Reconcile:** if an ADR changes an approved requirement, update the approved implementation plan, `PROJECT_PLAN.md` and `docs/plan/decision-log.md` through their normal process, in the same PR or a linked one (plan §4.17).

## Workflow

### Step 1 - Understand the problem

Use what the conversation already holds, then fill gaps from the repository before asking:

- **The GitHub issue:** `gh issue view <n> --json title,body,labels`. Every design doc should have one; offer to create it if missing (confirm first).
- **The plan:** `PROJECT_PLAN.md`, the phase file in `docs/plan/phases/` and the design sections it lists under *Read first* (plan §9.7). Do not load all of `docs/plan/`.
- **The implementation plan,** if one exists (`docs/plans/<plan>/plan.md`).
- **For an ADR:** the RFC or `docs/plans/<plan>/plan.md` that prompted the decision. Link it in `related`. If none exists, ask whether to proceed without one; do not block, because some ADRs stand alone (e.g. the sandbox ADR, the §0.3 fallback ADR).

Then ask the user about what is still unclear:

- What problem are we solving, and why does it matter now?
- What is in scope, and what is explicitly out of scope?
- Which existing systems, issues, RFCs or ADRs relate to it?

Do not rush this step. Let the user explain in their own words, and ask clarifying questions until you understand the problem space.

### Step 2 - Choose the document type

Use the table above. The phase's process tier sets the default (§7.0). If unsure, ask: "Is the solution already decided, or are there several approaches to weigh?"

Reassess as the conversation develops:

- If real alternatives or trade-offs appear in a light-tier phase, suggest a full RFC. A design reviewer may also move a phase to the full tier.
- If the discussion narrows to a single decision, suggest an ADR instead.

Recommend, then let the user decide. Never switch type without their agreement.

### Step 3 - Check for existing work

Search before creating:

```
grep -ril "<keywords>" docs/rfcs docs/adr
gh pr list --state all --search "<keywords> in:title"
gh issue list --state all --label rfc,adr --search "<keywords>"
```

If anything related exists, show the links and ask whether to extend it, supersede it, or start a new doc.

### Step 4 - Create the document early

As soon as there is enough context for a meaningful title, create it. Do not wait for a finished draft.

1. Create a branch: `docs/<issue>-rfc-<topic>` or `docs/<issue>-adr-<topic>`.
2. Copy the template to its path. For an ADR, use the next free `NNNN` in `docs/adr/` (file `NNNN-<decision>.md`, `id: ADR-NNNN`); if a parallel PR takes the same number first, renumber before merge.
3. Fill in the front matter.
   - RFC: `status: draft`, phase, tier, issue, implementation plan, plan sections, date, authors, and for phase RFCs size, hardware and Pre-0.2 inputs.
   - ADR: `id`, title, `status: proposed` (ADRs have no draft status; the draft PR is the draft), date, issue, `related`, `supersedes`.
4. Commit the file (no attribution, per `AGENTS.md`).
5. **Confirm with the user, then publish:**
   - `git push -u origin HEAD`.
   - `gh pr create --draft --title "RFC: <title>" --body "<one-paragraph summary; Part of #N>" --label rfc` (or `adr`, plus `phase-N` if those labels exist).
   - Use `Part of #N`, not `Closes`, because the design does not finish the issue.
6. **Share the PR URL immediately,** before anything else, so the user can follow along and comment.

If there is no remote yet (plan §0.1 pending), commit locally, tell the user the PR will follow once the repository exists, and continue.

### Step 5 - Flesh out the document

Work through the template's sections in order, discussing each with the user. After each meaningful exchange, commit and push. Do not batch updates.

**Never work from stale content.** Before each edit:

- `git pull` (the user may have pushed edits).
- Read new feedback: `gh pr view --comments` for conversation comments, and `gh api repos/{owner}/{repo}/pulls/<n>/comments` for line comments. Address each, or flag it to the user.

Full RFC section guidance:

1. **Problem statement:** background, goals, non-goals.
2. **Possible solutions:** put all candidate approaches here first. For each, discuss pros, cons and trade-offs with the user until one emerges as the clear winner.
3. **Proposed solution:** move the winner here and detail it: components, contracts, schemas, data flows, Mermaid diagrams (GitHub renders them).
4. **Compatibility and versioning:**
   - Temporal Workflow versioning and patching for changed Workflow code.
   - Database migrations.
   - Gateway API and CRD compatibility.
   - Configuration toggles and their defaults.
   Write `N/A - <reason>` if none applies.
5. **Why this approach?:** the rationale.
6. **Risks and failure modes:** backward compatibility, performance, security (check against `docs/security/threat-model.md` once it exists), licensing, dependencies, failure and recovery, and the §7.1 rethink trigger with its threshold.
7. **Alternatives considered:** move the remaining options here, each with "Why not".
8. **Implementation plan:** issue-sized checklist items, plus a Mermaid sequencing diagram for parallel or dependent work.
9. **Acceptance tests and demo:** the automated acceptance suite and a demo (entry point, visible outcome, failure/recovery case, cleanup, evidence path), as required by the phase gate (plan §8).
10. **Future work:** what is deferred, and why.

For a **short RFC:** background; plan (the core: design, diagrams, subsections as needed); alternatives (brief); risks; testing and demo; future work.

For an **ADR** (follow the ADR rules above): context and problem statement; considered options; decision outcome (`Chosen option: "<x>", because <justification>`); consequences (good, bad, follow-up); confirmation; links. Keep it to about a page.

### Step 6 - Self-check and hand off for review

When all sections are filled:

- Read the whole document back and check:
  - it is internally consistent, and agrees with the project plan and implementation contract;
  - the title matches the content;
  - no template placeholders remain;
  - the "Possible solutions" working section has been emptied and removed.
- For an ADR, also run the checklist and fix any mistake below.
- Ask the user whether to adjust anything.

**ADR checklist**

- One decision, not a bundle
- Significant: affects structure, quality attributes, constraints or evolution
- Context explains why the decision was needed
- At least two options, with the rejected ones and why they lost
- Rationale tied to requirements, not preference
- Downsides and follow-up work recorded
- Confirmation says how compliance is checked
- `status` is `proposed` (the author never sets `accepted`); `date` is an ISO date
- `supersedes` is `null` or one ADR id; a superseded ADR's front matter (only) is updated in the same PR
- Unknowns are marked `Unknown`, not invented

**Common ADR mistakes**

| Mistake | Fix |
|---|---|
| Several decisions in one ADR | Split them. |
| Sales pitch | Add rejected options and negative consequences. |
| Invented context | Mark `Unknown` or ask. |
| Editing an old ADR's body to reflect a new decision | Write a new ADR with `supersedes`; leave the old file unchanged. |
| Omitting alternatives under time pressure | Include at least the rejected option and why it lost. |
| No way to check the decision is followed | Add a Confirmation: test, CI check, review item or demo step. |
- With their agreement, set `status: proposed`, push, and mark the PR ready: `gh pr ready` (confirm first).

**You are the author, not the reviewer.** Never set `status: accepted` and never approve or merge the PR. Approval comes from an **independent design review in a fresh session** (plan §0.3, §7.0) that receives only the approved inputs and this document: follow the PraxisMesh gate protocol there; use `design-review` for implementation-plan contracts (see `docs/reviews/README.md`). The review is saved under `docs/reviews/phase-N/design-review.md`. Status becomes `accepted` in the commit that merges after a passing review.

Give the user the PR URL and tell them they can keep chatting to make further edits.

### Step 7 - After approval (optional)

Offer to turn the implementation plan into GitHub issues. Confirm first, then create one per checklist item with `gh issue create --title ... --body "<scope, acceptance criteria; Part of #N; RFC: <path>>"`, and link the new numbers back into the RFC checklist in a follow-up PR.

For an ADR that supersedes another, see **Supersession** under ADR rules: a new ADR naming the old one in `supersedes`, without editing the old file.

## Style

- Plain, clear language; explain jargon where it is unavoidable.
- Plain Markdown and ASCII punctuation. No emoji. These are repository documents, rendered on GitHub and diffed in review.
- Prefer bullets and tables over long paragraphs. Keep sections concise.
- Use Mermaid for architecture and sequencing where it adds clarity.
- Distinguish planned from observed behavior. An RFC states intent, not proof.
- When unsure about a detail, ask the user rather than guessing.
- No attribution footers on commits, PRs, comments or issues (`AGENTS.md`).

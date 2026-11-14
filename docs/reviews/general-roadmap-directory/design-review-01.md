---
review: design
phase: general-roadmap-directory
change: docs/plans/2026-11-14-roadmap-directory
rfc: n/a
commit_sha: c76f77e11dc2ab309a38ef63836e8003f18c82cc
docs_sha: n/a
diff_base: n/a
session: fresh
date: 2026-11-14
verdict: FAIL
reviewers:
  - { lens: fresh reader, role: design-reader, status: completed }
  - { lens: codebase fit, role: design-reviewer, status: completed }
  - { lens: zoom out, role: design-reviewer, status: completed }
---

# Design review: Rename the project roadmap directory

**FAIL — four open Majors.** All three required reviewers completed. This reviews the whole documentation/tooling maintenance plan before implementation; it does not close a runtime phase.

The report is returned for coordinator persistence. No repository files, lifecycle metadata or review logs were changed. No tests, fixes, commits, configuration changes or GitHub writes occurred.

## Inputs and independence

Repository root: `/tmp/praxismesh-roadmap-design-review`.

All repository inputs were frozen at `c76f77e11dc2ab309a38ef63836e8003f18c82cc`. HEAD matched before and after review, and both working-tree status checks were empty.

Paths below are relative to that root; reviewer briefs used absolute paths.

| Input | Exact path |
|---|---|
| Plan | `docs/plans/2026-11-14-roadmap-directory/plan.md` |
| Phase | `docs/plans/2026-11-14-roadmap-directory/phases/01-roadmap-rename.md` |
| Notes | `docs/plans/2026-11-14-roadmap-directory/notes.md` |
| ADR | `docs/adr/0001-keep-default-openspec-schema.md` |
| ADR | `docs/adr/0002-paradedb-as-postgresql-server.md` |
| ADR | `docs/adr/0003-early-compose-task-ui.md` |
| ADR | `docs/adr/0004-use-implementation-plans-for-development.md` |
| ADR-directory guidance | `docs/adr/README.md` |
| Root guidance | `AGENTS.md` |
| Root guidance | `CLAUDE.md` |

The repository-wide guidance search found no nested AGENTS.md or CLAUDE.md files.

Each reviewer started with `fork_turns: none` and its prescribed skill brief:

- **Fresh reader:** plan.md only; instructed to open nothing else.
- **Codebase fit:** plan, phase, notes, all five ADR-directory files, both root guidance files, and repository access.
- **Zoom out:** plan, phase, notes, all five ADR-directory files, and repository access. No guidance files were explicitly added to its brief.

No reviewer received an author transcript, suspected findings, prior verdicts or another reviewer’s output. Only this coordinating session read the target `reviews.md`; it records no previous independent review or lifecycle approval.

**Reader-independence limitation:** after completing its assessment, the reader reported:

> Yes. The fresh context automatically included the full repository `AGENTS.md` text in a user message, along with environment details and the available-skills catalog. No `CLAUDE.md` content was visible. I opened only the assigned `plan.md` and did not use the supplied project instructions to supplement its explanations.

The reader therefore had a fresh conversation context but was not isolated from automatic project-instruction visibility.

Coordinator-only workflow inputs included the installed design-review skill, adjacent impl-plan skill and writing rules, PROJECT_PLAN.md, `docs/development/planning.md`, `docs/reviews/README.md`, and `docs/templates/review-report.md`.

## Checks

| Check | Command or method | Observed |
|---|---|---|
| Frozen revision | `git rev-parse HEAD`, before and after review | Requested full SHA |
| Clean inputs | `git status --porcelain --untracked-files=all`, before and after review | Empty |
| Mechanical structure | `python -B /home/geo/.agents/skills/impl-plan/plan-tool.py check docs/plans/2026-11-14-roadmap-directory` | Exit 0; 0 errors, 0 warnings |
| Guidance inventory | Repository-wide hidden-file search for AGENTS.md and CLAUDE.md | Root files only |
| Roadmap inventory | `git ls-tree -r --name-only HEAD docs/plan` | 19 files |
| Review reconciliation | Coordinator read `reviews.md` | No earlier findings to close or reopen |
| Lifecycle handoff | `python -B /home/geo/.agents/skills/impl-plan/plan-tool.py next docs/plans/2026-11-14-roadmap-directory` | Design review remains next because recorded state is `none` |

The helper used Python with bytecode disabled, avoiding uv cache writes. Implementation tests, scan canaries, link checks and runtime verification were not executed in this read-only design review.

## Fresh reader paraphrases — verbatim

### From the Summary

The change renames `docs/plan` to `docs/roadmap` to distinguish the long-term roadmap from implementation plans in `docs/plans`. It keeps `PROJECT_PLAN.md` as the entry point and updates navigation while preserving recorded content and runtime requirements. The main risks are broken links and accidentally changing what the secret scanner permits.

### From the whole plan

The plan moves 19 roadmap files and updates documentation, agent instructions, local skills, tooling consumers and historical Markdown link destinations. Historical labels, recorded paths, decisions and evidence must remain unchanged. It also retains the schema scanner exception at the old path and adds the new path, with checks intended to prove that the exception remains narrow. The purpose is to make directory names clearer without changing roadmap meaning, implementation-plan discovery or runtime behavior.

### How the existing system works, per this plan — verbatim

`PROJECT_PLAN.md` introduces a roadmap whose detailed architectural and phase documents live under `docs/plan`. Separate, dated implementation contracts live under `docs/plans`, where a shared helper and public validator discover them. Historical records contain navigation links and recorded provenance that require different treatment during the rename. Secret scanning already permits a particular schema prose phrase through an exception restricted by path, rule and line.

The reader reported no Summary-versus-plan discrepancy and no section it could not paraphrase.

## Reviewer results

| Lens | Status | Result |
|---|---|---|
| Structure | Completed | No findings |
| Fresh reader | Completed | Four Majors and six Nits |
| Codebase fit | Completed | No findings |
| Zoom out | Completed | No findings |

Codebase fit confirmed the inventory, discovery root, existing scanner restrictions, CI canary/history scanning, relevant ADR constraints, and task coverage of R1–R6 and D1–D3.

Zoom out found the rename appropriately scoped, with consumer updates, historical preservation, scan compatibility and rollback handled together in one reversible PR.

## Findings

Locations below use the plan folder as their base unless otherwise stated. All findings remain **open**; none was waived, accepted, contested or silently downgraded.

| ID | Severity | Reviewer | Location | Finding and evidence | Proposed action |
|---|---|---|---|---|---|
| F1 | Major | Fresh reader | `plan.md:49`, Terms; `plan.md:65`, R2 | “Shared helper” and “public validator” are unnamed. Their purpose is explained, but the reader cannot identify the components whose discovery behavior must remain unchanged. The public validator is concretely located at `.github/scripts/check_plans.py`; its discovery expression is at line 116. | **Fix:** name both components and link to their documented invocation locations. Keep detailed commands in tasks or notes. |
| F2 | Major | Fresh reader | `plan.md:85`, R6; `plan.md:107`, D3 | The preservation requirement does not state the exact schema paths, permitted phrase or rule identifier. D3 delegates detail to notes. The existing restriction is concrete in `.gitleaks.toml:10–16`: `generic-api-key`, AND matching, exact old schema path, and the reviewed line phrase. | **Fix:** identify the old/new paths and exact preserved restriction in a clearly linked scanner contract in notes; make that reference explicit from R6/D3. |
| F3 | Major | Fresh reader | `plan.md:129`, Rollout & rollback; R1–R6 | The reader could explain the outcomes but could not reproduce verification from plan.md. It says “See notes.md for the verification outline”; `notes.md:31–47` supplies an outline rather than exact procedures. | **Fix:** give tasks or notes concrete verification entry points, expected outcomes and the historical-comparison procedure, with a direct plan reference. Detailed mechanics need not move into plan.md. |
| F4 | Major | Fresh reader | `plan.md:100`, D2; `plan.md:124`, Risks; R4 | Historical preservation depends on comparison against “the frozen baseline,” but that baseline is not explicitly designated. `notes.md:5` names `baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda` as the inventory base; it does not explicitly establish it as the preservation-comparison baseline. | **Fix:** designate the full immutable comparison SHA, distinguish it from review and implementation SHAs, and specify how the affected historical-record inventory is recorded. |
| F5 | Nit | Fresh reader | `plan.md:24`, Why; `plan.md:114`, Assumptions | “Skill Central,” “private suite,” and “earlier skill migration” lack enough explanation to identify their boundaries. | **Fix:** add concise definitions or a descriptive link explaining the excluded suite and migration metadata. |
| F6 | Nit | Fresh reader | `plan.md:32`, What changes; R1; Impact | The plan states 19 tracked files without listing them or providing an inventory procedure. The count was independently confirmed during this review. | **Fix:** add a reproducible inventory command or frozen inventory in notes. |
| F7 | Nit | Fresh reader | `plan.md:78`, R4 scenario | The roughly 40-word scenario combines preservation of several content categories with separately recording maintenance. | **Fix:** separate preservation verification from maintenance-record verification. |
| F8 | Nit | Fresh reader | `plan.md:83`, R5 scenario | “An identified directory-organization decision entry” does not state its destination. | **Fix:** name the decision-log file or section that may receive the entry. |
| F9 | Nit | Fresh reader | `plan.md:73`, R3 scenario | “Preserves its intended anchor or behavior” combines Markdown-anchor checks with tooling behavior checks. | **Fix:** split link and active-consumer scenarios. |
| F10 | Nit | Fresh reader | `plan.md:38`, Non-goals; D1; D3 | Keeping PROJECT_PLAN.md/docs/plans unchanged and preserving the old scanner exception are repeated across sections. | **Fix:** state each rule once and use requirement/decision references elsewhere. |

The technical reviewers’ “No findings” results do not resolve the reader’s findings. Some reader concerns concern where execution detail belongs; the skill permits that detail in phases and notes. The proposed actions preserve that split.

## Verdict and coordinator handoff

**FAIL.** All required reviewers ran, but four Majors remain open. Under `docs/reviews/README.md` gate rule 5, every Major requires a fix or evidence-backed contest before PASS. There are no Blockers, missing reviewers or structure findings.

For coordinator persistence:

- Record round 1 as `changes-requested`, with all three reviewer statuses completed and F1–F10 open.
- Record the automatic AGENTS.md visibility limitation.
- Set whole-plan and phase design-review metadata to `changes-requested`, round 1, dated `2026-11-14`.
- Resolve findings outside this reviewing session. Any fresh re-check should follow the repository’s independence rules.

No persistence or metadata updates were performed here.

Next: /design-review docs/plans/2026-11-14-roadmap-directory

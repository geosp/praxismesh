---
review: design
phase: general-skill-central-migration
change: docs/plans/2026-11-13-skill-central-migration
rfc: n/a
adrs: [ADR-0003]
commit_sha: 272eb64bbec7e4ceeaa521202096dbbb758b2f3b
docs_sha: n/a
diff_base: n/a
session: fresh
date: 2026-11-14
verdict: FAIL
reviewers:
  - {lens: fresh-reader, status: completed}
  - {lens: codebase-fit, status: completed}
  - {lens: zoom-out, status: completed}
---

# Independent cutover design review, round 1

Frozen report below; transient checkout hyperlinks are rendered as repository
path references. Later fixes do not rewrite this verdict.

**Verdict: FAIL — changes requested.** One open Major: the cutover design conflicts with an accepted ADR and does not plan its reconciliation. All three reviewers completed. Mechanical checks passed.

This report is returned for coordinator persistence. No files, plan state, configuration, review logs or GitHub records were changed. No tests, fixes, installations or runtime phase completion were performed.

## Review record

```yaml
review: design
target: docs/plans/2026-11-13-skill-central-migration
phase: "03"
commit_sha: 272eb64bbec7e4ceeaa521202096dbbb758b2f3b
docs_sha: n/a
diff_base: n/a
session: fresh
date: 2026-11-14
verdict: FAIL
skill_result: changes-requested
reviewers:
  - {role: design-reader, lens: fresh reader, status: completed}
  - {role: design-reviewer, lens: codebase fit, status: completed}
  - {role: design-reviewer, lens: zoom out, status: completed}
```

HEAD matched the requested revision. The working tree was clean before and after review.

The three native roles started with fresh contexts (`fork_turns: none`). No author transcript, earlier findings, earlier verdicts or other reviewer’s output was supplied to them. Only the coordinator read the existing `reviews.md` for the skill’s closed-finding reconciliation step; it contained no prior design-review round.

**Reader independence limitation:** the harness could not guarantee suppression of automatically loaded project instructions. The reader explicitly reported receiving the supplied AGENTS.md guidance and project status automatically. It opened only the named `plan.md`. Its paraphrases therefore have less independence than a reader with no project instructions.

Repository content was reviewed at the frozen HEAD. Reviewers additionally inspected historical changed-path comparisons against `bfa79d1270ebba0f83fe3cf29d2abb7d448d37dd`; those comparisons are disclosed below and are not used to establish the design verdict. External Skill Central source, installations and activation claims were not independently verified.

## Input paths

All repository paths below are relative to `/tmp/praxismesh-cutover-independent-review`.

**Common design-reviewer inputs:**

```text
docs/plans/2026-11-13-skill-central-migration/plan.md
docs/plans/2026-11-13-skill-central-migration/phases/03-cutover.md
docs/plans/2026-11-13-skill-central-migration/notes.md
docs/adr/README.md
docs/adr/0001-keep-default-openspec-schema.md
docs/adr/0002-paradedb-as-postgresql-server.md
docs/adr/0003-early-compose-task-ui.md
```

**Fresh reader input:** only `docs/plans/2026-11-13-skill-central-migration/plan.md`, plus the automatically supplied project guidance disclosed above.

**Codebase-fit guidance and additional inspected content:**

```text
AGENTS.md
CLAUDE.md
PROJECT_PLAN.md
docs/development/planning.md
docs/reviews/README.md
docs/development/skill-central-migration-checks.md
docs/requirements/baseline.md
.github/scripts/check_plans.py
.github/scripts/ci_gate.py
.github/workflows/ci.yml
.github/pull_request_template.md
tests/test_plans.py
.agents/README.md
.agents/agents/README.md
.agents/skills/README.md
.agents/sync_agents.py
.agents/agents/verifier.md
.codex/agents/verifier.toml
.agents/skills/verify-phase/SKILL.md
pyproject.toml
```

The codebase-fit reviewer also read relevant search excerpts from:

```text
docs/plan/design-decisions.md
docs/plan/decision-log.md
.agents/skills/docs-design/SKILL.md
.agents/skills/github-pr/SKILL.md
```

It inventoried tooling, test and historical OpenSpec paths, inspected `.claude/skills` symlink metadata, and compared relevant changed paths with the historical baseline. It did not open `reviews.md` or prohibited review reports.

**Zoom-out additional inspected content:**

```text
docs/development/planning.md
docs/development/skill-central-migration-checks.md
.github/scripts/check_plans.py
.agents/sync_agents.py
```

It also inspected `git diff --name-status bfa79d1..HEAD`.

**Coordinator-only additional inputs:**

```text
docs/plans/2026-11-13-skill-central-migration/reviews.md
docs/templates/review-report.md
```

The coordinator read the common plan/ADR inputs and applicable guidance listed above, inspected committed-path inventories, and ran the mechanical checks below.

**Installed skill inputs, outside the repository snapshot:**

```text
/home/geo/.agents/skills/design-review/SKILL.md
/home/geo/.agents/skills/impl-plan/SKILL.md
/home/geo/.agents/skills/impl-plan/writing.md
/home/geo/.agents/skills/impl-plan/plan-tool.py
```

These installed files were not represented as committed repository inputs.

## Mechanical checks

Direct Python was used to avoid cache writes; `-B` disabled bytecode writes. Interpreter: **Python 3.14.10**.

| Check | Command | Observed |
|---|---|---|
| Shared plan structure | `python -B /home/geo/.agents/skills/impl-plan/plan-tool.py check docs/plans/2026-11-13-skill-central-migration` | Exit 0; **0 errors, 0 warnings** |
| Public plan validator | `python -B .github/scripts/check_plans.py` | Exit 0; **1 plan validated, 0 errors** |
| Generated agents | `python -B .agents/sync_agents.py --check` | Exit 0; **3 generated files up to date** |
| Lifecycle advisory | `python -B /home/geo/.agents/skills/impl-plan/plan-tool.py next docs/plans/2026-11-13-skill-central-migration` | Exit 0; requests whole-plan design review because recorded status is `none` |
| Snapshot integrity | `git rev-parse HEAD`, `git status --porcelain`, `git diff --exit-code HEAD` | Requested SHA; clean; no differences |
| Working-tree whitespace | `git diff --check HEAD` | Exit 0; clean diff, therefore no substantive whitespace coverage |

These checks establish structure and snapshot integrity. They do not establish design approval, execution evidence or closure.

## Fresh reader paraphrases — verbatim

### From the Summary

> This change moves implementation planning and independent reviews to the owner's Skill Central suite and retires active OpenSpec tooling. Completed phase records and their guarantees stay in place. The main risk is losing tool discovery or weakening phase gates during the transition, so the merged suite must be installed and verified before the PraxisMesh cutover merges.

### From the whole plan

> The change centralizes reusable planning skills and reviewer agents in Skill Central, adds installation support for the selected exports and harnesses, and switches future PraxisMesh requirements and designs to implementation plans. PraxisMesh then removes superseded tooling and replaces OpenSpec CI validation with a public, project-owned plans validator. Historical guarantees and phase evidence remain binding, and activation waits for protected suite merges and fresh-session discovery checks.

### How the existing system works, per this plan

> PraxisMesh currently has local skills or agents that the canonical suite will supersede, plus OpenSpec generation and validation tooling in CI. Its master plan controls scope and gates, and historical specifications and phase reports hold guarantees that must survive the migration. Phases 0 and 1 are closed, Phase 2 has not started, and there are no active OpenSpec changes.

The reader identified no section it could not paraphrase and no sentence over approximately 40 words.

## Consolidated findings

The reader’s original severities are retained below where synthesis changes them. Readability concerns are classified as Major only when they lead to a materially wrong understanding, as required by the skill.

| ID | Severity | Reviewer | Location | Finding and proposed change | Disposition |
|---|---|---|---|---|---|
| F1 | **Major** | Codebase fit; zoom out | D2; Open questions; phase 03 task 3.1 | D2 replaces parallel RFC/OpenSpec requirements, but accepted, unsuperseded ADR-0003 still requires an independently reviewed Phase 4A RFC and OpenSpec change. **Fix:** explicitly identify the conflict and add a task for a narrowly scoped superseding ADR that replaces the artifact requirement while preserving Phase 4A scope, sequencing and full-tier gates. | **Open; blocks PASS** |
| F2 | Nit | Fresh reader; originally Major for prerequisites | Summary; What changes | The Summary omits Codex/bundled-export prerequisites and the replacement public validator. **Fix:** add a short statement that the switch depends on the canonical suite prerequisites and replaces OpenSpec CI with local contract validation. The paraphrases otherwise convey the intended dependency order. | Open |
| F3 | Nit | Fresh reader; originally Major for several terms | Terms; R2; R4; rollout | “Protected review,” “doctor,” “coordinator” and “latest-head approval” are insufficiently introduced in the standalone plan. **Fix:** give brief definitions and name the linked workflow/protocol as their operational authority. Detailed procedures can remain outside `plan.md`. | Open |
| F4 | Nit | Fresh reader | D1; Terms | “Harness variants” and “owned links” are unexplained, and D1’s platform exception requires rereading. **Fix:** define ownership briefly and split the Codex registration explanation into a separate sentence. | Open |
| F5 | Nit | Fresh reader; originally Major | D3; R5 | The validator’s intended contract is broad: “repository-specific structure and closure references.” **Fix:** identify the principal validation categories and explicitly link their detailed specification. This would distinguish intended checks from execution evidence more clearly. | Open |
| F6 | Nit | Fresh reader | R4; rollout | R4 bundles several gates; the rollout paragraph combines ordering, evidence, merge authority and rollback. **Fix:** use separate acceptance scenarios and separate rollout/rollback paragraphs. | Open |
| F7 | Nit | Fresh reader; originally Major | Rollout & rollback | The plan says a Git revert restores project definitions but leaves the interaction with installed canonical tooling implicit. **Fix:** explain the intended installed-tooling state after repository rollback and point to the ownership-preserving recovery procedure. | Open |

**F1 evidence:**

- D2 (`docs/plans/2026-11-13-skill-central-migration/plan.md:82`) replaces parallel RFC/OpenSpec requirements.
- Open questions (`docs/plans/2026-11-13-skill-central-migration/plan.md:113`) says “None.”
- ADR-0003 (`docs/adr/0003-early-compose-task-ui.md:87`) requires an independently reviewed Phase 4A RFC and OpenSpec change.
- ADR policy (`docs/adr/README.md:6`) requires supersession through a new ADR without rewriting existing records.
- Cutover guidance (`docs/development/planning.md:52`) prohibits new OpenSpec changes and makes separate phase RFCs optional.
- Task 3.1 (`docs/plans/2026-11-13-skill-central-migration/phases/03-cutover.md:21`) does not explicitly deliver that reconciliation.

The following reader concerns were assessed but are **not additional defects**:

| Reader concern | Reported severity | Coordinator assessment |
|---|---|---|
| Tasks and phase-specific verification are absent from `plan.md`. | Major | Contest: the skill explicitly places tasks in phase files. Phase 03 contains task 3.1 and its Verify clause. |
| D1 defers installation locations and ownership mechanics to notes. | Major | Contest as a Major: the skill permits detailed mechanics in notes. D1 communicates the central installation choice; terminology improvement remains F4. |
| R3 incorporates guarantees through the linked baseline. | Major | Contest: explicit incorporation by reference is the selected design, and the baseline is directly identified. Duplicating the historical guarantees in this plan is unnecessary. |
| R4 relies on linked repository overrides and evidence procedures. | Major | Contest as a Major: R4 states the preserved gates, and the linked planning/review guidance supplies their mechanism. Naming that authority more clearly remains F3. |
| Linux/macOS checks lack their full matrix and procedure in `plan.md`. | Major | Contest as a Major: detailed activation procedures may live in linked tooling documentation. No missing matrix was independently established; terminology and navigation remain covered by F3. |

Neither design reviewer reported another code-fit, root-cause, simplicity, placement, failure-mode or rollout defect.

## Verdict and handoff

**FAIL / changes-requested:** all reviewers completed, but F1 remains an open Major. The proposed correction belongs in the authoring session, followed by fresh review of the affected design.

The missing prior design-review record is **not a finding**. Implementation status, owner scope approval and passing checks were **not counted as design approval**. No runtime closure is claimed.

Helper output, informational only:

```text
Next: /design-review docs/plans/2026-11-13-skill-central-migration
Reason: plan design review is none
```

That output reflects unchanged recorded plan state; it does not negate this phase-03 review.

---
review: design
phase: general-roadmap-directory
change: docs/plans/2026-11-14-roadmap-directory
rfc: n/a
adrs:
  - docs/adr/0001-keep-default-openspec-schema.md
  - docs/adr/0002-paradedb-as-postgresql-server.md
  - docs/adr/0003-early-compose-task-ui.md
  - docs/adr/0004-use-implementation-plans-for-development.md
commit_sha: fd9425d6635c2dd11b4bd33d06c198ed6338e8ac
docs_sha: n/a
diff_base: n/a
session: fresh
date: 2026-11-14
round: 2
final_round: true
verdict: PASS
reviewers:
  - { lens: fresh reader, role: design-reader, status: completed }
  - { lens: codebase fit, role: design-reviewer, status: completed }
  - { lens: zoom out, role: design-reviewer, status: completed }
---

# Design review: Rename the project roadmap directory

**PASS, with open Nits.** All three reviewers completed. The reader’s three Major findings are contested below with written evidence and the installed skill’s two-layer document rules. No Blocker or Major remains open.

This is the second and final pre-implementation documentation/tooling review. It does not close a runtime phase or authorize implementation or merge. This report is returned for persistence; no repository files or lifecycle metadata were changed.

## Frozen inputs and independence

Repository root: `/tmp/praxismesh-roadmap-design-review`.

HEAD was verified before and after review as:

`fd9425d6635c2dd11b4bd33d06c198ed6338e8ac`

The working tree was clean before and after review.

All three native reviewers were spawned with `fork_turns: none`, using their prescribed briefs. They received no prior findings, verdicts, author reasoning, conversation history or other reviewer output. Only the coordinator read `reviews.md` and reconciled its correction claims.

**Automatic instruction visibility limitation:** fresh forks do not establish that the harness suppressed automatically supplied project instructions. The fresh reader was explicitly told to open only `plan.md`, but instruction-free context cannot be certified. Similarly, the zoom-out brief supplied no guidance-file list, but automatic guidance visibility cannot be excluded. Treat the reader’s paraphrases as having this independence limitation.

### Exact reviewer input lists

All relative paths below resolve against the repository root.

| Reviewer | Explicit file inputs |
|---|---|
| Fresh reader | `docs/plans/2026-11-14-roadmap-directory/plan.md` only |
| Codebase fit | Plan, phase, notes, all five ADR-directory files below, `AGENTS.md`, `CLAUDE.md`; repository code available for inspection |
| Zoom out | Plan, phase, notes, all five ADR-directory files below; repository code available for inspection |

Plan, phase and notes:

- `docs/plans/2026-11-14-roadmap-directory/plan.md`
- `docs/plans/2026-11-14-roadmap-directory/phases/01-roadmap-rename.md`
- `docs/plans/2026-11-14-roadmap-directory/notes.md`

ADR-directory inputs:

- `docs/adr/0001-keep-default-openspec-schema.md`
- `docs/adr/0002-paradedb-as-postgresql-server.md`
- `docs/adr/0003-early-compose-task-ui.md`
- `docs/adr/0004-use-implementation-plans-for-development.md`
- `docs/adr/README.md`

Only root `AGENTS.md` and `CLAUDE.md` were found; no nested guidance files were found for the Impact paths. ADR-0002 and ADR-0003 are accepted; ADR-0001 and ADR-0004 remain proposed.

Coordinator-only reconciliation and procedural inputs included:

- `docs/plans/2026-11-14-roadmap-directory/reviews.md`
- `PROJECT_PLAN.md`
- `docs/development/planning.md`
- `docs/reviews/README.md`
- `docs/templates/review-report.md`
- `/home/geo/.agents/skills/design-review/SKILL.md`
- `/home/geo/.agents/skills/impl-plan/SKILL.md`
- `/home/geo/.agents/skills/impl-plan/writing.md`

The preservation baseline is separately designated as `baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda`; it is not this review’s frozen SHA.

## Fresh reader paraphrases — verbatim

### From the Summary

The change renames `docs/plan` to `docs/roadmap` to distinguish the long-term project roadmap from implementation contracts in `docs/plans`, while retaining `PROJECT_PLAN.md` as its entry point. References and historical navigation links will follow the new location without changing decisions, evidence or runtime requirements. The main risks are broken links and accidentally changing which content a secret-scanning exception permits.

### From the whole plan

The plan moves 19 roadmap files, updates documentation and tooling consumers, and repairs Markdown navigation destinations in historical records. It preserves roadmap meaning, historical prose and recorded provenance, and implementation-contract discovery under `docs/plans`. It also preserves a narrow secret-scanning exception at both the historical and new schema paths. The purpose is to remove confusing directory names without changing runtime behavior or the planning workflow.

### Additional reader assessment

The reader reported no Summary-versus-plan mismatch and no section it could not paraphrase. Its description of the existing system correctly distinguished the roadmap, implementation contracts, historical navigation and recorded paths, and scanner exception.

## Reviewer statuses

| Lens | Status | Assessment |
|---|---|---|
| Fresh reader | Completed | Accurate paraphrases; three proposed Majors and seven Nits, reconciled below |
| Codebase fit | Completed | No findings |
| Zoom out | Completed | No findings |
| Structure | Completed | Zero errors, zero warnings |

Codebase fit confirmed the 19-file baseline inventory; discovery at `.github/scripts/check_plans.py:116`; the scanner configuration at `.gitleaks.toml:10–16`; the existing canary at `.github/workflows/ci.yml:168–192`; and task coverage of R1–R6 and D1–D3. It identified no applicable guidance or accepted-ADR conflict. It explicitly did not independently inspect external installed-helper behavior.

Zoom out found that the rename addresses the naming ambiguity directly, with bounded scope, adequate preservation checks, and coherent one-PR rollout and rollback.

## Fresh findings and reconciliations

`P`, `N` and `T` denote this plan’s `plan.md`, `notes.md` and phase file respectively. Reader-proposed severities are preserved even where contested.

| ID | Severity raised | Reviewer | Location and evidence | Proposed action / evidence-backed reconciliation | Resolution |
|---|---|---|---|---|---|
| R2-01 | Major | Reader | P R6/D3, lines 98–101, 123–126: exact scanner details are delegated to notes. | **Contest:** P explicitly links the scanner contract. N:60–86 specifies the target rule, AND condition, line matching, exact frozen expression source and both exact paths. N:88–112 supplies the canary matrix. `writing.md` permits detailed mechanics in linked notes. The paraphrases correctly understand the invariant. | Contested; closed |
| R2-02 | Major | Reader | P R4/D2/Risks: baseline and inventory mechanics are outside `plan.md`. | **Contest:** P:89 and 115–119 explicitly link the preservation procedure. N:19–24 designates the full immutable baseline; N:26–58 defines inventory, byte reconstruction, comparisons and evidence. This is linked verification depth, not missing intent. | Contested; closed |
| R2-03 | Major | Reader | P R2–R3/Rollout: commands, expected results and active-consumer inventory require supporting documents. | **Contest:** P:52–54 names both validators and links invocation guidance; P:152–153 links verification. N:11–15 defines inventory scope; N:121–153 supplies commands, expected results and residual-path classification; N:155–160 gives the navigation walkthrough. Detailed commands and inventory mechanics belong in notes. | Contested; closed |
| R2-04 | Nit | Reader | P Assumptions, line 133: “private suite” is not explicitly identified as the defined Skill Central suite. | **Fix:** use “Skill Central suite” consistently. This narrowly reopens the terminology portion of prior F5. | Open |
| R2-05 | Nit | Reader | P Terms, lines 57–59: OpenSpec is named without explaining its former role. | **Fix:** add a short description of the former specification/change-artifact workflow. The existing definition explains replacement, but leaves that role implicit. | Open; related to prior F5 |
| R2-06 | Nit | Reader | P R1: authoritative 19-file inventory is outside the plan. | **Contest:** N:26–34 provides the frozen `git ls-tree` invocation and expected six-topic/thirteen-phase inventory. P links these notes. Duplicating the inventory in `plan.md` is unnecessary under the two-layer format. | Contested; closed |
| R2-07 | Nit | Reader | P R4, D2 and Risks repeat the preservation constraint. | **Fix:** shorten repeated wording while retaining the requirement, decision rationale and risk mitigation in their respective sections. The repetition is consistent and causes no wrong understanding. | Open |
| R2-08 | Nit | Reader | P R5, lines 93–94 combines several preserved properties and permitted edits. | **Fix:** clarify the distinction between the preservation invariant and allowed edits. These are coherent aspects of meaning preservation; the wording concern is Nit, not Major. | Open |
| R2-09 | Nit | Reader | P D1, lines 107–110: “their document contents” follows both a filename and a discovery root. | **Fix:** name `docs/plans` directly and identify which documents receive path maintenance. This narrowly reopens the clarity portion of prior F10. | Open |
| R2-10 | Nit | Reader | P R6, lines 98–99: “line expression” requires the linked scanner contract to interpret. | **Fix:** use “allowlist line-matching expression” or name the configuration field. The exact expression remains appropriately in notes; only wording needs clarification. | Open |

The reader’s proposed Majors concern executing checks from `plan.md` alone. They do not demonstrate materially wrong understanding: both paraphrases correctly state the change, preservation boundaries and scanner risk. The linked notes supply the questioned mechanics. These findings are explicitly contested, not silently waived or omitted.

## Reconciliation of every prior finding

Prior F1–F10 were recorded as fixed after owner-approved corrections. None was recorded as accepted or contested. Each fixed claim was checked against the frozen documents after fresh reviewer assessments were available.

| Prior ID | Evidence at frozen HEAD | Round-2 reconciliation |
|---|---|---|
| F1 — unnamed validators | P:52–54 names `impl-plan/plan-tool.py` and `.github/scripts/check_plans.py`, with invocation guidance. | Fixed; remains closed. R2-03’s separate demand for inline commands is contested above. |
| F2 — implicit scanner contract | P:98–99 and 123–126 link N:60–112, which specifies configuration invariants and canaries. | Fixed; remains closed. Fresh recurrence R2-01 is contested with the linked contract. |
| F3 — unreproducible verification outline | P:152–153 links N:114–160; N:36–58 defines exact historical comparison; N:88–112 defines canaries. | Fixed; remains closed. R2-03 is contested against those concrete procedures. |
| F4 — undesignated preservation baseline | N:19–24 supplies the full SHA and distinguishes review, implementation and final-head references; N:38–55 defines affected-record evidence. | Fixed; remains closed. R2-02 is contested. |
| F5 — external-suite/migration context | P:55–59 defines Skill Central and prior migration metadata. P:133 still says “private suite”; OpenSpec’s former role remains implicit. | Partially reopened as Nits R2-04 and R2-05; the supplied definitions are retained as evidence of the partial fix. |
| F6 — unreproducible inventory | N:26–34 provides immutable inventory command and expected composition; baseline inspection confirms 19 files. | Fixed; remains closed. R2-06 is contested. |
| F7 — combined preservation/recording scenario | P:88 and P:89 now separately specify preservation and maintenance-record evidence. | Fixed; remains closed. R2-07 concerns repetition, not the former combined scenario. |
| F8 — unspecified decision-entry destination | P:94 explicitly names `docs/roadmap/decision-log.md`. | Fixed; remains closed. R2-08 is a distinct wording concern. |
| F9 — combined anchor/consumer checks | P:82 and P:83 separate navigation/anchor checks from active-consumer behavior. | Fixed; remains closed. |
| F10 — repeated boundaries / D1 ambiguity | D3 refers to R6; D1 distinguishes the retained filename and discovery root from maintained contents, but its pronoun remains awkward. | Partially reopened as Nit R2-09. The fresh R4 repetition concern is separately retained as R2-07. |

The older “findings remain open” sentence in `reviews.md` is followed by the explicit owner-approved corrections entry and fixed resolutions. It was treated as historical narration, not as evidence that corrections were absent.

## Mechanical checks and scope limits

Executed read-only:

```text
python -B /home/geo/.agents/skills/impl-plan/plan-tool.py check docs/plans/2026-11-14-roadmap-directory
```

Result:

```text
2026-11-14-roadmap-directory: 0 error(s), 0 warning(s)
```

Additional read-only inspection confirmed:

- Baseline roadmap inventory: six topic files and thirteen phase files.
- Only this rename contract and its new review evidence differ from the preservation baseline; baseline historical records have not already been modified.
- The current scanner configuration matches the frozen configuration referenced by notes.
- Final HEAD and working-tree cleanliness are unchanged.

No tests, canaries, dependency synchronization, configuration changes, edits, fixes, commits or GitHub writes were performed. Future verification commands were assessed as documentation; their outcomes are not claimed.

## Verdict and remaining open items

**PASS.** All three reviewers completed; no Blocker or Major remains open after evidence-backed contests. Seven Nits remain open: R2-04, R2-05, R2-07, R2-08, R2-09 and R2-10 comprise six rows, with R2-05 separately tracking the second terminology concern. **The authoritative count is six open finding rows.**

Remaining work is to resolve or retain those six wording findings and persist this report and round-2 lifecycle result in an authorized writing session. No third review round is initiated.

The helper’s literal output still reflects unchanged round-1 metadata:

```text
Next: /design-review docs/plans/2026-11-14-roadmap-directory
Reason: plan design review is changes-requested
```

That output is recorded for accuracy; it does not override the instruction to stop after this final round.

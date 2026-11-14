# Reviews · Rename the project roadmap directory

No independent review or lifecycle approval has run for this contract.


## 2026-11-14 · design-review · plan · round 1 · changes-requested

- Frozen contract: c76f77e11dc2ab309a38ef63836e8003f18c82cc, committed only in
  a detached disposable review checkout; no commit was made on main.
- Reviewers: fresh reader completed; codebase fit completed; zoom out completed.
- [Independent report and verbatim reader paraphrases](../../reviews/general-roadmap-directory/design-review-01.md).
- Shared helper: zero errors and warnings. Inventory: 19 roadmap files.
- Reader opened only plan.md, but the harness automatically supplied AGENTS.md;
  the report discloses that independence limitation.
- Verdict: FAIL, four open Majors; no implementation or runtime phase closure.

| ID | Severity | Reviewer | Location | Finding | Proposed action | Resolution |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | Major | Reader | Terms, R2 | Validation components are unnamed. | Fix: identify the shared helper and public validator, linking invocation guidance. | fixed: Terms names both tools and links their invocation guidance. |
| F2 | Major | Reader | R6, D3 | Exact scanner preservation contract is implicit. | Fix: explicitly link the old/new paths, rule, AND restriction and existing line expression in notes. | fixed: R6/D3 link the notes Scanner contract, which identifies both exact paths, rule, AND mode and the unchanged line expression from immutable TOML. |
| F3 | Major | Reader | Rollout, R1–R6 | Verification outline lacks reproducible entry points. | Fix: document commands, expected results and the historical-comparison procedure. | fixed: notes Verification procedure gives commands, expected outcomes, canary matrix, navigation walkthrough and byte-comparison procedure. |
| F4 | Major | Reader | D2, R4 | Preservation baseline is not explicitly designated. | Fix: designate the full immutable SHA and affected-record inventory procedure. | fixed: notes Preservation baseline designates baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda, separates review/implementation/head SHAs and specifies the affected-record inventory. |
| F5 | Nit | Reader | Why, Assumptions | External suite and prior migration boundaries need context. | Fix: add concise definitions or descriptive links. | fixed: Terms defines Skill Central suite and prior migration metadata with descriptive links. |
| F6 | Nit | Reader | R1, Impact | The 19-file inventory is not reproducible from the plan. | Fix: add a frozen inventory command in notes. | fixed: notes gives the immutable git ls-tree command and expected six-topic/thirteen-phase inventory. |
| F7 | Nit | Reader | R4 scenario | Preservation and maintenance recording share one scenario. | Fix: split the scenarios. | fixed: R4 uses separate preservation and maintenance-record scenarios. |
| F8 | Nit | Reader | R5 scenario | Decision-entry destination is unspecified. | Fix: name the roadmap decision-log file. | fixed: R5 names docs/roadmap/decision-log.md as the only organization-entry destination. |
| F9 | Nit | Reader | R3 scenario | Anchor and active-consumer behavior checks are combined. | Fix: split navigation and consumer scenarios. | fixed: R3 separates link/anchor and active-consumer scenarios. |
| F10 | Nit | Reader | Non-goals, D1, D3 | Some unchanged-boundary rules are repeated. | Fix: distinguish unchanged names/discovery roots from updated document contents and refer to the authoritative rules. | fixed: D1 distinguishes retained filename/discovery root from maintained contents; D3 refers to R6 instead of restating its restriction. |

The technical reviewers reported no findings. Findings remain open pending the
engineer's choice of corrections. No fixes or waivers were applied by reviewers.

## 2026-11-14 · approved corrections · design round 1

The owner directed: “Apply all ten corrections.” F1–F10 were applied in the
plan and verification notes; each resolution above names its location. This
approval covers those plan corrections, not implementation or phase closure.
The frozen round-1 report remains unchanged. Design-review metadata remains
changes-requested pending the second, fresh review; no PASS is inferred from
structural validation or the author's corrections.


## 2026-11-14 · design-review · plan · round 2 · passed

- Frozen contract: fd9425d6635c2dd11b4bd33d06c198ed6338e8ac.
- Reviewers: fresh reader completed; codebase fit completed; zoom out completed.
- [Independent report and verbatim paraphrases](../../reviews/general-roadmap-directory/design-review-02.md).
- Helper: zero errors and warnings. Reader instruction-visibility limitation is
  disclosed. No Blocker or Major remains open; no implementation has begun.
- R2-01–03 are contested with evidence in the report: the explicit notes links
  supply the mechanics, as the skill's two-layer format permits. R2-06's demand
  to duplicate the inventory is also contested there.
- The report's authoritative count is six open wording rows, despite its initial
  seven-Nit wording. Those six corrections are resolved below; frozen report text
  remains unchanged. No third round was run.

| ID | Severity | Reviewer | Finding | Resolution |
| --- | --- | --- | --- | --- |
| R2-04 / F5 | Nit | Reader | Private-suite terminology is inconsistent. | fixed: Assumptions now uses the defined Skill Central suite term. |
| R2-05 / F5 | Nit | Reader | OpenSpec's former role is implicit. | fixed: Terms defines the retired specification/change-artifact workflow. |
| R2-07 | Nit | Reader | Historical preservation wording repeats. | fixed: D2 and the risk mitigation refer to R4 and the preservation procedure. |
| R2-08 | Nit | Reader | R5 blends the invariant and allowed edits. | fixed: R5 states preservation separately from its permitted-edits paragraph. |
| R2-09 / F10 | Nit | Reader | D1's pronoun obscures which contents change. | fixed: D1 explicitly names PROJECT_PLAN.md, docs/plans and navigation in root/contract files. |
| R2-10 | Nit | Reader | Line expression is vague. | fixed: R6 says allowlist line-matching expression; exact frozen field remains in the scanner contract. |

All ten owner-approved round-1 corrections are now resolved, including the narrow
terminology and clarity recurrences above. Final changes address wording only;
the reviewed scope and requirements remain intact. Plan/phase design-review
metadata is passed, two rounds. Lifecycle approval remains the next checkpoint.


## 2026-11-14 · approved · plan

The owner stated: “I approve it.” The approve gate passed after independent
whole-plan design review PASS (two rounds). Plan and phase 01 are approved;
no waiver was used. Task boxes remain unticked. Branch selection and the start
gate precede implementation.


## 2026-11-14 · impl-review · phase 01 · round 1 · passed

- Diff base: 824ddb625f9fc40b04ad5d097e16ba6aaa93a2b7.
- Frozen code_sha: 64cc13657ca601a4b225f24444f28869fffba519.
- Reviewers: contract completed; failure/retry completed; scope/composition completed.
- [Independent report](../../reviews/general-roadmap-directory/implementation-review-01.md).
- Mechanical helper/public validation, agent generation, discovery and diff checks
  passed. Reviewers independently reconstructed all 147 historical files and all
  19 roadmap files; exactly 15 authorized destinations and one decision entry differ.
- No Blocker or Major. All three task boxes remain unticked pending final delivery
  checks; no runtime phase completion is claimed.

| ID | Severity | Reviewer | Finding | Resolution |
| --- | --- | --- | --- | --- |
| IR-01 | Nit | Contract | Default history command visits a disclosed failing local-only ref. | fixed: notes now gives explicit HEAD-lineage and baseline comparisons beside the command, retaining the all-local-refs failure as a distinct observation. CI selection and exceptions are unchanged. |
| IR-02 | Nit | Failure/retry | Inherited canary can read a stale report after a scanner error on a local rerun. | open: follow-up tooling work; unchanged from the base, not introduced by the rename. Fresh CI isolation limits exposure. No waiver of a required acceptance check is claimed. |

## 2026-11-14 · implementation checks and maintenance walkthrough

- [Observed walkthrough and checks](../../demos/general-roadmap-directory.md).
- Full suite: 165 passed, 91 normally deselected; lint/format/types, dependency sync,
  agent generation, workflow lint, plan validators and offline links passed.
- Exact canary matrix passed. Temporary old-path-only and OR mutants were rejected.
- The file-aware committed HEAD-lineage scan passed. The pathless diff scan raised
  two warnings; file-aware scanning is authoritative for path-specific exceptions.
  The separate all-local-refs finding also reproduces with the baseline config.
- These checks were executed in the implementation session; they are not described
  as an independent verify-phase run or a runtime gate closure. Latest-head CI and
  final delivery/coordinator checks remain required before task completion.

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

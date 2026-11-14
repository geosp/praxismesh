# Reviews · Evaluate DSH as the primary agent harness

At plan creation, no independent review, lifecycle approval or executable
compatibility test had run. Dated entries below record subsequent reviews.


## 2026-11-14 · design-review · plan · round 1 · changes-requested

- Frozen contract: 3c994002986f9e2eb4df99d0161dbf2ec5327896, in a detached
  disposable checkout. No commit was made on main.
- Reviewers: reader completed; codebase fit completed; zoom out completed.
- [Independent report and verbatim paraphrases](../../reviews/general-dsh-harness-evaluation/design-review-01.md).
- Shared helper: zero errors/warnings; public validator: three plans, zero errors.
- All reviewers reported automatic AGENTS.md visibility; the reader opened only
  plan.md. The report discloses the resulting independence limitation.
- Verdict: FAIL because F8/F9 remain open Majors. No DSH code or model ran.

| ID | Severity | Reviewer | Finding | Proposed action / resolution |
| --- | --- | --- | --- | --- |
| F1 | Blocker, contested | Reader | Exact TaskResult mapping is outside plan.md. | contested: existing schema/runner and phase 02 task 2.2 supply the reference contract; detailed mapping belongs in the experiment. Optional concise Terms definition proposed. |
| F2 | Major, contested | Reader | Recovery/ownership guarantees allegedly undefined. | contested: R4 defines preserved state, nonduplication and exclusion; notes identifies interruption probes and barrier discovery as experiment work. |
| F3 | Major, contested | Reader | Ten benchmark checks are not in plan.md. | contested: linked benchmark and existing task source define reusable checks. |
| F4 | Nit | Reader | Model, profiles and template locks lack a short explanation. | fixed: Terms identifies model, worker profile/template and registry lock with source paths. |
| F5 | Nit | Reader | Runtime phases lack a one-line explanation. | fixed: Terms gives the Phase 1 harness baseline and unstarted Phase 2 communications scope. |
| F6 | Major contested; Nit open | Reader | Tasks are in phase files, but phase titles are not clickable. | contested as Major; fixed navigation Nit: phase titles link to their task files. |
| F7 | Major, contested | Reader | Artifact/revision details are in notes. | contested: notes pins revision; task 1.1 selects matching artifacts rather than claiming they already exist. |
| F8 | Major | Reader, upheld | Bounds/grace acceptance lacks values, configuration source or pre-run selection rule. | fixed: notes Stop and cleanup policy defines the frozen pre-run manifest, inherited/test limits, trigger, 5-second grace, 10-second observer and failure/cleanup rules. |
| F9 | Major | Reader, upheld | Usage ledger has no independent observation point, units or exhaustion oracle. | fixed: notes Independent usage ledger defines the external model gateway/tool executor, units, correlations, missing-usage handling and exact exhaustion/retry/auxiliary oracles. |
| F10 | Major, contested | Reader | Hard gates allegedly unidentified. | contested: notes identifies R1–R7/R10 and the separate R8 rule. |
| F11 | Major, contested | Reader | Fixture grants are not enumerated in plan.md. | contested: trusted composition is a task 1.1/1.2 deliverable; notes specifies disclosure and denial probes. |
| F12 | Nit | Reader | Missing-barrier failure versus unavailable-prerequisite blocking is implicit. | fixed: R9 and notes distinguish demonstrated missing-barrier failure from unavailable-prerequisite blocking. |
| F13 | Nit | Reader | Benchmark checks are bundled. | fixed: R8 links notes benchmark checks B1–B4. |
| F14 | Nit | Reader | Orchestration inventory and auxiliary accounting are combined. | fixed: R10 separates orchestration ownership inventory from auxiliary bounds/accounting. |

Codebase-fit and zoom-out reported no findings. Evidence-backed contests above
retain their detailed reasoning in the frozen report; no finding was silently
waived. Open findings await the engineer's choice of corrections.

## 2026-11-14 · approved corrections · design round 1

The owner directed: “Apply all.” F4/F5/F6/F8/F9/F12/F13/F14 corrections are applied
above, plus F1's optional concise TaskResult definition. These changes clarify the
experiment proposal; no runtime was installed or executed. The frozen
round-1 report is unchanged. Design review remains changes-requested pending a
fresh final round; author corrections do not themselves establish a passing review.


## 2026-11-14 · design-review · plan · round 2 · passed

- Frozen contract: de6507f73ba9ec0a775299125e49f0fc366938d1.
- Reviewers: reader completed; codebase fit completed; zoom out completed.
- [Independent report and verbatim paraphrases](../../reviews/general-dsh-harness-evaluation/design-review-02.md).
- Helper: zero errors/warnings; public validator: three plans, zero errors.
- Earlier F8/F9 fixes were independently verified and not reopened. No Blocker
  or Major remains open after evidence-backed contests in the report.
- S1/S3/S4/S5/S6/S7/S8 are explicitly contested and closed with evidence there;
  no acceptance condition was waived. Automatic instruction visibility and the
  shared read-only checkout limitation remain disclosed.

| ID | Severity | Reviewer | Finding | Resolution |
| --- | --- | --- | --- | --- |
| S2 | Nit | Reader | Trusted Cordis patches could imply source modifications. | fixed: Terms defines reviewed configuration overlays and separately hashed plugin bundles. |
| S9 | Nit | Reader | Adoption handoff repeats. | fixed: rollout refers to D5; the decision log records the owner's exploration request without repeating the adoption rule. |
| S10 | Nit | Reader | Stop and outcome cases are bundled. | fixed: R5 has separate stall/tool/cancel/step-limit scenarios; R7 links the labelled O1–O5 outcome checklist. |
| S11 | Nit | Coordinator | Initial log preamble contradicts later entries. | fixed: qualify it as the plan-creation state, preserving dated round entries and frozen reports. |

These final edits clarify wording and case navigation only. The second and final
review round is complete; no third round ran. Whole-plan and both phase review
metadata are passed with two rounds. Plan approval remains the next checkpoint;
no DSH package was installed, candidate code executed or adoption approved.


## 2026-11-14 · approved · plan

The owner stated: “Implementation approved.” The approve gate passed after
independent whole-plan design review PASS (two rounds). The plan and both passed
phases are approved; no waiver was used. No task is checked off. Phase 01 branch
selection and its start gate precede executable work. Approval authorizes the
isolated spike, not production DSH adoption or runtime phase closure.

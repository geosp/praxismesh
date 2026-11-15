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


## 2026-11-14 · impl-review · phase 01 · round 1 · changes-requested

- Frozen code_sha: 8d7897ed96698b87fc4d603783c24f273ee05251.
- Diff base: 952d01e097332905ba56d6c26e1e342431f8f394.
- Reviewers: Contract completed; Failure and retry completed; Scope and composition completed.
- [Fresh independent report](../../reviews/general-dsh-harness-evaluation/implementation-review-01.md).
- Verdict: FAIL; two open Majors. No corrections or waivers were applied in the review session.
- Mechanical checks: zero plan errors/warnings, public validation passed, diff check passed.
  The read-only session used python -B for the standard-library helpers because uv required a cache write.
- Tasks 1.1–1.3 remain unticked; all delivered IDs are defined and have scenarios.
  Runtime checks were not repeated by these read-only reviewers; independent verification remains due.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | Contract; Scope and composition | Preflight validates four files while executing the complete mutable dependency directory (R1). | open |
| F2 | Major | Failure and retry | Docker inspection errors can falsely confirm container absence and preserve success (R1). | open |
| F3 | Nit | Contract | Poison probes do not enforce a complete effective authority catalog (R3). | open |
| F4 | Nit | Contract | Present auxiliary facilities lack identified admission/control/accounting coverage (R10). | open |
| F5 | Nit | Contract | Declared ten-second observation window is not executed (task 1.2). | open |
| F6 | Nit | Scope and composition | Host gateway requests/handlers are outside recorded ownership and cleanup (D4, R10). | open |
| F7 | Nit | Failure and retry | Persisted manifests do not identify matching random scratch directories (R1). | fixed: test_manifest_identifies_exact_nonoverlapping_scratch_paths; UUID scratch_directory; fresh review pending |

Owner selection of corrections is the next review checkpoint. Phase 02 remains unstarted.

Additional implementer check, separate from reviewer findings: gitleaks flagged
one generic-api-key match at artifacts.json:14 in 5ef9eb701b7315a70a63ff945a97fafda334240d.
The value is the SHA-256 of the release SDK api.py, not a credential; it matches
installed/source bytes. The scanner result remains unresolved. No scanner policy,
ignore or security setting was changed. Offline links and actionlint passed.


## 2026-11-14 · approved corrections · implementation round 1

The owner directed “Proceeed” after the recommendation to correct all seven findings.
All seven fixes were implemented with failing regressions first. Each test detected
a temporary reversion of its fix, then the restored suite passed (22 tests).
F1 additionally passed fresh locked-install reproduction in a second directory.
The first report is frozen; metadata stays changes-requested pending fresh review.
No acceptance condition, scanner policy or production configuration was waived.


## 2026-11-14 · impl-review · phase 01 · round 2 · changes-requested

- Frozen code_sha: 35ac465bf2618f1e6031bc325be885800cbf9c2c.
- Diff base: 952d01e097332905ba56d6c26e1e342431f8f394.
- [Final full independent review report](../../reviews/general-dsh-harness-evaluation/implementation-review-02.md).
- Reviewers: Contract completed; Failure and retry completed; Scope and composition completed.
  Contract and Scope disclosed exposure to the correction summary in the as-built
  report before their complete assessments. They saw no other reviewer verdict;
  Failure and retry confirmed no prior-correction exposure. This is an explicit
  independence limitation, not a claim of fully isolated fresh assessment.
- Verdict: FAIL; two open Majors. All seven round-1 defects were addressed and
  none reopened as the same defect. The four findings below concern additional paths.
- Mechanical checks: zero plan errors/warnings, public validation passed, diff
  and syntax checks passed. Embedded evidence digests and source/configuration
  hashes matched the frozen revision. Runtime checks were not independently run.
- All task boxes remain open. Phase 02 remains unstarted.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | Failure and retry | A truncated fixture log can raise before mandatory container cleanup and result persistence (task 1.3). | fixed: test_bad_evidence_cannot_bypass_cleanup_or_failed_result; unconditional finish_run cleanup and persisted failure; independently addressed in targeted-follow-up-01.md |
| F2 | Major | Scope and composition; Contract subset | Code/configuration are mounted from mutable source after manifest hashing; granted skill has no content digest (R1). | fixed: test_changed_runtime_input_is_rejected_during_staging and test_mounts_use_snapshot_after_originals_change; verified runtime and skill snapshots; independently addressed in targeted-follow-up-01.md |
| F3 | Nit | Scope and composition | Gateway and container cleanup start separate clocks and may exceed the original five-second grace (task 1.2). | fixed: test_shared_trigger_detects_gateway_plus_removal_exceeding_grace; shared monotonic trigger; independently addressed in targeted-follow-up-01.md |
| F4 | Nit | Contract | manifest_sha256 hashes canonical JSON without the newline added to the persisted file (R1). | fixed: test_manifest_digest_identifies_exact_persisted_bytes; save_manifest hashes saved bytes; independently addressed in targeted-follow-up-01.md |

This was the second and final full review round. Owner selection of corrections
is the next checkpoint; no third full review is planned. Any correction validation
must remain explicitly targeted and does not erase this report or its limitations.


## 2026-11-14 · approved corrections · implementation round 2

The owner directed “All of them.” All four additional findings are corrected.
Eight new regression cases failed first; four temporary reversions each made the
corresponding regression fail, then restored code passed the complete suite.
Both frozen reports and the second-round independence limitation are preserved.
Only a targeted check of these corrections is authorized next; no third full
review is planned. Phase metadata stays changes-requested pending that check.


## 2026-11-14 · targeted implementation follow-up · phase 01 · passed corrections

- Frozen code_sha: 33a532b2fd039e3d715dae6e64290190e84ecd2c.
- Correction diff base: 35ac465bf2618f1e6031bc325be885800cbf9c2c.
- [Fresh targeted report](../../reviews/general-dsh-harness-evaluation/targeted-follow-up-01.md).
- Reviewer: fresh impl-reviewer completed; scope explicitly limited to round-2 F1–F4.
- Verdict: PASS for those four corrections only; all addressed, no residual
  correction-specific findings. All eight targeted manifest hashes identify exact
  newline-terminated bytes; runtime/skill/source identities matched frozen blobs.
- This is not a third full review or a replacement full-gate verdict. Both full
  reports retain FAIL at their reviewed revisions. The round-2 correction-summary
  exposure remains disclosed. No independence waiver or phase closure is recorded.
- Execution evidence: 30 isolated tests passed; all four temporary reversions were
  detected. Six deterministic walkthroughs passed. One local-model attempt failed
  on an empty final answer; one unchanged recheck passed. Both local attempts met
  cleanup/grace checks and are preserved in the targeted evidence. The fresh
  reviewer inspected these records but did not independently reproduce them.
- Mechanical helper, public validator, diff/syntax and evidence-linkage checks passed.
- Independent verification, the scanner false-positive disposition and required
  latest-head checks remain due. Phase metadata remains changes-requested rather
  than claiming the limited targeted verdict establishes the full gate. Tasks
  remain unticked; Phase 02 remains unstarted.


## 2026-11-14 · approved scanner exception and delivery preparation

The owner directed “Go ahead” after the recommendation to resolve the scanner
false positive, publish the feature branch/draft PR and run fresh verification.
Authorization covers those next actions; no phase closure, review-independence
waiver, production adoption or merge was authorized.

The scanner exception is restricted by rule, exact artifact path and exact complete
digest line. The artifact canary failed before the exception, passed after it,
and detected a temporary overbroad OR mutation. The existing schema canary passed.
The feature-branch history scan now passes with the corrected configuration.
A fresh targeted review of this security-relevant configuration/CI change and the
required local checks precede publication. No repository protection/settings or
scanner rules were disabled.


## 2026-11-14 · targeted scanner-exception review · passed

- Frozen scanner change: 7459b10f316e099f90661b03cec2500aac53c550.
- [Fresh scoped report](../../reviews/general-dsh-harness-evaluation/scanner-exception-review.md).
- Reviewer: fresh impl-reviewer completed; static PASS, no Blocker or Major.
- Nit S1: the canary lacked a same-directory sibling-path negative fixture.
  Reproduced: broadening the path to the whole spike directory left the old canary
  green. Fixed by adding the exact digest at a sibling path; the broadened-path
  mutation now fails and the restored exact exception passes. This strengthens
  the test without broadening the already reviewed exception.
- Full repository tests: 165 passed, 91 integration tests deselected. Isolated
  tests: 30 passed. Locked sync, lint/format, mypy, agent sync, plan validation,
  actionlint, offline links and scanner history checks passed locally.
- Added a standalone as-built verification input containing current runtime
  claims and documented operator prerequisites, without earlier review verdicts.
  Historical reports remain preserved and are excluded from verifier inputs.
- Draft delivery and independent execution verification remain next. Phase tasks
  and the review-independence question remain open.


## 2026-11-14 · independent execution verification · initial fail

- code_sha = docs_sha = aef22144d3e2a48af13cf921774ef6745e971af7 (published).
- [Initial report](../../reviews/general-dsh-harness-evaluation/verification-initial.md),
  [acceptance](../../reviews/general-dsh-harness-evaluation/verification-initial-acceptance.md),
  [as-built assessment](../../reviews/general-dsh-harness-evaluation/verification-initial-as-built.md),
  [demo](../../demos/general-dsh-harness-evaluation-01-initial.md).
- Two fresh verifiers completed sequentially, with no implementation history or
  previous review verdicts. Source and endpoint-redaction checks passed.
- Functional results: all seven first-attempt probes passed, including the local
  model; 165 root tests and 30 isolated tests passed. All 11 hosted checks passed.
- Verdict fail: V1 Nit, as-built wording placed persistence before decoding.
  Code correctly performs cleanup first and persists in finally afterward.
- V2–V5 evidence limits concerned historical assertions, provenance, necessity of
  executable tmpfs and an approximate disk estimate. Current verification/setup
  wording is now confined to recorded metadata and observable behavior. Historical
  records/narrative remain preserved; no required behavior or acceptance was removed.
- Author corrections touch documentation only, including the spike README. A new
  remote frozen revision and fresh reproduction will establish its exact SHA
  linkage without invoking a source-equality exception. Phase tasks remain open;
  the separate implementation-review independence limitation is not waived.


## 2026-11-14 · independent execution verification · passed

- code_sha = docs_sha = 65d03f0fdb56d8939e99d67156ddea398185a21f (published).
- [Verification](../../reviews/general-dsh-harness-evaluation/verification.md),
  [acceptance](../../reviews/general-dsh-harness-evaluation/verification-acceptance.md),
  [as-built](../../reviews/general-dsh-harness-evaluation/verification-as-built.md),
  [demo](../../demos/general-dsh-harness-evaluation-01.md).
- Two new fresh verifiers ran sequentially against current source/setup/as-built
  inputs and new raw observations; no earlier reports/verdicts or implementation
  transcript. Both completed. No source/tests/docs fixes occurred in verification.
- Verdict pass for the isolated Phase 01 scope. All seven first-run probes passed,
  including local spark with skill/two tool-body entries/exact quote. Root 165 and
  isolated 30 tests passed. All 11 frozen-commit hosted checks passed, including ci-ok.
- Current as-built claims are confirmed within their declared scope; empirical
  native build ancestry remains expressly unestablished, not asserted as verified.
  Initial environment restrictions and diagnostic errors are retained separately.
- Seven exact containers/scratch paths absent; no owned gateways; tracked source
  clean; endpoint/credential redaction checks passed. New manifests/results are
  in docs/spikes/dsh-phase01-verification-evidence.json.
- Initial failed verification remains frozen. The owner has not yet accepted the
  earlier implementation-review independence limitation. Phase metadata/tasks
  remain open; no closure or waiver is inferred from this verification PASS.


## 2026-11-14 · verifier-report scanner prose false positive

Publishing the independent evidence exposed a second generic-api-key false
positive: ordinary result-summary prose in the immutable acceptance report.
The first evidence push completed before the final scanner result was inspected;
no endpoint or credential was exposed. The report remains unchanged.

A separate AND-scoped exception now requires the exact report path and complete
known summary statement. Canaries cover the statement at first/later lines,
changed text, appended/new keys, sibling and unrelated paths. OR and path-widening
mutations were detected. The exact feature-history scan passes locally. This
changes only scanner configuration/canaries and the corresponding CI step name;
DSH runtime/code/configuration/dependency/skill inputs remain identical to the
independently verified revision. Fresh scoped verification precedes publication
of this correction. Phase closure and the earlier independence limitation remain
unapproved.


## 2026-11-14 · affected scanner/CI verification · passed

- Frozen affected-scope code: 295d5d30566a8007319c55face1756ecea94fd38.
- [Fresh executed follow-up](../../reviews/general-dsh-harness-evaluation/scanner-prose-follow-up.md).
- A fresh verifier independently reviewed the guard and executed current/schema
  canaries, whitespace/path/rule boundary fixtures, missing-exception/OR/unanchored/
  disabled-default mutations, complete frozen ancestry and feature-range scans,
  actionlint, Ruff and targeted mypy. All passed; no unresolved findings.
- Default rules remain active. Both known exceptions require exact paths and full
  known lines. Added credentials, changed lines and sibling/unrelated paths are
  detected. Original reports and all previous verdicts remain unchanged.
- Runtime equality to independently verified 65d03f0 was established by exact diff
  and comprehensive path inventory. Only three scanner/CI files differ outside
  docs; their affected review/tests/verification are recorded separately here.
  Earlier verification SHAs are not relabeled or retroactively changed.
- Independent execution verification and scanner clearance are complete for their
  stated scopes. Owner acceptance of the implementation-review limitation and
  latest-head CI remain prerequisites for phase closure. No waiver is inferred.


## 2026-11-14 · scoped canary fixture stabilization

One subsequent local canary run reported an expected-location mismatch with its
random generated token; the temporary fixture had already been cleaned and the
exact missing location was not retained. Fifteen diagnostic reruns passed, so no
specific root cause is claimed. The public fake-key vector is now derived
deterministically, and failures emit only missing/extra file-line-rule locations.
Twenty repeated runs pass. Ruff/format and targeted mypy pass. Exception regexes,
paths, rules, CI invocation, and all runtime inputs are unchanged. This fixture
change receives a final scoped check; no earlier result is relabeled.


## 2026-11-14 · final scanner fixture check · passed

- Frozen helper change: 90fd53058e3045a27a7ebe4cd05222a66acf03a8.
- [Fresh check](../../reviews/general-dsh-harness-evaluation/scanner-fixture-final.md).
- A new verifier confirmed the deterministic public vector and safe location-only
  diagnostics cannot broaden detection exceptions. Ten independent canary runs,
  missing-rule/OR negative mutations, Ruff, targeted mypy and redacted feature-history
  scan passed. No unresolved scoped issue. Exception policy/CI invocation unchanged.
- Full runtime verification remains pinned to 65d03f0; its input files are unchanged.
  The affected scanner guard and final fixture changes have their own review,
  execution and immutable-revision evidence. Earlier reports are not relabeled.
- Owner review-waiver decision and latest final-head CI remain the closure gates.

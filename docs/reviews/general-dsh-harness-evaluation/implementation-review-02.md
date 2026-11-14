---
review: implementation
phase: general-dsh-harness-evaluation/01
change: docs/plans/2026-11-14-dsh-harness-evaluation
rfc: n/a
adrs: []
commit_sha: 35ac465bf2618f1e6031bc325be885800cbf9c2c
code_sha: 35ac465bf2618f1e6031bc325be885800cbf9c2c
docs_sha: n/a
diff_base: 952d01e097332905ba56d6c26e1e342431f8f394
session: fresh
date: 2026-11-14
round: 2
verdict: FAIL
reviewers:
  - { lens: Contract, status: completed }
  - { lens: Failure and retry, status: completed }
  - { lens: Scope and composition, status: completed }
---

# Implementation review: DSH harness evaluation, Phase 01 — final round

## Inputs

Repository: `/tmp/praxismesh-dsh-implementation-review-r2`.

Used the installed `/home/geo/.agents/skills/impl-review/SKILL.md`. All three native `impl-reviewer` agents were launched concurrently with `fork_turns: none`, using the skill’s respective lens briefs and these inputs:

- Contract: `/tmp/praxismesh-dsh-implementation-review-r2/docs/plans/2026-11-14-dsh-harness-evaluation/plan.md`
- Phase: `/tmp/praxismesh-dsh-implementation-review-r2/docs/plans/2026-11-14-dsh-harness-evaluation/phases/01-controlled-runtime.md`
- Context: `/tmp/praxismesh-dsh-implementation-review-r2/docs/plans/2026-11-14-dsh-harness-evaluation/notes.md`
- Guidance under the repository root: `AGENTS.md`, `CLAUDE.md`, `PROJECT_PLAN.md`, `docs/reviews/README.md`, and `docs/development/planning.md`
- Delivered requirements: **R1, R2, R3, R10**
- Frozen diff:

```bash
git -C /tmp/praxismesh-dsh-implementation-review-r2 diff 952d01e097332905ba56d6c26e1e342431f8f394..35ac465bf2618f1e6031bc325be885800cbf9c2c
```

There are no nested committed `AGENTS.md` or `CLAUDE.md` files. Briefs also specified committed inputs only, read-only operation, prohibited candidate execution, and assessment before reading prior reviews or correction resolutions. No coordinator or implementer transcript, suspicions, or another reviewer’s verdict was supplied.

The coordinator read prior reports, `reviews.md`, and correction resolutions only after all three initial assessments had been returned.

### Independence and assessment limitations

This session was fresh and had no implementation history. Automatically visible instructions included system/developer instructions, native agent-role instructions, tool and sandbox restrictions, the skills catalog, and user-supplied repository guidance. Agents shared one read-only checkout; separate contexts did not provide separate filesystems.

**The requested assessment-before-corrections separation was not fully achieved.** Contract and Scope reviewers independently disclosed that reading `docs/spikes/dsh-harness.md` displayed its appended “Approved review corrections” section before their complete assessments were returned.

- **Contract:** reported no findings before exposure; its two Nits were identified afterward.
- **Scope:** inspected code/tests before exposure, but its complete findings were returned afterward.
- **Failure and retry:** explicitly confirmed no exposure to prior reports, `reviews.md`, the spike-report correction summary, or correction-resolution evidence before its assessment. It read `test_corrections.py` as committed test source.

Neither exposed reviewer read the prior implementation-review report or `reviews.md`. No reviewer received another reviewer’s findings. Nevertheless, Contract and Scope cannot be represented as wholly independent of earlier correction information.

No fixes, checkout writes, commits, GitHub writes, candidate binaries, Docker commands, or live model requests were performed. Runtime tests and demonstrations were not reproduced.

## Mechanical checks

| Check | Observed |
|---|---|
| Frozen revision | HEAD equals the specified `code_sha`. |
| Clean inputs | `git status --porcelain` was empty before and after review. |
| Frozen diff whitespace | `git diff --check <base>..<code_sha>` passed. |
| Shared helper through `uv run --offline --no-project --no-cache` | Could not run: uv attempted temporary-directory creation on the read-only filesystem. |
| Same helper through `python3 -B` | **Passed: 0 errors, 0 warnings.** |
| Public plan validator through `python3 -B` | **Passed: 3 plans, 0 errors.** |
| Changed committed Python, JSON, TOML and lockfile syntax | Parsing passed without importing candidate code. |
| Corrected evidence linkage | All seven embedded manifests matched their canonical serialized digests and result references. All recorded Python-source, artifact-manifest, lockfile and composition hashes matched the frozen revision. |

Unticked Phase 01 tasks:

- **1.1:** Separate environment, matching artifacts, platform, composition and prerequisites.
- **1.2:** Authority probes and real local skill/MCP task through a bounded bridge.
- **1.3:** Service/auxiliary inventory, evidence and teardown.

These remain unticked appropriately pending completion gates. Delivered requirements without scenarios: **none**. Undefined delivered requirement IDs: **none**.

The corrected walkthrough identifies source commit `75a3746ba8159059070c1565f086fdf8db154b53`. Its recorded source and configuration hashes match this review’s frozen inputs, but its execution and mutation-test claims remain implementer evidence, not independently reproduced results.

Dependency installation, lint/type suites, runtime tests and demonstrations were skipped to preserve the requested read-only assessment. No claim is made that those checks passed in this session.

## Findings

Duplicates were merged. Locations refer to the frozen `code_sha`. Proposed tests below were not executed.

| ID | Severity | Reviewer | Location | Requirement / decision | Scenario / evidence | Test and proposed action | Resolution |
|---|---|---|---|---|---|---|---|
| F1 | **Major** | Failure and retry | `spikes/dsh-harness/run_probe.py:374`; cleanup follows at `:384` | Task **1.3**; notes’ stop/cleanup policy | A timed-out candidate leaves `fixture-calls.jsonl` with an incomplete final JSON record. Parsing raises inside `finally` before container removal/observation and result persistence. The outer `finally` preserves scratch, but the running container receives no cleanup command. `mcp_fixture.py:47` writes the log directly. | **Fix:** Inject a timeout and log ending in `{"tool":`; require container cleanup and observation to execute and a failed result to persist. Put mandatory cleanup in an unconditional protected path; record evidence-decoding errors separately. | open |
| F2 | **Major** | Scope and composition; Contract identified the skill subset as Nit | `spikes/dsh-harness/run_probe.py:186`, `:232`, `:238` | **R1**, **D1/D2**, task **1.1** | The manifest hashes Python/configuration before staging, but Docker mounts the original files directly. A host edit during dependency copying can change executed code/composition while evidence retains earlier hashes. The granted skill is also mounted directly without a content digest or dirty-input rejection. Only dependencies receive a verified private snapshot. | **Fix:** Mutate code/composition during staging and modify the granted skill independently; require rejection or execution from a snapshot whose complete input hashes match the manifest. Include the skill tree in the recorded identity. | open |
| F3 | Nit | Scope and composition | `spikes/dsh-harness/run_probe.py:173`, `:369`, `:384`; `cleanup_container():57` | Notes’ stop/cleanup policy; task **1.2** | The manifest declares five seconds after the stop trigger, but gateway shutdown precedes container cleanup, whose timeout and observation timer start afresh. Two seconds of gateway shutdown plus four seconds of removal can exceed the declared grace while cleanup reports success. Full R5 validation is explicitly deferred, so this remains nonblocking here. | **Fix:** Use one fake monotonic clock across gateway and container cleanup; require the combined six-second case to violate the declared grace. Measure against the original trigger, or clarify the Phase 01 manifest semantics through the contract process. | open |
| F4 | Nit | Contract | `spikes/dsh-harness/run_probe.py:320` | **R1**, manifest evidence linkage | The controller hashes `encoded` but saves `encoded + b"\n"`. Hashing the saved manifest file therefore differs from `manifest_sha256`. Canonical embedded-object hashes remain reconstructible and passed the mechanical check. | **Fix:** Assert the result digest equals SHA-256 of the persisted manifest bytes; hash exactly what is saved, or explicitly document and test canonical-object hashing. | open |

Contract coverage otherwise identified enforcement and tests or documented walkthroughs for the delivered scenarios: artifact verification, local skill/MCP execution, authority restrictions, forbidden-operation rejection, disabled competing orchestration, and auxiliary inventory. Recovery, full cancellation/accounting, TaskResult mapping and benchmarking remain Phase 02 work; their absence was not treated as a Phase 01 failure.

## Recurrence disposition

Prior implementation findings were assessed only after the initial reviewer assessments existed. The correction narrative and mutation-test outcomes were treated as claims and checked against committed code/tests.

| Round-1 finding | Disposition at frozen revision |
|---|---|
| F1 — incomplete dependency verification | Original defect addressed: complete environment hashing, verified private dependency copy, separate bytecode cache, and changed-dependency regression exist. **Not reopened.** Current F2 concerns remaining code/configuration/skill inputs beyond that dependency correction. |
| F2 — Docker errors falsely establish absence | Addressed: absence requires a successful daemon listing; unknown state fails cleanup and the run. Regression exists. **Not reopened.** Current F1 is a different path that bypasses cleanup entirely. |
| F3 — incomplete authority oracle | Addressed: exact tool/model catalogs are enforced, configuration poison is injected, and an introduced operation is attempted. **Not reopened.** |
| F4 — auxiliary admission inventory gap | Addressed for Phase 01: producers are disabled or inventoried with bounds/accounting observation points; regression checks the configuration. Full reconciliation remains Phase 02. **Not reopened.** |
| F5 — missing observation window | Addressed: cleanup repeatedly observes through its declared ten-second window; late-work regression exists. **Not reopened.** Current F3 concerns the timer’s relationship to the original stop trigger. |
| F6 — untracked host gateway work | Addressed: ownership inventory, socket/connection tracking and handler shutdown regression exist. **Not reopened.** |
| F7 — unidentified scratch directories | Addressed: UUID-specific scratch paths are persisted and tested for nonoverlap. **Not reopened.** |

No original finding is reopened as the same defect. The new findings expose additional paths or remaining input coverage. Static correction assessment does not independently establish the claimed runtime or mutation-test outcomes.

## Verdict

**FAIL.** All three reviewers completed, but **F1 and F2 remain open Majors**. Under `docs/reviews/README.md` rule 5, each Major requires a fix or evidence-backed contest before PASS.

Additionally, accidental correction-summary exposure limits Contract and Scope independence; this report does not claim the requested fresh-assessment separation was fully satisfied.

## Open items

- Resolve F1–F2 and disposition F3–F4. No fixes were made here.
- Independent verification and the required walkthrough remain due before task completion.
- The previously recorded gitleaks artifact-hash match remains an unresolved check in committed evidence; it was not rerun here.
- Phase 02 remains unstarted.
- This is the second and final full implementation-review round. The invoking coordinator saves this report and review metadata; this session changed neither.

Helper output:

```text
Next: /impl-plan apply docs/plans/2026-11-14-dsh-harness-evaluation/01
Reason: 3 of 3 task(s) left
```

That lifecycle suggestion reflects unticked tasks, not authorization to close the phase or bypass the findings.
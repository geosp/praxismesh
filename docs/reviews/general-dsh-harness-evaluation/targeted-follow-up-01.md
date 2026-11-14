---
review: implementation
mode: targeted-follow-up
phase: general-dsh-harness-evaluation/01
change: docs/plans/2026-11-14-dsh-harness-evaluation
commit_sha: 33a532b2fd039e3d715dae6e64290190e84ecd2c
code_sha: 33a532b2fd039e3d715dae6e64290190e84ecd2c
diff_base: 35ac465bf2618f1e6031bc325be885800cbf9c2c
session: fresh
date: 2026-11-14
verdict: PASS
verdict_scope: Four corrections F1–F4 only
reviewers:
  - { lens: Targeted correction assessment, status: completed }
---

# Targeted follow-up: DSH evaluation Phase 01 corrections

**PASS for F1–F4 only.** All four corrections are addressed; no residual correction-specific findings were identified.

This is an explicitly targeted follow-up under `docs/reviews/README.md` rule 6. It is not a third full implementation-review round, independent verification, adoption approval, or phase closure.

## Inputs and independence

Repository: `/tmp/praxismesh-dsh-targeted-review`.

One fresh native `impl-reviewer` was launched with `fork_turns: none`, the pinned paths and references, and the four-finding scope. No coordinator or implementer transcript was supplied. Earlier findings and correction information were expressly permitted inputs for this targeted assessment.

Reviewed committed inputs included:

- `AGENTS.md`, `CLAUDE.md`, `PROJECT_PLAN.md`, `docs/reviews/README.md`, `docs/development/planning.md`, and the review-report template.
- `docs/plans/2026-11-14-dsh-harness-evaluation/{plan.md,notes.md,phases/01-controlled-runtime.md}`.
- F1–F4 in `docs/reviews/general-dsh-harness-evaluation/implementation-review-02.md`, their approved correction records, regression tests, and frozen spike evidence.
- Only the correction diff `35ac465bf2618f1e6031bc325be885800cbf9c2c..33a532b2fd039e3d715dae6e64290190e84ecd2c`.

No nested committed guidance files exist. Phase 01 delivers **R1, R2, R3, R10**. Phase 02 remains unstarted.

## Per-finding assessment

Locations refer to the pinned revision. Regression tests were inspected, not executed.

| Finding | Disposition | Code and test evidence |
|---|---|---|
| **F1 — malformed evidence bypasses mandatory cleanup and result persistence** | **Addressed** | `spikes/dsh-harness/run_probe.py:186` protects gateway shutdown; `:194` unconditionally enters container cleanup. Evidence decoding follows at `:205`; decoding errors mark failure at `:217`; result persistence occurs in `finally` at `:219`. `spikes/dsh-harness/test_final_corrections.py:22` covers truncated JSON and invalid UTF-8, asserting removal, observation, failed persisted output, and decoding-error type. |
| **F2 — mutable code/configuration and unidentified skill inputs** | **Addressed** | `run_probe.py:27` hashes runtime inputs and the complete skill-file tree, rejecting symlinks. `:51` creates private copies and verifies their identities against the manifest. Docker mounts the copies at `:358` and `:365`; the gateway loads its staged module at `:74` and `:468`. Dependency staging is independently verified at `:459`. `test_final_corrections.py:73` covers changed code, composition, and skill inputs; `:82` checks snapshot contents and mounts after subsequent edits to originals. |
| **F3 — cleanup clocks restart after gateway shutdown** | **Addressed** | `run_probe.py:492` preserves the original timeout trigger; `:497` supplies the return-time trigger otherwise. `finish_run` forwards it after gateway shutdown at `:198`. Container cleanup calculates remaining grace at `:122`, evaluates grace against the original trigger at `:158`, and observes through the original ten-second boundary at `:163`. `test_final_corrections.py:97` requires failure when two seconds of gateway shutdown plus four seconds of removal exceed the five-second grace. Existing late-work coverage remains at `test_corrections.py:45`. |
| **F4 — digest excludes the persisted manifest newline** | **Addressed** | `run_probe.py:68` constructs, writes, and hashes the same newline-terminated bytes; `:446` uses that digest. `test_final_corrections.py:118` compares the returned digest directly with SHA-256 of the persisted file and asserts its newline. The policy is documented at `run_probe.py:287`. |

## Residual correction-specific findings

None identified. No assessment is made of implementation paths beyond these four corrections.

## Mechanical validation

The fresh reviewer independently performed these read-only checks:

| Check | Result |
|---|---|
| `git rev-parse HEAD` | Matches the requested `code_sha`. |
| `git status --porcelain` before and after validation | Empty. |
| `git diff --check 35ac465bf2618f1e6031bc325be885800cbf9c2c..33a532b2fd039e3d715dae6e64290190e84ecd2c` | Passed. |
| `python3 -B /home/geo/.agents/skills/impl-plan/plan-tool.py check docs/plans/2026-11-14-dsh-harness-evaluation` | **0 errors, 0 warnings.** |
| `python3 -B .github/scripts/check_plans.py` | **3 plans validated, 0 errors.** |
| Standard-library parsing of pinned blobs without candidate imports | Both changed Python files parsed as ASTs; added JSON parsed successfully. |
| Embedded manifest/result linkage | All **22 records** validated: 14 historical records under their legacy canonical-object policy and eight targeted records under the newline-inclusive policy. |
| Targeted input identities | All recorded runtime, skill, Python-source, artifact-manifest, lockfile, and composition hashes matched pinned repository blobs. |

The targeted evidence names source commit `8772f7d95f73f5325d5c79a79f56311c08650780`. Its recorded content hashes match the reviewed snapshot; that earlier commit was not separately inspected.

Reconstructing embedded manifest digests does not independently establish that original files were persisted or that recorded executions occurred.

## Historical verdicts and execution evidence

Both full implementation-review verdicts remain **FAIL**:

| Report | Preserved verdict |
|---|---|
| `implementation-review-01.md` | **FAIL**, including two open Majors at its reviewed revision. |
| `implementation-review-02.md` | **FAIL**, including two additional open Majors at its reviewed revision. |

Round 2 disclosed correction-summary exposure affecting the Contract and Scope reviewers before their complete assessments were returned. Failure and retry reported no such exposure. This targeted follow-up preserves that limitation and does not retroactively restore independence.

The committed evidence retains failed and passing live-model attempts:

| Evidence series | Failed attempt | Passing attempt |
|---|---|---|
| Original Phase 01 walkthrough | Final answer failed strict JSON parsing after skill/tool execution. | Recheck passed after instructions required raw JSON. |
| Targeted correction walkthrough | Empty final answer after skill/tool use. | Unchanged recheck passed. |

The targeted failed and passing attempts both recorded successful cleanup and grace checks, with observation durations of **10.012** and **10.013 seconds**, respectively. Six deterministic targeted probes also recorded success.

These are inspected implementer records, not independently reproduced outcomes. Passing attempts do not erase the failures. Claims of eight initial regression failures, four detected temporary reversions, 30 passing isolated tests, and broader successful checks were likewise inspected only.

## Limitations and remaining gates

**PASS applies only to corrections F1–F4.** The reviewer completed and found no remaining correction-specific Blocker or Major.

- No SDK/candidate code, runtime tests, mutation tests, Docker, or models were executed.
- The outstanding artifact-hash gitleaks match remains unresolved. Its characterization as a false positive is a recorded claim, not this review’s determination; scanning was not rerun.
- Independent verification and the required walkthrough remain due. All three Phase 01 tasks remain unchecked.
- This report does not replace the full gate, adopt DSH, close Phase 01, start Phase 02, or authorize merging.

This document is returned for saving. No checkout files, commits, settings, or GitHub records were changed.
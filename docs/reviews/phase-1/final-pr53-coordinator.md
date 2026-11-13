# PR #53 final gate coordinator handoff

Issue: #44. Phase 1 remains open. No merge or phase closure was performed.

## Frozen assessment

- Previous reviewed revision: `60fe15d0fd755c391cbe79c0084f7def7b38c7db`.
- Reviewed and tested code: `9472d20d3b5e5d7cee1542ffedf9c25335defadd`.
- Assessed documentation: `f2789d505755397bfdd40a88106a04a0b192f3cf`.
- [Targeted implementation review](final-targeted-pr53.md): PASS for T1/T2 and
  correction regressions. Historical FAIL reports remain preserved.
- [Verification](final-verification-pr53.md) and
  [demo reproduction](../../demos/phase-1-final-pr53.md) record this run's
  independent execution; unavailable real-model prerequisites are not passed.
- Raw command evidence is under `final-pr53-evidence/` next to this file.

## PR status observed in this assessment

PR #53 was OPEN with head
`f2789d505755397bfdd40a88106a04a0b192f3cf` on 2026-11-13. All 11 check-runs
passed, including required `ci-ok` ([run](https://github.com/geosp/praxismesh/actions/runs/43442152986)).
`gh pr checks 53 --repo geosp/praxismesh --required` returned `ci-ok pass`.
This docs-only head is source-identical to the tested code. No check-runs were
attached directly to `code_sha` (API total_count 0); that informational fact is
not a substitute for the disposable-checkout execution evidence.
Latest-head status must be refreshed by the coordinator immediately before
approval/merge; the documentation PR's own head and checks are separate.

## Required coordinator sequence

1. Resolve every open verification failure or unavailable prerequisite in the
   new verification report. Supply the documented real local-model endpoint
   through the disposable checkout's own configuration; never copy another
   checkout's secrets. Re-run the real-model sample, benchmark, worker-container
   loss walkthrough, output/identity checks and trace demonstration. Benchmark
   must lose at most one task from the 10/10 baseline. Missing dependencies must
   continue to be recorded blocked. Return implementation findings to the
   implementer; reviewers do not fix source.
2. Obtain passing applicable implementation review and verification/demo
   evidence for the same final `code_sha` and accepted `docs_sha`, preserving
   historical verdicts. A source or test correction requires affected fresh
   review, tests and verification again. Documentation corrections need affected
   document verification and latest-head CI. A new assessment must use distinct
   evidence paths rather than overwrite this run.
3. Once all required gate evidence passes, integrate the documentation evidence
   through its own PR. Check the evidence-bearing delivery PR's latest head,
   including any documentation-only commits. For PR #53:

   ```bash
   git fetch origin refs/pull/53/head:refs/remotes/origin/pr-53
   head_sha=$(gh pr view 53 --repo geosp/praxismesh --json headRefOid --jq .headRefOid)
   test "$(git rev-parse origin/pr-53)" = "$head_sha"
   gh pr checks 53 --repo geosp/praxismesh --required
   gh api "repos/geosp/praxismesh/commits/$head_sha/check-runs" --jq '.check_runs[] | [.name,.status,.conclusion] | @tsv'
   git diff --exit-code 9472d20d3b5e5d7cee1542ffedf9c25335defadd "$head_sha" -- . ':!docs'
   ```

   Replace the code SHA above if a new source snapshot was independently
   reviewed and verified. Confirm `ci-ok` is successful on exactly `head_sha`.
   Recheck immediately before approval if the branch advances. Perform equivalent
   latest-head checks on the separate documentation PR; do not compare that
   main-based evidence-only branch to code_sha as if it contained the correction.
4. Record the final `head_sha` and evidence links in the PR or external approval
   record, never in a tracked file that would change that SHA. The coordinating
   session may then check only tasks and demo items actually supported by passing
   tests, acceptance, demo and as-built evidence. Prepare the closure documentation
   and OpenSpec finalization through the normal PR workflow, without silently
   closing deferred Nits.
5. Only the human owner merges. After every prerequisite above holds, the exact
   owner command for PR #53 is:

   ```bash
   gh pr merge 53 --repo geosp/praxismesh --squash --match-head-commit "$head_sha"
   ```

   If a different delivery PR carries the final implementation, use its number
   and separately checked head instead. After implementation/evidence and closure
   documentation have merged, and the phase is actually complete, the coordinator
   records closure; the owner may close the still-open issue explicitly:

   ```bash
   gh issue close 44 --repo geosp/praxismesh --reason completed
   ```

These commands are a future handoff, not authorization to bypass an outstanding
gate. This reviewing/verifying session did not tick Phase 1 boxes, archive the
OpenSpec change, alter repository protection, merge, or close issue #44.

# PR #53 coordinator handoff after real-model verification

Phase 1 remains open. This is a new handoff; previous reports and instructions
remain preserved as historical evidence.

- Applicable implementation review: [PASS](final-targeted-pr53.md).
- Combined independent verification: [pass](model-verification-pr53.md).
- Real-model [demo](../../demos/phase-1-model-pr53.md) and
  [10/10 benchmark](model-pr53-evidence/real-model-benchmark-2026-11-13.md).
- Code: `9472d20d3b5e5d7cee1542ffedf9c25335defadd`.
- Assessed docs: `f2789d505755397bfdd40a88106a04a0b192f3cf`.
- Earlier blocked reports are retained; the endpoint dependency is resolved by
  new execution. Unrelated nonblocking/historical Nits stay deferred.

## Remaining coordinator steps

1. Confirm the applicable current review, verification and demo evidence above
   identifies the same code/docs revisions. Preserve historical FAIL/BLOCKED
   reports as history; do not use their old revisions as the current gate target.
   No implementation blocker remains from this bounded assessment.
2. Check latest PR heads and required CI after the new evidence commit. Do not
   assume the checks on an earlier evidence head still apply:

   ```bash
   git fetch origin refs/pull/53/head:refs/remotes/origin/pr-53
   head_sha=$(gh pr view 53 --repo geosp/praxismesh --json headRefOid --jq .headRefOid)
   evidence_head=$(gh pr view 54 --repo geosp/praxismesh --json headRefOid --jq .headRefOid)
   test "$(git rev-parse origin/pr-53)" = "$head_sha"
   gh pr checks 53 --repo geosp/praxismesh --required
   gh pr checks 54 --repo geosp/praxismesh --required
   git diff --exit-code 9472d20d3b5e5d7cee1542ffedf9c25335defadd "$head_sha" -- . ':!docs'
   git fetch origin main
   git diff --exit-code origin/main "$evidence_head" -- . ':!docs'
   ```

   The final command checks the main-based evidence-only PR before the source
   correction merges. After PR #53 merges, main legitimately contains those
   source corrections while the older evidence branch may not; assess the
   documentation PR's own merge diff (`git diff origin/main...<evidence_head>`)
   for docs-only scope instead. The implementation source comparison always
   remains against the reviewed code SHA. Source/test changes require affected
   fresh review/tests/verification again; docs-only changes require affected
   doc checks and latest-head CI.
3. Record both exact heads and evidence links in the external PR/coordinator
   approval record, not a tracked file that would change the head. Confirm
   `ci-ok` succeeded on both exact heads. Complete coordinator approval before
   authorizing any owner merge. PR #54 remains a draft until coordinator review.
4. Only the human owner merges, after approval and successful latest-head checks:

   ```bash
   gh pr ready 54 --repo geosp/praxismesh
   gh pr merge 53 --repo geosp/praxismesh --squash --match-head-commit "$head_sha"
   gh pr merge 54 --repo geosp/praxismesh --squash --match-head-commit "$evidence_head"
   ```

   Re-read heads if either branch advances; never bypass protection. The normal
   checks still apply if the evidence branch needs updating after main moves.
5. The coordinating session then prepares the Phase 1 closure documentation and
   OpenSpec finalization through their normal PR workflow. Tick only tasks/demo
   items supported by the passing acceptance, demo and as-built evidence. This
   report does not perform closure. After the source, evidence and closure docs
   have merged and Phase 1 is actually complete, the owner may explicitly close
   issue #44 if still open:

   ```bash
   gh issue close 44 --repo geosp/praxismesh --reason completed
   ```

The reviewing/verifying session did not merge, mark ready, close the issue,
archive the OpenSpec change, change settings or mark Phase 1 closed.

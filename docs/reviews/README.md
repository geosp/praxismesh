# Reviews and the phase-gate protocol

Independent reviews are run with the `review-design` and `review-implementation` skills, and independent verification with the `verify-phase` skill (`.agents/skills/`). All three work in two modes:

- **Informal:** a stress-test at any time. Findings are reported in chat. The session may apply approved fixes and re-check. Nothing is saved.
- **Gate:** the review approves a phase RFC (design review) or closes a phase implementation (implementation review). Gate mode follows every rule below, and its report is the evidence the phase gate cites (plan §0.3, §4.17, §7.0, §8).

## Gate rules

1. **Fresh session.** A gate review runs in a new session that did not write, implement or discuss the work. If the session has that history, stop and say so. The report records `session: fresh`.
2. **Pinned revision.** Review a committed revision only.
   - Record `git rev-parse HEAD` as `commit_sha` (for an implementation review this is the `code_sha`).
   - The reviewed paths must have no uncommitted changes: `git status --porcelain -- <paths>` is empty.
   - Implementation review diffs `<base>..<commit_sha>`, not the working tree.
3. **Inputs only.** Reviewers receive the approved requirements, the relevant RFC and ADRs, the allowed artifacts and the pinned revision. They never receive the author's or implementer's reasoning, transcript, or another reviewer's verdict.
4. **Saved report.** Write it from [../templates/review-report.md](../templates/review-report.md) to:
   - `docs/reviews/phase-N/design-review.md`
   - `docs/reviews/phase-N/implementation-review.md`
   - `docs/reviews/phase-N/verification.md`, together with the demo evidence in `docs/demos/phase-N.md`
   - for work not tied to a phase, `docs/reviews/general-<topic>/...`
5. **Verdict.**
   - **FAIL** if any Blocker is open or any reviewer did not run.
   - Every Major must be fixed or contested with evidence before a PASS.
   - Nits do not block.
   - Verification uses `pass`, `fail` or `blocked` (see the `verify-phase` skill). Blocked is never counted as passed (§8).
6. **No fixing in the reviewing session.** Findings go back to the author or implementer. A re-check runs in another new session. That session gets the correction list only after it has recorded its own fresh assessment, or it is explicitly labeled a targeted follow-up (§0.3).
7. **Light tier (Phases 0-2).** One fresh session runs the implementation review and then verification against the same `code_sha`. Independence between those two is knowingly waived; independence from the implementer is not (§7.0). From Phase 3A on, they run in separate sessions.

A review verdict alone never authorizes a merge. Required CI checks on the latest head still apply.

## Coordinator approval gate

After design review, implementation review, verification and the demo evidence exist, the coordinating session (not a reviewer or the verifier) closes the phase (phase file, "Coordinator approval gate"; §4.17):

1. Every evidence file names the same `code_sha` (and verification names `docs_sha`), and each verdict passed.
2. Let `head_sha` be the PR head after the evidence commits. Required status checks pass on that **latest** head:
   `gh pr checks <pr>` or `gh api repos/{owner}/{repo}/commits/<head_sha>/check-runs`.
3. The source is unchanged from the reviewed snapshot: `git diff --stat <code_sha> <head_sha> -- . ':!docs'` is empty. Source changes require the affected code review, tests and verification again; docs-only changes need only the affected doc checks and latest-head CI.
4. Record `head_sha` in the PR or approval record (for example a PR comment), not inside a tracked file that would change it.
5. Only then tick the phase's tasks and demo items; otherwise list the precise blockers.

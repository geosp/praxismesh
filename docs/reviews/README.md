# Reviews and the phase-gate protocol

Independent reviews are run with the `review-design` and `review-implementation` skills (`.agents/skills/`). Both work in two modes:

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
   - for work not tied to a phase, `docs/reviews/general-<topic>/...`
5. **Verdict.**
   - **FAIL** if any Blocker is open or any reviewer did not run.
   - Every Major must be fixed or contested with evidence before a PASS.
   - Nits do not block.
6. **No fixing in the reviewing session.** Findings go back to the author or implementer. A re-check runs in another new session. That session gets the correction list only after it has recorded its own fresh assessment, or it is explicitly labeled a targeted follow-up (§0.3).
7. **Light tier (Phases 0-2).** One fresh session runs the implementation review and then verification against the same `code_sha`. Independence between those two is knowingly waived; independence from the implementer is not (§7.0). From Phase 3A on, they run in separate sessions.

A review verdict alone never authorizes a merge. Required CI checks on the latest head still apply.

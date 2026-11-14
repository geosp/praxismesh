# Reviews and the phase-gate protocol

Independent reviews are run with the `design-review` and `impl-review` skills, and independent verification with the `verify-phase` skill (`.agents/skills/`). The shared review skills support informal review; this repository supplies mandatory gate-mode rules below. `verify-phase` remains project-owned.

- **Informal:** a stress-test at any time. Findings are reported in chat and recorded in the shared suite's plan review log. Approved fixes and re-checks are allowed; these logs do not substitute for phase-gate evidence.
- **Gate:** the review approves a phase implementation plan (design review) or closes a phase implementation (implementation review). Gate mode follows every rule below, and its report is the evidence the phase gate cites (plan §0.3, §4.17, §7.0, §8).

Shared skills must use this protocol for phase gates. It takes precedence over their
working-tree diff default, in-session fixes, accepted-finding closure and early task
completion. Gate reviews never fix their own findings. Run tests and verification
before ticking phase tasks; invoke review/verification explicitly while boxes remain
open, then resume impl-plan after the coordinator approves closure. A missing
reviewer or open Blocker prevents PASS; Majors require a fix or evidence-backed contest.

For implementation gates, pass `<base>..<code_sha>` to the reviewers and use only
committed contract/code files. Do not use the shared skill's working-tree diff brief.
Record both the standard evidence report below and the summary in the plan's reviews.md.

## Gate rules

1. **Fresh session.** A gate review runs in a new session that did not write, implement or discuss the work. If the session has that history, stop and say so. The report records `session: fresh`.
2. **Pinned revision.** Review a committed revision only.
   - Record `git rev-parse HEAD` as `commit_sha` (for an implementation review this is the `code_sha`).
   - The reviewed paths must have no uncommitted changes: `git status --porcelain -- <paths>` is empty.
   - Implementation review diffs `<base>..<commit_sha>`, not the working tree.
3. **Inputs only.** Reviewers receive the approved requirements, the relevant implementation plan and ADRs, the allowed artifacts and the pinned revision. They never receive the author's or implementer's reasoning, transcript, or another reviewer's verdict.
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

## Session roles and permissions

Separation between roles comes from **sessions**, not credentials: every session uses the owner's GitHub login (owner decision; see the decision log). Each role runs in its own session with its own context, tools and instructions, and project permission rules stop every session from changing what protects `main`.

| Role | Runs | May | May not |
|---|---|---|---|
| Implementer | A normal session; Skill Central `impl-plan apply` | Edit files, run tests, commit, push a feature branch, open and update its PR | Push to `main`, merge, change repository settings, protection or secrets |
| Design or implementation reviewer | `design-review` / `impl-review`; agents `design-reader`, `design-reviewer`, `impl-reviewer` | Read code and inputs; run read-only commands (`git diff`, `git show`, `grep`, `gh issue view`, `gh pr view`) | Edit files, commit, push, write anything to GitHub, fix what it finds |
| Verifier | `verify-phase`; agent `verifier` | Run tests and the demo in a disposable worktree at the pinned commit | Edit the user's working copy, commit, push, write to GitHub |
| Coordinator | The session that runs a skill and writes its report | Choose inputs, merge findings, write the report, open a docs PR | Change the reviewed code, merge, change protection |
| Owner (a human) | - | Merge PRs, change repository settings, rulesets, secrets and security features | - |

**What enforces it:**

- **All Claude Code sessions and their subagents:** `.claude/settings.json` (committed). It denies pushing to `main`, force-pushes, `gh repo edit/delete/rename/archive`, any `gh api` request that writes (`-X`, `--method`, `-f`, `-F`, `--field`, `--raw-field`, `--input`), `gh secret`/`gh variable` changes, `gh workflow disable` and `gh auth token`, and asks before `gh pr merge`. Deny rules apply in every permission mode and override user-level allow rules. They match the command as written, so they are a guardrail, not a wall: a wrapper such as `bash -c '...'` is not seen through.
- **Reviewer and verifier agents:** the canonical Skill Central reviewer variants and local `.agents/agents/verifier.md` tool lists (Claude Code: no Edit or Write; Codex: permissions inherited from the parent session; role instructions alone do not enforce a separate sandbox) and their instructions.
- **GitHub, for every session:** ruleset `protect-main`. No push reaches `main` without a pull request and a passing `ci-ok`, whatever the session.

Agents therefore never change repository settings: when one is needed, the agent gives the owner the exact command to run.

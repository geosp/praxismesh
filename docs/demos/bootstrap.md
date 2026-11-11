# Bootstrap demo evidence (§0.4)

Evidence for the bootstrap demo checklist in [docs/plan/bootstrap.md](../plan/bootstrap.md) §0.4. **Overall status: all six demo items pass; §0 closed by owner decision on 2026-11-11 without a gate-mode verification run** (see the decision log). Items are marked pass only with observed evidence. The plan's §0.4 boxes are ticked only after the bootstrap's own gate verification (`docs/reviews/README.md`, coordinator approval gate).

## Environment

| Item | Value |
|---|---|
| Repository | `geosp/praxismesh` (public, Apache-2.0), default branch `main` |
| Branch protection | Ruleset `protect-main` (id 27003550): pull request required (0 approvals, conversations resolved, stale approvals dismissed), squash only, required status check `ci-ok` from GitHub Actions with branches up to date, force-push and deletion blocked, no bypass actors |
| CI | `.github/workflows/ci.yml`: lint, types, tests, agents-sync, openspec, secrets, links, licenses, workflows, aggregated by `ci-ok` (rule in `.github/scripts/ci_gate.py`) |
| Tooling | Python 3.11 (CI floor), uv, Node 26 via fnm, OpenSpec 1.17.0 |
| Dates | 2026-11-10 (items 1-5 and the runs for item 3); recorded 2026-11-11 |

## Demo checklist

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Show the GitHub repository, clone URL, default branch, protected change path and a clean clone | Pass | `gh repo view` shows the public repo and `main`. The ruleset above is active. A fresh clone of `https://github.com/geosp/praxismesh.git` was clean at `6cb4ad7` in the `verify-phase` dry run. |
| 2 | Show `openspec --version`, generated configuration and skill files, and a working OpenSpec command | Pass | `openspec --version`: `1.17.0`. `openspec/config.yaml` and six `.agents/skills/openspec-*` skills are present. `openspec validate --all` and `openspec update --dry-run` ("No changes") run in CI on every PR. Setup steps are documented in the [README](../../README.md#getting-started). |
| 3 | In separate fresh sessions, invoke `review-design`, `review-implementation` and `verify-phase` against the same pinned commit | **Pass** | Each skill was invoked in its own fresh GitHub Copilot session, all pinned to `2fcc822`, without sharing conversation history. All three loaded and ran; see below for their verdicts and what they found. |
| 4 | Demonstrate a blocked unauthorized write or branch-protection check; verify no secrets or session transcripts were committed | **Pass** | A direct push to `main` was rejected by the ruleset (see below). Secrets: gitleaks scans every PR (history scan clean, with one reviewed false positive allowlisted in `.gitleaks.toml`), and GitHub push protection is on. Transcripts: none in the tree (`verify-phase` dry run). |
| 5 | Open a PR with a deliberately failing check, show merge is blocked, fix it and show checks pass on the latest head | **Pass** | See below. |
| 6 | Save commands, versions, commit SHA, expected versus observed, and pass/fail here | **Pass** | This file records every item with its commands, commits, expected and observed results, and an explicit result. |

## Item 3: review skills in fresh sessions

Three fresh GitHub Copilot sessions, one per skill, each pinned to commit `2fcc822` (`main` after PR #11), on 2026-11-10. No session saw another's conversation.

| Skill | Mode | Input | Verdict | What it found |
|---|---|---|---|---|
| `review-design` | Informal | The repository at `2fcc822` | Nothing to review | No OpenSpec change, RFC or ADR existed, so there was no design to review. Correct result for the bootstrap. |
| `review-implementation` | Gate | The project CI work `6cb4ad7..d54adde` against issue #6 and the PR #7 description | FAIL | Findings F1-F20, filed as issues #12-#18. All are fixed (PRs #20, #21, #22) or contested with evidence (F3a, F3c, F13, F14, F18; see `docs/plan/decision-log.md`). |
| `verify-phase` | Informal (dry run) | The bootstrap stage, §0.4 | fail | Mostly circular: demo items 3 and 6 were still open at the time of the run. Documentation findings were filed as issue #19 and fixed in PR #23. |

The skills themselves worked, which is what this item demonstrates. The run also exposed two defects in the review process, both now addressed:

- **Reviewer independence broke under Copilot.** Copilot's `impl-reviewer` had only the `read` and `search` tools, so it could not run `git diff` or `gh`. The coordinator then retried with summaries of the diff, which gave the reviewers the coordinator's framing (issue #18). Fixed in PR #22: the Copilot reviewers have the `execute` tool, a reviewer that cannot read its inputs counts as "not run", and coordinators must not summarise the diff to make up for a missing tool. A live Copilot review run with `execute` has not happened yet.
- **The gate report was not saved as a file.** Gate mode requires a report under `docs/reviews/` (`docs/reviews/README.md`, rule 4). None was saved for this run. Its findings are preserved verbatim in issues #12-#18 and summarised in the decision log.

## Item 5: failing check blocks merge

PR [#8](https://github.com/geosp/praxismesh/pull/8), branch `demo/failing-check`, closed without merging.

| Step | Commit | Command or action | Expected | Observed | Result |
|---|---|---|---|---|---|
| Add an unused import to `tests/conftest.py` | `b1685ee` | Push and open PR #8; CI run [42956226787](https://github.com/geosp/praxismesh/actions/runs/42956226787) | `lint` fails, so `ci-ok` fails, so merge is blocked | `lint`: fail (`F401 os imported but unused` and `E402 module level import not at top of file`, because the import follows code); `ci-ok`: fail; all other jobs pass. `gh pr view 8 --json mergeStateStatus,mergeable`: `BLOCKED`, `MERGEABLE` (no conflicts, so the block is the failing required check) | Pass |
| Revert the change | `ac365bc` | Push; CI run [42956377332](https://github.com/geosp/praxismesh/actions/runs/42956377332) | All checks pass; merge allowed | All 8 jobs and `ci-ok` pass. `mergeStateStatus`: `CLEAN` | Pass |
| Clean up | - | `gh pr close 8 --delete-branch` | PR closed unmerged, branch removed | `state: CLOSED`, `mergedAt: null` | Pass |

Not done by an agent: actually clicking merge on the blocked PR. An agent must not attempt merges, and GitHub's `BLOCKED` merge state is the platform's own answer.

## Item 4: direct push to main is rejected

Run by the repository owner on 2026-11-10 from a throwaway local branch holding an empty commit (`81e6b10`). No branch contains that commit, but the rejected push uploaded it, so GitHub still serves it by SHA.

| Step | Command | Expected | Observed | Result |
|---|---|---|---|---|
| Push straight to `main` | `git push origin HEAD:main` | Rejected by ruleset `protect-main` | `remote: error: GH013: Repository rule violations found for refs/heads/main.` with `- Changes must be made through a pull request.` and `- Required status check "ci-ok" is expected.`, then `! [remote rejected] HEAD -> main (push declined due to repository rule violations)` | Pass |
| Confirm `main` unchanged | `git ls-remote origin refs/heads/main` | Still `97e66f3` | `97e66f3...` | Pass |
| Clean up | `git branch -D demo/direct-push` | Local branch removed | Deleted | Pass |

## Reproduce item 5

```bash
git switch -c demo/failing-check main
printf 'import os  # deliberate lint error for the bootstrap demo (unused import)\n' >> tests/conftest.py   # ruff: F401 and E402
git commit -am "Demo: deliberate lint error (do not merge)" && git push -u origin HEAD
gh pr create --title "Demo: failing check (do not merge)" --body "Demo"
gh pr checks <pr> --watch; gh pr view <pr> --json mergeStateStatus   # BLOCKED
git revert --no-edit HEAD && git push
gh pr checks <pr> --watch; gh pr view <pr> --json mergeStateStatus   # CLEAN
gh pr close <pr> --delete-branch
```

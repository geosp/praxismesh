---
name: github-pr
description: >-
  Prepares and opens a GitHub pull request for PraxisMesh: gets the work onto a
  feature branch with clean commits, links the GitHub issue it resolves, fills in
  .github/pull_request_template.md from the diff (plan/requirement trace, tests, demo
  evidence), and optionally pushes and runs `gh pr create`. Use when the user asks
  to open, create, prepare or write up a PR, or to write a PR description.
---

# GitHub pull request

Work is tracked in **GitHub issues** and delivered through **pull requests into the default branch** (`main`). Follow the branch, commit and attribution rules in `AGENTS.md` throughout.

## Step 1 - Check the repository and the base branch

1. Find the base branch: `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`. If that fails (no remote or no `gh` auth), use `main`.
2. Run `git remote -v`. If there is no remote, say so: you can still prepare the description (Steps 2-6), but pushing and creating the PR in Step 7 are unavailable until the repository exists (plan §0.1).

## Step 2 - Get to a clean feature branch

Run `git status` (including untracked files) and check the current branch.

If the current branch is the base branch, the work was done without a feature branch:

1. If there are unstaged or untracked changes, stash them (`git stash --include-untracked`).
2. Update the base branch (`git pull`) if a remote exists.
3. Create a feature branch that follows the branch naming in `AGENTS.md`: `<type>/<issue>-<slug>`. If you don't know the issue number, go to Step 3 first.
4. If changes were stashed, pop them (`git stash pop`).

If there are unstaged or untracked changes (on any branch):

1. Show the user a summary of the changes and ask whether they belong in this PR. If not, stop and let the user sort them out.
2. Stage and commit them with clear, descriptive messages. Prefer several small commits when the changes are logically distinct. **No attribution:** no `Co-Authored-By` trailers, no "Generated with ..." lines, and no agent as author (`AGENTS.md`).

Never commit secrets, `.env` files or `pr-description.md`.

## Step 3 - Identify the GitHub issue

Look for the issue number, in this order:

1. The branch name (`feat/42-blob-store` -> `#42`).
2. The commit messages (`git log <base>..HEAD`).
3. Ask the user.

When you have a number, read the issue: `gh issue view <n> --json number,title,body,labels,milestone,state`. Use its acceptance criteria, phase label and linked plan sections as context.

If there is no issue and the change is more than trivial, offer to create one first. **Confirm before running it**, since this publishes to GitHub. Add no attribution footer to the issue.

```
gh issue create --title "<title>" --body "<problem, acceptance criteria, plan refs>" [--label <label>]
```

## Step 4 - Understand the diff

Run `git log --oneline <base>..HEAD` and `git diff <base>...HEAD`, and read them carefully: what changed and why. Note anything a reviewer must know, such as:

- schema or migration changes;
- new dependencies;
- Workflow code changes, which need replay tests (plan §8);
- gateway API or CRD compatibility;
- secrets handling;
- edits to the plan or decision log.

## Step 5 - Gather what the diff cannot tell you

Check the branch, the commits, the issue and `docs/` before asking. Ask only for what is still missing, typically:

- **Plan and spec trace:** the phase (e.g. Phase 1, 3A), the plan sections, the implementation plan path, and any RFC or ADR.
- **Testing:** which suites ran (unit, replay, integration, e2e) and their results. Do not claim a test passed unless it was run.
- **Demo evidence:** the `docs/demos/phase-N.md` entry, if this PR closes a phase task.
- **Whether the PR fully resolves the issue or is one part of it.**
- **Draft or ready for review?**

Ask all questions in a single message, and do not proceed until the user has answered.

## Step 6 - Write the description

Read `.github/pull_request_template.md`. If `.github/PULL_REQUEST_TEMPLATE/` holds several templates, ask the user which one to use. Fill it in from the diff, the issue and the user's answers, concisely and specifically:

- Remove every `> [!TIP]` callout from the output, but keep `> [!NOTE]` and `> [!WARNING]` blocks.
- Delete template sections that truly do not apply; do not leave placeholder text or HTML comments.
- Tick a checklist item only if it is actually true for this PR.
- No attribution footer (no "Generated with ..." line) (`AGENTS.md`).

Title: imperative, specific, under 72 characters (e.g. `Add SeaweedFS BlobStore adapter`). No issue number in the title; the body links it.

Write the result to `pr-description.md` in the repo root (it is git-ignored) and tell the user it is ready.

## Step 7 - Deliver

Ask: "Want me to push the branch, create the PR, and delete `pr-description.md`?" If yes, and a remote exists, do this in order:

1. `git push -u origin HEAD`.
2. `gh pr create --base <base> --title "<title>" --body-file pr-description.md --assignee @me`. Add `--draft` if the user chose draft. If the issue has a phase label, pass the same label with `--label`.
3. After the PR is created, print its URL and delete `pr-description.md`.

Never merge the PR and never push to the base branch. Merging goes through review and required checks (plan §0.1, §9.2).

## GitHub issue references

**Use closing keywords only for the issue this PR resolves.** On merge into the default branch, GitHub automatically closes every issue referenced as `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves` or `resolved` followed by `#N`, in any capitalization. A passing "fixes #12" about some other issue will close #12.

- Resolves the issue: `Closes #42`.
- Partial work toward an issue: `Part of #42`. It stays open.
- Related work: `Related: #17, PR #20`. Plain `#N` creates a cross-reference only, which is harmless.

Do not write a bare `@name` unless you mean to notify that GitHub user. Put roles and code in backticks.

## Style

- Plain ASCII punctuation only. No em dashes, smart quotes or arrows: use `-`, `"`, `->`.
- Summary: 2-5 sentences.
- No line-length limit in the PR body; GitHub wraps long lines.

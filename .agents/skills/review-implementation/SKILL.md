---
name: review-implementation
description: >-
  Reviews a PraxisMesh change's code and tests against its contract - OpenSpec
  specs and design plus the approved RFC and ADRs - with reviewers that start
  from a fresh context. Use after openspec-apply-change and before running the
  test suites and github-pr, when the engineer asks to check an implementation
  against what it promised, or to run the independent implementation review
  that closes a phase (gate mode).
---

# Implementation review

Design review happens before the code exists, and tests and mutation checks only measure the code that was written. Neither notices a promise the code quietly doesn't keep: a requirement enforced in one place but not another, a retry that reads the wrong state, or a limit that holds per batch but not per run. This skill hands the contract and the diff to reviewers with no conversation history, so they judge the code only against what was promised.

It is the implementation counterpart of `review-design`. Order of work: `openspec-propose` -> `review-design` -> `openspec-apply-change` -> **`review-implementation`** -> tests -> `github-pr` -> at a phase gate, `verify-phase`.

## Step 0: Choose the mode

- **Informal:** a check during development.
  - The diff includes uncommitted changes.
  - The report goes in chat.
  - This session may apply approved fixes, test first (Step 5).
- **Gate:** the review closes a phase implementation. Follow every rule in `docs/reviews/README.md`:
  - **Fresh session:** if this session implemented or discussed the change, stop and say a new session is needed.
  - **Pinned revision:** review the committed `code_sha` only. The diff is `<diff base>..<code_sha>`, and the reviewed paths must have no uncommitted changes.
  - **Saved report:** with a verdict.
  - **No Step 5:** findings go back to the implementer.
  - **Light tier** (Phases 0-2): the same fresh session then runs verification against the same `code_sha`.

If the user doesn't say, ask which mode. Use gate mode only when they confirm.

## Step 1: Select the change

If a change name was provided, use it. Otherwise infer it from the conversation, auto-select it if only one active change exists, or run `openspec list --json` and ask the engineer to pick one.

Announce: "Using change: <name>".

- **Contract:** the change's `specs/**` and `design.md`, **plus the approved RFC and ADRs** linked to it (RFC front matter `openspec_change`, or `grep -rl "<name>" docs/rfcs docs/adr`).
- **Context:** `proposal.md` and `tasks.md`.
- **No OpenSpec change:** the contract is the pull request description and its GitHub issue (`gh pr view`, `gh issue view`). Say so, and give the reviewers those instead.

Skip trivial changes with no promises to check (a typo, a one-line fix) and say that you skipped it.

## Step 2: Build the inputs

- **Contract files:** absolute paths to the change's `proposal.md`, `design.md`, `tasks.md`, every file under `specs/`, and the linked RFC and ADRs.
- **Guidance files:**
  - the root `AGENTS.md`, plus any nested `AGENTS.md` in the top-level packages the diff touches (for example `orchestrator/`, `gateway/`, `harness_activity/`, `common/`);
  - `PROJECT_PLAN.md`, read for §2 (hard constraints) and §8 (testing rules).
- **Repository root:** the absolute path of the checkout being reviewed.
- **Diff base:** `git merge-base origin/main HEAD`; without a remote, `git merge-base main HEAD`.
- **Diff range:**
  - informal mode: `git diff <diff base>`, which includes uncommitted changes;
  - gate mode: `git diff <diff base> <code_sha>`.

Do not add anything else. In particular, don't pass along your own reasoning, the conversation, or what you suspect is wrong. The reviewers are only useful if they don't share your context.

## Step 3: Run the reviewers

Start all three reviewers at once with the `impl-reviewer` agent (defined in `.agents/agents/` and generated for each harness). Give each one its brief from [Reviewer briefs](#reviewer-briefs) with the placeholders filled in, and nothing more. If a harness cannot load the agent, spawn a fresh read-only subagent for each.

| Reviewer | Asks |
| --- | --- |
| Contract | Does the code keep every promise, everywhere it applies? |
| Failure and retry | What does a retry, resume, replay or next run see after a stop at any point? |
| Scope and composition | Does each mechanism hold at its promised scope, and do correct parts stay correct together? |

A reviewer that errors or returns nothing has not reviewed. Retry it once. If it fails again, report it as "not run", never as "no findings".

## Step 4: Report

Report in chat. In gate mode, also write the report from `docs/templates/review-report.md` to `docs/reviews/phase-N/implementation-review.md`, with `commit_sha` (the `code_sha`), the diff base, inputs, reviewer statuses and verdict (`docs/reviews/README.md`, rule 5). Offer to commit it as a documentation-only change.

1. **The findings table.** Merge duplicates across reviewers. Give each finding an id, a severity (Blocker / Major / Nit), the reviewer that raised it, its failure scenario in one line, and one proposed action:
   - **Fix:** the test that fails today, then the code change.
   - **Contest:** why the finding is wrong, with evidence from the code or a decision the engineer made.

   If a reviewer raised something only because the reason exists in the conversation, the reason is missing from the code or the design. Propose writing it into `design.md`, the RFC or a code comment rather than contesting.
2. Each reviewer's status: completed or not run.
3. In gate mode, the verdict: PASS or FAIL, and the rule that decided it.

In informal mode, ask the engineer which fixes to apply. In gate mode, stop here: the implementer fixes, and any re-check runs in a new session.

## Step 5: Fix, test first (informal mode only)

For each approved fix:

1. Write the test from the finding and confirm it fails: `uv run pytest <test path>`.
2. Make the fix and confirm the test passes, then run the touched package's tests. If the fix touches Workflow code, also run its replay and time-skipping tests (plan §8).
3. Confirm the test pins the fix:
   - Revert only the fix in the Python source (keep a copy of the fixed file), run the new test, and check that it fails. Then restore the fix and confirm the test passes again.
   - A mutation that leaves every test passing may not have reached the code the tests run. Check what the test actually imports, and whether a stub or mock stands in for it.
4. If the fix changes a decision, update `design.md` and `tasks.md` (and the RFC or an ADR when the decision is architectural), and run `openspec validate "<name>" --strict`.

If a Blocker or Major was fixed, offer one more round with fresh reviewers for the lenses that raised them. In that round:

- A finding the engineer contested or accepted stays closed, even if a new reviewer raises it again.
- A fixed finding that comes back means the fix didn't work. Reopen it.

Stop after the second round and list anything still open. Suggest running the test suites and then `github-pr` as the next steps; at a phase gate, `verify-phase` follows (in the light tier, in this same fresh session against the same `code_sha`).

## Reviewer briefs

All three share this header, with the placeholders filled in:

```text
Review the implementation of the change in <change directory>, in the
repository at <repository root>. Stay inside that repository. Review only
this diff: `git -C <repository root> diff <diff range>`. Read whatever code
and tests you need to judge it.

Read the contract: <contract file paths>
Read the guidance files: <guidance file paths>
```

### Contract

```text
<header>

Your lens is the contract: does the code keep every promise, everywhere it
applies?

1. List every requirement: each SHALL or MUST in the specs, each scenario,
   each design decision stated as a rule, and each accepted ADR decision the
   diff touches. For each, give the file:line that enforces it and the test
   that would fail without it. A requirement with no enforcing code, or no
   test that would fail, is a finding.
2. Universal claims. For each requirement that says "only", "never",
   "every", "all", "at most", "during", "across" or "before", list every
   place in the diff it applies to (every database read, every write, every
   external call, every Activity, every place the work happens) and check
   each one. One missed place is a finding.
3. Observability. For each requirement, ask whether the test setup can
   observe it at all. For example: Temporal's time-skipping test environment
   hides real timer and timeout behavior; mocked Activities in Workflow tests
   hide their failures and retries; deterministic model stubs hide real vLLM
   output and tool-call parsing; a fake or in-memory store hides SeaweedFS
   and PostgreSQL behavior such as transactions, constraints and concurrent
   writers. A requirement the tests can't observe is a finding: say what setup
   would observe it.

For each finding, give a severity (Blocker / Major / Nit), the location, a
concrete failure scenario (inputs and state, then the wrong outcome), the
evidence (file:line, or a quote from the contract), and the test that would
expose it. Report every mismatch you notice, including one you judge
acceptable or can't fully verify: rate it Nit and say why. The engineer
decides, and a mismatch left out of the report is lost. "No findings" is a
valid answer.
```

### Failure and retry

```text
<header>

Your lens is failure: what happens when the code stops partway and runs
again?

1. For each long-running unit in the diff (Temporal Workflow, Activity,
   harness invocation, batch loop, webhook consumer, script), list in order
   every await and side effect from its start to its completion, including
   those inside helpers it calls.
2. For each one, ask: if it throws, the worker process dies, or the pod is
   deleted right here, what state is persisted (Temporal history, application
   PostgreSQL, BlobStore, workspace checkpoint), and what does the retry, the
   replay, the resume and the next fresh run read? Cover at least:
   - a failure before any state is first saved;
   - a death after the last save but before completion;
   - a write that partly applied, and whether every write uses a stable
     operation ID so a retry is idempotent;
   - state a previous run left under the same key or id;
   - a cancellation, including while paused, waiting on a Signal or Update,
     or between heartbeats;
   - two runs overlapping, and a Signal or Update delivered twice;
   - a Workflow replayed after this code changed (non-determinism), and state
     carried across Continue-As-New;
   - an Activity that outlives its heartbeat or start-to-close timeout.
3. Read the source of every reused helper the unit depends on (BlobStore and
   persistence repositories, retry and budget wrappers, task-queue routing,
   GitHub integration) instead of assuming its behavior, and cite the behavior
   you relied on with file:line.

For each finding, give a severity (Blocker / Major / Nit), the location, a
concrete failure scenario (inputs and state, then the wrong outcome), the
evidence (file:line, or a quote from the contract), and the test that would
expose it. Report every mismatch you notice, including one you judge
acceptable or can't fully verify: rate it Nit and say why. The engineer
decides, and a mismatch left out of the report is lost. "No findings" is a
valid answer.
```

### Scope and composition

```text
<header>

Your lens is scope: does each mechanism hold at the scope the contract
promises, and do parts that are correct alone stay correct together?

1. For every rate, limit, budget, ceiling, cost counter, window, lock, cache,
   history-size bound or checkpoint, find where it is created, reset and
   checked (per call, per Activity attempt, per task, per plan revision, per
   request, per run, per repository), and compare that with the scope the
   contract promises it at. A mismatch is a finding.
2. Look for pairs of mechanisms that are each correct alone but break when
   combined, especially new code next to a reused helper's behavior (for
   example, Temporal's own retries on top of an application retry loop).
3. For each promised property, check that some test exercises it at its
   promised scope (several tasks, a retry, a resume, a second run, a
   Continue-As-New). A property tested only at a smaller scope is a finding.

For each finding, give a severity (Blocker / Major / Nit), the location, a
concrete failure scenario (inputs and state, then the wrong outcome), the
evidence (file:line, or a quote from the contract), and the test that would
expose it. Report every mismatch you notice, including one you judge
acceptable or can't fully verify: rate it Nit and say why. The engineer
decides, and a mismatch left out of the report is lost. "No findings" is a
valid answer.
```

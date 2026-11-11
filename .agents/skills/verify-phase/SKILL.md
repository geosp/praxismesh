---
name: verify-phase
description: >-
  Independently verifies a PraxisMesh phase (or bootstrap stage) by executing it:
  reproduces the acceptance tests and the phase demo from the documented
  instructions, and checks the as-built architecture claims, in a disposable
  checkout of the frozen code_sha. Saves the verification report and demo
  evidence with a pass/fail/blocked verdict. Use after review-implementation to
  close a phase (gate mode), or to dry-run a phase's tests and demo (informal).
---

# Phase verification

Design review reads the design and implementation review reads the code; neither runs anything. Verification is the step that **executes**: it reproduces the acceptance tests and the demo from what the documentation says, and checks that the as-built documentation describes what actually happens. It answers one question: does the frozen system really behave as claimed?

Order of work: `review-design` -> implementation -> `review-implementation` -> **`verify-phase`** -> coordinator approval gate (`docs/reviews/README.md`) -> merge.

This skill was written for this project from plan §0.3, §4.15, §4.17 and §8; it is not adapted from an earlier skill (see the decision log).

## Step 0: Choose the mode

- **Informal:** a dry run during development. Uses the current commit (uncommitted changes are not verified; say so), reports in chat, and writes no files in the repository.
- **Gate:** closes a phase. Follow every rule in `docs/reviews/README.md`:
  - **Fresh session:** if this session implemented, reviewed or discussed the work, stop.
  - **Light-tier exception:** in Phases 0-2, the same fresh session may run `review-implementation` first and then this skill against the same `code_sha`. The report then states that independence between the two was waived (§7.0).
  - **Pinned revisions:** the user names `code_sha` (the tested implementation) and `docs_sha` (the as-built documentation revision). Both must be commits that exist on the remote (`git branch -r --contains <sha>`).
  - **Evidence files:** `docs/reviews/phase-N/verification.md` and `docs/demos/phase-N.md`. They identify `code_sha` and `docs_sha`, but need not contain the SHA of the later commit that adds them (phase file, independent verification session).
  - **No fixing:** findings go back to the implementer.

If the user doesn't say, ask which mode. Use gate mode only when they confirm. Never accept a verdict, summary or transcript from an earlier review as input; if one is offered, decline it and continue without it.

## Step 1: Identify the phase and revisions

1. **Phase:** the phase name (for example `0`, `3a`, or `bootstrap`) and its file in `docs/plan/phases/` (`docs/plan/bootstrap.md` §0.4 for the bootstrap). Read the phase file's tasks, **Accept** criteria and **Demo checklist**.
2. **Revisions:**
   - gate mode: `code_sha` and `docs_sha` from the user;
   - informal mode: both are `git rev-parse HEAD`.
3. **Documentation to check:** at `docs_sha`, read
   - `docs/architecture/overview.md` (or the phase's as-built section);
   - the phase RFC in `docs/rfcs/`;
   - the documented demo and setup instructions (README, `docs/operations/`, the RFC's demo section).

   If the as-built documentation does not exist, it is a gate Blocker for Phase 0 onward (§4.17). For the bootstrap stage it does not apply.

## Step 2: Prepare the disposable checkout

Never run tests or demos in the user's working copy.

```bash
VERIFY_DIR="$(mktemp -d)/verify-<phase>"
git worktree add --detach "$VERIFY_DIR" <code_sha>
mkdir -p "$VERIFY_DIR/.verify"            # scratch: logs and captured output
git -C "$VERIFY_DIR" log -1 --format='%H %cI'
```

Prerequisites come only from the documentation (for example `.env.example` copied to `.env` as documented). Never copy secrets from the user's working copy. A prerequisite the docs do not mention but the run needs is a finding (Major): the demo is not "runnable from documented prerequisites" (§8).

## Step 3: Run the verifier

Use the `verifier` agent (defined in `.agents/agents/`, generated for each harness). Run the two briefs **one after the other** (they share the checkout and any running services), each in a fresh verifier with the placeholders filled in and nothing more. If a harness cannot load the agent, spawn a fresh subagent with the same restrictions.

1. **Acceptance and demo** (brief below).
2. **As-built claims** (brief below). It may reuse services the first brief left running; tell it whether they are up.

A verifier that errors or returns nothing has not verified. Retry it once; if it fails again, report that part as "not run". Not run is never "passed".

## Step 4: Evidence checks (this session, no agent)

Run these directly and record command and output:

- **Revisions:** `git cat-file -t <code_sha>` and `<docs_sha>` are commits. Gate mode only: both are on the remote.
- **Docs describe this code:** `git diff --stat <code_sha> <docs_sha> -- . ':!docs'` is empty. If not, the docs revision carries source changes the tests did not cover (Blocker).
- **CI on the tested code, informational:** `gh api repos/{owner}/{repo}/commits/<code_sha>/check-runs --jq '.check_runs[] | [.name,.conclusion] | @tsv'`. Latest-head CI is the coordinator's check, not a verification input.
- **Nothing that must not be committed:** scan the tree at `code_sha` and `docs_sha` for secrets and session transcripts:
  ```bash
  git grep -nIE 'gh[opsu]_[A-Za-z0-9]{20,}|github_pat_|sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY' <sha>
  git ls-tree -r --name-only <sha> | grep -iE '\.jsonl$|transcript'
  ```
- **Demo evidence completeness** (gate mode, after Step 5 writes it): `docs/demos/phase-N.md` has environment and versions, exact commands, IDs and links, expected against observed for each step, the failure or recovery case, cleanup, and pass/fail.

## Step 5: Verdict and report

**Verdict** (plan §4.15 states; the report also records each check):

- **fail** if any of these holds:
  - an acceptance test or demo step fails;
  - an as-built claim is contradicted;
  - the docs revision carries untested source changes;
  - a secret or transcript is committed;
  - a demo step needs an undocumented prerequisite and fails without it.
- **blocked** if no check failed but one could not run because a dependency is unavailable (name it). A blocked demo item is never marked passed (§8).
- **pass** only when every acceptance test and demo step passed with observed output, every as-built claim is confirmed (or explicitly marked unverifiable with a reason the user accepts), and the evidence checks are clean.

**Report in chat**:

1. The verdict and the rule that decided it.
2. A checks table: check, command or step, expected, observed, result (pass / fail / blocked / not run).
3. The as-built claims table: claim (quoted, with location), status (confirmed / contradicted / unverifiable), evidence.
4. Findings: id, severity (Blocker / Major / Nit), location, what was expected, what was observed.

**Gate mode, also write**:

- `docs/reviews/phase-N/verification.md` from `docs/templates/review-report.md` (`review: verification`, `commit_sha` = `code_sha`, `docs_sha`, `verdict`, the tables above). For the bootstrap, use `docs/reviews/bootstrap/verification.md`.
- `docs/demos/phase-N.md` (or `docs/demos/bootstrap.md`) with the demo evidence as observed by this run: environment and versions, exact commands, IDs and links, expected against observed, failure and recovery case, cleanup, pass/fail per demo item.

Offer to commit both as a documentation-only change on a branch (`docs/<issue>-phase-N-verification`) and open a PR with `github-pr`. Do not push to `main`.

## Step 6: Clean up

Run the documented teardown (for example `make down`) in the checkout, then:

```bash
git worktree remove --force "$VERIFY_DIR" && git worktree prune
```

Confirm that `git status` in the user's working copy is unchanged from before Step 2.

## Verifier briefs

### Acceptance and demo

```text
You are verifying phase <phase> of the repository checked out at
<verification checkout>, which is the frozen commit <code_sha>. Work only in
that directory; write logs and captured output only under
<verification checkout>/.verify.

Read the requirements: <phase file path> (tasks, "Accept" criteria and "Demo
checklist"), and the RFC's acceptance tests: <RFC path, or "none">.
Read the setup and demo instructions: <documentation paths>.

1. Prerequisites. Using only the documented setup steps, prepare the
   environment. List every step you ran. A step the run needs but the
   documentation does not mention is a finding.
2. Acceptance tests. Run every automated acceptance suite the phase or RFC
   names, with the documented commands. For each, record the command, the
   exit status and the summary lines of the output.
3. Demo. Walk the demo checklist in order, using the documented commands or
   API calls. For each item: the exact command or action, the expected result
   (quote the checklist or doc), the observed result (quote the output), and
   pass / fail / blocked. Include the failure or recovery item; it must
   produce the documented diagnostic or recovery, not silent success.
4. Leave services running only if told the next check needs them; otherwise
   run the documented teardown.

If something cannot run because a dependency is unavailable (GPU, model, test
repository, credentials), mark it blocked with the reason. Never mark it
passed and never replace it with a mock. "No findings" is a valid answer only
when every item passed with quoted output.
```

### As-built claims

```text
You are checking whether documentation describes the system as it actually
is. The frozen code is checked out at <verification checkout> (commit
<code_sha>). Work only in that directory; write only under
<verification checkout>/.verify. Services from the previous check are
<running | stopped>.

Read the as-built documentation at revision <docs_sha>:
<as-built doc paths> (use `git -C <verification checkout> show <docs_sha>:<path>`
if the file differs at <code_sha>).

1. List every factual claim about the system: components and services, ports
   and endpoints, data stores and what they hold, Workflows and Activities,
   data flows, persistence and restart behavior, failure and recovery
   behavior, configuration, and every element of each diagram.
2. For each claim, check it against the code (file:line) and, where it
   describes runtime behavior, against observation: run a read-only probe
   (a status command, a query, a health endpoint) using documented commands
   only.
3. Classify each claim: confirmed (with evidence), contradicted (what you
   observed instead, with evidence), or unverifiable (why). Claims about
   planned or future behavior presented as current are contradicted.

For each contradicted or unverifiable claim give a severity (Blocker / Major /
Nit), the location in the document, the claim quoted, and the evidence.
```

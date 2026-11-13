---
review: implementation
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: [docs/adr/0001-keep-default-openspec-schema.md, docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 60fe15d0fd755c391cbe79c0084f7def7b38c7db
docs_sha: n/a
diff_base: cbd48750a936f38cfe94e0178ddc92335e82c650
session: fresh (targeted follow-up, docs/reviews/README.md rule 6)
date: 2026-11-13
verdict: FAIL
reviewers:
  - { lens: contract, status: completed }
  - { lens: failure and retry, status: completed }
  - { lens: scope and composition, status: completed }
---

# Phase 1 gate: targeted follow-up of PR #53

This fresh session reviewed only committed corrections for M1–M7 and N1/N9
from PR #52, plus regressions introduced by the correction diff. It did not
implement the change or consume an implementation-session transcript or summary.
Existing reports and demo evidence are preserved. Tracking issue: #44.

## Inputs

- Repository: `/home/geo/develop/praxismesh`.
- PR: <https://github.com/geosp/praxismesh/pull/53>.
- Code and requested documentation revision:
  `60fe15d0fd755c391cbe79c0084f7def7b38c7db`.
- Diff: `git diff cbd48750a936f38cfe94e0178ddc92335e82c650 60fe15d0fd755c391cbe79c0084f7def7b38c7db`.
- Original report obtained directly from PR #52, whose head was
  `7dab16041f9e0fe0ebf642515ec97dee6d7accba`:
  [gate-followup.md at the original revision](https://github.com/geosp/praxismesh/blob/7dab16041f9e0fe0ebf642515ec97dee6d7accba/docs/reviews/phase-1/gate-followup.md).
  Retrieval used `gh pr view 52 --json body,comments,files,headRefOid`, then
  `gh api repos/geosp/praxismesh/contents/docs/reviews/phase-1/gate-followup.md?ref=7dab16041f9e0fe0ebf642515ec97dee6d7accba --jq .content`
  with base64 decoding. Only the targeted correction list and scope/severity
  rules were supplied to reviewers; they did not receive that report's other
  reviewer verdicts or the implementation PR's reasoning.

All three reviewers were launched in parallel as fresh `impl-reviewer` agents
with no inherited conversation. Each received the same pinned diff, repository
root, correction list and permitted files, plus its independent skill lens.
They used read-only inspection; no tests, builds or mutations were run. No
reviewer's findings or verdict were shared with another reviewer.

The following paths are relative to the absolute repository root above and
were supplied as that root plus the named contract paths:

- `openspec/changes/phase-1-single-agent/proposal.md`
- `openspec/changes/phase-1-single-agent/design.md`
- `openspec/changes/phase-1-single-agent/tasks.md`
- `openspec/changes/phase-1-single-agent/specs/agents/capability-model/spec.md`
- `openspec/changes/phase-1-single-agent/specs/execution/durability/spec.md`
- `openspec/changes/phase-1-single-agent/specs/execution/harness-turn/spec.md`
- `openspec/changes/phase-1-single-agent/specs/execution/task-workflow/spec.md`
- `openspec/changes/phase-1-single-agent/specs/observability/baseline/spec.md`
- `openspec/changes/phase-1-single-agent/specs/persistence/app-database/spec.md`
- `openspec/changes/phase-1-single-agent/specs/quality/agent-benchmarks/spec.md`
- `openspec/changes/phase-1-single-agent/specs/security/threat-model/spec.md`
- `openspec/changes/phase-1-single-agent/specs/storage/blob-store/spec.md`
- `docs/rfcs/phase-1-single-agent.md`
- `docs/adr/0001-keep-default-openspec-schema.md`
- `docs/adr/0002-paradedb-as-postgresql-server.md`
- `docs/plan/phases/phase-1.md`
- `docs/security/threat-model.md`
- `docs/plan/decision-log.md`, only rows dated 2026-11-11 and 2026-11-12,
  to establish prior decisions and accepted Phase 1 risks.

Guidance: `AGENTS.md` and `PROJECT_PLAN.md` §2 and §8. There are no nested
`AGENTS.md` files in the touched packages. The coordinating session first read
the core plan, Phase 1 plan, required design sections §4.1/4.2/4.10/4.13,
schemas, gate protocol, implementation-review skill and report template.

## Revision and cleanliness evidence

| Check | Command | Observed |
|---|---|---|
| Committed snapshot | `git rev-parse HEAD` | `60fe15d0fd755c391cbe79c0084f7def7b38c7db` |
| Commit object | `git cat-file -t 60fe15d0fd755c391cbe79c0084f7def7b38c7db` | `commit` |
| Remote PR head | `git ls-remote origin refs/pull/53/head refs/pull/52/head` | PR #53: `60fe15d0fd755c391cbe79c0084f7def7b38c7db`; PR #52: `7dab16041f9e0fe0ebf642515ec97dee6d7accba` |
| Remote containment | After fetching `refs/pull/53/head:refs/remotes/origin/pr-53`, `git branch -r --contains 60fe15d0fd755c391cbe79c0084f7def7b38c7db` | `origin/pr-53`, `origin/fix/44-phase-1-followup-fixes` |
| Clean reviewed files | `git status --porcelain` before review and before report creation | Empty |
| Diff whitespace | `git diff --check cbd48750a936f38cfe94e0178ddc92335e82c650 60fe15d0fd755c391cbe79c0084f7def7b38c7db` | Exit 0, no diff diagnostics |

The requested `docs_sha` equals the remotely confirmed `code_sha`. Verification
was conditional on an implementation PASS and was not started.

## Reviewer statuses

| Lens | Status | Assessment |
|---|---|---|
| Contract | completed | M2 partly resolved; one remaining Major |
| Failure and retry | completed | No Blocker/Major; one logging Nit |
| Scope and composition | completed | No Blocker/Major; same logging Nit |

The latter two reviewers considered M2 resolved by the newly asserted counts.
The merged report retains the contract reviewer's more specific gap: observation
counts do not pin the promised measured sizes and durations, and the fixture
never produces output tokens. Findings are assessed on evidence, not by vote.

## Targeted correction status

These are inspection results, not claims that tests passed in this session.

| Original ID | Status | Evidence at the pinned revision |
|---|---|---|
| M1 | Resolved by inspection | `Progress.attempts` and `prior.attempts = real_attempt` carry actual attempts in heartbeat details; live-heartbeat assertions and `test_turn_timeout_fails_the_turn` check timeout attempt/token accounting |
| M2 | **Partly resolved** | Input-token delta and checkpoint observation counts now asserted; output-token accounting and checkpoint measurement values remain unpinned (T1) |
| M3 | Resolved by inspection | `test_inner_turns_are_summed_over_turns` checks 3 + 4 = 7 through the mocked completion input; `test_complete_task_closes_rows_left_open` checks real completion persistence of `inner_turns=9` |
| M4 | Resolved by inspection | Workflow harness-Activity stub asserts `turn.request_id == "req-1"`, exercising the Workflow handoff |
| M5 | Core correction resolved; Nit remains | CLI configures JSON logging on stderr and emits contextual submission log; test checks task/request IDs and clean stdout JSON; known Workflow ID omitted (T2) |
| M6 | Resolved by inspection | C7 names inherited SDK defaults; actual runner starts stdio environment fixture, checks keys against grants plus SDK defaults and excludes worker canary |
| M7 | Resolved by inspection | Command tests exercise workspace cwd, shortened configured timeout and output larger than the cap; C5 maps these tests |
| N1 | Resolved by inspection | Terminal cleanup supplies `through_attempt=attempt`; SQL bounds `attempt <= :through_attempt`; regression starts replacement attempt 2 before stale attempt 1 fails and checks replacement stays open |
| N9 | Resolved by inspection | File-tool test now invokes `list_files` with parent, absolute and symlink directory escapes, asserting explicit rejection |

## Findings

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| T1 (remaining M2) | Major | Contract | `tests/integration/test_harness_activity.py:87-93,483-494`; `harness_activity/activity.py:306-307,328` | Metrics fixture produces 20 input tokens and zero output tokens. Only input-token delta and checkpoint histogram `_count` are asserted. Removing the output-token increment is invisible to these assertions; replacing both checkpoint observations with `observe(0)` still increments the counts but falsely reports zero size/time. RFC line 365 and observability spec line 24 promise tokens and checkpoint size/time. These parts of the requirement have no exposing assertion. This is a static test-observability finding; these mutations were not executed and no runtime failure is claimed. | Fix: exercise nonzero output tokens and assert both direction deltas; assert checkpoint histogram sum deltas against known archived sizes and controlled elapsed times. Demonstrate those tests fail when output-token recording is removed or checkpoint values are zeroed. | open |
| T2 | Nit | Failure and retry; Scope and composition | `orchestrator/cli.py:82,88`; `tests/test_cli.py:83-86` | Successful submission knows Workflow ID equals `start.task_id` (`orchestrator/submit.py:60`), but new JSON log context includes only task/request IDs. Observability spec requires IDs where known, so filtering by `workflow_id` misses this record. Correlation through identical task ID remains possible. | Fix: add `workflow_id=start.task_id` to submission log context and assert it in CLI test. | open |

No additional regressions were identified in the pinned diff. Unrelated prior
Nits remain outside this targeted follow-up and are not silently closed.

## Verdict

**FAIL** under `docs/reviews/README.md` rule 5: all three reviewers completed,
but T1 leaves M2 partially unresolved, with an open Major. The original severity
rule treats a requirement without an exposing test as Major. No Blocker was
identified. Production metric recording appears correct by inspection; the
blocker to a PASS is the missing regression protection for its promised values.

`verify-phase` was **not run**, because the requested prerequisite was an
implementation-review PASS. There is no new verification or demo verdict, and
no prior evidence is being counted as a pass for this revision. No implementation
code, repository settings, PR state or Phase 1 task status was changed.

## Open items and coordinator handoff

1. Return T1 and T2 to the implementer through this report. Fix T1 (or contest
   it with concrete contract/test evidence); T2 is nonblocking. A correction
   requires a new committed remote revision and a fresh targeted review session.
2. After implementation review passes, run gate-mode `verify-phase` against
   that exact code/documentation revision, using the Phase 1 light-tier exception.
   Run acceptance tests, recovery, real-model benchmark, demo and as-built checks
   in a disposable checkout; use only documented prerequisites and never copy
   working-checkout secrets. Unavailable dependencies must be recorded blocked.
   Preserve this and all earlier reports and demo evidence under distinct paths.
3. Only after all required verdicts pass, the coordinator must check the latest
   evidence-bearing PR head. For this PR, obtain and record it externally:

   ```bash
   head_sha=$(gh pr view 53 --repo geosp/praxismesh --json headRefOid --jq .headRefOid)
   gh pr checks 53 --repo geosp/praxismesh --required
   gh api "repos/geosp/praxismesh/commits/$head_sha/check-runs" --jq '.check_runs[] | [.name,.conclusion] | @tsv'
   git fetch origin refs/pull/53/head:refs/remotes/origin/pr-53
   git rev-parse origin/pr-53
   git diff --stat 60fe15d0fd755c391cbe79c0084f7def7b38c7db "$head_sha" -- . ':!docs'
   ```

   Confirm the fetched SHA equals `head_sha`, required `ci-ok` passed on that
   exact latest head, and the source diff is empty. The SHA above is the snapshot
   reviewed here; **if fixes change source/tests, replace it with the newly
   reviewed and verified `code_sha`**, after rerunning affected review, tests
   and verification. Never use this FAIL report to approve changed source.
   Confirm all applicable evidence identifies the same final tested `code_sha`
   and verification names the accepted `docs_sha`; record `head_sha` in the PR
   or coordinator approval record, not a tracked file. Docs-only evidence
   changes still require affected documentation checks and latest-head CI.
4. Phase 1 remains open. This session does not merge, post to GitHub or close
   the phase. The report is left as a documentation-only working-tree addition
   for the coordinator to commit on an appropriate branch.

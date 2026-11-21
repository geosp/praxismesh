---
review: verification
phase: Phase 3A persistence (plan docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle, phase 02)
change: docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle
rfc: n/a
adrs: []
commit_sha: 4dde76d70a3a7e378dddb1a7714f0a9ddc76362a
docs_sha: 0d9db273d179c27f8abb203e85524625c1ef040d
diff_base: n/a
session: coordinator with fresh verifier subagents run one at a time (docs/reviews/README.md rules 1 and 8)
date: 2026-11-21
verdict: pass
reviewers:
  - { lens: acceptance and operator commands (at 4dde76d), status: completed, result: pass with 4 minor findings }
  - { lens: as-built claims (code and docs 4dde76d), status: completed, result: 1 Major and 9 Nits, all documentation }
  - { lens: as-built follow-up (docs 0d9db27), status: completed, result: pass }
---

# Verification: Phase 3A persistence, phase 02 (GC and delete-by-request; issue #92)

## Inputs

A disposable worktree of the pinned commit, with `infra/.env` from `infra/.env.example` changed
only as README "Several checkouts" and "Model endpoint" direct (Compose project `pmverify3a`, its
own ports, `VLLM_BASE_URL=http://spark-01:8000`); the owner's `praxismesh` stack was not touched.
The plan, the phase file and the notes it links, README, AGENTS.md, the Makefile, the runbook
(including "Removing data"), the overview's Phase 3A persistence draft. Raw reports:
[raw/persistence-verification-phase-02-*.md](raw/). This phase has no demo checklist: the plan's
demo is phase 03's (task 3.2). The observed behaviour is collected in the acceptance walkthrough
[docs/demos/phase-3a-persistence-02.md](../../demos/phase-3a-persistence-02.md).

## History

1. Acceptance at `4dde76d`: every repository check, the unit suite (376 passed), the full
   integration suite (337 passed, none skipped) and `make smoke` (307 passed); every task's
   Verify line and every Given/When/Then of the delivered requirements shown by a passing test;
   the documented operator commands run on the real stack (Temporal, SeaweedFS, the model).
   Four minor findings, none blocking.
2. As-built claims at `4dde76d`: one Major (the runbook said the app role cannot change or
   delete tombstones; it can still `TRUNCATE` the table it owns, as threat model R10 records)
   and nine Nits, all wording.
3. Docs corrected in `0d9db27` (documentation only); a follow-up confirmed every corrected
   statement.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `make up`, `make status`, `make migrate` (pmverify3a) | healthy, migrations at head | all services healthy; migrations at 0007 | pass |
| Repository checks | AGENTS.md "Checks" | exit 0 | all exit 0 | pass |
| Unit | `uv run pytest` | pass | `376 passed` | pass |
| Integration | `uv run --env-file infra/.env pytest -m integration -rs`, workers stopped | pass | `337 passed`, none skipped | pass |
| Smoke | `make smoke`, workers stopped | pass | `307 passed` | pass |
| Task Verify lines | phase file tasks 1.1-4.1 | each passes | each mapped to passing tests (raw acceptance report, 2c) | pass |
| Requirements | R3, R6-R13, R15, R21, R22, R24, R25, each scenario | each shown | each shown by a passing test (raw acceptance report, 2d) | pass |
| Operator commands | runbook "Removing data" on the real stack | as documented | gc (dry and real), request delete (dry counts equal the real run's), task output and tail after the delete, events prune --dry-run, --force on a terminated Workflow, the lock message, a resubmitted file revived | pass |
| Link check | lychee, CI args, offline | 0 errors | `0 Errors` at 4dde76d and at 0d9db27 (local lychee 0.24.2) | pass |
| gitleaks, actionlint | - | - | not installed on the host; CI runs both | blocked locally (CI) |
| Revisions | `git cat-file -t`; `git branch -r --contains` | commits on the remote | both on `origin/feat/92-phase-3a-gc-and-delete` | pass |
| Docs describe the code | `git diff --stat 4dde76d 0d9db27 -- . ':!docs' ':!README.md'` | empty | empty | pass |
| Secrets and transcripts | `git grep` for token patterns; `.jsonl`/transcript files | none | only the scan pattern itself in two docs; `.jsonl` files are spike results and test fixtures accepted in earlier verifications | pass |

## As-built claims

Every claim in the runbook's "Removing data", the overview's Phase 3A persistence draft, the
README and `agentctl` lines about these commands, and notes.md#redact, #d6 and #revive is
confirmed against the code and read-only probes, or corrected in `0d9db27` and confirmed by
the follow-up. See the raw as-built and follow-up reports.

| Claim (quoted) | Location | Status | Evidence |
|---|---|---|---|
| "The app role cannot change or delete these rows." | runbook, Tombstones | contradicted (M1), fixed in `0d9db27` | the trigger refuses UPDATE and DELETE; the owning app role can TRUNCATE (threat model R10); follow-up confirmed the new text |
| "`ephemeral` 1 day after it was written" | runbook, overview | contradicted for rows (N1, N2), fixed | wake and event-batch rows expire from their task's end |
| "Nothing is removed on its own" | runbook | overbroad (N4), fixed | the publisher and the dispatcher already prune their own rows |
| dry-run locks, delete deletes "task rows", fencing row "status", tombstone "reason", session-ID "assumption", README workers and smoke lines | runbook, overview, notes.md, README | Nits N3, N5-N9, fixed | follow-up confirmed each |

## Findings

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| V1 | Minor | The real Temporal mapping (`workflow_status`) has no test; `running` and `closed` were checked by hand on the real stack, `missing` was not | accepted: impl-review F130; phase 03's acceptance and drill run against real Temporal |
| V2 | Minor | No local command is documented for the link check | accepted: CI's `links` job runs it; the CI arguments with a local lychee were used here |
| V3 | Minor | Kill tests raise in-process instead of killing a process | accepted: impl-review F164; phase 03's drill stops a real process |
| V4 | Observation | On the real stack nothing had expired, so gc's positive paths are shown only by the time-shifted scratch-database tests; R25 with a still-running Activity only by its test | accepted: the tests run the same code on PostgreSQL |
| A1 | Major | The runbook overstated what the audit log refuses | fixed in `0d9db27` |
| A2-A10 | Nit | Wording (N1-N9 of the as-built report) | fixed in `0d9db27` |
| B1 | - | gitleaks and actionlint not installed on the host | accepted: CI runs both |

## Verdict

**pass**: at `4dde76d` every acceptance test, Verify line and requirement scenario passed with
observed output, and the operator commands behaved as documented on the real stack; the docs at
`0d9db27` are confirmed; `0d9db27` changes documentation only; both commits are on the remote;
the evidence checks are clean.

## Open items

- None for this phase. V1 and V3 are covered by phase 03's acceptance and drill.

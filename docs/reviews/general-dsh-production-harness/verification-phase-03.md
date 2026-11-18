---
review: verification
phase: general-dsh-production-harness (plan phase 03)
change: docs/plans/2026-11-15-dsh-production-harness
rfc: n/a
adrs: [ADR-0005, ADR-0006]
commit_sha: d55f3add6dcb9e2db2d4bf3047f3bb78be0cfdf7
docs_sha: 06dd64737ee280d33574422982a2dcd37504ea31
diff_base: n/a
session: coordinator with fresh verifier subagents run one at a time (docs/reviews/README.md rules 1 and 8; light tier, independence from impl-review waived per rule 7)
date: 2026-11-17
verdict: pass
reviewers:
  - { lens: acceptance and demo (at d55f3ad), status: completed, result: pass }
  - { lens: as-built claims (docs 0e35ec6), status: completed }
  - { lens: as-built wording follow-up (docs 06dd647), status: completed }
---

# Verification: DSH migration phase 03 (acceptance and default switch)

## Inputs

A disposable worktree of `code_sha`; the plan, phase file and notes; setup docs (README, AGENTS.md
"Checks", Makefile, `infra/.env.example`, `docs/operations/runbook.md`); the as-built section
"DSH migration phase 03" of `docs/architecture/overview.md`, the demo record and the 2026-11-17
decision-log row. A disposable Compose project (`verify03acc`, own ports) set up from
`infra/.env.example`, with `VLLM_BASE_URL` set to the real model endpoint for the benchmarks; the
owner's running stack was not stopped or changed. Raw reports:
[raw/](raw/) (`verification-phase-03-*.md`). Demo evidence:
[docs/demos/general-dsh-production-harness-03.md](../../demos/general-dsh-production-harness-03.md).

## History

1. Acceptance and demo at d55f3ad: **pass**. One documentation finding (V1).
2. As-built claims against docs 0e35ec6: one Major (V2) and Nits (V3-V6).
3. Wording fixed in 06dd647 (docs only; `git diff --stat d55f3ad 06dd647 -- . ':!docs'` is empty).
   A narrow follow-up confirmed the corrected statements; it found the demo record's Cleanup row
   written before the teardown ran (V7), corrected afterwards with the observed teardown.

## Checks (at code d55f3ad)

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `infra/.env` from `.env.example` (own project and ports); `make up`, `make status`, `make migrate`, `make workers-up` | healthy, 0004 | "all services healthy"; "0003 -> 0004"; all workers and both DSH pairs healthy | pass |
| Lint, format, types | `ruff check .`, `ruff format --check .`, `mypy` | clean | clean; 123 files | pass |
| Plans, agents, notices | `check_plans.py`, `sync_agents.py --check`, `check_dsh_licences.py` | 0 errors | 0 errors; up to date; 7 distributions | pass |
| Unit | `uv run pytest` | pass | 286 passed, 178 deselected | pass |
| Stack jobs | `make smoke`, `restart-check`, `unhealthy-check`, `workers-check`, `recovery-check` | pass | 154 passed; PASS; PASS; `local-default` succeeded; 5 passed | pass |
| R19 | `make benchmark ARGS="--profile dsh"` | at most one failure | 10 of 10 | pass |
| R4 | `make benchmark ARGS="--profile openai"` | at most one failure | 10 of 10 | pass |
| R20 | licence check intact, with a file removed, with a directory removed | pass, fail, fail | exit 0, 1, 1 naming the distribution; restored, 0 | pass |
| Tasks 1.1-2.2 | each task's Verify item (demo record, section "Independent verification") | as stated | as stated; the revert walkthrough's old task finished on `local-dsh` after a `lost` attempt, `usage_known: false`, orders once each | pass |
| gitleaks, actionlint | not installed locally | — | run by CI on the PR | not run |
| Evidence | commits; docs diff; secrets; transcripts | clean | both commits; `git diff --stat d55f3ad 06dd647 -- . ':!docs'` empty; secret scan matches only the scan's own pattern in docs; the only `.jsonl` files are the spike results already on `main` | pass |
| Remote | `git branch -r --contains` both SHAs | on the remote | pending: the branch is pushed with the PR, after the owner approves | pending |

## As-built claims

All claims in the phase 03 section, the runbook, the demo record and the decision-log row were
checked against the code and the disposable stack (raw/verification-phase-03-as-built.md). After
the 06dd647 wording fixes, the follow-up confirmed each corrected statement
(raw/verification-phase-03-follow-up.md).

| Claim | Status | Note |
|---|---|---|
| Implementer's demo rows on the owner's stack | unverifiable here | the owner's project was off-limits; the verifier reproduced each item in its own project |
| Owner's quote in the 2026-11-17 decision-log row | unverifiable here | recorded by the coordinator from the owner's instruction in the session |

## Findings

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| V1 | Nit | README "Several checkouts" does not say `PRAXIS_SAMPLE_DB_URL` carries the database port, so a second checkout changing only `DB_PORT` points host-run tests at the first checkout's database | open: README is outside `docs/`; a follow-up docs change after the merge |
| V2 | Major | Runbook said tasks on a stopped DSH queue wait "until the pairs return" or until `default` is switched back; they fail after `schedule_to_close`, and switching back does not move them | fixed in 06dd647; confirmed by the follow-up |
| V3 | Nit | Overview and runbook said the lock pins templates only; it also pins the DSH runtime digest | fixed in 06dd647; confirmed |
| V4 | Nit | Demo record promised a verification section that did not exist yet | fixed in 06dd647 (section added); confirmed |
| V5 | Nit | Demo record said `/attempts` empty; it holds the control socket | fixed in 06dd647; confirmed |
| V6 | Nit | Phase 02 known-limits bullet in the present tense | fixed in 06dd647; confirmed |
| V7 | Nit | Demo record's Cleanup row written before the teardown ran | fixed after the teardown, with the observed result |
| V8 | Note | The verifier's builds retagged the shared `:dev` images (a documented known limit); the owner's stack kept running | reported to the owner |

## Verdict

**pass**: every acceptance test and demo item passed with observed output at d55f3ad, the as-built
claims at 06dd647 are confirmed (two marked unverifiable here, with reasons), and the evidence
checks are clean except the remote check, which follows the push. gitleaks and actionlint run in CI.

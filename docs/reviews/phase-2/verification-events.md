---
review: verification
phase: Phase 2 events (plan docs/plans/2026-11-18-phase-2-agent-events, phase 01)
change: docs/plans/2026-11-18-phase-2-agent-events
rfc: n/a
adrs: [ADR-0007, ADR-0009]
commit_sha: 499eb635d605826e912fb0fb4f52f02e63da99c5
docs_sha: 965e8e83e9d24d5798d5dd367092c5d29953da34
diff_base: 41c0bcfbb192e7211ff1100d0849856215aef7a3
session: coordinator with fresh verifier subagents run one at a time (docs/reviews/README.md rules 1 and 8; light tier, independence from impl-review waived per rule 7)
date: 2026-11-18
verdict: pass
reviewers:
  - { lens: acceptance and demo (at 629e8db), status: completed, result: fail (V1) }
  - { lens: acceptance re-run after the V1 fix (at 499eb63), status: completed, result: pass }
  - { lens: as-built claims (code 499eb63, docs 87f5d44), status: completed, result: pass with nits }
  - { lens: as-built follow-up (docs 965e8e8), status: completed, result: pass }
---

# Verification: Phase 2 events, the event table and `agentctl tail` (issue #79)

## Inputs

A disposable worktree of the pinned commit, with `infra/.env` from `infra/.env.example` changed
only as the example directs for a second stack (Compose project `pmverify2`, its own ports) plus
the local model endpoint; the owner's `praxismesh` stack was not touched. The plan, the phase file,
README, AGENTS.md, Makefile, the runbook (Deploy, Agent events), the demo record and script, and
the as-built overview, schemas, decision log. Raw reports:
[raw/events-verification-*.md](raw/). Demo evidence:
[docs/demos/phase-2-events.md](../../demos/phase-2-events.md).

## History

1. Acceptance and demo at `629e8db`: **fail** on one test. `test_tool_and_token_events[dsh]`
   expected token payloads without `request_id`, which DSH carries as documented (V1); the code
   was right. Everything else passed, including the full demo on the local model with the worker
   kill (task `task-a70928e4-...`: `reset` at 22 naming `:1:1:1`, offsets 1..41 once each,
   `Expired(10)` first).
2. Fixed in `499eb63` (the test, README's check list, the demo prerequisites); the load benchmark
   rerun at `499eb63` (V2) and committed in `87f5d44`.
3. Acceptance re-run at `499eb63`: **pass**. `git diff --stat 629e8db 499eb63` touches only the test,
   README and docs, so the workers built at `629e8db` serve `499eb63`.
4. As-built claims (code `499eb63`, docs `87f5d44`): no Blocker or Major; 4 Nits, 2 claims
   unverifiable. Docs corrected in `965e8e8`; a follow-up confirmed each corrected statement.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `make up`, `make migrate`, `make workers-up`, `make status` (pmverify2) | healthy, migrations at head | all services healthy; `0005 (head)`; migration down to 0004 and up again | pass |
| Deploy check | `make task PROFILE=default ...` and `PROFILE=openai` | `local-dsh` and `local-default` | both `succeeded` with those templates | pass |
| Repository checks | AGENTS.md "Checks" | exit 0 | all exit 0 | pass |
| Unit | `uv run pytest` | pass | `308 passed` | pass |
| Integration | `uv run --env-file infra/.env pytest -m integration` | pass | at 629e8db `1 failed, 209 passed` (V1); at 499eb63 `210 passed`, none skipped; conformance 20 `openai_agents` + 20 `dsh` | pass (after fix) |
| Load (task 2.3) | `python -m tests.benchmarks.event_load` | display p95 <= 1 s in 3 fenced runs, publish p95 < 250 ms, every offset once, fenced DB CPU <= 2x unfenced | committed results at 499eb63, not dirty: display p95 0.209 s, publish p95 10 ms, all tailers complete, CPU 2.9-3.5% fenced vs 3.4% unfenced; a 60 s verifier run also passed | pass |
| Demo (task 4.1) | `sh infra/demo/phase-2-events.sh` | the demo record's steps | every step as recorded, including the worker kill and recovery | pass |
| gitleaks, actionlint | - | - | not installed on the host; CI runs both | blocked locally (CI) |
| Remote | `git branch -r --contains` both SHAs | on the remote | `origin/feat/79-agent-events` | pass |

## Findings

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| V1 | Major | `test_tool_and_token_events[dsh]` rejected DSH's documented `request_id` | fixed in 499eb63; re-run passed |
| V2 | Minor | Committed load results named `cda93d9`, before the review fixes | fixed: rerun at 499eb63, committed in 87f5d44 |
| V3 | Minor | Database CPU sits at noise level, so the 2x gate discriminates little | accepted: the publish p95 gate is the binding one; both are recorded |
| V4 | Minor | `make workers-up` in a second checkout re-tags the shared `praxismesh-worker:dev` and `praxismesh-dsh:dev` images | accepted: the owner is told; a restart of the owner's stack uses images built at the verified commit |
| V5 | Trivial | README's check list lacked the licence check; README and AGENTS.md status lines | check list fixed in 499eb63; status lines are updated when the Phase 2 work closes |
| V6 | Trivial | The demo script's host prerequisites were not documented | fixed in 499eb63 (demo record) |
| A1 | Nit | schemas.md omitted lost or killed attempts from the `status` exceptions | fixed in 965e8e8 |
| A2 | Nit | schemas.md said every attempt opens with `reset`; one refused at start or past its limit stores no events | fixed in 965e8e8 |
| A3 | Nit | The DSH executor path does not cap refused tool names | accepted: the executor only receives granted tools; the gateway refuses (and caps) every other name |
| A4 | Nit | The demo record abbreviated the prune output | fixed in 965e8e8 |
| A5 | Unverifiable | The demo's recorded values come from the owner's stack | accepted: the verifier's own demo run on pmverify2 matched (41 events, same types) |
| A6 | Unverifiable | A live `events prune` was not run by the as-built verifier (permission) | accepted: confirmed by the acceptance verifier's demo run and the table tests |

## Verdict

**pass**: at `499eb63` every acceptance test and demo step passed with observed output; the docs at
`965e8e8` are confirmed or marked unverifiable with reasons; `git diff --stat 499eb63 965e8e8 -- .
':!docs'` is empty; both SHAs are on the remote.

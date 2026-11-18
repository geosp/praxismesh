---
review: verification
phase: general-event-transport-spike (plan phases 01 and 02, one verification by owner decision)
change: docs/plans/2026-11-17-event-transport-spike
rfc: n/a
adrs: [ADR-0007, ADR-0009]
commit_sha: 8153e7b8dd534da06fb4a16f9a7dd8c78ff4829a
docs_sha: 1f2871d739412ec8847252c324b774d6bb8c0f70
diff_base: n/a
session: coordinator with fresh verifier subagents run one at a time (docs/reviews/README.md rules 1 and 8; light tier, independence from impl-review waived per rule 7)
date: 2026-11-18
verdict: pass
reviewers:
  - { lens: acceptance and demo (at 8153e7b), status: completed, result: pass }
  - { lens: as-built claims (docs 8153e7b), status: completed }
  - { lens: as-built wording follow-up (docs ac6e548), status: completed }
---

# Verification: event-transport spike (issue #76)

## Inputs

A disposable worktree of `code_sha`; the plan, both phase files and notes; the spike README,
`measure.sh`, `load.py` and the suite's docstrings, `stack.env`; the spike report
(`docs/spikes/event-transport.md`), ADR-0009, the probes README, the decision-log rows and
notes.md#verified. The disposable Compose project `pmspike76` (from `stack.env`); the owner's
`praxismesh` stack was not touched. No model endpoint (the spike replays a committed recording).
Raw reports: [raw/](raw/) (`verification-*.md`). Demo evidence:
[docs/demos/general-event-transport-spike.md](../../demos/general-event-transport-spike.md).

The Workflow Streams and NATS JetStream implementations were deleted after the owner's decision
(task 3.1); their items cannot run at `code_sha`, so the verifier checked their committed results
files, which name the commit (`c1fda62`, `69c95c4`) and command that produced them.

## History

1. Acceptance and demo at `8153e7b`: **pass**, with four minor findings (V1-V4).
2. As-built claims at `8153e7b`: no Blockers or Majors; every figure recomputes from the committed
   results; 14 contradicted or imprecise statements (V5) and 6 unverifiable ones (V6).
3. Wording fixed in `ac6e548` and `1f2871d` (Markdown only: `git diff --stat 8153e7b 1f2871d`
   changes `docs/` and two READMEs under `spikes/event-transport/`). A narrow follow-up confirmed
   every corrected statement; its one wording note was fixed in `1f2871d`.

## Checks (at code 8153e7b)

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `uv sync --locked`; `make up ENV_FILE=spikes/event-transport/stack.env` | healthy | "stack is up"; `make status`: all services healthy | pass |
| Unit | `uv run pytest` (spike) | pass | 33 passed, 3 skipped (stack-only and hosted-only tests) | pass |
| Shared suite, memory and table | `SPIKE_TRANSPORTS=memory,table uv run pytest tests/test_suite.py tests/test_table_notify.py` | pass | 15 passed, 2 skipped (R4 truncation, hosted only) | pass |
| Load-runner tests with the stack | `SPIKE_STACK=1 uv run pytest tests/test_load.py` | pass | 6 passed, including the failing-transport run leaving no agent running | pass |
| Measurement, table | `sh measure.sh` | 3 runs, same pass/fail | exit 0; each run: suite 7 passed, load R6 pass, p95 203.2-203.6 ms, 60,232 events, commit 8153e7b, dirty false | pass |
| Phase 01 Verify items 1.1-2.1, 2.3 (R9) | per task | as stated | as stated | pass |
| Phase 01 items 2.2, 2.3 (Streams, NATS) | committed results | files name commit and command | `results/suite-{streams,nats}.json` at 69c95c4 | not reproducible at this commit; evidence present |
| Phase 02 Verify items 1.1, 1.2 (table), 2.1, 2.2, 3.1 | per task | as stated | as stated; 1.1's growth metric is not in load.py (V2) | pass |
| Phase 02 item 1.2 (Streams) | committed results | as above | `results/load-streams-run{1,2,3}.json` at c1fda62; growth via the provenance file | not reproducible at this commit; evidence present |
| Failure and recovery | expiry report (R2), re-send (R3), stopped and resumed tailer (R1), failing transport, unreachable database | documented diagnostic or recovery | each observed; the unreachable database exits 1 with `ConnectionRefusedError` | pass |
| Evidence | commit; R9; secrets; transcripts | clean | commit; `git diff --stat main...8153e7b -- . ':!spikes' ':!docs'` empty; no secrets; the only new `.jsonl` is the recorded DSH turn (event data: counts, tool names, statuses; tested) | pass |
| Remote | `git branch -r --contains` both SHAs | on the remote | both on `origin/spike/76-event-transport` (PR #77) | pass |

## As-built claims

Every number in the spike report, ADR-0009, the decision-log row and the notes recomputes from the
committed results files; versions, ports, schema, mechanisms and line counts match the code
(at `8153e7b`, and at `1bfac67` for the deleted options) or the running stack. After the wording
fixes, the follow-up confirmed each corrected statement.

| Claim | Status | Note |
|---|---|---|
| Probe outputs for the deleted options (JetStream start below base; Streams roll-over) | unverifiable here | the scripts are at 1bfac67 and agree with the stated outputs |
| The 2,000-Update stall message | unverifiable here | the committed Update counts total exactly 2,000 per run |
| "The 200 ms batch accounts for most of the latency" | unverifiable here | consistent with mean latency against the mean batch wait |
| Why Temporal suggested Continue-As-New | unverifiable here | stated as "apparently on history size" |
| External documentation facts (limits, Helm chart, auth) | unverifiable here | sourced in notes.md#verified; code constants agree |

## Findings

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| V1 | Nit | The stack-backed load test needs `SPIKE_STACK`, which no document named. | fixed: spike README |
| V2 | Nit | load.py writes no growth-per-minute metric (phase 02 task 1.1). | accepted: recorded in the report and the provenance file; growth came from the probe, per tailer inferred from Update counts |
| V3 | Nit | A failing load run reports `WorkflowFailureError` without the cause. | accepted: the run fails visibly (exit 1, outcomes "error"); a fuller message belongs to Phase 2's port |
| V4 | Note | Test runs overwrite committed results files. | fixed: the spike README documents `SPIKE_RESULTS` |
| V5 | Nit | 14 contradicted or imprecise statements (NATS workloads, R2 attribution, F55's scope, ratios, units, line-count label, pool arithmetic, planned work stated as current). | fixed in ac6e548 and 1f2871d; confirmed by the follow-up |
| V6 | Nit | 6 claims unverifiable at this commit (above). | accepted: reasons given |

## Verdict

**pass**: every acceptance test and every Verify item that can run at `code_sha` passed with
observed output; the items for the deleted options have committed results naming their commit and
command; the as-built claims at `docs_sha` are confirmed or marked unverifiable with reasons; the
evidence checks are clean, including the remote check after the push (PR #77).

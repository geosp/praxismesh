<!-- Verbatim verifier report (Phase 2 events, phase 01 gate verification, acceptance re-run after the V1 fix, at code 499eb63, docs 87f5d44); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-acceptance-rerun.md per docs/reviews/README.md rule 1. -->

# Phase 2 events, phase 01: acceptance re-verification at 499eb63

Checkout: /tmp/claude-1000/-home-geo-develop-praxismesh/599639d3-a59f-4a32-945c-fd5372c3c537/scratchpad/verify-phase2-events
`git log -1 --oneline`: `499eb63 Allow DSH's request_id in the token-event conformance test`. `git status --short`: only `?? .verify/`.
Stack: Compose project `pmverify2` (11 containers, all Up/healthy before and after; `.verify/rerun-ps-before.txt`, `.verify/rerun-ps-after.txt`). No `praxismesh-*` container or volume was touched. Nothing in the checkout was edited.

**Verdict: PASS.** The earlier blocking finding (V1, `test_tool_and_token_events[dsh]` failing) is resolved: the full integration suite is green at 499eb63 and the conformance suite passes for both runners. The committed load results name 499eb63, are clean, record their command, pass every task 2.3 threshold, and are byte-identical to the run copy under `.verify/`.

## 1. Diff since the failed verification

Command: `git diff --stat 629e8db17fa03f13d12421e12aa0d1ba62e99540 499eb63`
Expected: touches only tests/test_runner_conformance.py, README.md and docs.
Observed:
```
 README.md                                          |   1 +
 docs/demos/phase-2-events.md                       |   5 +-
 .../phase-2/raw/events-verification-acceptance.md  | 112 +++++++++++++++++++++
 tests/test_runner_conformance.py                   |   7 +-
 4 files changed, 120 insertions(+), 5 deletions(-)
```
Pass. No source change, so the running workers (built at the earlier commit) match 499eb63's runtime code; no rebuild was needed.

The test change replaces `set(e.payload) == {"input_tokens", "output_tokens"}` with `counts <= keys <= counts | {"request_id"}`. This matches the documented contract, `docs/roadmap/schemas.md:48`: ``| `token` | `input_tokens`, `output_tokens` (DSH adds `request_id`) | both runners, one per model response |``, and R6 ("only counts, names, IDs and statuses"). The test still rejects any other key, and the model-text checks below it are unchanged.

## 2. Repository checks, unit suite, integration suite

All run with `.verify/env.sh` sourced (drops the owner's venv from PATH and unsets VIRTUAL_ENV). Log: `.verify/rerun-checks.log`.

| Command | Expected | Exit | Observed |
|---|---|---|---|
| `uv sync --locked` | ok | 0 | `Checked 86 packages` |
| `uv run ruff check .` | ok | 0 | `All checks passed!` |
| `uv run ruff format --check .` | ok | 0 | `427 files already formatted` |
| `uv run mypy` | ok | 0 | `Success: no issues found in 134 source files` |
| `uv run .agents/sync_agents.py --check` | ok | 0 | `ok: 3 generated agent file(s) up to date` |
| `uv run .github/scripts/check_plans.py` | ok | 0 | `Validated 7 implementation plan(s); 0 error(s)` |
| `uv run .github/scripts/check_dsh_licences.py` | ok | 0 | `licence notices present for 7 pinned DSH distributions` |
| `uv run pytest` (unit) | all pass | 0 | `308 passed, 210 deselected in 36.39s` (`.verify/rerun-unit.log`) |
| `uv run --env-file infra/.env pytest -m integration -v -rs` | all pass | 0 | `210 passed, 308 deselected in 387.67s (0:06:27)`; 0 FAILED/ERROR/SKIPPED lines (`.verify/rerun-integration.log`) |
| `uv run --env-file infra/.env pytest tests/test_runner_conformance.py -m "integration or not integration" -v` | both runners pass | 0 | `40 passed in 62.77s`: 20 `openai_agents` PASSED, 20 `dsh` PASSED (`.verify/rerun-conformance-both.log`) |

Phase-relevant integration counts in the full run: `tests/integration/test_event_table.py` 22 passed, `tests/integration/test_harness_activity.py` 28 passed, `tests/integration/test_dsh_activity.py` 18 passed. The previously failing test:
```
tests/test_runner_conformance.py::test_tool_and_token_events[dsh] PASSED [100%]
tests/test_runner_conformance.py::test_tool_and_token_events[openai_agents] PASSED [ 97%]
```
Note: the checks list in AGENTS.md is the gitleaks/actionlint/link-check-free local list; CI-only jobs (gitleaks, actionlint, link check, dependency review) were not run here and are not claimed.

## 3. Committed load results (task 2.3)

Command: `git show 87f5d44:docs/benchmarks/2026-11-18-event-load.json` (saved as `.verify/rerun-committed-load.json`).

| Check | Expected | Observed | Result |
|---|---|---|---|
| Names its commit | 499eb63 | `"commit": "499eb635d605826e912fb0fb4f52f02e63da99c5"` | pass |
| Not dirty | false | `"dirty": false` | pass |
| Records command | present | `"command": "python -m tests.benchmarks.event_load --seconds 180 --runs 3 --out .../.verify/event-load-499eb63.json"` | pass |
| 3 fenced runs + unfenced in one session | yes | runs: fenced x3, `"fenced": false` x1, same file/date `2026-11-18T20:38:10+00:00` | pass |
| Display p95 <= 1 s in each fenced run | <= 1.0 | 0.208687, 0.208686, 0.20869 | pass |
| Publish p95 < 250 ms | < 0.25 | fenced 0.01014, 0.01010, 0.01023 (unfenced 0.00967) | pass |
| Fenced DB CPU <= 2x unfenced | ratio <= 2.0 | fenced medians 3.54, 2.9, 3.05 (median 3.05) vs unfenced 3.36; ratio 0.91 (worst single run 1.05). Script computes median-of-fenced vs unfenced (tests/benchmarks/event_load.py:216-222) | pass |
| Tailers complete | true | `"tailers_complete": true` in all 4 runs | pass |
| Verdict | pass | `"verdict": {"display_p95": true, "publish_p95": true, "tailers_complete": true, "db_cpu_ratio": true}, "pass": true` | pass |

Comparison with the run copy: `cmp .verify/rerun-committed-load.json .verify/event-load-499eb63.json` -> identical (also identical after `json.tool --sort-keys`). `.verify/event-load.out` ends with `"pass": true` for that out path; `.verify/event-load.err` shows the four per-run lines with the same numbers as the JSON (e.g. run 1 `"publish_p95_s": 0.010136065058759414, "display_p95_s": 0.208687`), plus a benign uv VIRTUAL_ENV warning. The benchmark runs from the checkout's source (the commit field is 499eb63), so the earlier-built workers do not affect it.

Commit 87f5d44 changes only `docs/benchmarks/2026-11-18-event-load.json` and one line of `docs/architecture/overview.md`; the new overview figures ("display p95 0.209 s, publish p95 10 ms, database CPU 2.9-3.5% fenced against 3.4% unfenced") match the JSON.

## 4. Services

`pmverify2` services were left running (11 containers Up, `.verify/rerun-ps-after.txt`).

## Findings

| ID | Severity | Finding |
|---|---|---|
| R1 | Minor (non-blocking) | `docs/architecture/overview.md` (Testing, "Unit:") lists "the runner conformance event test" as a unit test. Only its `openai_agents` parameter runs in the unit suite; the `dsh` parameter is integration-marked and, per the earlier report's V1, CI's stack job runs only `tests/integration`, so CI never runs `test_tool_and_token_events[dsh]`. The gap that let V1 through remains; worth a follow-up (doc wording or CI coverage), not a blocker for this phase. |

No blocking findings. Task 4.2's as-built check was not in this brief and is not assessed here.

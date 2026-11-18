<!-- Verbatim verifier report (event-transport spike verification, acceptance and demo, code_sha 8153e7b8dd534da06fb4a16f9a7dd8c78ff4829a); fresh verifier subagent; saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Acceptance verification: event-transport spike (issue #76), phases 01 and 02

- Checkout: /tmp/claude-1000/-home-geo-develop-praxismesh/599639d3-a59f-4a32-945c-fd5372c3c537/scratchpad/verify-76, HEAD `8153e7b8dd534da06fb4a16f9a7dd8c78ff4829a` (confirmed with `git rev-parse HEAD`; tree clean at start).
- Logs: `.verify/01-sync.log` to `.verify/10-demo-table.log`; regenerated results copied to `.verify/results-rerun/`.
- Date: 2026-11-18. No model endpoint was used. The `praxismesh` project was not touched (its containers were still "Up 3 days (healthy)" at the end).

**Verdict: PASS WITH FINDINGS.** Every automated suite and every Verify item I could reproduce passed, with output quoted below. Items that need the deleted Streams and NATS code have committed results files that name their commit and command. Findings F1 to F4 are minor documentation and diagnostic gaps. None of them changes a requirement outcome.

## 1. Prerequisites (documented steps only)

| # | Step (source) | Command | Result |
|---|---|---|---|
| 1 | README Setup | `cd spikes/event-transport && uv sync --locked` | exit 0; "Resolved 18 packages", "Installed 16 packages" incl. `temporalio==1.36.0`, `asyncpg==0.32.0`, `pydantic==2.14.3` |
| 2 | README Setup | `make up ENV_FILE=spikes/event-transport/stack.env` (repo root) | exit 0; "stack is up; run 'make status' for addresses and health" |

No step beyond the documented ones was needed for the suites. The spike creates its `spike76` schema itself (`CREATE SCHEMA IF NOT EXISTS spike76` in table.py), so no migration is needed. One undocumented switch is needed to run the stack-backed load test (F1). A harmless uv warning about the host's `VIRTUAL_ENV` appeared on every `uv run`; it comes from the environment, not the spike.

## 2. Acceptance suites

| Suite | Command (cwd spikes/event-transport) | Exit | Summary |
|---|---|---|---|
| Spike unit tests (default, memory) | `uv run pytest -rs` | 0 | "33 passed, 3 skipped in 66.00s". Skips: "test_load.py:99: needs the disposable stack", "test_suite.py:54: no Workflow to roll over (R4 is n/a)", "test_table_notify.py:39: needs the disposable stack" |
| Shared suite, memory + table, plus NOTIFY test | `SPIKE_TRANSPORTS=memory,table uv run pytest -rs -v tests/test_suite.py tests/test_table_notify.py` | 0 | "15 passed, 2 skipped in 113.31s"; every R1/R2/R3/R4/R7 test PASSED for `[memory]` and `[table]`; `test_a_notify_during_a_fetch_is_not_lost PASSED`; the 2 skips are `test_r4_truncating_roll_over` (R4 n/a) |
| Load-runner tests incl. the stack-backed one | `SPIKE_STACK=1 uv run pytest -rs -v tests/test_load.py` | 0 | "6 passed in 5.22s", incl. `test_a_failing_transport_ends_the_run_and_leaves_no_agent_running PASSED` |
| Measurement script, table | `sh measure.sh` | 0 | "real 19m41.292s". 3 runs, each preceded by reset + up. Suite each run: "7 passed, 1 skipped". Load: open1 p95 203.59 ms, open2 203.33 ms, open3 203.18 ms; each `"published": 60232`, `"requirements": {"R5": "n/a", "R6": "pass", "R11": "n/a"}`, `"complete": true` |

Note: a first unit run that I started with `SPIKE_RESULTS` set skipped `test_results_file.py` ("nested run"). That skip came from my variable, not from the spike. The documented rerun above runs those 3 tests and passes them.

Results written by measure.sh at HEAD (from `results/open{1,2,3}/suite-table.json` and `results/load-table-open{1,2,3}.json`): each has `commit 8153e7b`, `dirty False`, suite `partial False`, suite `{'R1':'pass','R2':'pass','R3':'pass','R4':'n/a','R7':'pass'}`, `agent_errors []`, killable tailers `restarts 5` each, no expiries seen.

## 3. Demo: Verify items in order

### Phase 01

| Item | Action | Expected (quoted) | Observed | Result |
|---|---|---|---|---|
| 1.1 | `uv sync --locked`; read notes.md#verified | "`uv sync --locked` in the spike; the limits and their source are in notes.md" | exit 0 (above). notes.md l.27-33: "Temporal limits (task 1.1; docs.temporal.io/workflow-execution/limits and /self-hosted-guide/defaults ...) Event History per run: error at 51,200 events or 50 MB ... Payload ...: error at 2 MB". The pins match the plan: temporalio 1.36.0, asyncpg 0.32.0. nats-py was removed with NATS (D6). | pass |
| 1.2 | unit run: `tests/test_memory.py`, `tests/test_models.py` | "unit tests of the reference implementation; a check that the copy's fields match `common/schemas/events.py`" | "tests/test_memory.py ....." and "tests/test_models.py ." passed. `test_copy_matches_the_root_schema` compares the field list with the AST of `common/schemas/events.py` | pass |
| 1.3 | `tests/test_fixture.py`; manual inspection | "the fixture parses with the spike's `AgentEvent` copy and holds no prompt text or credentials" | tests passed. 44 lines; types `{'tool_call': 18, 'tool_result': 18, 'token': 8}`; payload keys only `call, input_tokens, output_tokens, request_id, status, tool`. Grepping for secret or prompt keywords hit only "sk-" inside "task-spike76-capture", a false positive | pass |
| 1.4 | `tests/test_suite.py` (memory) and `tests/test_suite_validation.py` | "the suite passes on the reference implementation, and fails when the reference drops an event, repeats one, skips an expiry report or stores a re-sent batch twice" | "tests/test_suite.py ......s." and "tests/test_suite_validation.py .........." (10 passed: the reference passes and the broken variants DropsEvent, RepeatsEvent and others are caught) | pass |
| 2.1 | suite on table in the disposable project | "the suite runs against it in a disposable project and its results file is written" | `results/suite-table.json`: `"commit": "8153e7b..."`, `"partial": false`, R1/R2/R3/R7 "pass", R4 "n/a" | pass |
| 2.2 | Streams transport | "as 2.1" | not reproducible at this commit (code at 1bfac67; `git ls-tree 1bfac67` lists `streams.py`, `streams_workflow.py`). Committed `results/suite-streams.json`: commit `69c95c4`, dirty False, partial False, command "SPIKE_TRANSPORTS=memory,table,streams,nats SUITE_HORIZON_S=60 pytest -q -p no:cacheprovider tests/test_suite.py tests/test_table_notify.py", R1-R4, R7 all "pass". `results/run{1,2,3}/suite-streams.json`: commit `c1fda62`, all pass. Both commits are ancestors of HEAD | files present with provenance |
| 2.3 | NATS probe; R9 | "as 2.1; `git diff --stat ...` is empty" | NATS: not reproducible at this commit (code at 1bfac67, `jetstream.py`). `results/suite-nats.json`: commit `69c95c4`, the same command, R1/R2/R3/R7 "pass", R4 "n/a". R9: `git diff --stat main...HEAD -- . ':!spikes' ':!docs'` printed nothing (main = 951c0ce); the whole diff is "73 files changed, 11020 insertions(+)" inside spikes/ and docs/ | R9 pass; NATS files present with provenance |

### Phase 02

| Item | Action | Expected | Observed | Result |
|---|---|---|---|---|
| 1.1 | `uv run python load.py memory --seconds 30 --label dry` | "a 30 s dry run against the reference implementation writes a results file with every metric" | exit 0; `"published": 6016`, p95 194.65 ms, R6 "pass"; file keys: agent_errors, batches (588), command, commit (8153e7b, dirty False), complete, containers (db and temporal CPU and memory samples), history (limits plus max_run_events/bytes/carried, null for non-hosted), latency_ms, publish_ms, published, requirements, tailers. **No field for "growth per minute per agent and per tailer"** (F2) | pass with finding F2 |
| 1.2 (table) | `sh measure.sh` | "each results file names its commit and command; every requirement's pass/fail matches across the 3 runs" | 3/3 suites identical (R1/R2/R3/R7 pass, R4 n/a); 3/3 loads R5 n/a, R6 pass, R11 n/a; each file names commit 8153e7b and its command ("uv run python load.py table --label openN", "SPIKE_TRANSPORTS=table ... tests/test_suite.py"). My p95s (203.6/203.3/203.2 ms) agree with the committed `5854ca2` set (204.0/204.4/203.6) | pass |
| 1.2 (Streams, roll-over-off run) | committed files | the same | not reproducible at this commit (code at 1bfac67). `load-streams-run{1,2,3}.json`: commit c1fda62, dirty False, "uv run python load.py streams --label runN", R5/R6/R11 pass in 3/3. Roll-over off: `streams-growth-norollover.provenance.json` names commit "36ebee0 (the probe ran from the working tree just before this commit ...)" and command "PYTHONPATH=. uv run python probes/streams_update_limit.py > results/streams-growth-norollover.json" | files present with provenance (the 36ebee0 run was from a working tree, not a clean commit; the file says so) |
| 2.1 | read docs/spikes/event-transport.md "Operating cost" and "Fencing" | "every option has every heading filled, with sources" | the table has 9 headings (New components ... Limits that bind), each filled for Streams, table and NATS; "Sources: notes.md#verified and #d5 ..."; the Fencing (R10) section has a statement per option | pass |
| 2.2 | trace report numbers to committed results | "every number in the report traces to a committed results file (R8)" | spot-checked against `git show HEAD:...`: Streams p95 198.9/199.6/199.0 -> "199 (199-200)"; table p95 187.8/186.8/187.1 -> "187 (187-188)"; open-loop 204.0/204.4/203.6 -> "204 (204-204)"; published 54,897 / 58,002 / 60,232; Streams max_run_events 3531/3519/3519 and bytes 4,495,354 -> "3,519 (3,519-3,531)", "4.50 MB"; carried 297,764 -> "298 KB"; Temporal CPU medians 32.6/32.1/32.4 -> "32.4% (32.1-32.6%)", peaks 204/39/185 -> "185% (39-204%)"; table 1.6/1.4/1.4; DB 13.1/12.8/12.1 and 3.2/4.0/7.1. All match. ADR-0009 and the decision-log entry exist | pass (sampled, not every figure) |
| 3.1 | suite for the winner; R9 | "the suite still passes for the winner; `git diff --stat ...` is empty" | table suite passed (section 2, and 3/3 in measure.sh); R9 empty (above); `event_transport/` holds only memory.py and table.py; factories `OPTIONS` = memory, table | pass |

### Failure and recovery paths

| Path | Command | Expected | Observed | Result |
|---|---|---|---|---|
| Expiry report (R2), live table | `.verify/scripts/demo_table.py` (verifier script; publishes 20 events, `expire_below(15)`) | "an expiry report naming B, then B onwards"; at B-1 "B onwards and no expiry report" | "after 5 (B=15): ['Expired(retained_base=15)', 15, 16, 17, 18, 19, 20]"; "after 14 (B-1): [15, 16, 17, 18, 19, 20]" | pass |
| Re-send dedup (R3) | same script | "each event appears once" | after re-sending batch b0, "latest after re-send: 20" | pass |
| Stopped and resumed tailer (R1) | same script; also the load runs | "N+1 onwards in order with no repeat" | follower cancelled: "follower stopped at 20"; after 5 more events: "resumed after 20 : [21, 22, 23, 24, 25]". In each of the 3 measure.sh loads every killable tailer has `restarts 5`, `complete true`, no expiries. Suite `test_r1_resume`/`test_r1_cancel[table]` PASSED | pass |
| Failing transport ends a load run | `SPIKE_STACK=1 uv run pytest -s -v ".../test_load.py::test_a_failing_transport_ends_the_run_and_leaves_no_agent_running"` | the run ends with an error, not success, and leaves no agent running | `{"option": "memory", "label": "fail", "requirements": {"R5": "error", "R6": "error", "R11": "error"}, "published": 0, ...}`; the results file has `agent_errors: ['WorkflowFailureError: Workflow execution failed', x4]`; the test asserts `code != 0` within 60 s and no Running `SpikeLoadAgent`; "1 passed in 0.45s" | pass (finding F3 on diagnostic detail) |
| Unreachable database | `SPIKE_PG_DSN=postgresql://...@127.0.0.1:1/praxismesh uv run python load.py table --seconds 5 --label verifybad` | not silent success | "ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 1)", exit 1, no results file written | pass |

## Findings

- **F1 (minor, docs): an undocumented switch is needed for the stack-backed load test.** `tests/test_load.py:99` runs only with `SPIKE_STACK` set. The README, the load.py and test_suite.py docstrings and measure.sh never mention it; it appears only in the skip reason "needs the disposable stack". The README also gives no test commands at all; they live only in module docstrings.
- **F2 (minor, Phase 02 task 1.1 Verify): the dry-run results file does not hold every listed metric.** The task lists "growth per minute per agent and per tailer". `load.py` writes no growth field (`grep -i growth load.py` finds nothing). Streams growth came from a separate probe, and the provenance says `"per_tailer": "not measured directly: inferred from Update counts"`. The report says so openly, but the Verify wording ("every metric") is not met literally.
- **F3 (minor, diagnostics): a failing load run hides the cause.** The run fails visibly (exit non-zero, R5/R6/R11 "error"), but `agent_errors` holds only "WorkflowFailureError: Workflow execution failed". It does not show the underlying cause ("the transport is down"), and the summary also prints `"complete": true`.
- **F4 (observation): any documented test run overwrites committed results files.** A plain `uv run pytest` rewrote `results/suite-memory.json` (commit 69c95c4 became 8153e7b, and the command became "SPIKE_TRANSPORTS=memory SUITE_HORIZON_S=60 pytest -rs"). The table suite run likewise rewrote `results/suite-table.json`. Unit runs can therefore silently replace committed provenance.

## State left behind

- `pmspike76` is running: `make status ENV_FILE=spikes/event-transport/stack.env` reports "all services healthy" (Temporal 127.0.0.1:37233, DB 127.0.0.1:35432). measure.sh ends with reset + up, so the database holds only the later dry run, failure demo and demo-script data.
- Modified in the disposable checkout, all by documented commands: `spikes/event-transport/results/{suite-memory,suite-table,load-memory-dry,load-table-open1,load-table-open2,load-table-open3}.json` and `results/open{1,2,3}/suite-table.json`. Copies are in `.verify/results-rerun/`. No source, test or doc was edited. Nothing was committed.

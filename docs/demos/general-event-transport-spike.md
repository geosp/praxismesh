# Demo evidence: event-transport spike (issue #76)

- Code: `8153e7b8dd534da06fb4a16f9a7dd8c78ff4829a`; docs: `1f2871d739412ec8847252c324b774d6bb8c0f70`;
  date 2026-11-18.
- Environment: Linux x86_64 (Fedora, cgroup v2), Docker Compose, Python 3.11 via uv; the spike's own
  environment (`temporalio` 1.36.0, `asyncpg` 0.32.0, `pydantic` 2.14.3); the disposable Compose
  project `pmspike76` (`spikes/event-transport/stack.env`: Temporal 1.32.2 on 127.0.0.1:37233,
  ParadeDB 0.26.6 / PostgreSQL 16 on 127.0.0.1:35432). No model endpoint.
- Run by a fresh verifier subagent in a disposable worktree; full output in
  [raw/verification-acceptance.md](../reviews/general-event-transport-spike/raw/verification-acceptance.md).
- Commands run from `spikes/event-transport/` unless stated.

| Item | Command | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `uv sync --locked`; from the repo root `make up ENV_FILE=spikes/event-transport/stack.env` | stack healthy | "stack is up"; all services healthy | pass |
| Interface and reference (phase 01 1.2) | `uv run pytest tests/test_memory.py tests/test_models.py` | pass; the `AgentEvent` copy matches the root schema | passed | pass |
| Recorded turn (1.3) | `uv run pytest tests/test_fixture.py` | parses; no prompt text or credentials | passed; 44 events (8 token, 18 tool_call, 18 tool_result), payload keys only counts, tool names, statuses | pass |
| Suite and its validation (1.4) | `uv run pytest tests/test_suite.py tests/test_suite_validation.py` | passes on the reference; fails on broken variants | passed | pass |
| Table transport (2.1) | `SPIKE_TRANSPORTS=memory,table uv run pytest tests/test_suite.py tests/test_table_notify.py` | R1-R3, R7 pass; R4 n/a | 15 passed, 2 skipped; results name 8153e7b | pass |
| Streams and NATS (2.2, 2.3) | committed `results/suite-{streams,nats}.json` | files name commit and command | 69c95c4, clean, full runs; R1-R4 (Streams), R1-R3 and R7 pass | not reproducible at this commit (code at 1bfac67) |
| Dry run (phase 02 1.1) | `uv run python load.py memory --seconds 30 --label dry` | every metric written | 6,016 events, p95 194.65 ms, R6 pass; no growth metric (verification V2) | pass |
| Measurement, table (1.2) | `sh measure.sh` | 3 runs, same pass/fail, commit and command named | exit 0 in 19 m 41 s; each run on a reset stack: suite 7 passed; load 60,232 events, p95 203.2-203.6 ms, R6 pass | pass |
| Measurement, Streams (1.2) | committed `results/load-streams-run{1,2,3}.json`, growth provenance file | as above | c1fda62, clean; R5, R6, R11 pass in 3/3 | not reproducible at this commit |
| Report, ADR, deletion (2.1, 2.2, 3.1) | read and recompute | every number traces; the winner's suite passes; R9 | all figures recompute; suite passes; R9 diff empty | pass |
| Failure: expiry (R2) | verifier script: publish 20, `expire_below(15)`, read after 5 and after 14 | `Expired(15)` then 15 onwards; none after 14 | "after 5 (B=15): ['Expired(retained_base=15)', 15, ...]"; after 14 no expiry | pass |
| Failure: re-send (R3) | re-send batch b0 | stored once | "latest after re-send: 20" | pass |
| Recovery: stopped tailer (R1) | cancel a follower at 20, publish 5, resume after 20 | 21 onwards, no repeat | "resumed after 20 : [21, 22, 23, 24, 25]" | pass |
| Failure: failing transport | `SPIKE_STACK=1 uv run pytest tests/test_load.py -k failing` | the run ends with an error and leaves no agent running | passed: non-zero exit, outcomes "error", no `SpikeLoadAgent` running | pass |
| Failure: unreachable database | `SPIKE_PG_DSN=postgresql://...@127.0.0.1:1/praxismesh uv run python load.py table --seconds 5 --label verifybad` | not silent success | `ConnectionRefusedError`, exit 1, no results file | pass |
| Cleanup | `make reset ENV_FILE=spikes/event-transport/stack.env`; worktree removed | nothing of `pmspike76` left; owner's stack unchanged | see the verification report | pass |

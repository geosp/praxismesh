<!-- Verbatim verifier report (Phase 2 events, phase 01 gate verification, as-built claims, code 499eb63, docs 87f5d44); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-as-built.md per docs/reviews/README.md rule 1. -->

# As-built documentation check: Phase 2 events (docs at 87f5d44, code at 499eb63)

Verifier: fresh-context as-built verifier. Code: the frozen checkout at 499eb63
(`git log -1` -> `499eb63 Allow DSH's request_id in the token-event conformance test`).
Docs read with `git show 87f5d44:<path>`. `git diff --stat 499eb63 87f5d44` touches only
`docs/architecture/overview.md` (benchmark line) and `docs/benchmarks/2026-11-18-event-load.json`,
so the code at 499eb63 is the code the docs at 87f5d44 describe.
Runtime: Compose project `pmverify2` (infra/.env, `COMPOSE_PROJECT_NAME=pmverify2`). No `praxismesh-*`
container or volume was touched.

## Verdict

**Pass with nits.** 0 Blocker, 0 Major, 4 Nit contradictions, 2 claims unverifiable on purpose
(owner's stack). Every component, path, constant, table, column, data-flow edge and CLI behaviour
checked matches the code; runtime probes match.

## Probes run (read-only)

| # | Command | Observed (quoted) |
|---|---|---|
| P1 | `make status` | `all services healthy`; `addresses: Temporal 127.0.0.1:57233, ... DB 127.0.0.1:55432`; `model endpoint: http://spark-01:8000 answers /v1/models` |
| P2 | `docker exec pmverify2-db-1 psql -U praxismesh -d praxismesh -c "select version_num from alembic_version"` | `0005` |
| P3 | `psql ... "\d event_logs" / "\d agent_events" / "\d event_batches"` | event_logs: `workflow_id` PK, `next_offset bigint default 1`, `retained_base bigint default 1`, `retention_class default 'task'`; agent_events PK `(workflow_id, "offset")`, columns `task_id, attempt_id, seq, type, payload json, blob_ref json, emitted_at, stored_at, retention_class`; event_batches PK `(workflow_id, batch_id)`, `seen_at`, `retention_class default 'task'` |
| P4 | gap query: per workflow, `count(*) <> max-min+1 OR max <> next_offset-1 OR min <> retained_base` | `0` rows of 72 `event_logs` rows |
| P5 | first event per attempt for real task workflows (excluding `task-load-*`/`task-test-*` benchmark/test streams that publish directly) | every attempt starts with `reset`, except `task-a70928e4-...:1:1` whose offsets 1-9 were pruned by the demo (`retained_base` 10) |
| P6 | last event per real attempt that is not `status`, joined to `task_attempts` | 7 attempts, all `outcome = lost`, `failure_category = lost_or_timed_out` (killed workers) |
| P7 | payload keys by type (all rows) | `reset: restored_from`; `status: status, error`; `token: input_tokens, output_tokens, request_id` (plus `i` only in load-benchmark streams); `tool_call: call, tool`; `tool_result: call, status, tool` |
| P8 | `select batch_id ... from event_batches` | e.g. `task-864bc8f9-...:task-864bc8f9-...:1:1:1` = `<workflow>:<attempt_id>:<n>` |
| P9 | batch rows of the finished demo task | `9|9` (9 rows older than 600 s out of 9) |
| P10 | `./agentctl tail task-a70928e4-... --after 3 --no-follow` | first line `expired: events before 10 were pruned`, then `10<TAB>task-a70928e4-...:1:1<TAB>tool_call<TAB>{"call": 4, "tool": "lookup_price"}` |
| P11 | `timeout 60 ./agentctl tail task-a70928e4-... --after 38` (follow, completed Workflow) | printed 39, 40, `41 ... status {"status": "done"}`, `exit=0`, real 0.495 s |
| P12 | `timeout 30 ./agentctl tail task-verify-nonexistent-0000` (follow, unknown Workflow) | no output, `exit=0` (stopped on NOT_FOUND, not on the timeout) |
| P13 | `./agentctl task status task-a70928e4-...` | `COMPLETED succeeded [(1, 1, 'lost'), (1, 2, 'done')]` |
| P14 | `./agentctl events prune --help` | `(--below BELOW | --older-than OLDER_THAN)`, `--older-than ... for example 7d, 12h, 30m` |
| P15 | `git show 87f5d44:docs/benchmarks/2026-11-18-event-load.json` | commit `499eb635...`, dirty False; fenced publish p95 0.0101/0.0101/0.0102 s, display p95 0.2087 s, CPU 3.54/2.9/3.05 %; unfenced 3.36 %; `pass: True` |

A live `events prune` (even a no-op `--below 5` on an already-pruned stream) was refused by the
permission classifier, so prune behaviour is checked against the code and against the earlier
verifier's run of the demo on this same stack at 499eb63 (`.verify/demo-run.log`, `.verify/demo/`),
which I read but did not produce. Existing test logs (`.verify/rerun-unit.log`: `308 passed`;
`.verify/rerun-integration.log`: `210 passed`, exit 0) were read, not rerun.

## 1. docs/architecture/overview.md, "Phase 2 events: the event table and `agentctl tail`"

| # | Claim | Status | Evidence |
|---|---|---|---|
| O1 | Links: plan `docs/plans/2026-11-18-phase-2-agent-events/plan.md` (R1-R9), ADR-0009, runbook#agent-events | Confirmed | files exist at 87f5d44; plan.md:78 `### R1`, :122 `### R9`; runbook heading `## Agent events` |
| O2 | Event tables in `0005_agent_events.py`: `event_logs` (next offset, retained base), `agent_events` (keyed by workflow and offset; columns mirror `AgentEvent`), `event_batches` (batch IDs seen in last 600 s) | Confirmed | 0005_agent_events.py:41-70; P3; columns map to `AgentEvent` fields (common/schemas/events.py:30-40; `timestamp` -> `emitted_at`, plus `stored_at`) |
| O3 | All carry retention class `task` and are in `APP_TABLES` | Confirmed | 0005:33-37 default `'task'`; retention.py:31-33; P3 |
| O4 | Fence `common/persistence/fence.py`: per-task advisory lock, newer-turn-or-attempt check, `FenceRejected` | Confirmed | fence.py:15, 20, 23-26 |
| O5 | Used by every fenced write in `repositories.py` and by the event table | Confirmed | repositories.py:17-19 imports; uses at :144, :193, :238, :268, :382, :490, :540; table.py:35, 64-68; `grep pg_advisory` finds no other copy outside tests/spikes |
| O6 | Transport `common/events/`: interface `publish, read, latest, prune` | Confirmed | transport.py:85-111 (plus `close`) |
| O7 | Reader rule: `Expired` before pruned offsets, on a jump during a read; a repeat raises | Confirmed | transport.py:57-82 (`guarded`); table.py:123-128; P10 |
| O8 | In-memory reference and `TableTransport` | Confirmed | common/events/__init__.py:4-5 |
| O9 | Publish: task lock and fence check, then `event_logs` row lock, dedupes batch ID, inserts, advances offset, `NOTIFY agent_events` | Confirmed | table.py:62-103 in exactly that order; CHANNEL table.py:39 |
| O10 | A following reader `LISTEN`s on its own autocommit connection and polls every 1 s | Confirmed | table.py:111-121 (`AUTOCOMMIT`, `add_listener`), :41 `POLL_S = 1.0`, :140 |
| O11 | Publisher `harness_activity/events.py` (`BatchingPublisher`), one per attempt | Confirmed | events.py:67; activity.py:414-422 creates one inside `_attempt` |
| O12 | Batches of at most 64; cut when full, 200 ms after oldest buffered event's emit time, or at close | Confirmed | events.py:92-93, 181-194 (time is `time.monotonic()` at `emit`, events.py:122) |
| O13 | One publish at a time in `seq` order | Confirmed | single `_run` task (events.py:112, 165-179); `AttemptEvents.emit` delivers under its lock (events.py:52-63) |
| O14 | Cut batch frozen, re-sent unchanged after a DB error; backoff 0.25, 0.5, 1 s once per batch, then one try per trigger, also while closing | Confirmed | events.py:94, 191, 196-217, 157-159, 179 |
| O15 | A refusal stops it | Confirmed | events.py:204-208, 170-173, 116-117 |
| O16 | `close()` runs once, shielded from caller's cancellation, bounds final flush at 10 s (`CLOSE_TIMEOUT_S`) in a task of its own | Confirmed | events.py:22, 130-155 |
| O17 | `run_harness_turn` creates `AttemptEvents` over the publisher and passes it to `HarnessRunner.run` | Confirmed | activity.py:424-426, 557-559 (via `_run`) |
| O18 | Emits `reset` first, right after the checkpoint lookup and before opening the attempt; a failure before then still stores a `reset` | Confirmed, with Nit N2 | activity.py:429-433, 449-450 |
| O19 | Emits `status` before the final flush | Confirmed | activity.py:618-620 |
| O20 | Both success paths (normal, restore short-circuit) reach `_finish`, which flushes first; refusal raises `Superseded` before finish checkpoint, artifacts and outcome; a flush that fails for good raises retryable `EventsUnavailable` | Confirmed | activity.py:502, 579, 616-626; `EventsUnavailable(Exception)` at :101 is not in `NON_RETRYABLE` (orchestrator/workflow.py:29-35) |
| O21 | Failure and cancel paths store their events and re-raise the original error | Confirmed | activity.py:446-458 (`except BaseException` ... `raise`); P5 statuses include `cancelled`/`failed` with `error` |
| O22 | Workers publish to `TableTransport`; without a transport events go nowhere | Confirmed | workers/main.py:113, 123; activity.py:214-215, 422-426 (`NoOpSink`) |
| O23 | `openai_agents` emits `token`, `tool_call`, `tool_result` through run hooks; parallel calls to one tool keep own call numbers | Confirmed | runner.py:184-188, 207-226 (`self.calls` FIFO per tool) |
| O24 | `refused` pairs for ungranted tools, as DSH does from its gateway and executor | Confirmed | runner.py:201-202; gateway.py:338-339; executor.py:130-131 |
| O25 | `DshRunner` no longer takes a sink | Confirmed | dsh/runner.py:222-230 (no sink parameter); `run(..., events)` at :343-352 |
| O26 | Payloads hold counts, names (refused names capped at 64), IDs and statuses only | Confirmed, with Nit N3 | P7 keys; runner.py:201-202 and gateway.py:338-339 cap with `[:64]`; executor.py:130-131 does not |
| O27 | CLI `agentctl`, `orchestrator/cli.py`: `tail TASK [--after N] [--no-follow]`, `events prune --task T (--below N \| --older-than 7d)` | Confirmed | agentctl:1-9; cli.py:305-314; P14 |
| O28 | Each line is flushed | Confirmed | cli.py:215 `print(line, flush=True)` |
| O29 | `tail --follow` stops after one more read once Temporal reports Workflow closed or not found | Confirmed | cli.py:226-235, 249-258; P11, P12 |
| O30 | Other Temporal errors are logged and it keeps following | Confirmed (scope: `RPCError`) | cli.py:252-257 catches `RPCError` only; a non-RPC exception from `describe()` would end the tail. Not raised as a finding: Temporal client errors surface as `RPCError`. |
| O31 | `--no-follow` reads the table only | Confirmed | cli.py:242-246 (no Temporal `connect()`) |
| O32 | Diagram: runner (DSH / openai_agents) --emit--> AttemptEvents --> BatchingPublisher | Confirmed | gateway.py:319, executor.py:175-177, runner.py:184; events.py:63 |
| O33 | Diagram: --publish (fence, event_logs row lock, batch dedup, NOTIFY)--> agent_events | Confirmed | table.py:62-103 |
| O34 | Diagram: agentctl tail --LISTEN agent_events + 1 s poll--> reads offsets above N (reader rule) | Confirmed | table.py:110-143; cli.py:217-222; P10, P11 |
| O35 | Superseded attempt's publish refused; stores nothing more; raises `Superseded` at final flush or earlier at next model call | Confirmed | table.py:65-68; events.py:116-117; activity.py:621-622, 549-552 |
| O36 | Lost reply re-sends same batch ID, stored once (within 600 s) | Confirmed | transport.py:35; table.py:79-94; test `test_resends_are_recognised_only_inside_the_horizon` (test_event_table.py:269) |
| O37 | Worker killed mid-turn loses buffered events (up to 64 or 200 ms worth); retried attempt opens with `reset` naming the checkpoint | Confirmed | P6 (7 lost attempts end without `status`); P-restored query: e.g. `task-a70928e4-...:1:2 {"restored_from": "task-a70928e4-...:1:1:1"}` |
| O38 | Reader below retained base gets `Expired(base)` first, then continues from base | Confirmed | table.py:123-128; P10 |
| O39 | Tests: unit `tests/test_event_publisher.py`, runner conformance event test, CLI tail/prune tests | Confirmed | files exist; test_runner_conformance.py:559 `test_tool_and_token_events`; tests/test_cli.py; `.verify/rerun-unit.log` `308 passed` |
| O40 | Integration: `test_event_table.py` (shared suite on table and memory, fence, lock order, horizon, `older_than`, notify during fetch), `test_harness_activity.py`, `test_dsh_activity.py` | Confirmed | test_event_table.py:232, 247, 269, 282, 310 and shared tests :98-193; `.verify/rerun-integration.log` `210 passed`, exit 0 |
| O41 | Load: `python -m tests.benchmarks.event_load`; at 499eb63 display p95 0.209 s, publish p95 10 ms, CPU 2.9-3.5 % fenced vs 3.4 % unfenced | Confirmed | P15 (0.2087 s; 0.0101-0.0102 s; 3.54/2.9/3.05 vs 3.36; commit 499eb635, not dirty) |
| O42 | Demo `sh infra/demo/phase-2-events.sh` | Confirmed | file exists; run on this stack in `.verify/demo-run.log` ends `offsets across both tails: 1..41, each once` |
| O43 | Pruning is manual until Phase 3A; a finished workflow keeps its last 600 s of batch rows | Confirmed | no scheduled prune in code (only cli.py:273-281); event_batches deleted only inside a publish of the same workflow (table.py:79-85); P9 |
| O44 | A stale attempt still running after task completion can publish after tail's final read; fence refuses only when a newer attempt exists | Confirmed | fence.py:23-26 checks only newer attempts |
| O45 | `status` reports runner's result, not recorded outcome | Confirmed | activity.py:618 emitted before finish writes |
| O46 | One global NOTIFY channel; every follower receives every workflow's notification | Confirmed | table.py:39, 116-118 (filtered client-side) |

## 2. docs/roadmap/schemas.md, Phase 2 events paragraph and table

| # | Claim | Status | Evidence |
|---|---|---|---|
| S1 | Events stored in `agent_events` at a gap-free `offset` per workflow (the task's workflow ID) | Confirmed | table.py:73-102; P4; submit.py:60 `id=start.task_id` |
| S2 | `event_logs` holds next offset and retained base; `event_batches` the batch IDs `<workflow>:<attempt_id>:<n>` seen in last 600 s; re-sent batch stored once | Confirmed | events.py:191; P8; table.py:79-94 |
| S3 | All three carry retention class `task` | Confirmed | P3 |
| S4 | `seq` stays per attempt | Confirmed | events.py:47-62 (`AttemptEvents.seq` per instance, one per attempt) |
| S5 | No model or tool text in payloads | Confirmed | P7 key set |
| S6 | `reset`: `restored_from` (checkpoint ID, or null for fresh start or failure before lookup), Activity, first event of every attempt | Confirmed, with Nit N2 | activity.py:429-430, 449-450; P5 |
| S7 | `token`: `input_tokens`, `output_tokens` (DSH adds `request_id`), both runners, one per model response | Confirmed | runner.py:184-188; gateway.py:319-323; P7 |
| S8 | `tool_call`: `tool`, `call`, both runners | Confirmed | runner.py:201, 209; executor.py:175 |
| S9 | `tool_result`: `tool`, `call`, `status` (`refused` for ungranted, name capped at 64) | Confirmed, with Nit N3 | runner.py:202, 222-226; executor.py:177; gateway.py:339 |
| S10 | `status`: `status` (runner's result), `error` on failure; last event of every attempt except a superseded one | Contradicted (Nit N1) | see N1 |

## 3. docs/operations/runbook.md, "Agent events"

| # | Claim | Status | Evidence |
|---|---|---|---|
| R1 | Every harness attempt, on either runner, publishes to the event table (migration 0005) | Confirmed | workers/main.py:113, 123; P2 |
| R2 | Offsets per task (workflow ID is task ID), start at 1, no gaps | Confirmed | 0005:44 default 1; P4; submit.py:60 |
| R3 | `tail TASK_ID` follows live, stops once the Workflow closed | Confirmed | P11 |
| R4 | `tail --after 120` resumes after offset 120 | Confirmed | cli.py:307; P11 started at 39 for `--after 38` |
| R5 | `tail --no-follow` prints what is stored and exits | Confirmed | P10 (33 lines, exit) |
| R6 | `events prune --below 500` deletes offsets below 500 | Confirmed (code + earlier run) | table.py:188-209; `.verify/demo/prune.json` `{"task_id": "task-a70928e4-...", "retained_base": 10}` after `--below 10`, and P4 shows min offset 10 for that stream |
| R7 | `--older-than 7d` deletes the oldest events up to the first newer than 7 days | Confirmed (code) | table.py:190-200 (`stored_at >= now() - 7d`); cli.py:184-188; test_event_table.py:282 |
| R8 | `agentctl` runs the CLI with `infra/.env`; `ENV_FILE=...` selects another | Confirmed | agentctl:8-9 |
| R9 | Line format `offset<TAB>attempt<TAB>type<TAB>payload` | Confirmed | cli.py:191-196; P10 |
| R10 | `expired: events before N were pruned`; reading continues at N | Confirmed | cli.py:193; P10 |
| R11 | Each attempt starts with a `reset` naming its restored checkpoint | Confirmed, with Nit N2 | P5 and restored query |
| R12 | Pruning manual until Phase 3A; rows carry retention class `task` | Confirmed | as O43, O3 |
| R13 | Deploy: `make migrate` (0005) before restarting harness workers; running tasks need no drain, because `TaskWorkflow` did not change | Confirmed | Makefile:101-102; `git log main..499eb63 -- orchestrator/workflow.py` is empty |
| R14 | If the DB cannot store an attempt's last events, the attempt fails with retryable `EventsUnavailable` and writes no finish; Temporal retries the turn | Confirmed | activity.py:619-626; workflow.py:29-35; test_harness_activity.py:855 |

## 4. docs/demos/phase-2-events.md

| # | Claim | Status | Evidence |
|---|---|---|---|
| D1 | Recorded 2026-11-18 at `acd713e` on the owner's stack (`praxismesh`), versions listed | Unverifiable (by instruction) | the owner's stack must not be touched; record-of-a-run claim |
| D2 | Reproduce with `sh infra/demo/phase-2-events.sh [OUT_DIR]`; needs `make workers-up`, a model endpoint, `python3`, GNU `grep -P`, `timeout` | Confirmed | phase-2-events.sh:5, 25 (python3), 57 (timeout), 70 (`grep -P`) |
| D3 | Steps: submit DSH task, tail live, kill after second checkpoint, retried attempt opens with `reset`, stop first tail 15 s after kill and resume with `--after`, offsets 1..N once, prune `--below 10`, tail `--after 3 --no-follow`, restart killed container | Confirmed | script :29-74 (`-ge 2` checkpoints :38, `sleep 15` :50) |
| D4 | Observed values of the owner's run (task ID, `praxismesh-worker-dsh-a-1`, attempts `(1,1,lost)`, `(1,2,done)`) | Unverifiable for that run; reproduced equivalently | `.verify/demo-run.log` on pmverify2 at 499eb63: `killed pmverify2-worker-dsh-b-1`, `first tail stopped after offset 21`, `offsets across both tails: 1..41, each once`, `22 ... reset {"restored_from": "...:1:1:1"}`; P13 `[(1, 1, 'lost'), (1, 2, 'done')]` |
| D5 | 41 events: 2 reset, 6 token, 16 tool_call, 16 tool_result, 1 status; keys `call, input_tokens, output_tokens, request_id, restored_from, status, tool` | Confirmed on reproduction | `.verify/demo/tail-{1,2}.log`: `2 reset, 1 status, 6 token, 16 tool_call, 16 tool_result`; same key set |
| D6 | Prune: `{"retained_base": 10}`; tail shows expiry then `10 ... tool_call {"call": 4, "tool": "lookup_price"}` | Confirmed (Nit N4 on quoting) | P10; `.verify/demo/prune.json` |
| D7 | Found while recording: tail block-buffered; fixed in `acd713e` (each line flushed) | Confirmed (fix present) | cli.py:215 |

## 5. docs/roadmap/decision-log.md, row 2026-11-18 (Phase 2 events)

| # | Claim | Status | Evidence |
|---|---|---|---|
| L1 | Each attempt publishes through one `BatchingPublisher` owned by `run_harness_turn` | Confirmed | activity.py:414-422 |
| L2 | `HarnessRunner.run` gains a required `events` argument | Confirmed | runner.py:125-137 (no default); dsh/runner.py:343-352; runner.py:246 |
| L3 | `DshRunner` takes no sink | Confirmed | dsh/runner.py:222-230 |
| L4 | Every publish takes ADR-0007's fence via `common/persistence/fence.py` | Confirmed | table.py:35, 63-68 (the `fenced=False` flag exists only for the benchmark baseline, table.py:54-56; production constructs `TableTransport(engine)` with the default `True`, workers/main.py:113, 123) |
| L5 | Final flush runs at the start of `_finish`, before any finish write | Confirmed | activity.py:618-626 |
| L6 | `agentctl` wraps the CLI with `tail` and `events prune` | Confirmed | agentctl:8-9; cli.py:305-327 |
| L7 | Refused flush raises `Superseded`; a flush that fails for good raises retryable `EventsUnavailable` | Confirmed | activity.py:621-624; workflow.py:29-35 |

## Contradicted or unverifiable claims

**N1 (Nit), docs/roadmap/schemas.md, Phase 2 events table, row `status`:** "the Activity, last event
of every attempt except a superseded one". Evidence: a lost (killed) attempt has no `status`.
P6 lists 7 attempts whose last stored event is `reset`, `tool_call` or `tool_result`, all with
`outcome = lost`, e.g. `task-a70928e4-...:1:1|tool_result|20|lost|lost_or_timed_out`. The overview's
failure section documents this ("A worker killed mid-turn loses its buffered events"), so the
system is as designed. The table's exception list is incomplete: it should say "except a superseded
or lost one".

**N2 (Nit), docs/roadmap/schemas.md, `reset` row ("first event of every attempt"); overview
Activity row ("a failure before then still stores a `reset`"); runbook ("Each attempt starts with a
`reset`"):** an Activity attempt that ends before the publisher exists stores no events at all. That
covers a fence refusal at `attempts.start` (activity.py:409-412, raised as `Superseded` before the
publisher is created at :414) and `AttemptsExhausted` (activity.py:263-264, before `_attempt`).
Version and preflight refusals are not counted as attempts, so they are not affected. Code
evidence only; I did not observe either case in the stored data.

**N3 (Nit), overview Runners row ("refused names capped at 64 characters") and schemas.md
`tool_result` row ("its name is capped at 64 characters"):** the DSH executor's refused pair is
emitted uncapped: executor.py:130-131 calls `self._emit("tool_call", name, number)` and
`self._emit("tool_result", name, number, "refused")`, and `_emit` (:171-177) does not truncate. The
gateway (gateway.py:338-339) and `openai_agents` (runner.py:201-202) cap with `[:64]`. In practice
the names that reach the executor are granted, prefixed tool names (the gateway handles ungranted
names). The doc is still more general than the code.

**N4 (Nit), docs/demos/phase-2-events.md, row "Prune and expiry", Observed:** `{"retained_base": 10}`.
The actual output also carries the task ID: `{"task_id": "task-a70928e4-...", "retained_base": 10}`
(cli.py:282; `.verify/demo/prune.json`). The quote is abbreviated, not wrong.

**U1 (Unverifiable, Nit), demo record header and observed values from the owner's run** (commit
`acd713e`, `praxismesh-worker-dsh-a-1`, task `task-f2492737-...`, versions). This needs the owner's
`praxismesh` stack, which is out of bounds. An equivalent run on `pmverify2` at 499eb63 reproduced
every step with the same event composition (D4, D5).

**U2 (Unverifiable live, confirmed by code and prior evidence), runbook `events prune` commands:**
the permission classifier denied my live no-op prune. Code (table.py:170-209), the integration
tests (test_event_table.py:135-193, 282) and the earlier demo run on this stack (`prune.json`, P4
minimum offset 10) agree with the runbook.

## Observations (not doc claims)

- `tool_result.status` uses different words for a failed tool on each runner: `openai_agents` emits
  `failed` (runner.py:225), DSH emits `error` (executor.py:149-150). The schemas table does not list
  the values, so nothing contradicts it. A consumer filtering on status would still see the
  difference.
- `tail --follow` keeps following only on `RPCError`. Any other exception from `describe()` ends
  the tail (cli.py:250-258).

## Changes made

None. I wrote no files except this report. I ran no write queries: one `events prune` invocation was
attempted, denied by the permission system, and never executed.

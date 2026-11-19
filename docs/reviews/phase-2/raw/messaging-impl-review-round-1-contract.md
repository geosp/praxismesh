<!-- Verbatim subagent report (messaging plan impl-review round 1, contract, diff 7f0ed85..dae914b); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Contract review of phase 02 (diff 7f0ed85..dae914b). I found five Major findings and a set of Nits. Most promises have code that enforces them and a test that would fail without it. The gaps are in reply routing, the R31 ending, `post_status` on `openai_agents`, the same-step ask race (R19) and `complete_task`'s retries.

## Promise map (code that enforces each promise → test that would fail without it)

| Promise | Code | Test |
|---|---|---|
| R10 / D9 request scope | messages.py:387 `_refusal` | test_messages.py:71, test_comms_mcp.py:106 |
| R11 refusal rows | messages.py:124-127, 165-168, 478-495 | test_messages.py:79-81 (cross-request row only) |
| R12 commit before success | messages.py:114-139 (returns inside `engine.begin()`) | **none** (Nit) |
| R13 dedup and one turn | idempotency_key messages.py:97; claim and read_claimed use `claimed_turn` | test_messages.py:86; test_harness_activity "woken turn ... rerun" |
| R14 / R15 / D7 claim before sleeping | workflow.py:336-352 | test_task_workflow_waiting.py:142, 173 |
| R16 reply wakes the asker | messages.py:121-139; render activity.py:506 | test_messages.py:128 — **routing gap, finding 1** |
| R17 expiry | messages.py:237-259; workflow.py:369 | test_messages.py:104; waiting.py:159 |
| R18 late reply refused | messages.py:408 | test_messages.py:117 |
| R19 / D8 finish check | tools.py:736-742; activity.py:458-469; runner.py:675-701 | test_runner_conformance.py "refused_finish" (both runners); test_harness_activity "finish_check ... tool thread" — **race, finding 4** |
| R20 idle timeout | workflow.py:358-368 | waiting.py:151 |
| R21 / R31 wall time | workflow.py:333-335, 362-376 | waiting.py:192 — **gap, finding 2** |
| R22 / D14 wake budget | workflow.py:240-258; activities.py:92-94 | waiting.py:203 |
| R23 cycles | messages.py:159-164, 412-430 | test_messages.py:157 |
| R24 / D17 an ending closes messages | messages.py:289-327; activities.py:150; workflow.py:288-290, 347-350 | test_messages.py:173, 264; waiting.py:211, 225 — **finding 5** |
| R25 ended tasks | messages.py:385-390 | test_messages.py:189-193 |
| R26 identity | server.py:293-301 | test_comms_mcp.py:114 (weak, Nit) |
| R27 fence | messages.py:355-363; server.py:332 | test_messages.py:196 |
| R28 IDs only | InboxClaim; Signal takes no args | test_messages.py:237 (claim result only, Nit) |
| R29 / D12 replay | workflow.py:93-94 | test_task_workflow.py:228 (unchanged) |
| R30 undelivered | messages.py:318-324, 340-346 | test_messages.py:183, 191 |
| R32 / D18 outputs | activity.py:587, 663; workflow.py:285-286 | test_harness_activity "lost waiting turn keeps outputs" (Workflow side untested, Nit) |
| R33 / D11 bounded runs | workflow.py:327-332 | waiting.py:238 |
| D5 `--join` | cli.py:89-91; submit.py:45 | test_cli.py, test_submit.py |
| D6 dispatcher | dispatcher.py | test_dispatcher.py |
| D13 role | migration 0006, roles.sh | test_comms_role.py |
| D15 status events | executor.py:150-151; runner.py:666-667 | **finding 3** |

## Major

**1. A reply's recipient is never checked against the question's asker (R16, R11, D8).**
- Where: `common/persistence/messages.py:121-139` and `_question_for_reply` at 393-410.
- What: `send(..., recipient, reply_to=q)` checks only that the question was addressed to the replier. It does not check that `recipient` is the asker.
- Scenario: A asks B (q1) and waits. B calls `send_to_agent(task_id=C, text="12.50", reply_to=q1)`, where C is a third task of the request.
  - q1 becomes `answered` (line 134-137) and the reply row goes to C.
  - A's claim finds nothing, because only `expired`/`cancelled` asks get a notice (line 253-256). A sleeps until its idle timeout and ends `succeeded` without the answer.
  - C's `blocking_finish` now reports "unread reply from B" (line 216), so C cannot finish until it waits.
- Test that would expose it: a repository test where a reply with `recipient != question.sender_task` should be refused and stored as `rejected` (or routed to the asker).

**2. If the wall time is already spent when a `waiting` turn returns, the task succeeds even with an open question (R31, D7).**
- Where: `orchestrator/workflow.py:333-335` calls `_out_of_wall_time(None)` before any claim, so open questions are never looked at.
- Why it is reachable: each attempt is bounded by `turn.remaining_wall_time` (`activity.py:389-390`), but every retried attempt gets the same remaining time, and `schedule_to_close` is `turn_timeout * 6`.
- Scenario: 10 minutes of wall time are left. Attempt 1 is lost at minute 9. Attempt 2 runs about 10 minutes, calls `ask_agent`, then `finish_task("waiting")`. The Workflow returns `succeeded`. R31 says: "completes `failed` with 'wall-time budget exhausted'".
- Test that would expose it: a time-skipping test whose fake `run_harness_turn` sleeps past `max_wall_time` and returns `waiting`, with a claim returning a far `next_deadline`; expect `failed`. A fix needs the open-question state (for example one final claim) before deciding.

**3. `post_status` never becomes a `status` event on `openai_agents` (D15; task 3.2).**
- Where: `harness_activity/runner.py:666-667` passes `str(result)` to `emit_agent_status` (`events.py:612-618`).
- Why it fails: for an MCP tool, agents 0.24 hands `on_tool_end` the raw `ToolOutputTextDict` `{"type": "text", "text": "{...}"}` (`.venv/.../agents/mcp/util.py:800-819`; `run_internal/tool_execution.py:2192`). Its `str()` is a Python repr with single quotes, so `json.loads` raises and the function returns silently. Even if it parsed, the dict has no `stage` key.
- DSH works: `executor.py:162` joins the content text into JSON.
- Observability: `test_a_status_result_becomes_a_status_event` calls `emit_agent_status` with a hand-made JSON string, so it cannot see this. Task 3.2 asked for conformance tests "on both runners ... for a `status` event".
- Test that would expose it: a parametrized conformance test that has the fake model call `post_status` through the real `comms` server and asserts a `status` event with a `stage`.

**4. On `openai_agents`, an ask in the same model step can miss the finish check (R19, D8).**
- D8 promises the check runs "under the request lock so an ask in the same model step is seen". The lock makes each check atomic but does not order it against the ask.
- Why it fails: `openai_agents` runs one response's tool calls concurrently (sync tools via `asyncio.to_thread`; `parallel_tool_calls` is not disabled in `runner.py`).
- Scenario: the model emits `[ask_agent(B), finish_task("done")]`. The `finish_task` thread takes the request lock (`messages.py:208-209`) before the comms subprocess commits the ask. The check returns `[]`, the finish is accepted, and the task ends `succeeded` with a question it just asked. `end_task` then cancels it.
- DSH is not affected: `executor.py:121` serializes calls.
- Test that would expose it: a conformance test against the real database check, with a single response containing both calls; expect a refusal.

**5. `complete_task` does not retry long enough for an ending during a database outage (R24 "by any path", D17, Risks).**
- Where: `workflow.py:386-406` uses `SHORT_RETRY` (5 attempts). The Risks section says a long outage "leaves such tasks `failed` once it returns".
- Scenario: the database is down for more than about 15 s when a task ends (idle timeout, budget, cancel, or a failed claim at the wall deadline).
  - `complete_task` fails 5 times and the Workflow fails. `end_task` never runs.
  - The `tasks` row stays `running`, so sends to it keep being accepted.
  - Its pending messages are never marked `undelivered`, and askers learn nothing until their own deadlines.
- Test that would expose it: a time-skipping test whose fake `complete_task` fails N > 5 times and then succeeds; expect a completed result. A fix would be unlimited retries bounded by a long `schedule_to_close`.

## Nits (one line each)

- `orchestrator/dispatcher.py:43-45`, `workers/main.py:196-198` (R14, D6): if the first `engine.connect()` fails, the dispatcher task dies silently and nothing restarts it, so no wakes for that process. Rated Nit because Compose waits for a healthy `db`; it can still happen on host runs or a restart race.
- R12: no test where the database fails during a send; the code (return inside `begin()`) does enforce it.
- `tests/integration/test_comms_mcp.py:124` (R26): `senders <= {a}` also passes when nothing was stored; assert that one row exists with sender `a`.
- R28: the "three 16 KB messages, inspect history" scenario is untested (only the claim result is checked), and phase 03 does not list R28.
- R32: the Workflow tests' fake `TurnOutcome` has no outputs, so dropping `run.outputs` at `_complete` would go unnoticed.
- R20: the 60-65 s completion window is not asserted.
- R22 / D14: "a `continue` after a woken turn counts against `max_turns`" has no test.
- R17 / R24: `render_inbox` text for expired and cancelled questions (`activity.py:494-500`) is untested.
- R11: rejected rows are asserted only for cross-request refusals, not for cycle, ended-task or closed-question refusals.
- `workflow.py:250-253` (R21): a woken turn that reaches the wall deadline ends `failed` even with no open question. It is an edge case and arguably the task is no longer "waiting".
- `messages.py:318-324` (R30): rows a woken turn marked `read` before failing for good stay `read`, not `undelivered`, though the model may never have seen them.
- `messages.py:378` and the migration's `length(body) <= 16384` count characters, not bytes; D6 says "at most 16 KB".
- `comms_mcp/server.py:346`: `deadline_seconds=0` silently becomes 300, and a negative value gives a deadline already in the past (no lower clamp).
- `messages.py:499`: the comment says the comms role cannot read wake rows, but migration `GRANTS` gives it `SELECT` on `message_wakes`.
- Migration 0006: grants `task_inbox` `SELECT` only, where notes.md#d6 says `SELECT, INSERT, UPDATE`. More restrictive and works.
- `infra/docker-compose.yml`: `roles.sh` is mounted at `/usr/local/bin` and called from `init.sh`, not mounted as `/docker-entrypoint-initdb.d/21_roles.sh` as task 2.1 and the notes say. Same effect.
- `plan.md` Phases table shows `0/15` while all 15 tasks are checked.
- `workflow.py:107-112, 218-223` (R24): a cancel that lands while `record_task` is in flight leaves the run outside the `try`, so the row can stay `running` with no `end_task`. Narrow window; Phase 1 had the same behaviour.
- R33: between a Signal and the next claim, `sleeping` is still true, so further sends add new wake rows and more Signals. The per-turn scenario still holds.
- `messages.py:240` vs `workflow.py:369`: expiry uses `deadline < now`, and the timer fires exactly at the deadline, which costs one extra claim. Harmless.

Files: /home/geo/develop/praxismesh/common/persistence/messages.py, /home/geo/develop/praxismesh/orchestrator/workflow.py, /home/geo/develop/praxismesh/harness_activity/runner.py, /home/geo/develop/praxismesh/harness_activity/events.py, /home/geo/develop/praxismesh/harness_activity/tools.py, /home/geo/develop/praxismesh/orchestrator/dispatcher.py, /home/geo/develop/praxismesh/comms_mcp/server.py, /home/geo/develop/praxismesh/tests/test_task_workflow_waiting.py, /home/geo/develop/praxismesh/tests/test_runner_conformance.py

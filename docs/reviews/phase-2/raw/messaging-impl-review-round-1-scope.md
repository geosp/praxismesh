<!-- Verbatim subagent report (messaging plan impl-review round 1, scope and composition, diff 7f0ed85..dae914b); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

## Scope review: Phase 02 (Inbox, comms MCP and waiting tasks), diff 7f0ed853..dae914b5

I found 5 Major findings and 14 Nits. I ran nothing; this is from reading the code only. Finding 1 relies on the installed openai-agents SDK source in `.venv`, which I read but did not execute.

### Major

**1. openai_agents never publishes `post_status` as a `status` event (D15; task 3.2)**
- **Location:** `harness_activity/runner.py` `_Hooks.on_tool_end` (`emit_agent_status(self.events, str(result))`), and `harness_activity/events.py` `emit_agent_status` (`json.loads(result)`).
- **How it breaks:** The runner builds `MCPServerStdio` without `use_structured_content` (runner.py:269-275).
  - In that case the SDK hands back an MCP tool's result as a `ToolOutputTextDict` dict, `{"type": "text", "text": "<json>"}`. See `.venv/.../agents/mcp/util.py:797-819`. That dict is the `final_result` that reaches `on_tool_end`.
  - `str()` of the dict is a Python repr with single quotes. `json.loads` raises `ValueError`, and `emit_agent_status` returns silently.
  - Even if it parsed, the top-level keys would be `type` and `text`, not `stage`.
- **Scenario:** An `openai`-profile task calls `post_status(stage="working", progress=40)`. The tool succeeds, but no `status` event is stored. The DSH path works because the executor joins the content text into a JSON string (dsh/executor.py `_run`).
- **Test gap:** Task 3.2 says "conformance tests on both runners ... for a `status` event". The only test is `tests/test_runner_conformance.py::test_a_status_result_becomes_a_status_event`, a unit test that feeds raw JSON into `emit_agent_status`, so it misses this.
- **Test that would expose it:** a conformance test that runs the comms server through `OpenAIAgentsRunner` with the fake model calling `post_status`, then asserts a `status` event.

**2. The finish check does not see an ask made in the same model step on openai_agents (R19, D8)**
- **Location:** `harness_activity/tools.py` `finish_task_body`; `harness_activity/runner.py` `_stop_on_accepted_finish`.
- **How it breaks:** D8 says the check runs "under the request lock so an ask in the same model step is seen". The lock makes the check atomic but does not order it.
  - openai_agents runs one response's tool calls concurrently: function tools through `asyncio.to_thread`, MCP tools as separate coroutines.
  - If `finish_task("done")` reaches the request lock before `ask_agent` commits, the check returns `[]`, the finish is recorded, and the run stops once the step's tools complete.
  - If the model lists `finish_task` before `ask_agent`, it is accepted however the calls are scheduled.
  - DSH is safe: `Executor.call` serialises calls under `self.lock`, and sets `self.finished` so a later ask is refused.
- **Scenario:** A's model emits `ask_agent(B, "price?")` and `finish_task("done")` in one response on the `openai` profile. Finish wins the lock, so A completes `succeeded`. `end_task` then cancels A's question ("asker ended"), and B's reply is refused. R19's "a task with open questions cannot finish" is broken.
- **Test gap:** `test_a_refused_finish_lets_the_model_wait` uses a fake `finish_check` lambda, and no test puts an ask and a finish in one step.
- **Test that would expose it:** an openai_agents conformance test with the real comms server where one fake-model response holds both calls, in both orders. Assert the result is not `done`.

**3. `complete_task` gives up after 5 attempts, so a long database outage leaves the task `running` with its questions open (D17, R24, Risks)**
- **Location:** `orchestrator/workflow.py` `_complete` (`retry_policy=SHORT_RETRY`, `maximum_attempts=5`).
- **How it breaks:** The Risks section promises that after a long outage "the task ends through `complete_task` ... so a long outage leaves such tasks `failed` once it returns". D17 says the Workflow runs `complete_task` on every ending.
  - The claim retries until the wall-time deadline (D7) and then returns "inbox unavailable".
  - `complete_task` then has only about 15 s of backoff before the ActivityError fails the Workflow execution, so `end_task` never runs.
- **Scenario:** The database is down for 20 minutes while A waits, and A's wall time runs out during the outage.
  - The claim fails for good, and `complete_task` fails 5 times. TaskWorkflow fails and `tasks.status` stays `running`.
  - B's question to A stays open until its deadline instead of being cancelled, and B is not woken by A's end.
  - Sends to A are still accepted (R25 in effect), and A's messages never become `undelivered` (R30).
- **Test gap:** `test_a_claim_that_keeps_failing_ends_the_task_through_complete_task` lets `complete_task` succeed on the first try.
- **Test that would expose it:** the same test with `complete_task` failing for more than 5 attempts and then succeeding. Assert the Workflow still completes through it.

**4. The wall-time check at the top of `_wait` treats every task as having no open question, so R31 can end as `succeeded` (R31, R21)**
- **Location:** `orchestrator/workflow.py` `_wait`: `if remaining <= timedelta(0): return self._out_of_wall_time(None)`.
- **How it breaks:** The last claim's `next_deadline` is known but dropped, so this path always returns `succeeded`. It is reached in three ways:
  - (a) An `inbox` Signal and the wall-time timer land in the same workflow task. `wait_condition` returns on the condition, with no TimeoutError, the loop restarts, and `remaining <= 0`.
  - (b) A `waiting` turn returns at or after `run.deadline`.
  - (c) A continued run starts right at the deadline.
- **Scenario:** A has an open question to B (deadline far away). A Signal arrives as A's wall time ends. A completes `succeeded` instead of `failed, "wall-time budget exhausted"`.
- **Related edge in the main loop:** after a claim that returned rows, `remaining_time <= 0` gives `failed, "wall-time budget exhausted"` even with no open question, the opposite error for R21.
- **Test gap:** `test_out_of_wall_time_ends_by_open_questions` only covers the timer path.
- **Test that would expose it:** a time-skipping test that signals at `run.deadline` with an open question, or a turn fake that returns `waiting` after the deadline. Assert `failed`.

**5. A dispatcher that fails at startup or outside `drain` is never restarted (D6, R14, Risks)**
- **Location:** `workers/main.py` (`asyncio.create_task(Dispatcher(make_engine(), client).run())`, never awaited or supervised) and `orchestrator/dispatcher.py` `run`. Only `drain()` sits inside the try/except; `engine.connect()`, `get_raw_connection` and `add_listener` do not.
- **How it breaks:** D6 promises a loop that "polls every 1 s", and Risks says "the dispatcher is down → wake rows wait for it". That holds only for errors inside `drain`.
- **Scenario:** The database is unreachable for a moment when the orchestrator worker starts.
  - `run()` raises, and the task dies with "Task exception was never retrieved". The worker keeps serving Workflows with no dispatcher for the rest of its life.
  - Every sleeping task with no open question then ends `succeeded` at its idle timeout, and the messages sent to it become `undelivered`. R14 fails silently.
- **Test that would expose it:** start `Dispatcher.run()` against an engine that refuses the first connect, then make it available and assert a wake row is delivered.

### Nits
- **`common/persistence/messages.py` `_by_key` before `_refusal` (R13, R11):** A refusal is cached under the idempotency key for the whole turn. An identical retry later in the turn gets the stale refusal: for example "would deadlock" after the cycle cleared, or "not a task of this request" for a task that joined since.
- **`messages.py` `MAX_BODY` / migration `length(body) <= 16384` (D6):** The limit counts characters, not bytes. The plan says "at most 16 KB", so multibyte text can be up to about 64 KB per row.
- **`comms_mcp/server.py` `ask_agent` (D8):** `deadline_seconds` is not validated. A negative value gives a deadline in the past, and the tool still tells the model to wait. A value of 0 silently becomes 300.
- **`messages.py` `claim` vs `_question_for_reply`, `blocking_finish` and `_waits_on` (D7):** Expiry uses the Workflow's `now`, while the rest uses the database's `now()`. Plan notes accept this, but under time skipping the two disagree. Also, a timer firing exactly at `deadline == now` is not expired (`<`), giving a zero timeout and an extra claim.
- **`workflow.py` `_wait` idle branch (R20):** An idle timeout ends the task without a final claim. A message that commits while the Signal races the timer becomes `undelivered` rather than waking the task.
- **`workflow.py` `_wait` claim (R21):** A claim that fails because `schedule_to_close=remaining` ran out returns `failed, "inbox unavailable"` even with no open question.
- **`messages.py` `_wake_if_sleeping` (R33, D6):** `sleeping` stays true until the next claim. After the dispatcher deletes a wake row, each later send during the same sleep adds another wake and Signal. This is bounded but more than one per sleep. It is only tested at the repository level (`test_only_a_sleeping_recipient_is_woken_once`).
- **`orchestrator/dispatcher.py` `drain` (D6):** It returns when a full batch had no successes, and failed rows are re-selected first (`ORDER BY id`). 50 rows that keep failing would block later rows. The multi-batch path is untested.
- **`tests/integration/test_dispatcher.py::test_a_wake_for_a_closed_workflow_is_deleted_and_logged` (D6, task 4.5):** It only uses a never-started workflow, not a completed one, which is the "closed" case the task names.
- **`tests/test_task_workflow_waiting.py::test_woken_turns_have_their_own_budget` (R22):** It tests 4 wakes with `max_turns` 1, not the plan's 20 wakes with `max_turns` 6. No test checks that `wakes`, `work_turns` or `deadline` survive Continue-As-New: the 100-wake test only checks `turns`.
- **`tests/integration/test_harness_activity.py::test_a_woken_turn_runs_the_model_with_its_messages` (R13 second scenario):** The "rerun" calls `read_claimed` directly with attempt 1. It does not exercise attempt 2 through the Activity, restoring from turn 1's checkpoint.
- **`tests/integration/test_comms_mcp.py::test_the_sender_is_always_the_calling_task` (R26):** `assert senders <= {a}` also passes when nothing was stored, for example if the extra `sender` argument rejects the call.
- **R12 and R28:** I found no test where the database fails during a send. I also found no history-inspection test with three 16 KB messages. These may be meant for phase 03; please confirm.
- **`migrations/versions/0006_task_messages.py` GRANTS:** `task_inbox` is granted `SELECT` only, but notes.md#d6 says `SELECT, INSERT, UPDATE`. The code only needs `SELECT`, so the docs and the code differ.

### Files
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/orchestrator/dispatcher.py
- /home/geo/develop/praxismesh/workers/main.py
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/harness_activity/runner.py
- /home/geo/develop/praxismesh/harness_activity/events.py
- /home/geo/develop/praxismesh/harness_activity/tools.py
- /home/geo/develop/praxismesh/comms_mcp/server.py
- /home/geo/develop/praxismesh/tests/test_task_workflow_waiting.py
- /home/geo/develop/praxismesh/tests/test_runner_conformance.py

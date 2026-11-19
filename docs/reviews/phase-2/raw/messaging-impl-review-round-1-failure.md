<!-- Verbatim subagent report (messaging plan impl-review round 1, failure and retry, diff 7f0ed85..dae914b); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

## Failure-lens review: Phase 02 (inbox, comms MCP and waiting tasks), diff 7f0ed85..dae914b

I found 4 Major findings and 9 Nits. Everything below is from reading the code at dae914b. I ran no tests or builds.

### What I traced

- **`TaskWorkflow._run_v2` and `_wait`** (`orchestrator/workflow.py`), in order: resolve_capabilities → record_task → [turn → (waiting) → continue-as-new check → `woken=False` → claim_inbox → wait_condition → claim …] → complete_task.
- **`claim_inbox` and `MessageRepository.claim`**: request lock → expire → claim pending rows → set notice_turn → select IDs → find min deadline → upsert task_inbox, all in one transaction.
- **`complete_task`**: ledger → `close_unfinished` (its own transaction) → `end_task` (its own transaction: tasks status, cancel questions, mark undelivered, wake askers).
- **`run_harness_turn` restore path**: `checkpoints.latest` → finish short-circuit (same turn only) → `read_claimed` (fenced; marks rows read) → model → finish checkpoint → outputs.
- **comms_mcp `send` / `ask`**: task lock → fence → request lock → lookup by key → refusal checks → insert → wake row and NOTIFY.
- **`Dispatcher.run` / `drain`**: LISTEN → loop { select up to 50 rows FOR UPDATE SKIP LOCKED → one Signal per row → DELETE the delivered IDs → commit }.

Helpers I read rather than assumed:
- `fence.py` TASK_LOCK and NO_NEWER_ATTEMPT (`common/persistence/fence.py`).
- `wait_set` (`common/events/transport.py:20-31`).
- openai-agents runs sync tools via `asyncio.to_thread` (`.venv/.../agents/tool.py:2830`), and DSH does the same (`harness_activity/dsh/executor.py:166`). So `finish_check` calling `run_coroutine_threadsafe(...).result()` cannot deadlock the loop.
- `AttemptRepository.start` is fenced and runs before the MCP servers start (`harness_activity/activity.py` `_attempt`).

These paths hold up:
- A claim rerun returns the same IDs.
- A rerun of a woken turn re-reads the same rows: `read_claimed` selects by `claimed_turn` with no status filter.
- An identical repeated send is deduplicated under the task lock.
- A stale attempt is fenced, and once its task has ended its sends are refused by the sender-status check.
- `end_task` is idempotent on retry.
- A Signal lost across continue-as-new is covered because the new run claims first.
- A cancel during a turn, a claim or a sleep reaches `_complete`.

### Major

**M1. The dispatcher can drop a wake: a send that lands during a drain is swallowed, then the old row is deleted.**
- **Location:** `orchestrator/dispatcher.py:62-79` together with `common/persistence/messages.py` `_wake_if_sleeping` (`ON CONFLICT (recipient_workflow) DO NOTHING`).
- **Concerns:** R14, R15, D6.
- **Scenario:**
  1. Task B's claim finds nothing and sets `sleeping=true`. Message A commits and inserts wake row W.
  2. Before the dispatcher delivers W, B claims for another reason (a question-deadline timer, or the dispatcher was down, as in the Risks section). That claim takes A and runs a turn. The turn ends `waiting`, and the next claim finds nothing and sets `sleeping=true` again. W is now stale.
  3. A drain selects W, possibly as row 1 of 50, holds it FOR UPDATE and Signals B.
  4. B claims, finds nothing and sleeps.
  5. Message B2 now commits. Its wake insert conflicts with W, which is committed and only row-locked, so DO NOTHING does not wait.
  6. The drain then runs `DELETE ... WHERE id = ANY(:ids)` and removes W.
  7. B2 is pending with no wake row. B sleeps until its idle timeout, ends `succeeded`, and `end_task` marks B2 `undelivered`.
- **Why the window is real:** it is the whole span of the batch's Signal RPCs before the single DELETE (`dispatcher.py:73-77`).
- **Possible fix:** delete each row before signaling (`DELETE ... RETURNING` in the transaction, roll back if the Signal fails), so a concurrent insert blocks and then adds a fresh row. Alternatively, have the claim delete the task's wake row.
- **Test:** an integration test with a stub client whose `signal()` runs a claim (finds nothing) and then a send to the same recipient. After `drain()`, assert a wake row exists for the recipient. Today none does.

**M2. If the database is still down when a task ends, it is never marked ended: complete_task gives up after 5 attempts.**
- **Location:** `orchestrator/workflow.py` `_complete` (uses `SHORT_RETRY`, `maximum_attempts=5`, `workflow.py:43`); `_run_v2` does not catch its failure.
- **Concerns:** R24, D17, and the plan's Risks section.
- **Scenario:**
  1. The database goes down while A waits on a question to B.
  2. A's claim retries until A's wall-time deadline (`schedule_to_close_timeout=remaining`), then `_wait` returns `failed`, "inbox unavailable".
  3. `complete_task` fails 5 times within about 15 s plus the start-to-close timeouts. The ActivityError escapes `run`, so the Workflow execution fails.
  4. The `tasks` row stays `running`. A's questions stay open, waiters are never woken, and sends to A are accepted.
- **Why it contradicts the plan:** the Risks section says "past it, the task ends through `complete_task` ... so a long outage leaves such tasks `failed` once it returns". The code leaves them `running` permanently.
- **Wider effect:** the same applies to every v2 ending (done, budget, cancel) during an outage longer than about 15 s.
- **Related gap:** a cancel delivered while `complete_task` is scheduled or in retry backoff (default TRY_CANCEL) cancels it, and it is never rerun.
- **Possible fix:** give `complete_task` an unlimited-attempt retry policy (it is idempotent: `end_task` re-applies cleanly). Also catch `CancelledError` around `_complete` and run it again.
- **Test:** a time-skipping test where the fake `complete_task` fails 6 times and then succeeds. Assert the Workflow still records the completion. Add a variant that cancels during `complete_task`'s backoff.

**M3. The dispatcher dies silently if its first connection fails, and never restarts.**
- **Location:** `workers/main.py` (`asyncio.create_task(Dispatcher(...).run())`, never awaited or supervised); `orchestrator/dispatcher.py:43-46` (`engine.connect()` and `add_listener` sit outside the retry loop).
- **Concerns:** D6, R14.
- **Scenario:**
  1. The orchestrator worker starts while Postgres is restarting. `engine.connect()` raises.
  2. The dispatcher task finishes with an unobserved exception. No log appears until garbage collection or exit.
  3. The worker keeps serving Workflows. Every wake row piles up.
  4. Sleeping tasks wake only on deadlines and idle timeouts, so idle tasks end `succeeded` with their messages `undelivered`.
- **Why it contradicts the plan:** the Risks section assumes "wake rows wait for it", meaning the dispatcher comes back. Here it never does until the worker restarts.
- **Contrast:** once running, a dropped LISTEN connection is harmless, because `drain` uses pooled connections and the 1 s poll continues.
- **Possible fix:** wrap the connect-and-listen block in the retry loop, or supervise the task and exit the worker when it dies.
- **Test:** start `Dispatcher.run()` with an engine whose first connect raises. Assert it retries, then delivers a wake once the database is reachable.

**M4. At the wall-time deadline, the ending ignores open questions when a Signal or a claim with rows arrives first.**
- **Location:** `orchestrator/workflow.py` `_wait`, the top of the loop: `if remaining <= timedelta(0): return self._out_of_wall_time(None)`. Also `_run_v2`'s `remaining_time <= 0` check, which returns "wall-time budget exhausted".
- **Concerns:** R21, R31 (owner decisions).
- **Scenario 1 (R31):**
  1. A waits with an open question whose deadline is after the wall-time deadline.
  2. An `inbox` Signal arrives in the same activation as, or just after, the wall-time timer, so `wait_condition` returns normally instead of raising `TimeoutError`.
  3. The loop restarts with `remaining <= 0` and A ends `succeeded`. R31 requires `failed`, "wall-time budget exhausted".
- **Scenario 2:** the same applies after continue-as-new, or when a turn's finish handling crosses the deadline.
- **Scenario 3 (R21):** a claim that returns rows just before the deadline reaches `_run_v2`'s check and ends `failed`, even with no open question.
- **Window:** narrow (a Signal or claim landing at the deadline). The status is still wrong, and it contradicts an explicit owner decision.
- **Test:** a time-skipping test where the wall-time timer and an `inbox` Signal coincide while the last claim reported a `next_deadline`. Assert the result is `failed`.

### Nits

- **`_run_v2` before `try` (resolve_capabilities, record_task) (R24):** a cancel that lands while `record_task` runs ends the Workflow without `complete_task`. If the row committed, it stays `running` with no `end_task`. The window is small and Phase 1 had the same gap, but R24 says "any path".
- **`_wait`, claim `schedule_to_close_timeout=remaining` (R21):** a claim scheduled moments before the deadline times out and ends `failed`, "inbox unavailable", instead of the R21/R31 ending by open questions. The Risks section accepts `failed` for an outage, but not for a tiny remainder.
- **`messages.py` `_by_key` returns stored rejections (R11, R13):** a refusal that was transient within a turn ("not a task of this request" while a `--join` peer has no row yet, a cycle that later clears) is replayed for identical retries for the rest of the turn.
- **`messages.py` `read_claimed` marks rows `read` before the model runs (R30):** if that woken turn then fails for good, the rows stay `read`, never become `undelivered`, and senders' `get_task_context` does not list them. This is consistent with notes.md's definition of `read`, so I rate it a Nit.
- **`comms_mcp/server.py` `ask_agent` (D8):** `deadline_seconds=0` silently becomes 300. A negative value gives a deadline in the past, so the question is stored already closed. There is no validation.
- **`orchestrator/workflow.py` `_complete` with continue-as-new (D11):** `tasks.run_id` keeps the first run's ID after continue-as-new, because `record_task` is skipped. It is informational only, but it goes stale.
- **`0006_task_messages.py` GRANTS (D6):** `task_inbox` gets `SELECT` only, where notes.md#d6 says `SELECT, INSERT, UPDATE`. That is fewer privileges and the code needs only SELECT, but it differs from the plan text.
- **`dispatcher.py` `run`, `finally: remove_listener` (D6):** after a database restart the listener connection is dead, so this can raise and replace the `CancelledError` at shutdown. The only effect is cosmetic shutdown noise.
- **`messages.py` claim `deadline < :now` versus timer, and `wait_condition(timeout=0)` (R17):** a question due at exactly `now`, or a past `next_deadline` from a claim whose `now` was fixed at schedule time across retries, yields a zero timeout and an extra claim round trip. I checked that it terminates, because `workflow.now()` advances per activation. Noted only as extra history events.

### Tests that would expose the Major findings

| Finding | Test |
| --- | --- |
| M1 | `tests/integration/test_dispatcher.py`: a send during a drain leaves a wake row |
| M2 | `tests/test_task_workflow_waiting.py`: `complete_task` fails more than 5 times, and a cancel during `complete_task` |
| M3 | A dispatcher unit test with a failing first connect |
| M4 | `tests/test_task_workflow_waiting.py`: a Signal coinciding with the wall-time deadline while a question is open |

Files referenced:
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/orchestrator/dispatcher.py
- /home/geo/develop/praxismesh/orchestrator/activities.py
- /home/geo/develop/praxismesh/workers/main.py
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0006_task_messages.py
- /home/geo/develop/praxismesh/comms_mcp/server.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/tests/test_task_workflow_waiting.py
- /home/geo/develop/praxismesh/tests/integration/test_dispatcher.py

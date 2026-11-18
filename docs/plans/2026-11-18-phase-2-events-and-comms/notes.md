# Notes · Phase 2 messaging - comms MCP, inbox and waiting tasks

The event table, publisher and `agentctl tail` are in the events plan
(`docs/plans/2026-11-18-phase-2-agent-events/notes.md`).

## Evidence from the code (2026-11-18, main at 73801ea)

- Events: `harness_activity/events.py` has `EventSink`, `NoOpSink`, `MemorySink` and `AttemptEvents`
  (per-attempt `seq`, emission under a lock). Only the DSH runner emits: tool events
  (`harness_activity/dsh/executor.py`), one `token` event per response and refused-tool events
  (`gateway.py`). `DshRunner` builds its own `AttemptEvents` from a per-worker sink that defaults to
  `NoOpSink` (`harness_activity/dsh/runner.py:238`, `:360`); `workers/main.py` passes none.
  `openai_agents` emits none. `HarnessRunner.run` takes no events argument (`harness_activity/runner.py`).
- `AgentEvent` (`common/schemas/events.py`): `seq`, timestamp, workflow, task, `attempt_id`
  (`task:turn:attempt`), type, content-free payload, optional `blob_ref`.
- Fence: `common/persistence/repositories.py` `_TASK_LOCK` (`pg_advisory_xact_lock(hashtext(task))`)
  and `_NO_NEWER_ATTEMPT`, used by `AttemptRepository.start`, `assert_current` and
  `CheckpointRepository.insert_fenced`; the Activity turns `FenceRejected` into `Superseded`.
- `TaskWorkflow` (`orchestrator/workflow.py`): runs turns until `done`, `needs_input` or a budget
  (`max_turns` is `min(profile, template cap)`, 6 and 10 today); no Signals, no Continue-As-New.
  `TurnOutcome`, `RunResult` and `AttemptOutcome` statuses lack `waiting`.
- Restore (`harness_activity/activity.py` `_run`): the newest checkpoint of the task, across turns; a
  checkpoint with a finish report short-circuits the model; otherwise the input is `CONTINUE_MESSAGE`.
- MCP servers are stdio subprocesses the worker starts per attempt for both runners
  (`harness_activity/config.py`, `harness_activity/dsh/executor.py`, `MCP_CALL_TIMEOUT_S = 120`); they
  get `PRAXIS_TASK_ID` and template-granted secrets only. DSH reaches them through one bridge
  (`infra/dsh/mcp_bridge.py`, 150 s timeout). `sample_mcp` keys idempotency on task, tool and arguments.
- Every `task submit` makes a new `request_id` (`orchestrator/submit.py`); the CLI's `--request` is a
  JSON request file (`orchestrator/cli.py`). No tenant field exists.
- A worker loads one version per template and refuses turns for another (`registry/loader.py`,
  `harness_activity/activity.py`).
- The fake model (`tests/support/fake_model/`) serves one script, stepping by tool-result count.
- Replay: `tests/test_task_workflow.py` replays `tests/fixtures/task_workflow_history.json`.

## D6 · Messages, wake rows and the comms role

Migration 0006:

- `agent_messages (message_id PK, request_id, sender_task, recipient_task, kind send|ask|reply,
  correlation_id, reply_to, deadline, status pending|claimed|read|answered|expired|cancelled|
  undelivered|rejected, reason, body text (<= 16 KB), idempotency_key UNIQUE, claimed_turn, created_at)`.
  A claimed row becomes `read` when the woken turn's Activity has rendered it into the turn input.
- `message_wakes (id, recipient_workflow, created_at)`. Each insert runs `NOTIFY message_wakes` in the
  same transaction. The dispatcher selects rows `FOR UPDATE SKIP LOCKED` (several orchestrator replicas
  are safe), Signals `inbox`, and deletes a row once the Signal returns, or on "workflow not found" or
  "already completed" (with a log line). Any other error leaves the row for the next poll.
- Role: `infra/db/roles.sh` runs as the database superuser, creates `praxis_comms` if missing (password
  from `PRAXIS_COMMS_DB_PASSWORD`), and grants it `CONNECT` on `praxismesh` and `USAGE` on `public`
  (`init.sh` revokes `CONNECT` from `PUBLIC`). `init.sh` calls it on a fresh volume; operators run it
  once on an existing one (`make db-roles`). Migration 0006, run as the app role that owns the
  tables, grants `SELECT, INSERT, UPDATE` on `agent_messages`, `INSERT` on `message_wakes`, `SELECT` on
  `tasks` and `task_attempts`, and revokes them on downgrade.
- Idempotency key: sha256 of sender task, turn, tool name and canonical arguments. Attempts of one turn
  share it, so a retried attempt that repeats a send stores nothing new and gets the stored result. A
  regenerated send (different text) is a new message.
- Locks (D10): sender `_TASK_LOCK` and the fence check, then `pg_advisory_xact_lock(2, hashtext(request_id))`
  (task locks use the one-key form, so the namespaces differ). Recipient status (R25), the cycle walk
  (R23) and `end_task` (R24, R30) read and write under the request lock. `end_task` takes only the
  request lock (it is not an attempt write).
- Cycle walk (R23): from the recipient, follow its open questions' recipients, breadth first, within
  the request; reaching the asker refuses the ask.

## D7 · Claim, restore and the wait loop

- `claim(task, turn, now)`, in one transaction under the request lock: mark the task's questions with
  `deadline < now` `expired`; set `claimed_turn = turn` on pending rows for the task (messages, replies,
  and its own questions now expired or cancelled); return their IDs, the count, and the earliest
  deadline of its open questions. A rerun for the same turn returns the same IDs. `now` is
  `workflow.now()`, so expiry and the Workflow's timers agree under time skipping; `reply` and
  `open_questions` use the database clock and also treat a passed deadline as not open.
- `read_claimed(task, turn)`: the woken turn's Activity reads the bodies and marks them `read`.
- Restore: the finish short-circuit applies only to a checkpoint of the same turn. A woken turn's input
  lists its rows (sender, kind, correlation ID, body) instead of `CONTINUE_MESSAGE`.
- Wait loop, after a `waiting` outcome: claim; a count above zero runs the woken turn now; otherwise
  sleep on `workflow.wait_condition(lambda: woken, timeout=...)` until the earliest of the returned
  deadline, the idle timeout (only with no open question) and the wall-time deadline; clear `woken`;
  claim again. Because the loop always claims before it sleeps, a Signal that arrived during a turn is
  covered by the claim; the flag only ends a sleep early.
- Endings: idle timeout -> `succeeded` (R20); wall time -> `succeeded` (R21) or `failed` (R31) by open
  questions; `max_wakes` reached -> `failed` "wake budget exhausted"; `CancelledError` caught in the
  wait -> `failed` "cancelled", after `complete_task`. Every ending runs `complete_task`, which runs
  `end_task`. The result's artifacts are the latest `waiting` turn's outputs.
- `TaskState`: resolved task, turn and wake counters, usage totals, wall-time deadline, latest outputs
  and summary. `run(start, state=None)`: a continued run skips `resolve_capabilities` and
  `record_task` (which refuses a new run ID) and claims first. The patch marker and the optional
  argument keep Phase 1 histories replaying.

# Notes · Phase 2 - real-time events and the comms MCP

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

## D1 · Event tables

Migration 0005, in the app database (the spike's `spike76` schema is not reused):

- `event_logs (workflow_id PK, next_offset bigint default 1, retained_base bigint default 1)`.
- `agent_events (workflow_id, "offset", task_id, attempt_id, seq, type, payload jsonb, blob_ref jsonb,
  emitted_at, stored_at; PK (workflow_id, "offset"))`. Columns mirror `AgentEvent`.
- `event_batches (workflow_id, batch_id, seen_at; PK (workflow_id, batch_id))`. Each publish deletes
  that workflow's rows older than 600 s (the spike's re-send horizon).
- `NOTIFY agent_events, <workflow_id>` per batch; following readers `LISTEN`, clear their wake-up before
  each fetch and poll every 1 s (spike `table.py`).
- `LISTEN` needs a raw asyncpg connection from the SQLAlchemy engine; verify the SQLAlchemy 2.1 API
  before relying on it.

## D2 · Publish order and cost

One transaction per batch: `_TASK_LOCK`; `_NO_NEWER_ATTEMPT` (refuse with `FenceRejected`); upsert and
lock the `event_logs` row; batch-ID check; insert; advance `next_offset`; delete old batch rows;
`NOTIFY`. Every other fenced write takes `_TASK_LOCK` first and never holds an `event_logs` row, so the
order cannot invert. The flush runs in a background task; a refusal sets a flag that
`before_model_call` and the final flush raise as `Superseded`, and the Activity skips its finish writes.

## D6 · Messages, wake rows and the comms role

Migration 0006:

- `agent_messages (message_id PK, request_id, sender_task, recipient_task, kind send|ask|reply,
  correlation_id, reply_to, deadline, status pending|claimed|answered|expired|cancelled|rejected,
  reason, body text (<= 16 KB), idempotency_key UNIQUE, claimed_turn, created_at)`.
- `message_wakes (id, recipient_workflow, created_at)`. The dispatcher selects rows
  `FOR UPDATE SKIP LOCKED` (several orchestrator replicas are safe), Signals `inbox`, and deletes a row
  after the Signal call returns. A closed or missing Workflow also deletes the row, with a log line.
- Role: `infra/db/init.sh` creates `praxis_comms` (password from `infra/.env`); 0006 grants it
  `SELECT, INSERT, UPDATE` on `agent_messages`, `INSERT` on `message_wakes`, `SELECT` on `tasks` and
  `task_attempts`. Templates grant `PRAXIS_COMMS_DB_URL` as a secret, as `sample-shop` does.
- Idempotency key: sha256 of sender task, turn, tool name and canonical arguments. Attempts of one
  turn share it, so a retried attempt that repeats a send stores nothing new and gets the stored result.
- Locks (D10): sender `_TASK_LOCK` and the fence check, then `pg_advisory_xact_lock(2, hashtext(request_id))`
  (task locks use the one-key form, so the namespaces differ). Recipient status (R25), the cycle walk
  (R23) and `cancel_for` (R24) read under the request lock.

## D7 · Claim, restore and the wait loop

- `claim(task, turn, now)`, in one transaction under the request lock: mark the task's own questions
  past `deadline < now` `expired`; assign pending rows for the task (messages, replies, and its own
  questions now expired or cancelled) to `claimed_turn = turn`; return them, plus the earliest deadline
  of its still-open questions. A rerun for the same turn returns the same rows. `now` is the
  Workflow's `workflow.now()`, so timers and expiry agree under time skipping.
- `reply` refuses when the question's status is not open or `now() > deadline`.
- Restore: the finish short-circuit applies only to a checkpoint of the same turn. A woken turn's
  input lists its claimed rows (sender, kind, correlation ID, body) instead of `CONTINUE_MESSAGE`.
- Wait loop, after a `waiting` outcome: claim (turn N+1); if rows came back, run turn N+1 now;
  otherwise sleep until `woken`, the returned deadline, the idle timeout (only with no open question)
  or the wall-time deadline, then claim again. `woken` is set by the Signal handler at any time and
  cleared before each claim, so a Signal during a turn is never lost.
- Endings: idle timeout -> `succeeded` (R20); wall time -> `succeeded` or `failed` by open questions
  (R21); `max_wakes` reached -> `failed` "wake budget exhausted". Every ending runs `cancel_for` in
  `complete_task`.
- `TaskState`: resolved task, turn and wake counters, usage totals, wall-time deadline, `woken`, the
  last summary. A continued run skips `resolve_capabilities` and `record_task` (which refuses a new run
  ID) and claims first.

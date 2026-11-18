# Notes · Phase 2 - real-time events and the comms MCP

## Evidence from the code (2026-11-18, main at 73801ea)

- Events: `harness_activity/events.py` has `EventSink`, `NoOpSink`, `MemorySink` and `AttemptEvents`
  (per-attempt `seq`, emission under a lock). Only the DSH runner emits (`harness_activity/dsh/executor.py`
  tool events, `gateway.py` token and refused-tool events); `workers/main.py` gives it `NoOpSink`.
  `openai_agents` emits none.
- `AgentEvent` (`common/schemas/events.py`): `seq`, timestamp, workflow, task, `attempt_id`
  (`task:turn:attempt`), type, content-free payload, optional `blob_ref`.
- Fence: `common/persistence/repositories.py` `_TASK_LOCK` (`pg_advisory_xact_lock(hashtext(task))`)
  and `_NO_NEWER_ATTEMPT`, used by `AttemptRepository.start`, `assert_current` and
  `CheckpointRepository.insert_fenced`; `FenceRejected` is turned into `Superseded` by the Activity.
- `TaskWorkflow` (`orchestrator/workflow.py`): runs turns until `done`, `needs_input` or a budget; no
  Signals, no Continue-As-New. `TurnOutcome.status` is `done | continue | needs_input`;
  `finish_task` accepts `done | needs_input` (`harness_activity/tools.py`).
- MCP servers are stdio subprocesses the worker starts per attempt for both runners
  (`harness_activity/config.py`, `harness_activity/dsh/executor.py`, `MCP_CALL_TIMEOUT_S = 120`); they
  get `PRAXIS_TASK_ID` only. DSH sees them through one bridge (`infra/dsh/mcp_bridge.py`, 150 s timeout).
- Every `task submit` makes a new `request_id` (`orchestrator/submit.py`). No tenant field exists.
- The DSH gateway asks the model for complete responses (`harness_activity/dsh/gateway.py`), so
  there are no token deltas to stream.
- Replay: `tests/test_hello_replay.py` shows the replay-test pattern; `tests/test_task_workflow.py`
  uses the time-skipping environment.

## D1 · Event tables

Migration 0005, in the app database (the spike's `spike76` schema is not reused):

- `event_logs (workflow_id PK, next_offset bigint default 1, retained_base bigint default 1)`.
- `agent_events (workflow_id, "offset", task_id, attempt_id, seq, type, payload jsonb, blob_ref jsonb,
  emitted_at, stored_at; PK (workflow_id, "offset"))`. Columns mirror `AgentEvent`, so readers rebuild it.
- `event_batches (workflow_id, batch_id, seen_at; PK (workflow_id, batch_id))`, kept 600 s
  (the spike's re-send horizon); `prune` also deletes old batch rows.
- `LISTEN/NOTIFY` on one channel, `agent_events`, payload the workflow ID; readers clear their wake-up
  before each fetch and poll every 1 s (spike, `spikes/event-transport/event_transport/table.py`).
- The transport takes a raw asyncpg connection from the SQLAlchemy engine for `LISTEN`
  (`AsyncConnection.get_raw_connection()`); verify against the SQLAlchemy 2.1 docs before relying on it.

## D2 · Publish order and cost

One transaction per batch: `_TASK_LOCK`; `_NO_NEWER_ATTEMPT` (refuse with `FenceRejected`); upsert and
lock the `event_logs` row; batch-ID check within the horizon; insert events; advance `next_offset`;
`NOTIFY`. Every other fenced write takes `_TASK_LOCK` first and never holds an `event_logs` row, so the
order cannot invert. The flush runs in a background task of the Activity; a `FenceRejected` there sets
a flag read by `before_model_call`, and the attempt's final flush re-raises it as `Superseded`.
At the spike's load (~5 batches/s per agent) each publish adds one advisory lock; task 2.3 measures it.

## D6 · Messages and wake rows

- `agent_messages (message_id PK, request_id, sender_task, recipient_task, kind send|ask|reply,
  correlation_id, reply_to, deadline, status pending|claimed|expired|cancelled|rejected, body_ref jsonb,
  idempotency_key UNIQUE, claimed_turn, created_at)`.
- `message_wakes (recipient_workflow, message_id, created_at)`. The dispatcher `LISTEN`s on
  `message_wakes`, reads rows, sends Signal `inbox` and deletes the row only after the Signal call
  returns; a `WorkflowNotFound` or closed Workflow deletes the row and records it.
- Idempotency key: sha256 of sender task, turn, attempt, tool call number and the canonical
  arguments, like `sample_mcp`'s `record_order`. A retried attempt that repeats the same call stores
  nothing new.
- `claim(task, turn)`: in one transaction, `expire_due` marks asks past their deadline `expired`,
  then rows `pending` for the recipient get `claimed_turn = turn`; a repeat for the same turn returns
  the same rows. The turn input lists claimed messages, replies, and the sender's own questions
  that expired or were cancelled.
- The Workflow's wait timer is the minimum of: the earliest deadline of its own open questions, the
  idle timeout (only with no open question), and the wall-time deadline.

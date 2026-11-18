# Notes · Phase 2 events - the event table and agentctl tail

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

- `event_logs (workflow_id PK, next_offset bigint default 1, retained_base bigint default 1,
  retention_class)`.
- `agent_events (workflow_id, "offset", task_id, attempt_id, seq, type, payload jsonb, blob_ref jsonb,
  emitted_at, stored_at, retention_class; PK (workflow_id, "offset"))`. Columns mirror `AgentEvent`.
- `event_batches (workflow_id, batch_id, seen_at, retention_class; PK (workflow_id, batch_id))`. Each
  publish deletes that workflow's rows older than 600 s, the spike's re-send horizon; D2's re-sends
  finish within ~2 s, so the horizon is ample.
- Retention class `task` for all three (`common/persistence/retention.py`; design §4.13: every stored
  row carries one from its first write).
- `NOTIFY agent_events, <workflow_id>` per batch; following readers `LISTEN`, clear their wake-up before
  each fetch and poll every 1 s (spike `table.py`).
- `LISTEN` needs a raw asyncpg connection from the SQLAlchemy engine; verify the SQLAlchemy 2.1 API
  before relying on it.
- The workflow ID equals the task ID today (`orchestrator/submit.py`), so `tail TASK` needs no lookup;
  the table is keyed by workflow ID so a later workflow-per-many-tasks change does not move offsets.

## D2 · Publish order, the publisher and the final flush

- One transaction per batch: the task lock and newer-turn-or-attempt check from `fence.py`
  (`FenceRejected` on refusal); upsert and lock the `event_logs` row; the batch-ID check; insert;
  advance `next_offset`; delete old batch rows; `NOTIFY`. Every other fenced write takes the task lock
  first and never holds an `event_logs` row, so the order cannot invert.
- `BatchingPublisher`: `emit` appends under a lock and schedules a flush on the Activity's event loop
  (`loop.call_soon_threadsafe`), so emitting from a thread is safe. One background task cuts batches
  of at most 64 in `seq` order and publishes them one at a time. A cut batch is frozen: its ID and
  events never change. A database error re-sends it unchanged (backoff 0.25 s, 0.5 s, 1 s, then at
  each later trigger); new events wait in the buffer for later batches. So a commit whose reply was
  lost is deduplicated by its ID, and no new event ever shares a stored batch's ID.
- `close()` (shielded, bounded by `asyncio.wait_for` at 10 s, run inside the heartbeat scope): cancels
  the trigger timer, publishes everything buffered, awaits the background task, and returns either
  nothing, `FenceRejected`, or the last database error.
- Placement in `run_harness_turn`: `_finish` is reached by both success paths, the normal one (runner
  returns, then the finish checkpoint) and the restore short-circuit (a checkpoint that already holds
  a finish report). So the normal path writes its finish checkpoint as part of `_finish`, and
  `_finish` starts with: emit `status`; `close()`; on `FenceRejected` raise `Superseded` (no finish
  writes); on a database error raise a retryable error; otherwise the finish checkpoint, artifacts and
  outcome as today. Failure and cancel paths emit `status` with the failure, run `close()`, log a
  refusal or database error, and re-raise the original exception (ADR-0007: the failure still
  propagates).
- A refusal during a background flush needs no flag: `before_model_call` already stops a superseded
  attempt, and the final flush refuses again.

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

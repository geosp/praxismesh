<!-- Verbatim subagent report (events plan design-review round 1, zoom out, at aa6580f); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Design review: Phase 2 events plan, `docs/plans/2026-11-18-phase-2-agent-events` (plan.md, phases/01-event-table-and-tail.md and notes.md as of aa6580f)

**Verdict: changes requested.** I found 2 Majors and 6 Nits.

**What holds up:**
- **Root cause:** the plan fixes the cause. Events go to a `NoOpSink`, only DSH emits them, and nothing stores them (`harness_activity/dsh/runner.py:238`, `:360`; `harness_activity/events.py`). The plan replaces the sink at the shared `run_harness_turn` seam, which ADR-0007 requires.
- **Lock order:** the order in notes.md#d2 is sound. Every existing fenced write takes `_TASK_LOCK` first and never touches `event_logs` (`common/persistence/repositories.py:380-384`, used at `:141`, `:190`, `:265`, `:394`, `:502`, `:552`), so the order cannot invert.
- **Event loop:** DSH and `openai_agents` emit on the event loop thread, not from worker threads (`harness_activity/dsh/executor.py:171-177`, `gateway.py:318-338`). A synchronous `BatchingPublisher.emit` that schedules a background task is therefore workable.
- **`openai_agents` hooks:** `RunHooks` has `on_llm_end`, `on_tool_start` and `on_tool_end` in the installed openai-agents 0.24.0, and `_Hooks` already exists (`harness_activity/runner.py:143`).
- **Rollout:** the migration is additive and `TaskWorkflow` is unchanged. Rollback by redeploying the old workers is safe because the new tables simply go unused. "Rollout & rollback" covers what it needs to.

## Majors

### M1. Where the final flush and the `status` event go, and how the publisher shuts down, is not specified
**Location:** plan.md › Decisions › D2, D3; Requirements › R5, R8; notes.md#d2; phase 01 tasks 2.1 and 2.2.

The plan says the final flush raises `Superseded` and that "the Activity skips its finish writes" (notes.md#d2). It also says the Activity emits "`status` at turn end" (D3). It never places either one against the two fenced finish writes in `_run` and `_finish`:
- the final `checkpoint(finish)` (`harness_activity/activity.py:524`);
- the outcome write, `attempts.finish(..., fenced=True)` (`activity.py:557-571`).

Both possible orderings are defensible, but they behave differently:
- **Flush after `attempts.finish`:** a refused final flush raises `Superseded` after a committed `done` row and uploaded artifacts. Temporal then retries a turn the database already records as finished.
- **Flush before it:** the `status` event can be stored for an attempt whose fenced finish is then refused.

The failure paths are also missing:
- **No flush or `status` named:** `_runner_failed` (`activity.py:313-343`), the `NonRetryableError` branch (`activity.py:279-301`) and the `CancelledError` path (`activity.py:330-331`).
- **Shielding:** a heartbeat-timeout cancellation would cancel the final flush unless it is shielded, as `scope.close()` already is (`activity.py:413-415`).
- **Background flush task:** the plan does not say who awaits or cancels it when `_attempt` exits. A leaked task can keep publishing after the attempt has returned.

So R8 ("Every event an attempt emitted before it ended is stored") is defined only for the success path. None of task 2.1's tests check ordering against the finish writes or a failing or cancelled attempt.

**Fix:** state where the final flush runs (in a `finally` in `_attempt`, shielded, and before which fenced write). State whether `status` is also emitted on failure and cancel. Add a 2.2 test for a runner failure and a cancellation.

### M2. Publisher retry and concurrent flushes are undefined, so R1's retry case and R9's "reset first" have nothing behind them
**Location:** plan.md › R1 (first scenario), R9, D2; task 2.1.

- **Retry:** R1 promises that "a batch publish retried after a lost reply … is stored once". But no decision or task says the `BatchingPublisher` retries at all, or what happens on a transient database error: retry, drop or fail the attempt. Batch-ID dedup only matters if the publisher re-sends. Temporal's own retries make a new attempt with new batch IDs (`<workflow>:<attempt_id>:<n>`), which never collide. As written, `event_batches` and its 600 s cleanup protect a path the plan never creates. A transient error during the final flush is also unresolved against R8.
- **Concurrent flushes:** the flush "runs in a background task" (notes.md#d2), triggered at 64 events or after 200 ms (R7). Nothing says only one flush runs at a time. Two in-flight flushes for one attempt serialize on the task lock in arbitrary order, so offsets can contradict `seq`. A batch holding the attempt's `reset` could then land after a later batch, which breaks R9.
- **Risks interaction:** the Risks section allows publishes up to 250 ms p95, which is longer than the 200 ms trigger, so overlap is the expected case, not a corner case.

**Fix:** specify one in-flight flush per publisher, plus a bounded retry that re-sends the same batch ID and fails the attempt once retries run out. Add 2.1 tests for a lost reply (commit succeeds, reply fails, re-send stores nothing) and for a slow flush that overlaps the next trigger.

## Nits

- **plan.md › D2 and R5 (refusal flag):** the flag duplicates guarantees the Activity already has. `before_model_call` already checks for a newer attempt (`activity.py:487-490`), and both checkpoint inserts are fenced (`activity.py:461-481`, `:524`). R5's 60 s tool-call scenario already ends `Superseded` with no checkpoint under today's code. Consider dropping the flag, or say what it adds.
- **plan.md › D1 (dedup):** a unique key on `agent_events (workflow_id, attempt_id, seq)`, checked under the `event_logs` row lock, would deduplicate re-sends without `event_batches` or the 600 s cleanup. It would also enforce 2.2's "one `seq` sequence per attempt". This is optional because ADR-0009 names batch IDs.
- **plan.md › D1, D5 (workflow ID):** the workflow ID is the task ID (`orchestrator/submit.py:60`, `id=start.task_id`). So "Rejected: per-task offsets" and "resolves the task's workflow ID" describe a distinction that does not exist today; say so to avoid a needless lookup.
- **plan.md › R8:** buffered events (up to 200 ms or 64 events) are lost when a worker is SIGKILLed, which demo 4.1 does deliberately. R8 should exempt a killed attempt as well as a superseded one.
- **phase 01 › task 3.1 (`tail` stop):** "Stops following when the task ends" should require one final drain fetch after the end is seen. Otherwise a 1 s poll that sees `complete` can drop the last batch.
- **plan.md › What changes; tasks 1.3 and 2.1 (placement):** neither says where `BatchingPublisher` lives (next to `EventSink` in `harness_activity/events.py`?). Nor do they say how `common/events/` gets the fence, since `_TASK_LOCK` and `_NO_NEWER_ATTEMPT` are private to `common/persistence/repositories.py:380-384`. Name both, so the fence predicate stays defined in one place.
- **plan.md › Risks (second item):** "ADR-0009's revisit trigger applies" sets no threshold, and task 2.3 records database CPU with no pass or fail condition. That leaves the mitigation as an observation, not a gate.

## Files
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/plan.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/notes.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/phases/01-event-table-and-tail.md
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/events.py
- /home/geo/develop/praxismesh/harness_activity/runner.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/orchestrator/submit.py
- /home/geo/develop/praxismesh/spikes/event-transport/event_transport/table.py

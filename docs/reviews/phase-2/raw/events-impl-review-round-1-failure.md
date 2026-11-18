<!-- Verbatim subagent report (events plan impl-review round 1, failure and retry, diff 41c0bcf..c7dcbcd); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Failure-lens review of phase 01 (diff 41c0bcf..c7dcbcd)

I found one Major and eleven Nits. No Blockers.

The core recovery paths hold up:
- **Fenced publish:** `common/events/table.py:62-99` takes the task lock, checks for a newer attempt, then locks the workflow's `event_logs` row. Prune takes only the `event_logs` row lock, so the lock order cannot invert.
- **Duplicate batches:** a re-sent batch is recognised by its `event_batches` row inside the same transaction.
- **Gap-free reads:** the `FOR UPDATE` lock on `event_logs` stays held until commit, so readers see offsets in commit order with no gaps.
- **Final flush:** it runs before every finish write (`harness_activity/activity.py`, `_finish`). On every other ending, a `BaseException` handler emits `status` and closes the publisher before the error propagates.
- **Cancellation:** `close()` is shielded and the publisher's background task is not the activity's task, so a cancellation does not stop it. The workflow uses `WAIT_CANCELLATION_COMPLETED` (`orchestrator/workflow.py:130`), so a cancelled attempt's last events are committed before `tail`'s final read.
- **Timeout under cancellation:** the venv's Python is 3.11.17, whose `asyncio.timeouts.Timeout.__aexit__` compares `uncancel() <= self._cancelling`. So `close()`'s 10 s timeout still raises `TimeoutError` inside an already-cancelled activity task.
- **Overlapping attempts:** the per-task lock serialises them, and the fence refuses the stale attempt once the newer start commits (`common/persistence/repositories.py:140-173`).

## Major

**M1 · R9 (D3) · An attempt that fails before `checkpoints.latest` returns stores `status` as its first event, with no `reset`.**
- **Location:** `harness_activity/activity.py`. In `_attempt`, the publisher and `AttemptEvents` are created right after `attempts.start`, then `_open` runs (DSH). `reset` is emitted only inside `_run`, after `build_config`, `session_store(...)` and `await self.checkpoints.latest(...)` (the line `events.emit("reset", restored_from=...)`).
- **Scenario:** a DSH attempt whose `open_attempt` raises: the container fails to start, the attempt is cancelled during `_open`'s `_charge` or `open_attempt` await, or `checkpoints.latest` hits a database error. The `except BaseException` handler runs `events.emit("status", **_failure_status(e))` as seq 0 and flushes it.
- **Wrong outcome:** `tail` shows that attempt's events beginning with `status` (`failed` or `cancelled`) and no `reset`. R9 requires "An attempt's first event is a `reset`", and D3 says "The Activity emits `reset` at attempt start".
- **Test that would expose it:** in `tests/integration/test_harness_activity.py`, use an `open_attempt` that raises (or a cancel while it awaits) with a `TableTransport`, then assert `[e.type for e in stored] == ["reset", "status"]`. Today it yields `["status"]`.
- **Possible fixes:** emit `reset` (`restored_from` unknown or None) before `_open`, or have the failure handler emit `reset` first when `events.seq == 0`.

## Nits

1. `harness_activity/events.py` (`_run` exit check and `emit`), R8: an `emit` from another thread that lands after `_run` has checked `closing and _empty()`, or after the task is done, is appended to `buffer` and never published, while `close()` returns None. The realistic case is a DSH tool thread (`dsh/executor.py:177`, via `run_coroutine_threadsafe(...).result(...)`) finishing after a cancellation. Arguably outside R8's "emitted before it ended", but the loss is silent and not logged.
2. `orchestrator/cli.py`, `tail.closed()`, D5: `except Exception: return True` treats any describe failure as a closed workflow. A transient Temporal frontend error makes `tail --follow` do its final read and exit 0 while the task is still running. Fix: treat only not-found as closed.
3. `orchestrator/cli.py`, `tail`, D5: `connect()` to Temporal runs even with `--no-follow`, so a database-only read fails when Temporal is down. Also, if `connect()` raises, the engine created just before is not disposed.
4. `harness_activity/events.py`, `_drain` (`for wait in (*self.backoff_s, None)`), task 2.1: every later trigger re-runs the whole 0.25/0.5/1 s backoff (four tries, about 1.75 s of sleep). Task 2.1 says "backoff 0.25, 0.5, 1 s, then at each trigger", meaning one try per trigger.
5. `harness_activity/events.py`, `_cut` (`self.oldest = time.monotonic() if self.buffer else 0.0`), R7: after a cap cut, the leftover events' 200 ms timer restarts at cut time, not at the oldest leftover event's emit time. They can be published up to about 200 ms later than R7's "200 ms after the oldest unpublished event".
6. `harness_activity/activity.py`, `_finish` plus the `BaseException` handler, D3: a cancellation that arrives while `_finish` awaits `publisher.close()` makes `close()` raise `CancelledError` while the flush continues. The handler then sees `not publisher.closed` and emits a second `status` (`cancelled`) after `status: done`, so the attempt stores two `status` events.
7. `harness_activity/activity.py`, `_finish`, D3: `status: done` is flushed before the finish checkpoint. If that checkpoint then fails with a database error, the stream says `done` for an attempt that fails and retries. D3 permits this ("not the recorded outcome"); listed for visibility.
8. `harness_activity/events.py` `_cut` (batch ID) with `repositories.py:168` (`ON CONFLICT ... DO UPDATE`), R1: batch IDs are `<wf>:<task>:<turn>:<attempt>:<n>`, and `attempts.start` accepts a repeated (turn, attempt). If the same Temporal attempt number re-runs within 600 s (for example after a Temporal workflow reset), its batches match the earlier run's `event_batches` rows and are silently dropped as re-sends. This is rare, so I rated it a Nit.
9. `common/events/table.py` (horizon `DELETE` before the dedup insert) with `BatchingPublisher`'s unbounded retry at each trigger, R1: a commit whose reply was lost, followed by more than 600 s of database errors while the attempt keeps running, is re-sent after its row was purged and stored twice. R1 promises only "within 600 s", so this is accepted by the plan; listed because the publisher does not stop retrying at the horizon.
10. `harness_activity/events.py` `emit` (`self.loop.call_soon_threadsafe`): an `emit` from a runner thread after the worker's event loop has closed raises `RuntimeError` in that thread. This only happens at shutdown.
11. `harness_activity/runner.py`, `_Hooks.on_tool_start`/`on_tool_end` (`self.calls[tool.name]`), D3 (outside the failure lens): parallel calls to the same tool overwrite each other's call number, so `tool_result.call` can name the wrong call. Also, `openai_agents` emits no events for refused tool calls, while DSH emits them (`dsh/gateway.py:337-338`).

## Files
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/events.py
- /home/geo/develop/praxismesh/harness_activity/runner.py
- /home/geo/develop/praxismesh/common/events/table.py
- /home/geo/develop/praxismesh/common/events/transport.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/orchestrator/cli.py
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/tests/integration/test_harness_activity.py

<!-- Verbatim subagent report (impl-review-phase-02-round-2-failure); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. The coordinator's brief carried a wrong full SHA; the reviewer received the correction and reviewed the stated range. -->

**Phase 02 failure-lens review: 3 Major, 7 Nit, no Blockers**

Diff reviewed: `562733a72b880d13576ced63e8b8ad09716094df..e053d233cb39655e47ed0c22d1e37c1ed71fe14b`, using the corrected full SHA. I made no builds, test runs or writes.

**Units traced (awaits and side effects, in order)**

- **Activity** (`harness_activity/activity.py`): `run_harness_turn` → `_attempt`:
  - `attempts.start`, which is fenced and marks older `started` rows `lost` (`repositories.py` `start`).
  - `_open`, which calls `_charge`. That runs `ledger.close_unknown`, which closes earlier unsettled rows, nulls their attempt rows and fixes up `lost` rows. Then `open_attempt`.
  - `_run`: `checkpoints.latest`, unpack, `store.load`, then `runner.run` (the barrier does `checkpoint()` = pack → `blobs.put` → `capture` → `insert_fenced`), then the final `checkpoint(finish)`.
  - `_finish`: `assert_current` → artifact `put` → fenced `attempts.finish`.
  - `finally` closes the scope, then `_runner_failed` or the NonRetryable path runs.
- **DshRunner.run** (`harness_activity/dsh/runner.py`):
  - `executor.start`, Gateway and SocketServer, writes the config files, `server.start`, launcher `start`, then the `poll` loop.
  - On a stop: `server.close` → `attempt.stop`. On a clean exit: read `result.json` → `freeze`.
  - Then `classify`.
- **Gateway request** (`harness_activity/dsh/gateway.py`): barrier (marker check → `freeze` → capture/commit → `thaw`) → `ledger.admit` (durable `dispatch` row) → upstream POST → `settle` → counters → event.
- **Launcher** (`infra/dsh/launcher.py`): `setup_cgroups` → `reap` → serve. Each connection handles open/start/exec/freeze/poll/stop, and `destroy` runs when the connection ends.

## Major

**M1 · A dirty cleanup found during a run never marks the worker unhealthy** (R10, R8; the review F71 fix)
- Where: `harness_activity/dsh/runner.py:147-151, 157-163, 463`.
- How it happens: `DshAttempt.stop()` sets `self.stopped = True`. `close()` only checks the report and calls `on_dirty` when `if not self.stopped:`. Every stop inside `run()` (deadline, cancel, step limit, abort) goes through `report = await asyncio.shield(attempt.stop(grace))`. Its report goes to `classify` and nowhere else; `_dirty` is never called on that path.
- Scenario: the turn deadline fires; the launcher's `destroy` returns `processes_left: 1` (`launcher.py:271-276`: the cgroup is not removed when `left != 0`).
  - The attempt is classified `DshCleanupFailure` (`policy.py:39-40`), so the turn fails.
  - `self.unhealthy` stays `None`, and the next `open_attempt` on the same container succeeds while a process from the old attempt is still running.
- Second path, same result: if the launcher replies with an error to `stop` (any `OSError` in `destroy`, e.g. `cg.rmdir()` EBUSY), `LauncherError` is raised.
  - In `run()` it is caught by `except Exception` with `report = None`, so `cleanup_ok = report is None or ...` evaluates True. A cleanup of unknown outcome is classified as clean and retryable (`DshTurnDeadline` or `DshUsageUnknown`).
  - In `close()`, a `LauncherError` or `TimeoutError` from `stop` is only logged (`runner.py:164-165`), with no `on_dirty`.
- Existing test misses it: `test_failed_cleanup_after_success_stops_new_attempts` (`tests/integration/test_dsh_activity.py:533`) only covers the post-success `close()` path.
- Test that would expose it: patch `stop` to return `processes_left: 1` during a deadline stop (or to raise `LauncherError`), then assert the next `open_attempt` raises `LauncherUnhealthy`.

**M2 · A worker that refuses attempts keeps polling the queue and burns every turn's attempts** (R17, R10/F71)
- Where: `runner.py:209-224` and `pins.py` (`RuntimePinMismatch` and `LauncherUnhealthy` are plain retryable exceptions); `activity.py:374-378`.
- Ordering: `_open` runs after `attempts.start`, so each refusal counts as a real attempt. The worker (`workers/main.py`, `max_concurrent_activities=1`) keeps polling `tpl.local-dsh`.
- Scenario (the Compose default has one DSH worker pair): after a dirty cleanup (or a recreated container with another digest), every task routed there gets `LauncherUnhealthy` on attempts 1–5. Temporal's backoff is about 1+2+4+8 s, so attempt 6 hits `AttemptsExhausted` (`activity.py:234`) and the task fails "lost_or_timed_out" within seconds.
- Why it contradicts the contract: R17 says the worker "refuses to serve the queue". The `LauncherUnhealthy` docstring says "another worker may take the turn". In practice the worker keeps serving and fails every task.
- Test that would expose it: a TaskWorkflow run with a single DSH worker whose runner is marked unhealthy. Assert the task is not failed by that worker (for example, the worker stops polling or exits).

**M3 · A cancelled turn's usage and its D9 charge never reach the TaskResult** (D7, D9/F59, R12)
- Where: `activity.py:282-306`, `orchestrator/workflow.py` `failed_turn_usage`.
- What happens: `_runner_failed` computes the charge into `heartbeat.base`, then `raise asyncio.CancelledError()` with no details.
  - The SDK reports `CancelledError("Cancelled")` (`.venv/.../temporalio/worker/_activity.py:485-492`), with no details.
  - The workflow catches `ActivityError` and calls `failed_turn_usage(e.cause)`. A `CancelledError` cause has no `last_heartbeat_details` and empty `details`, so it falls through to `return 0, 0, 0, 1, True`.
- Scenario: cancel while a request is in flight (the R18 `cancel` case). The attempt row correctly says `(None, None, False)`, but `complete_task` gets tokens 0 and `usage_known=True` for that turn.
- Same loss in related windows: a cancel that lands outside the runner's poll loop (during `_open` before `_charge`, during restore in `_run`, or during `_finish`) leaves the attempt row `started` and skips the F59 charge altogether.
- Existing test misses it: `test_cancel_stops_the_attempt_within_the_grace_and_stays_clean` (`test_dsh_outcomes.py:349`) suppresses `WorkflowFailureError` and never checks the TaskResult.
- Not fully verified: I traced the SDK source but did not run it. The spike evidence has no `result` for `cancel`, so R18 itself does not pin this down.
- Test that would expose it: in that test, read `tasks.result` and assert `usage_known is False` with tokens at or above the D9 charge.

## Nit

**N1 · A thaw that fails after a successful commit leaves a committed checkpoint** (D6)
- Where: `barrier.py:67-76`.
- D6 says "A failed barrier writes no checkpoint". Here `BarrierFailed` is raised after `capture_and_commit` has already committed.
- The capture was taken while frozen, so it is consistent. Probably acceptable, but it differs from D6's wording.
- Test: `test_..._thaw` in `test_dsh_activity.py`, extended to assert the checkpoint row count.

**N2 · A tree can be orphaned between `mkdir` and launcher `open`** (R10)
- Where: `runner.py:225-232`.
- The worker creates `tree/{workspace,home,...}` before sending `open`. If the worker is SIGKILLed or cancelled in that window, the launcher has no attempt to destroy, and `reap()` only runs at launcher start (`launcher.py:395-397`).
- The leftover is empty directories, so this is low impact.
- Test: kill the worker after the `mkdir` and before `open`; assert the tree is gone 10 s later.

**N3 · Dirty cleanup after a successful turn does not change the outcome** (R8, R9)
- Where: `activity.py:388-391`.
- After a `done` turn, `close()` marks the worker unhealthy, but the outcome stands. During a run, the same report is non-retryable `DshCleanupFailure`. The test documents this deliberately (F71); I note the asymmetry only.

**N4 · No timeouts on `poll` and in-run `stop`**
- Where: `runner.py:431, 463`.
- If the launcher stalls (for example, cgroupfs writes block), the poll loop never reaches its deadline check. The heartbeat task keeps heartbeating, so only `start_to_close` ends the attempt, and the `STOP_MARGIN_SECONDS` stop never happens.

**N5 · Tool-call counts for a lost attempt come only from the last heartbeat** (R11)
- Where: `executor.py:66, 134`.
- Executor entries are in memory only. Tool calls made after a lost attempt's last heartbeat (up to `heartbeat_timeout/3`) are dropped from the totals.
- R11 says tool usage comes "from the gateway ledger and executor"; only tokens are rebuilt from durable state (`close_unknown`).

**N6 · Rows closed by `close_unfinished` keep the column default of 0 tokens** (D7)
- Where: `activity.py:246-255`, `repositories.py` `close_unfinished`.
- On the NonRetryable path (for example `BlobCorrupt` → `HarnessInputError` in the DSH path), the current row is marked `failed` with tokens 0 (default from `0003_phase1_tables.py:68`) and `usage_known=true`.
- The third `close_unknown` update only rewrites `outcome = 'lost'` rows. The notes say every attempt row holds the turn's cumulative usage.

**N7 · Any `CancelledError` is labelled a cancel**
- Where: `runner.py:449-450`, `activity.py:287-293`.
- Heartbeat-error and timeout cancellations (`_activity.py:327, 426`) also become `DshCancelled` and an attempt row `cancelled`, if no newer attempt has started yet.
- The turn then retries, and the earlier row reads `cancelled` rather than `lost` or timed out.

## Checked and consistent

- The stale-attempt ledger path: `dispatch` is fenced under the advisory lock (`repositories.py`, `UsageLedgerRepository.dispatch`). `settle`, once `close_unknown` has closed a row, is a no-op (`settled_at IS NULL`), and totals are recomputed from the rows each time.
- A checkpoint commit that partly applied: the next attempt resumes from it, and a final checkpoint with `finish` goes straight to `_finish`.
- A worker SIGKILL: the connection-close `destroy` (`launcher.py:388-392`) thaws, then kills.
- A cancel during a barrier: `server.close` cancels the barrier, and the thaw still runs (`barrier.py:68-72`); the launcher's `stop` also thaws first (`launcher.py:257`).
- R7: artifact references are returned only after the fenced finish.
- The migration runs in one transaction, and the ledger's primary key covers (task, turn, attempt, request).

## Relevant files

- <repo>/harness_activity/activity.py
- <repo>/harness_activity/dsh/runner.py
- <repo>/harness_activity/dsh/barrier.py
- <repo>/harness_activity/dsh/gateway.py
- <repo>/harness_activity/dsh/policy.py
- <repo>/harness_activity/dsh/pins.py
- <repo>/infra/dsh/launcher.py
- <repo>/common/persistence/repositories.py
- <repo>/orchestrator/workflow.py
- <repo>/tests/integration/test_dsh_activity.py
- <repo>/tests/integration/test_dsh_outcomes.py

Round 2 failure review of the fixes in `3ca9f3d..bd10edc` (review commit bd10edc), plan `docs/plans/2026-11-18-phase-2-events-and-comms`, phase 02.

One fix does not close its finding: the cancel half of F98. That is a Major, so the verdict is changes-requested. Everything else that was marked fixed holds; what is left are Nits.

## Major

**M1. F98 (R24, D17): a cancel that lands while `complete_task` runs still ends the task without `complete_task`, and no test covers it.**
- **Location:** `orchestrator/workflow.py` `_complete`, the lines `for _ in range(2): try: ... except asyncio.CancelledError: continue` (around 428-441 at bd10edc).
- **Scenario:** a task ends during a database outage, so `complete_task` keeps failing and retrying under `COMPLETE_RETRY`. The owner then cancels the Workflow.
  - `execute_activity` uses the default `ActivityCancellationType.TRY_CANCEL` (`temporalio/workflow/_activities.py:118`).
  - On a Workflow cancel, `_await_temporal_operation` catches the `asyncio.CancelledError`, calls `apply_cancel` (which issues `RequestCancelActivityTask`), clears the cancel with `task.uncancel()`, and goes back to awaiting the result (`temporalio/worker/_workflow_instance.py:2416-2437`).
  - The Activity then resolves as `cancelled`, and that becomes an exception on the handle (`_workflow_instance.py:969-973`). The exception is an `ActivityError` whose cause is `CancelledError`. It is not an `asyncio.CancelledError`.
  - `asyncio.CancelledError` only reaches `_complete` in the rare case at line 2418, where the future had already completed.
- **Wrong outcome:** the `except asyncio.CancelledError` never fires, so `complete_task` is never rerun. The `ActivityError` passes out of `_complete` and `run`, and the SDK treats it as a cancellation (`exceptions.py:477-503`), so the Workflow closes as cancelled. The `tasks` row stays `running`. The task's questions stay open. Tasks waiting on it are not woken and wait until their deadlines. That is exactly what F98 named ("a cancel during it was not rerun").
- **Evidence:** the plan says "The Workflow runs `complete_task` on every ending: done, a budget, a cancellation or a failed claim during a wait" (D17). R24 says "When a task ends by any path, including cancellation ... every question to or from it closes".
- **Test that would expose it:** none exists. `test_complete_task_is_retried_until_it_succeeds` covers only the retries. Add a time-skipping Workflow test in which `complete_task` fails a few times, the test calls `handle.cancel()` while it is retrying, and then asserts that `complete_task` succeeded once and the run returned a `TaskResult`.
- **Likely fix:** catch `ActivityError` whose cause is `CancelledError` and rerun once, or run `complete_task` with a cancellation type that is not cancelled by the Workflow cancel.

## Fixes confirmed

For each finding below, the change closes the scenario it names, and the cited test would fail on 3ca9f3d.

- **F94:** `_question_for_reply` now compares `sender_task` with the recipient. Without that check, `test_a_reply_must_go_to_the_asker` would get `wrong.ok`.
- **F95:** both `remaining <= 0` paths in `_wait` and the woken-turn branch in `_run_v2` now go through `_ending_at_wall_time`. Without this, `test_a_waiting_turn_past_the_deadline_fails_with_an_open_question` would end `succeeded`, because the old `_out_of_wall_time(None)` was used. A final claim that brings rows sets them to `claimed`, and `end_task` turns them into `undelivered`, so R26 holds.
- **F96:** `tool_text` matches the SDK's output shapes: a `ToolOutputTextDict`, a list of them, or a JSON string for structured content (`agents/mcp/util.py:796-818`).
- **F97:** the check after the run is fenced through `_enter`, and a `FenceRejected` there becomes `Superseded`. It runs before the finish checkpoint is written, so a lost attempt after it does not replay a stale `done`. If the check itself fails, the attempt fails and reruns from the checkpoint taken before the last model call. Without the fix, the test would return `done`.
- **F99:** the delete happens before the Signal, inside a savepoint. A sender's `ON CONFLICT DO NOTHING` insert then waits on the uncommitted delete: it inserts a new row after the commit, or finds the conflict after a rollback. If the process dies before the commit, every row is kept and re-signalled. Without the fix, the old row would be live, `DO NOTHING` would return at once, the later delete would remove it, and `pending` would be 0.
- **F100:** the connect now sits inside `run`'s loop. `test_a_failed_first_connect_is_retried` would see the task finished. `CancelledError` is a `BaseException`, so it still stops `run`.
- **F102, F106, F107, F108:** confirmed. F108's test relies on retries reusing the first input's `now`, so only the final claim succeeds.

## Nits

- **`workflow.py` `_ending_at_wall_time` (R24, F95):** the `except ActivityError` also catches a cancel (cause `CancelledError`) that lands during the final claim. The task then ends with reason "wall-time budget exhausted" instead of "cancelled". `complete_task` still runs, so this only mislabels the reason.
- **`workflow.py` `_ending_at_wall_time` (R21):** if the final claim fails, a waiting task with no open question fails "wall-time budget exhausted". This is the default `unavailable` text, and it is used on the `_wait` paths and the woken-turn path. The ending cannot be known, but the reason claims a cause it did not check.
- **`workflow.py` (F109, R21):** nothing tests the woken-turn branch at the deadline in `_run_v2`. The F95 test only exercises `_wait`'s `remaining <= 0` path.
- **`workflow.py` (determinism, D12):** there is no `workflow.patched` marker for the new commands, so a v2 history recorded on 3ca9f3d and replayed on the new code fails as nondeterministic. The new commands are the `claim_inbox` in `_ending_at_wall_time` and the timer before the final claim in `_wait`. The phase is unmerged, so only a dev Workflow caught in that window is affected.
- **`workflow.py` `_complete` (D17):** `COMPLETE_RETRY` has no `schedule_to_close`, so a permanent, retryable bug in `complete_task` keeps the Workflow open for good. This is by design for outages, but it never surfaces the bug.
- **`workflow.py` `_ending_at_wall_time`:** the final claim can run up to `SHORT*2` (60 s) past the wall-time deadline. R21 sets no timing, so this is harmless.
- **`dispatcher.py` `drain` (D6), lock held during an external call:**
  - Once a row's Signal succeeds, its delete stays uncommitted until the whole batch commits. A sender to that recipient blocks inside `_wake_if_sleeping` while holding its task lock and request lock, for up to (BATCH-1) x `SIGNAL_TIMEOUT`, about 245 s, if Temporal is slow or starting to time out.
  - Meanwhile every send, claim and `complete_task` in that request waits too, including requests that have nothing to do with the slow rows.
  - It bounds itself and recovers (claims retry, and sends are idempotent by key), so I rate it Nit. Committing after each row would remove the stall.
- **`dispatcher.py` `drain`:** an exception from `_signal` other than `RPCError` rolls back the whole batch, so rows already signalled are signalled again. Signals are only hints, so this is harmless.
- **`02-inbox-and-comms.md` front matter (process):** it sets `status: impl-reviewed` and `impl_review: { status: passed, rounds: 1 }`, but reviews.md records round 1 as changes-requested, and round 2 is still running. plan.md's Phases table still says `in-progress`, so the two disagree.

Verdict: changes-requested

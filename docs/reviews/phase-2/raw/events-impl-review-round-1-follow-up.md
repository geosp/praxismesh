<!-- Verbatim subagent report (events plan impl-review, targeted follow-up of round 1, diff c7dcbcd..4463f52); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Targeted follow-up review of `c7dcbcd..4463f52` (phase 01, Phase 2 agent events), read at 4463f52.

**Verdict:** properties 1 and 3 hold. Property 2 holds in the code, but its checkpoint-lookup branch has no test. The diff adds one new defect (Major).

## Properties checked

**1. A timed-out final flush ends in EventsUnavailable: holds.**
- `harness_activity/events.py` `close()`: on `TimeoutError` it cancels the task, stores the result in `self.result` and returns it. `closing` is set first and `closed` now returns `closing`.
- `_finish` (`activity.py` ~line 620) emits one `status` event, then raises `EventsUnavailable` before `finish_checkpoint` and `attempts.finish`.
- The `except BaseException` handler (`activity.py:448`) now sees `publisher.closed` as true. It skips the second `status` event and the second `close()`, so the old `CancelledError` (from shielding a task that was being cancelled) no longer replaces the error.
- Tests: `tests/integration/test_harness_activity.py::test_a_final_flush_that_times_out_raises_events_unavailable` would fail before the fix, because the second close raised `CancelledError`, which `pytest.raises(Exception)` does not catch. It also asserts `(0, "started")`, i.e. no finish write. `tests/test_event_publisher.py::test_close_is_bounded_and_runs_once` covers a second close returning the same result without waiting.

**2. Every attempt's first event is `reset`: holds in the code.**
- `activity.py:428-430` emits `reset` right after `checkpoints.latest`, before `_open` and before `build_config` (which runs in `_run`).
- If `checkpoints.latest` itself fails, `events.seq == 0` triggers a fallback `reset(restored_from=None)` (`activity.py:450`).
- `attempts.start` fails before any publisher exists, so that path stores no events.

**3. The close bound and its timeout path are tested: holds.**
- Unit: `test_close_is_bounded_and_runs_once` and `test_a_database_that_stays_down_is_returned_from_close`.
- Integration: the test above, with `CLOSE_TIMEOUT_S` monkeypatched. `close()` looks up that module-level value at call time, so the patch takes effect.

## Findings

**F1 — Major — `harness_activity/events.py` `_run` (lines ~156-163) and `close()`; R8, D2. New defect: the publisher can loop forever after its caller is cancelled.**
- **What changed:** the `_run` exit condition went from `self.closing and (self.error is not None or self._empty())` to `self.closing and self._empty()`. Now the only thing that stops a publisher retrying against a failing database is `close()`'s timeout branch calling `self.task.cancel()`.
- **Failure scenario:**
  1. The Activity is cancelled (Temporal cancel or heartbeat timeout) while `_finish` or the failure handler is awaiting `publisher.close()`.
  2. Meanwhile the app database is down, or the batch fails with any non-fence exception that keeps recurring.
  3. The `CancelledError` exits `asyncio.timeout` through the shield, so the timeout branch never runs and `self.task` is never cancelled.
  4. `_run` then retries the pending batch every `delay_s` for the life of the worker. Each such attempt leaks one task.
- **Secondary effect:** `self.result` stays `None`, so a later `close()` reports "every event was stored" when that is false.
- **Exposing test:** emit one event to a publisher whose transport is `LostReplies(fails=10**6)`, cancel a `close()` caller as `test_close_completes_when_its_caller_is_cancelled` does, then assert that `p.task` finishes within a few `delay_s` (or within the close bound). Today it never finishes.
- **Possible fix:** cancel `self.task` and set `self.result` in a `CancelledError` branch once the bound expires, or run the bound inside the shielded part.

**F2 — Nit (test gap) — `harness_activity/activity.py:450`; R9.**
- The `events.seq == 0` fallback for a failing `checkpoints.latest` has no test.
- `test_an_attempt_that_fails_early_still_opens_with_reset` fails in `open_attempt`, after the normal `reset` was already emitted, so it passes with or without that branch.
- The property you asked about names "the checkpoint lookup failing" explicitly.
- **Exposing test:** make `h.acts.checkpoints.latest` raise, then assert the stored types are `["reset", "status"]`.

**F3 — Nit — `tests/integration/test_harness_activity.py`, the timeout test; R8.**
- "At most one status event stored" is only covered by code inspection. With a transport that hangs forever, nothing is ever stored, so the test cannot observe a second `status` event.
- Asserting on a `MemorySink`, or checking `events.seq`, would pin it down.
- Separately, the class name `HangsAfterFirst` is misleading: it hangs on every publish, the first included.

**F4 — Nit — `harness_activity/events.py` `emit()`; R8.**
- The guard `self.closing and self.task.done()` leaves a small race. `_run` can see `_empty()` and return, then an event emitted (for example, from a gateway thread) before the task is marked done gets appended to `buffer` and is dropped without the warning.
- The effect is a lost late event with no log line. Ordering and the fence are unaffected.

I found no defects in the `runner.py` (per-tool queue of open call numbers, refused-call events), `dsh/gateway.py` (name capped at 64 characters; `name` is always a `str`) or `orchestrator/cli.py` changes. In `cli.py`, Expired resumes after `retained_base - 1`, and non-follow tail no longer connects to Temporal. One change in the cli follow path: `closed()` now lets exceptions that are not `RPCError` propagate instead of treating them as closed. That looks intended, so it is not a finding.

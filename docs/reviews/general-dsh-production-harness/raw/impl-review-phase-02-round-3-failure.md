<!-- Verbatim subagent report (impl-review-phase-02-round-3-failure, targeted follow-up); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. The run stopped once on a usage limit and was resumed. -->

Phase 02 implementation review, failure lens, targeted follow-up round (frozen commit 98835319, phase diff 562733a7..98835319, focus on 76dffd6e..98835319)

Verdict: two Major findings and several Nits. Both Majors are in the round-2 changes (F99 preflight refusal and F101 ledger usage), on restart and partial-failure paths that the new tests don't exercise.

## Major

### M1. A preflight that cannot reach the launcher uses up a real attempt, and the worker keeps polling (R17, R10, D3)
- **Where:** `harness_activity/activity.py:227-241`. Only `Unserviceable` is caught. `DshRunner.check()` (`harness_activity/dsh/runner.py:267-276`) first calls `LauncherClient.connect`, which raises `LauncherError` (`harness_activity/dsh/launcher_client.py:31-34`). `request()` raises `LauncherError` too (`:54-55`, `:62-63`). `LauncherError` is a `RuntimeError`, not `Unserviceable`.
- **What happens:**
  - The exception leaves `run_harness_turn` before any heartbeat or `record_refusal`, so `prior.refusals` is not incremented.
  - The next Temporal attempt computes `real_attempt = attempt - prior.refusals` (`activity.py:243`), so this attempt counts as real even though no turn ran and no attempt row was written.
  - `on_unserviceable` is not called, so the worker keeps polling.
- **When it happens:** the paired DSH container restarts. This is the documented way to clear a dirty launcher (`infra/dsh/launcher.py:677-679`, "until this launcher restarts"), and also covers a crash or OOM. During startup `reap()` runs, and so does `digests()`, which hashes every installed file (`launcher.py:311-337`). Only then does the launcher replace the control socket (`launcher.py:425-431`). Until then, connecting to the stale socket path fails.
  - The worker container is not restarted, because compose `depends_on: service_started` does not restart dependents.
  - Each task the worker picks up fails its preflight. The default Temporal backoff is 1, 2, 4 and 8 s (`TURN_ATTEMPTS = 0`, `orchestrator/workflow.py:43,131`), so 5 attempts fit in about 15 s.
  - The 6th attempt raises `AttemptsExhausted("turn 1 was lost 5 times")` (`activity.py:257-258`), which is non-retryable. The task fails for good although no attempt ever ran.
- **Contract:** commit d8c576b states the intent "Refuse a turn the worker cannot serve without using an attempt". A launcher you cannot reach is the clearest case of a worker that cannot serve.
- **Test that would expose it:** point `h.acts.preflight` at a `DshRunner` whose control path does not exist. Run attempts 1..6 with the heartbeats carried over. Assert that every attempt is a refusal and that the turn never reaches `AttemptsExhausted`.
- **Possible fix:** treat `LauncherError` (and `OSError`) from the preflight as a refusal. Stop polling, or leave the worker's restart policy to decide.

### M2. Rows marked `lost` by `start` or by a refusal never get the ledger's usage unless a later real attempt opens (R12, D7 per notes.md#d7 and F101)
- **Where:**
  - `AttemptRepository.start` (`common/persistence/repositories.py:~146-157`) and `record_refusal` (`:238-250`) mark earlier `started` rows of the turn as `lost`. They don't touch tokens: the rows keep the 0 they were created with (server default 0 per migration 0003:68) and `usage_known = true`.
  - Only `close_unknown` (via `_charge` in `_open`) applies `_ledger_usage_sql` to `lost` rows (`repositories.py:569-571`).
  - The new F101 update in `close_unfinished` selects only `a.outcome = 'started'` (`repositories.py:291-301`).
  - `complete_task` calls `close_unfinished(task_id, None, ...)` (`orchestrator/activities.py:122`), so it never reaches `lost` rows.
- **Failure scenario:**
  1. Worker A is SIGKILLed during turn 1, attempt 1, with a dispatched request whose ledger row has NULL tokens.
  2. The heartbeat timeout fires. Attempt 2 goes to worker B, whose container is dirty or has a pin mismatch. `record_refusal(..., "dsh_unserviceable")` marks attempt 1 `lost` and B stops polling. This path is new in this round.
  3. No serving worker is left, so `schedule_to_close` (`turn_timeout * 6`) expires and `complete_task` runs.
  4. The TaskResult is charged correctly (F98), but attempt row 1 stays `(lost, 0, 0, usage_known=true)`. That is exactly the "never 0" case R12 forbids. notes.md#d7 says "A row closed without a finish (lost, ...) gets the ledger's settled usage through it, or NULL ...".
- **Same gap on another path:** a worker that dies between `attempts.start` (`activity.py:397`) and `_charge` in `_open` (`activity.py:374`), where the task then ends without another real attempt.
- **Test that would expose it:** extend `test_rows_closed_without_a_finish_hold_the_ledger_usage` with a closer "refused, then task completed":
  1. Start attempt 1 and dispatch an unsettled ledger row.
  2. Call `record_refusal(t, 1, 2, ...)`.
  3. Call `close_unfinished(t, None, "task_completed")`.
  4. Assert row 1 is `(lost, NULL, NULL, False)`.
- **Possible fix:** apply `_ledger_usage_sql` to `lost` rows as well in `close_unfinished`. It is idempotent, because it derives from the ledger and has an `a.usage_known` guard. Or apply it in `start` and `record_refusal` inside the same transaction.

## Nits (reported so you can decide; I judged each acceptable or could not fully verify it)

**N1. `destroy()` exceptions skip the DIRTY record (R10, F99).** In `infra/dsh/launcher.py:288-307`, `DIRTY.add` runs only if `destroy` gets to its end. An `OSError` from writing `cgroup.kill` or `cgroup.freeze`, or from `cg.rmdir()` (EBUSY), propagates out:
- On the `stop` op it becomes an error reply. The worker marks itself unhealthy, exits 3 and restarts. Its startup `check()` then passes, because the launcher's DIRTY set is empty.
- In the `finally` of `serve_connection` (`:419-422`) the exception kills the thread before `conn.close()`.

Either way a container with leftovers can be served again. Test: make the cgroup's `rmdir` fail, or have `cgroup.kill` raise, then assert `digests` reports the attempt as dirty.

**N2. A worker-side stop timeout fails the task for good even when the launcher later cleans up (R9).** `DshAttempt.stop` (`harness_activity/dsh/runner.py:175-197`) turns a timeout after `grace + STOP_REPLY_MARGIN_SECONDS` into `processes_left=None`. `classify` then sees `cleanup_ok` false, which gives `("DshCleanupFailure", False)`; see the expectation in `tests/integration/test_dsh_activity.py`, F100 test. A slow but successful launcher (load, or a 5 s grace plus a 5 s kill wait close to the 15 s cap) therefore ends the task non-retryably. That is conservative and consistent with R9, but it could be retryable after the worker's self-quarantine.

**N3. Final checkpoint after a step-limit stop skips the D6 tool-call check (R5, D6, F96).** After the `keep_tree` stop (`runner.py:438-443`), the `_run` final `checkpoint()` (`activity.py:515`) captures the home directory with no barrier and no D6 check of the newest tool-call ID. Nothing is running, because `kill_members` empties the cgroup and a non-cooperative stop is classified as a failure. So the capture is at rest, but the D6 consistency proof (the tool-call ID in the session files) is not applied. I could not verify DSH's on-SIGTERM session writes.

**N4. A cancel that lands during the step-limit stop leaves the row for `complete_task`.** `asyncio.shield(attempt.stop(..., keep_tree=True))` re-raises `CancelledError` through `except (asyncio.CancelledError, Superseded): raise` (`runner.py:516-517`). That is a bare `CancelledError` rather than a `RunnerFailure(cancelled=True)`, so `_runner_failed` doesn't run. The row is not recorded `cancelled` and is closed later as `failed/task_completed` (R18 cancel case). This is a narrow window, and F98 and F101 now cover the usage.

**N5. `complete_task` has new dependencies and gaps (F98).** `_with_ledger_usage` (`orchestrator/activities.py:42-60`):
- It now does `self.registry.templates[payload.resolved.template]`. A template renamed or removed in the orchestrator's registry while tasks are in flight raises `KeyError`. After 5 `SHORT_RETRY` attempts the Workflow fails without completing the task.
- It uses the current registry's `context_window`, not the pinned version's.
- It does not reconcile `inner_turns` with the ledger (D11) for turns that ended with no Activity code running.

**N6. Race in `list_files_body` (F97).** `list_files_body` (`harness_activity/tools.py:183-197`) checks `base` and then calls `os.walk(base)`. A command could swap `base` for a link between the check and the walk; `scandir` of the top level follows it. Only file names would leak, not contents.

**N7. `stop_polling` keeps no reference to the shutdown task.** `workers/main.py:165-169` creates `create_task(worker.shutdown())` without keeping a reference, and asyncio docs advise holding one. In practice it is kept alive by its awaited futures. A dirty launcher also only clears on a DSH container restart, so the worker restart-loops (exit 3, then a `CapabilityError` at startup) until an operator acts. That looks intended, but no doc I read says so.

**N8. Same partial-failure pattern as M1 on the refusal path itself.** In `activity.py:233-237`, the refusal heartbeat (refusals + 1) is sent before `record_refusal`. If the DB write fails, the exception escapes, `on_unserviceable` is not called, and the next attempt still treats this one as a refusal while no refused row exists. This mirrors the pre-existing version-refusal path.

**N9. Process metadata disagrees about review state.** The phase front matter has `impl_review: passed`, but `design_review: { status: changes-requested }`. The plan's decision log (2026-11-16) says "A targeted design review is due", and the plan's Phases table still shows phase 02 "in-progress". I did not find that targeted design review recorded in this range.

## Checked and found sound
- `LauncherClient` matches replies by id (`launcher_client.py:37-44`). A stop request cancelled by `wait_for` cannot hand its stale reply to a later request.
- The `keep_tree` stop followed by `close()` gives a full stop (destroy). A worker death in between leads to destroy on connection close (`launcher.py:419-421`).
- The F99 refusal fences a zombie's later finish: a newer row exists, so `FenceRejected` leads to `Superseded` (R6).
- `share()` and `open_inside` use O_NOFOLLOW per component plus fwalk with `follow_symlinks=False`.
- `complete_task` takes the max of the Workflow and ledger totals, so it is idempotent on retry and never double-counts a request.

Files cited:
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/dsh/runner.py
- <repo>/harness_activity/dsh/launcher_client.py
- <repo>/common/persistence/repositories.py
- <repo>/orchestrator/activities.py
- <repo>/orchestrator/workflow.py
- <repo>/infra/dsh/launcher.py
- <repo>/workers/main.py
- <repo>/harness_activity/tools.py
- <repo>/tests/integration/test_dsh_usage.py
- <repo>/tests/integration/test_dsh_activity.py

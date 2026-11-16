<!-- Verbatim subagent report (impl-review-phase-02-round-2-scope); saved by the coordinator per docs/reviews/README.md rule 1. The coordinator's brief carried a wrong full SHA; the reviewer received the correction and reviewed the stated range. -->

Scope review: phase 02, DSH runner and worker pair. Diff 562733a..e053d233cb39655e47ed0c22d1e37c1ed71fe14b

The full SHA in the original brief (e053d2362a5d…) does not resolve. I reviewed the corrected range, `562733a72b880d13576ced63e8b8ad09716094df..e053d233cb39655e47ed0c22d1e37c1ed71fe14b`, with all files read at e053d23. Nothing was run.

## Major

**M1. The D9 charge and `usage_known=false` never reach the Workflow when a turn is cancelled, and the charge is never made when a turn ends without Activity code running (R12, R13, D7, D9)**
- **Where:** `harness_activity/activity.py`, `run_harness_turn` → `_runner_failed` and `_charge`; `orchestrator/workflow.py`, `failed_turn_usage`.
- **Mechanism:**
  - The `_charge` in `_runner_failed` changes `heartbeat.base` only after `heartbeat.running()` has already sent its final heartbeat. The final heartbeat is sent in the `finally` of `running()`, inside `_attempt`. `_runner_failed` runs later, in `run_harness_turn`'s `except RunnerFailure`.
  - On a non-retryable failure the charge still travels in the `ApplicationError` details. On cancel, the code raises a bare `asyncio.CancelledError() from failure`, which carries no details.
  - So the Workflow's `failed_turn_usage(e.cause)` sees only the pre-charge heartbeat: tokens without the `context_window + 2048` charge, and `usage_known` true.
- **Scenario:** a DSH turn whose model request is in flight (fake model `pause`), then `handle.cancel()`.
  - The attempt row is correctly `(NULL, NULL, false)`.
  - But if the Workflow goes on to `complete_task`, it gets `usage_known=True` and tokens without the charge for the in-flight request.
- **Same gap when no Activity code runs:** when the last attempt is lost and the turn ends without any Activity code running, the charge is never made at all:
  - `schedule_to_close` expires (`turn_timeout * 6`);
  - or a cancel arrives while the worker is dead, which `WAIT_CANCELLATION_COMPLETED` resolves only by timeout.
  - In both cases the Workflow reads the last heartbeat. The lost attempt's row keeps its creation-time zeros, because `close_unknown`'s lost-row fix runs only from a later `_charge`.
  - notes.md#d9 promises: "A turn that ends with no later attempt (cancel, a non-retryable failure, attempts exhausted) charges its own unsettled rows."
- **Evidence:** `activity.py` `_attempt` (`async with heartbeat.running():`), `_runner_failed` (`if failure.cancelled: raise asyncio.CancelledError() from failure`), `workflow.py` `failed_turn_usage`. The tests stop at the attempt row:
  - `tests/integration/test_dsh_outcomes.py` `test_cancel_stops_the_attempt_within_the_grace_and_stays_clean` checks `task_attempts` only and suppresses `WorkflowFailureError`.
  - `tests/integration/test_dsh_usage.py` `test_cancelled_attempt_charges_its_own_unknown_request` asserts only the row.
- **Not verified:** I could not confirm whether the Python SDK puts the last heartbeat into a cancelled activity's `CancelledError.details`. Either way, that heartbeat is pre-charge.
- **Test that would expose it:** cancel with a request in flight, then assert `TaskResult.usage_known is False` and `tokens_in == settled + WINDOW` (and the tasks row too).

**M2. A pin mismatch or a dirty container is refused per attempt, not per queue, so one bad worker burns the whole turn (R17, R10, D3)**
- **Where:** `harness_activity/dsh/runner.py`, `open_attempt` (`if self.unhealthy is not None: raise LauncherUnhealthy`, and the `RuntimePinMismatch` re-check); `activity.py` `_attempt`, which calls `attempts.start(...)` before `_open`.
- **Mechanism:**
  - R17 says the worker "refuses to serve the queue". After start-up, though, the refusal is a plain retryable exception thrown after the attempt row was inserted.
  - It is not a `record_refusal` (the uncounted refusal used for template-version mismatches), so it counts toward `MAX_REAL_ATTEMPTS`.
  - The worker keeps polling `tpl.local-dsh`.
- **Scenario:** one `local-dsh` worker whose container was recreated from another image, or one that saw a leaky stop.
  - Temporal retries the turn on the same worker with 1, 2, 4, 8 s backoff.
  - Each retry inserts a `started` row that the next start marks `lost`.
  - On the sixth Temporal attempt the turn fails with `AttemptsExhausted`, within about 15 s.
  - Nothing ran, yet the turn records five lost attempts.
- **Scope of `unhealthy`:** the flag lives on the `DshRunner` object, so it covers one worker process, while the fault is in the container:
  - a restarted worker process starts with `unhealthy=None`;
  - the launcher reaps only at its own start, and its `digests` report has no leftovers field;
  - so the restarted worker serves the dirty container again.
- **Tests:** they cover only the runner level (`test_dsh_activity.py`: `test_attempt_on_an_unpinned_runtime_is_refused`, `test_failed_cleanup_after_success_stops_new_attempts`). Nothing tests the Activity or queue level.
- **Test that would expose it:** run a workflow against a worker whose `DshRunner.unhealthy` is set, or whose pin mismatches. Assert the turn is not failed and no `lost` rows pile up, or that the worker stops polling.

**M3. A dirty stop during a run never marks the container unhealthy (R10, review F71 mechanism)**
- **Where:** `runner.py`, `DshAttempt.stop` sets `self.stopped = True`; `DshAttempt.close` calls `on_dirty` only `if not self.stopped`.
- **Mechanism:**
  - On the deadline, cancel, abort and step-limit paths, `run()` calls `attempt.stop(grace)` itself.
  - The report then feeds `classify` (`DshCleanupFailure`), but `_dirty` is never called.
  - Only a clean-exit run, where `close()` does the stop, can set `unhealthy`.
- **Scenario:** a deadline stop where `destroy()` leaves `processes_left=1` (for example a process stuck in D state within the 5 s kill wait).
  - The turn fails `DshCleanupFailure`.
  - The same worker then opens the next attempt of another task on a container that still holds a live leftover process and its non-removed cgroup.
- **Test:** only the success-then-close path is tested (`test_failed_cleanup_after_success_stops_new_attempts`).
- **Test that would expose it:** patch the `stop` reply to `processes_left: 1` on a deadline-stopped run, then assert the next `open_attempt` raises `LauncherUnhealthy`.

**M4. Attempt rows closed by `close_unfinished` keep the 0 they were created with (D7, R12)**
- **Where:** `repositories.py` `close_unfinished` (no token update), and `close_unknown`:
  - its second UPDATE reaches only attempts with their own NULL ledger rows;
  - its third UPDATE reaches only `outcome = 'lost'` rows.
- **Scenario:**
  - Attempt 1 is lost with an unsettled request, so it is charged.
  - Attempt 2 fails with `HarnessInputError`, for example `BlobCorrupt` from `DshSessionStore.load` on a session-digest mismatch. That goes down the `NonRetryableError` path, where `close_unfinished` marks attempt 2 `failed`.
  - The `_charge(attempt+1)` that follows leaves attempt 2's row at `tokens_in = tokens_out = 0, usage_known = true`.
  - notes.md#d7 says "An attempt row holds the turn's cumulative usage through that attempt … numbers with `usage_known = false` when they include a D9 charge". R12 says "never as 0".
  - The same applies to rows `complete_task` closes with `turn=None`.
- **Test that would expose it:** a lost attempt with an unsettled row, then a corrupt session blob on attempt 2. Assert attempt 2's row is not `(0, 0, true)`.

## Nit

**N1. `inner_turns` is counted two different ways (D11)**
- The gateway sets `usage.inner_turns = ledger.settled()["logical_steps"]`: distinct request bodies (`gateway.py` `completions`).
- `_charge` uses `settled_count + unknown`: ledger rows (`activity.py` `_charge`, `inner_turns=max(..., settled_count + unknown - live.inner_turns)`).
- **Scenario:** an attempt where the runtime resends the same body after a 502 has two rows but one step.
  - With no later attempt, the turn reports 1.
  - If any later attempt opens, it reports 2.
- Refused-before-generation (4xx) rows also count as steps there.
- The R18 cases have one dispatch per step, so `extra_inner_turns` cannot catch this.

**N2. The `inner_max_turns` ceiling is per attempt, while D11 counts steps per turn (D11)**
- `UsageLedger(..., steps=config.inner_max_turns)` is built per `run()` and counts only that attempt's records.
- A turn can therefore make up to 5 × `inner_max_turns` model steps.
- `openai_agents` passes `max_turns` per `Runner.run`, so both runners agree. Reported because D11 makes counting per turn while the limit stays per attempt.

**N3. `request_id` and event `seq` restart for a second run in a kept attempt (bare `HarnessRunner` contract)**
- `UsageLedger` numbers requests `req-0001…` per instance, and `AttemptEvents.seq` starts at 0 per run.
- `_attempt_for` reuses a kept attempt ("a second run in an attempt this runner kept"). Against `UsageLedgerRepository`, the second run's first dispatch hits the `usage_ledger` primary key (task, turn, attempt, request_id), and the `IntegrityError` escapes the gateway route.
- The conformance test `test_stop_run_and_superseded_reach_the_runner_unwrapped` runs twice in one attempt, but it uses `MemoryLedgerStore`, which overwrites dict keys, so this is masked.
- The Activity path is not affected: one run per attempt.

**N4. Tool-call usage does not survive worker loss (R11)**
- Tokens are rebuilt from the durable ledger, but `tool_calls` exist only in the executor's memory (`executor.py` `self.usage.tool_calls += 1`) and the heartbeat.
- A SIGKILL loses the tool calls made since the last heartbeat (up to `heartbeat_timeout/3`).
- R11 says "Token and tool usage come from the gateway ledger and executor". `test_worker_sigkill_reaps_attempt_and_replacement_recovers` does not check `tool_calls`.

**N5. An "unresolved usage" denial starts no exit timer (R8)**
- `STEP_DENIALS` covers only `model-step limit` and `token budget`, so `limited_at` is not set after an `unresolved usage` 429.
- A runtime that keeps retrying after a 5xx or transport failure is stopped only at `context.deadline`, up to `turn_timeout - 20 s` later, instead of within the grace.
- The R18 retry cases pass only because DSH 0.2.2rc2 exits by itself.

**N6. The test's heartbeat hand-off does not match Temporal (D9, test scope)**
- `test_retryable_failure_is_charged_once_across_attempts` feeds the `ApplicationError` details to the next attempt as `heartbeat_details` (`heartbeats.append(raised.value.details[0])`).
- Real Temporal hands over the last heartbeat, which is pre-charge (see M1).
- The result is still right because `_charge` rebuilds the totals from the ledger. But the "charged once" property is only tested with the post-charge base, not the base production actually passes.

**N7. Worker-side tool bodies are not covered by the barrier freeze (D6)**
- File and MCP tool bodies run in the worker (`asyncio.to_thread(_invoke, ...)`, MCP servers started by the worker), outside the attempt cgroup.
- A call DSH's MCP client gave up on, but that is still running in the worker thread, can write to the workspace while the barrier captures it.
- This needs a client-side timeout shorter than the tool's, so it is unlikely; not tested.

## Checked and consistent
- The token budget is per turn across attempts: `_open` passes `turn.remaining_tokens − cumulative` including charges.
- The ledger dispatch fence and stale-attempt settles: `settled_at IS NULL` after `close_unknown`.
- Charging repeatedly is idempotent across several lost attempts (the `max()` against the heartbeat base).
- D10 publishes outputs only after the fenced finish.
- The pin is checked at start-up and at every attempt open.
- The barrier runs on every request after the first.
- Isolation: per-attempt `/tmp`, attempt trees hidden behind a tmpfs, kill on control-socket close.
- Event `seq` is per attempt under the lock.
- `concurrency_per_pod: 1` is enforced by the loader and used for `max_concurrent_activities`.

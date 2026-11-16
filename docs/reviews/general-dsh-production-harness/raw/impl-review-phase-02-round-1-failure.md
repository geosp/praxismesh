<!-- Verbatim subagent report (impl-review-phase-02-round-1-failure); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. -->

Review of phase 02 (diff 562733a..43798c7, frozen at 43798c7), through the failure/restart lens. All file:line references are at 43798c7.

I found 2 Majors on usage accounting (R12/R13/D7), 1 Major on stopping a frozen attempt (D6/R8/R9), 1 Major on cross-task /tmp visibility (R15), 1 Major on the pin check only running at startup (R17), and 1 Major on usage spent by a stale attempt during overlap (R11/R13). Nits follow. I ran nothing; everything below comes from reading the code.

## How each unit runs (what I traced)

**run_harness_turn (DSH path)**, in order:
1. Read the heartbeat details; template check or `record_refusal`.
2. Start the heartbeat task; `attempts.start`. This is fenced and marks earlier `started` rows as `lost` (`repositories.py:137-170`).
3. `_open`: `ledger.close_unknown` runs under the task lock (`repositories.py:487-535`). It closes unsettled rows, nulls earlier attempt rows and returns the settled totals. Then `heartbeat.base` is raised and `open_attempt` runs: connect, `rmtree` and `mkdir` the tree, then the launcher `open` (`runner.py:176-199`).
4. `_run`: `checkpoints.latest`, blob get and unpack, `DshSessionStore.load` (clear the home, get the blob, check the digest, unpack, share), or `_fresh_start`.
5. `DshRunner.run`:
   - setup: `executor.start` (MCP servers), Gateway, SocketServer, config writes, `server.start`, launcher `start`;
   - the poll loop;
   - per request in a separate server task: barrier (`newer_attempt_exists`, `ws.pack`, 2 blob puts, `insert_fenced`, thaw), then `ledger.admit` (durable dispatch row, `ledger.py:90-91`), forward, then settle (`repositories.py:461-485`, `WHERE settled_at IS NULL`);
   - at the end: read `result.json`, freeze.
6. `classify`, then raise `RunnerFailure` (→ `_runner_failed`), or `checkpoint(finish)` then `_finish` (`assert_current`, output blob puts, fenced `attempts.finish`).
7. `scope.close` is shielded: launcher `stop`, close, `rmtree`.

**Launcher, per connection** (`infra/dsh/launcher.py:310-370`): `open` creates the cgroup (`exist_ok=False`). The other ops run serially. `exec` runs on its own thread. The `finally` runs `destroy` if an attempt is still open.

What holds up well: a SIGKILLed worker releases its attempt (the connection closes, then `destroy`). A lost-after-finish attempt goes straight to `_finish`. A stale attempt that finishes is rejected at `insert_fenced` and the fenced finish. For a stale attempt, `close_unfinished` does nothing, because `start` already marked its row `lost`. Launcher replies carry ids, so a cancelled `poll` cannot be mistaken for a later reply (`launcher_client.py:37-64`).

## Findings

### 1. Major: a turn that fails for good reports `usage_known = true` and leaves out the current attempt's unknown requests (R12, R13, D7, D9)

**Where:**
- `orchestrator/workflow.py:131-139` and `46-59`: the `ActivityError` branch takes tokens, inner turns and attempts from the details but never reads `usage_known`, so `usage_known` stays `True`.
- `harness_activity/activity.py:273-305`: `_runner_failed` records the failing attempt with `used = heartbeat.current()` and `usage_known=used.usage_known`. Neither includes this attempt's own unsettled requests (`ledger.settled()["unknown_usage"]`), so there is no D9 charge.
- `harness_activity/dsh/policy.py:39-50`: `DshCleanupFailure`, `DshBlocked`, `DshForcedStop` and `DshCheckpointLimit` are non-retryable and are checked before `DshUsageUnknown`. Cancellation (`DshCancelled`) goes the same way.

**Scenario:**
1. The model stalls with one request dispatched and unsettled. The deadline fires and the runtime ignores SIGTERM (the R9 case).
2. `classify` returns `("DshForcedStop", False)`.
3. The attempt row gets non-null tokens that exclude the in-flight request, with `usage_known = true`.
4. The `ApplicationError` details carry `usage_known: true` and no `context_window + 2048` charge.
5. No next attempt runs, so nothing charges that request. The `TaskResult` says `usage_known = true` and under-counts.

The same thing happens when:
- an earlier lost attempt was charged (base `usage_known = false`) and the turn later fails non-retryably: the workflow still reports `usage_known = true`;
- the 6th attempt hits `AttemptsExhausted` (`activity.py:233-257`): that path skips `close_unknown`, so the 5th attempt's in-flight request is never charged;
- `schedule_to_close` expires: `last_heartbeat_details` carries `usage_known`, but it is ignored.

**Test:** an Activity integration test with a stalled model plus an ignored SIGTERM. Assert that the attempt row has null tokens and `usage_known = false`, that the details include the D9 charge, and that `TaskResult.usage_known is False`. Add a workflow unit test where `ActivityError` details carry `usage_known: false`.

### 2. Major: stopping an attempt while the barrier holds it frozen is always a forced stop (D6, R8, R9)

**Where:**
- `infra/dsh/launcher.py:242-251`: `stop` calls `runtime.terminate()` and `wait(grace)` without thawing first. The thaw only happens later, in `destroy` (`launcher.py:257`).
- `runner.py:385-397`: the poll loop stops on deadline, cancellation, abort or `thaw_failed`, whether or not a barrier currently holds the cgroup frozen (`runner.py:291-310`).

**Scenario 1 (deadline):** the turn deadline arrives while the barrier is in `capture_and_commit` (workspace pack plus 2 blob puts plus a DB insert; seconds for a large workspace or slow S3). A frozen process cannot handle SIGTERM, so `wait(5)` times out and `cooperative` is `False`. `classify` returns `DshForcedStop`, non-retryable (`policy.py:43-44`). An ordinary deadline that should be `DshTurnDeadline` (retryable) fails the turn and the task for good.

**Scenario 2 (thaw fails):** thaw times out (`launcher.py:229-237`), so `thaw_failed` is set and the poll loop calls `stop` on a cgroup that is still frozen. The result is a forced stop, non-retryable, which contradicts D6: "A failed barrier is a retryable infrastructure failure with no checkpoint." In this case the barrier's checkpoint was also already committed (`barrier.py:69-76`); see Nit 2.

**Scenario 3 (cancellation during a barrier):** same as scenario 1, recorded as `failed`/`DshForcedStop` rather than `cancelled`.

**Related race, unproven:** `destroy` runs `rmtree` on the tree while the barrier task may still be packing. `ws.pack` of a home that has already gone yields an empty archive without error (`workspace.py:19-29`; `rglob` on a missing directory returns nothing). The window before `server.close()` cancels the barrier task is small, but a commit inside it would hand the next attempt an empty session, so it would start fresh and lose the conversation (R5).

**Test:** launcher test: `freeze`, then `stop` on a SIGTERM-honouring runtime; expect `cooperative: true`. Runner test: deadline while the fake commit sleeps; expect `DshTurnDeadline`.

### 3. Major: commands share the container `/tmp` across attempts and tasks (R15)

**Where:** `launcher.py:141-154`. `_isolate` hides only `ATTEMPTS` behind a tmpfs. Commands keep the container-wide `/tmp` tmpfs (`infra/docker-compose.yml:194`, `tmpfs: [/tmp, /work, /run]`). The command env sets no `TMPDIR` (`launcher.py:203`). `destroy` and `reap` never clean `/tmp`.

**Scenario:** a command in task A runs `echo data > /tmp/x`. A later attempt, of another task, runs `cat /tmp/x` and reads it. This is state an earlier run left behind and it survives every attempt until the container restarts. R15: "Commands only see their own attempt's workspace."

**Test:** an integration test with two attempts in sequence: the first writes `/tmp/marker`, and the second must fail to read it.

### 4. Major: the pin is checked only at worker startup, not after the DSH container restarts (R17)

**Where:** `workers/main.py:97-100`. `verify_launcher_report` runs once in `build_harness`. `DshRunner.open_attempt` (`runner.py:176-193`) connects to whatever launcher is listening at `DSH_CONTROL`. `dsh-a` has `restart: unless-stopped` and can be recreated on its own.

**Scenario:** `docker compose up -d --build dsh-a` with a bumped DSH release, or the container restarting from a different image tag. The launcher re-creates the control socket (`launcher.py:376-380`). The running worker never re-checks and keeps serving `tpl.local-dsh` on unpinned digests. R17: "Workers serve a DSH queue only when the launcher's digests match."

**Test:** start the worker against launcher A, swap in a launcher whose `digests` reply differs, run a turn, and expect a refusal or a worker exit.

### 5. Major: model usage a stale attempt spends after the new attempt starts is not counted in the turn's result (R11, R13, D9)

**Where:**
- `activity.py:314-328`: `close_unknown` is read once, at the start of the new attempt.
- `gateway.py:234-238`: there is no barrier, and so no `newer_attempt_exists` check, before an attempt's first request.
- After the barrier's fenced commit, `ledger.admit` writes the dispatch row (`ledger.py:90-91`).

**Scenario:** worker A (attempt 1) passes its barrier's fenced insert and is paused (SIGSTOP or GC) before `admit`. Its heartbeat times out and attempt 2 starts on worker B; `close_unknown` sees no row from attempt 1. A resumes, inserts the dispatch row, forwards the request and settles it with real tokens (the row is still `settled_at IS NULL`, `repositories.py:475`). Attempt 2's `TurnOutcome` and budget leave out those tokens. If A dies before settling, the row stays unsettled and only an attempt 3 would charge it.

The same applies to a stale attempt's first request, which has no guard at all.

**Test:** extend `test_stale_dsh_attempt_writes_no_checkpoint_outcome_or_artifact` so that A is stopped between the barrier commit and dispatch. Assert that the ledger total equals `TaskResult.tokens_in`.

## Nits

1. **R12, D7: a lost attempt's row reads 0 tokens when all its requests settled.** Migration `0004` makes the columns nullable but keeps `server_default "0"` (from `0003_phase1_tables.py:68-69`). `close_unknown` nulls only attempts with unsettled rows (`repositories.py:511-515`). An attempt lost after only settled requests keeps `tokens_in = 0, usage_known = true`, while the ledger shows the spend. Rated Nit because the usage isn't unobserved, but the attempt row still reads 0.
2. **D6: a failed thaw is reported as a barrier failure after the checkpoint was already committed** (`barrier.py:72-76`). D6 says "a failed barrier ... with no checkpoint." The checkpoint was captured while frozen, so it is consistent, which is why I rate this Nit.
3. **D7: the current attempt's row combines `usage_known = false` with non-null tokens** (`repositories.py:211`, `activity.py:518`). `common/schemas/task.py` says "None when usage_known is false (D7)". The test `test_dsh_outcomes.py:570-578` asserts the combination, so it looks deliberate, but it contradicts that schema comment.
4. **Cancellation before or after the poll loop leaves the row `started`.** If a cancellation arrives during `executor.start`, launcher `start`, `checkpoint(finish)` or `_finish`, the error is re-raised (`runner.py:404-405`) and the row stays `started` until a later start marks it `lost`. Only a cancellation inside the poll loop records `cancelled`. Inconsistent, not harmful.
5. **`STOP_MARGIN_SECONDS` misses the time already spent before `_open`.** The deadline is computed in `_open` (`activity.py:329-339`) from the full `start_to_close` and a `remaining_wall_time` the TurnInput fixed when the turn was scheduled, so it is the same for every retry. On retries the attempt deadline can therefore run past the task's wall-time budget. The 20 s margin covers normal cases.
6. **Usage-ledger request ids restart for a second `run` in the same attempt.** A second run in an attempt the runner kept (`runner.py:372-374`, bare `HarnessRunner` use) starts a new `UsageLedger` at `req-0001`. With `UsageLedgerRepository` that collides with the `usage_ledger` primary key (task, turn, attempt, request_id) and raises unhandled in the gateway route. The Activity path makes one run per attempt, hence Nit.
7. **A tool thread can recreate files after `destroy`.** A worker-side tool body running in `asyncio.to_thread` (`executor.py:163`) is not stopped by `server.close()`. A `write_file` that finishes after `destroy` could leave files in the shared volume (R10, "no attempt tree remains"). Narrow window.
8. **R11: tool-call counts since the last heartbeat are lost with the worker.** They live only in the heartbeat and executor memory, so a lost attempt's tool calls after its last heartbeat are uncounted. The ledger rebuilds tokens only.
9. **D7 type.** D7 says `checkpoints.session_ref jsonb`; the migration uses `sa.JSON` (json). It is functionally fine.
10. **A transient barrier failure discards a run that finished.** Any transient barrier failure sets `gateway.fault`, so a run that later ends with `finish_task` is still classified `DshCheckpointFailure` (`policy.py:61-62`) and retried. This is safe but wasteful.

## Files referenced
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/dsh/runner.py
- <repo>/harness_activity/dsh/gateway.py
- <repo>/harness_activity/dsh/ledger.py
- <repo>/harness_activity/dsh/barrier.py
- <repo>/harness_activity/dsh/policy.py
- <repo>/harness_activity/dsh/executor.py
- <repo>/infra/dsh/launcher.py
- <repo>/infra/docker-compose.yml
- <repo>/common/persistence/repositories.py
- <repo>/common/persistence/migrations/versions/0004_dsh_usage_and_sessions.py
- <repo>/orchestrator/workflow.py
- <repo>/workers/main.py
- <repo>/tests/integration/test_dsh_outcomes.py

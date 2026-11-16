<!-- Verbatim subagent report (impl-review-phase-02-round-2-contract); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. The coordinator's brief carried a wrong full SHA; the reviewer received the correction and reviewed the stated range. -->

## Phase 02 contract review: DSH runner and worker pair

I reviewed `562733a7..e053d233cb39655e47ed0c22d1e37c1ed71fe14b`, the corrected full SHA. I read the code but ran nothing (no builds or tests). Three findings are real problems, two Blockers and two Majors; a handful of smaller mismatches are rated Nit.

### Blocker 1: when the runtime is stopped at the step limit or token budget, an empty checkpoint is committed (R5, D6, D1)
- **Where:** `harness_activity/dsh/runner.py:440-463` (the poll loop sets `STEP_LIMIT_STOP`, then `attempt.stop(grace)`), `runner.py:485-500` (`returncode=0` and `candidate={}`, so `classify` returns None) and `runner.py:513-514` (returns a valid `continue` result). Then `harness_activity/activity.py:492` (`await checkpoint(finish)`), with `ws.pack` and `store.capture()` at `:434-436`.
- **What goes wrong:** the launcher's `stop` calls `destroy()`, which removes the whole attempt tree (`infra/dsh/launcher.py:263, 279-284`). The runner still reports a valid `continue`, so the Activity packs `<tree>/workspace` and `<tree>/home`, which no longer exist.
  - `Path.rglob` on a missing directory yields nothing, so `ws.pack` and `pack_session` produce empty archives.
  - Those go through `insert_fenced` as the latest checkpoint.
- **Scenario:** `inner_max_turns=1`, or a barrier `StopRun` for the token budget. The runtime gets the 429 and doesn't exit within `LIMIT_EXIT_SECONDS` (2 s). The turn ends `continue` and commits an empty workspace and session. The next turn restores nothing: all edits are lost, and since `resume=False` it starts with no conversation and only `CONTINUE_MESSAGE` as input.
- **Why no test catches it:** `test_step_limit_stops_a_runtime_that_does_not_exit` (`tests/integration/test_dsh_activity.py:501`) calls `runner.run` directly, not through the Activity. The R18 `inner-limit` case uses the real DSH, which exits on its own (the spike evidence shows `exit: 0`, `finish_reason: error`), so it never takes this path. Non-success cases don't check artifacts either.
- **Test that would expose it:** the stubborn driver through `run_harness_turn`, then assert the latest checkpoint still contains `input.txt` and a non-empty `session_ref`.

### Blocker 2: an output symlink makes the worker publish its own files, including its credentials (D4, R15, plan Summary)
- **Where:** `harness_activity/activity.py:525-527` (`target = workdir / path; if target.is_file(): ... target.read_bytes()`). Unlike `tools.inside`, this does no `inside()` check, no `lstat` and no symlink refusal.
- **Scenario:** untrusted task text or a repository file gets the model to run `run_command("ln -s /proc/self/environ answer.txt")`, then `finish_task(done)`. At `_finish` the worker follows the link in its own mount namespace. It reads its own environment (database, S3 and model keys, template `secret_refs`) and uploads it as the `audit` output artifact in the TaskResult. No race is needed.
- **Related, needs a race:** `inside()` (`harness_activity/tools.py:54-59`) resolves the path, then opens it. A backgrounded command (still alive and not frozen during tool execution) can swap a directory under the workspace for a symlink to `/proc/self` between the check and the open. `read_file` then returns worker files to the model. `share()` (`runner.py:98-109`) does `lstat`, then `chown`/`chmod` that follow links, which is the same pattern.
- **Contract:** the Summary says the DSH container "has no credentials"; D4 confines commands to their workspace; R15 says commands "only see their own attempt's workspace". Under DSH this code now runs against a workspace that a separate, untrusted UID can write.
- **Test that would expose it:** an R15-style integration test where a command symlinks the declared output to `/proc/self/environ`. Assert the task's artifact is refused or empty.

### Major 1: a turn that ends with no Activity code running stores 0 and reports usage as known (R12, R13, R11, D9, D7)
- **Where:** `orchestrator/activities.py` `complete_task` calls `close_unfinished(task_id, None, "task_completed")` (`common/persistence/repositories.py:267-300`). That changes only outcome and category, so tokens keep their `server_default="0"` (`0003_phase1_tables.py:68-69`) and `usage_known` stays true. `orchestrator/workflow.py` `failed_turn_usage` takes usage from the last heartbeat, which has no ledger view.
- **Scenario:** the worker is SIGKILLed on the last attempt with a request in flight, and `schedule_to_close` (`turn_timeout*6`) expires before another attempt runs. Cancelling the workflow while the worker is dead does the same, as does a cancel outside the poll loop (`runner.py:473-474` re-raises without `RunnerFailure`, for example during the final checkpoint).
  - The attempt row ends with `tokens_in=0, usage_known=true`.
  - The TaskResult has neither the D9 charge nor requests settled after the last heartbeat, and says `usage_known=true`.
  - The notes say a turn that "fails for good, is cancelled or runs out of attempts charges its own unsettled requests". These three ends are missed.
- **Test that would expose it:** SIGKILL the worker mid-request with `maximum_attempts` or `schedule_to_close` set so that no second attempt runs. Assert the attempt row has NULL tokens and the TaskResult has `usage_known=false` and includes the charge.

### Major 2: commands share persistent writable locations across attempts and tasks (D4 restated, R15)
- **Where:** `infra/dsh/launcher.py:143-159` (`_isolate`) re-mounts only `/work`, `/tmp` and `/attempts`. The container's `/run` tmpfs (`infra/docker-compose.yml`, `tmpfs: [/tmp, /work, /run]`) and Docker's default `/dev/shm` stay shared.
  - Docker tmpfs mounts default to mode 1777, so UID 4242 can write them. I inferred this; check it with a probe.
  - `reap()` and `destroy()` never clean them.
- **Scenario:** a task A command runs `cp -r /work /dev/shm/a` (or writes to `/run/a`). A later task B attempt on the same container, with the same UID 4242, runs `cat /dev/shm/a/...` and reads task A's files. D4 promises "a private mount view that shows only their own workspace (as /work) and a per-attempt /tmp"; impl-review F63 fixed `/tmp` for exactly this reason.
- **Why no test catches it:** the R15 test (`test_dsh_outcomes.py:416`) only probes another attempt's tree, the session file and a backgrounded process.
- **Test that would expose it:** attempt 1 writes `/dev/shm/x` and `/run/x`; attempt 2 must not see them. Alternatively, the probe can assert that a command's writable mounts are exactly `/work` and `/tmp`.

### Nits
1. **Stale attempt writes without the fence (R6, D10).** `_runner_failed` → `_charge` → `close_unknown` (`repositories.py`, `UsageLedgerRepository.close_unknown`) runs even for a stale attempt. It rewrites `tokens_in`/`tokens_out`/`usage_known` on rows at or below the writer, including its own and lost rows. The outcome isn't changed and the values come deterministically from the ledger, but R6 says stale attempts write no attempt outcome. Rated Nit because only usage columns change.
2. **Leftover child processes don't count as a forced stop (R9).** `stop()` judges "cooperative" only by the runtime PID (`launcher.py:251-263`). The runtime's own children, such as `mcp_bridge`, that need `cgroup.kill` after a natural exit are killed silently. They aren't recorded as a forced stop, only as dirty if they survive the kill.
3. **`inner_turns` mixes two counts (D11).** `_charge` (`activity.py`, `inner_turns=max(..., settled_count + unknown - live)`) counts earlier attempts' ledger requests. The gateway counts logical steps (`gateway.py`, `usage.inner_turns = ledger.settled()["logical_steps"]`). They differ if a body is re-sent.
4. **R18 `cancel` checks less than the other cases.** `test_cancel_stops_the_attempt_within_the_grace_and_stays_clean` suppresses the workflow result and compares only the stop reason. That is acceptable because the spike's `result` for `cancel` is null, which I confirmed in the evidence file.
5. **The output cap doesn't bound `n` (D9).** The gateway caps `max_tokens` (`gateway.py` `to_model`) but leaves `n` alone. A request with `n>1` could exceed the 2048-per-request output charge.
6. **R17 trusts the launcher's own report.** The digest is self-reported, and `verify_installed` skips RECORD paths outside the site directory (`infra/dsh/pins.py`). A tampered launcher could report the pinned digest. This seems inherent in the design.
7. **`usage_known` is missing from the CLI (D7).** `AttemptRepository.list` (`repositories.py:302-312`, used by `orchestrator/cli.py:129`) doesn't select it. Rows carrying a D9 charge show numbers with no unknown flag.
8. **Downgrade writes 0 (R12).** The 0004 downgrade turns NULL tokens into 0. Downgrade is declared unsupported, so this is Nit.

### Promises checked and enforced, with tests that would fail
- **R5:** barrier checkpoints are committed through the fence. Tested by `test_worker_sigkill_reaps_attempt_and_replacement_recovers` with a real SIGKILL.
- **R6/R7:** fenced start, checkpoint and finish, and outputs only after the fenced finish. Tested by `test_stale_attempt_that_finished_is_fenced` (three stages, real Postgres) and the SIGSTOP stale-worker test.
- **R8/R9:** deadline, cancel, freeze-then-stop and ignored SIGTERM are all tested with real containers and a 10 s window.
- **R10:** a closed connection destroys the attempt, and startup reaps leftovers. Tested by the launcher tests and the real SIGKILL test.
- **R11–R13:** the ledger is written before dispatch and fenced, the D9 charge is applied and the turn is retried. Tested by `check_usage` across the R18 cases.
- **R14:** composition unit tests plus a live grant test.
- **R16:** content-free, ordered events stamped with the attempt ID. Tested by `test_dsh_turn_through_the_activity`.
- **R17:** checked at worker start and again at every attempt open. Tested by `test_worker_runner.py` and `test_attempt_on_an_unpinned_runtime_is_refused`.
- **R18:** 12 parametrized cases plus `lost-after-finish` and `cancel`.
- **D3:** `concurrency_per_pod: 1` is enforced at registry load (`registry/loader.py:166`) and passed to the worker as `max_concurrent_activities`.

### Files
- <repo>/harness_activity/dsh/runner.py
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/tools.py
- <repo>/infra/dsh/launcher.py
- <repo>/infra/docker-compose.yml
- <repo>/common/persistence/repositories.py
- <repo>/orchestrator/activities.py
- <repo>/orchestrator/workflow.py
- <repo>/tests/integration/test_dsh_activity.py
- <repo>/tests/integration/test_dsh_outcomes.py

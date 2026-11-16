<!-- Verbatim subagent report (impl-review-phase-02-round-3-contract, targeted follow-up); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. The run stopped once on a usage limit and was resumed. -->

I found two Majors and four Nits in phase 02, with the deepest look at 76dffd6..9883531. Both Majors are places where a round-2 fix covers one path but misses another place the same promise applies.

Scope: frozen commit 9883531, full diff 562733a..9883531. Contract files are plan.md and phases/02-dsh-runner.md in <repo>/docs/plans/2026-11-15-dsh-production-harness/. I read the code and diffs only; I ran nothing. F103–F112 are still open as deferred in reviews.md and I have not re-raised them.

## Major

**M1 · R17, R10 (F99 is incomplete): a launcher the worker cannot reach still uses up real attempts, records no row, and the worker keeps polling.**
- **Location:**
  - `<repo>/harness_activity/activity.py:227-239`. The preflight catches only `Unserviceable`.
  - `<repo>/harness_activity/dsh/runner.py` `check()` calls `LauncherClient.connect` and `request("digests")` with no handler.
  - `<repo>/harness_activity/dsh/launcher_client.py:31-35` raises `LauncherError` (a `RuntimeError`, not `Unserviceable`) when it cannot connect.
- **Scenario:**
  1. The paired DSH container is stopped or restarting. The control socket on the shared tmpfs volume is stale, so connect fails with ECONNREFUSED.
  2. `worker-dsh-a` is still polling `tpl.local-dsh` and picks up a turn.
  3. `preflight()` raises `LauncherError` before `attempts.start`. The error is not caught, so there is no refusal row, `prior.refusals` is not incremented and `on_unserviceable` is not called.
  4. Temporal retries the turn without limit (`TURN_ATTEMPTS = 0`, `orchestrator/workflow.py:43`). Each retry gives `real_attempt = attempt - refusals`, one higher each time.
  5. After 5 retries `AttemptsExhausted` fails the turn for good ("lost 5 times"). No attempt ever ran and `task_attempts` has no rows for it.
- **Why it matters:** this is the burn-five-attempts problem F99 set out to fix. Before F99, the same error came from `open_attempt` after the row was started, so it was at least recorded. A `check()` that hangs on `digests` has the same effect: there is no timeout, it does not heartbeat, and the heartbeat timeout fails it as a counted attempt.
- **Test that would expose it:** call `run_harness_turn` with `preflight` connecting to a missing socket. Assert a `refused`/`dsh_unserviceable` row, `refusals == 1`, and that `on_unserviceable` was called. Today the call raises a bare `LauncherError` and none of these hold.

**M2 · R15, D4 (same class as F102): commands of different attempts and tasks share one IPC namespace.**
- **Location:** `<repo>/infra/dsh/launcher.py:148`. Only `CLONE_NEWNS` is unshared; `CLONE_NEWIPC` is not defined or used anywhere. The F102 fix (`launcher.py:153-154`) gives private `/run` and `/dev/shm`, but SysV IPC and POSIX message queues belong to the IPC namespace, not to a mount.
- **Scenario:**
  1. A command in task A (UID 4242) creates a SysV shared-memory segment or message queue and writes workspace data into it. It can use `ipcmk` (the base userland stays, F89) or `python3`/ctypes `shmget`. The seccomp filter allows both (`launcher.py:99-103` filters only clone/unshare `CLONE_NEWUSER`).
  2. The segment outlives the process: `cgroup.kill` and destroy do not remove IPC objects.
  3. A later attempt of task B runs as the same UID 4242 in the same container IPC namespace, attaches to the segment and reads task A's data.
- **Why it matters:** R15 says commands "only see their own attempt's workspace", and the F102 resolution claims each attempt's writable places are its own.
- **Why the test misses it:** `test_commands_get_their_own_tmp` (`tests/integration/test_dsh_launcher.py:189`) checks only `/tmp`, `/run` and `/dev/shm`.
- **Test that would expose it:** attempt 1 runs `ipcmk -M 4096` (or a `shmget` with a fixed key); attempt 2 runs `ipcs -m` or attaches to that key. Today attempt 2 sees the segment. The fix would add `CLONE_NEWIPC` (the launcher holds `SYS_ADMIN`) and, if `/dev/mqueue` is used, mount a fresh mqueue.

## Nit

- **N1 · D4 (F97 resolution text).** The F97 row in reviews.md says "outputs, read_file, write_file and list_files open each component with O_NOFOLLOW". `list_files_body` does not (`<repo>/harness_activity/tools.py:183-197`): it checks with `inside()` (which resolves links), then calls `os.walk(base)`.
  - **Scenario:** a command swaps `sub/` for a symlink to `/` between the check and the walk. `os.walk` follows a symlink passed as its top directory, so the worker lists the names of its own top-level files to the model.
  - Only names leak (no contents) and the race window is narrow, so I rate it Nit.
  - **Test:** after the check, replace the directory with a link, by monkeypatching `inside`.
- **N2 · Task 2.3 ("conformance suite unchanged for openai_agents").** `read_file`/`write_file` now refuse any symlink, including one that points to another file inside the workspace (ELOOP becomes "path outside the workspace", `tools.py:96-98`). Before, `inside()` allowed in-workspace links. This changes `openai_agents` tool behaviour without a recorded decision. It is harmless for safety; reported because it is a mismatch.
- **N3 · R11, D9 (F98 fix).**
  - `orchestrator/activities.py:747` looks the template up by name in the orchestrator's current registry (`self.registry.templates[...]`). It is not pinned to the task's `template_hash`.
  - If the orchestrator now holds a different version with a different `context_window`, the D9 charge in the TaskResult differs from the one the Activity charged. `max()` hides the difference.
  - If the template is gone from the registry, the `KeyError` fails `complete_task` (SHORT_RETRY, 5 tries).
  - No test covers a version skew.
- **N4 · Observability (R17, F99).**
  - **Heartbeat hand-off:** `test_unserviceable_worker_refuses_without_using_an_attempt` passes the refusal heartbeat into the next attempt by hand (`h.env(2, h.heartbeats[-1])`). The test cannot see whether real Temporal delivers the heartbeat of a failed attempt to the next one. This is the same pattern as the F7 version refusal.
  - **Shutdown wiring:** the shutdown path in `workers/main.py:165-171` and exit code 3 have no test (already acknowledged in the F99 resolution).
  - **What would observe them:** a time-skipping Temporal test environment with a real worker, where the first preflight raises `Unserviceable`.

## Checked and found consistent

- **F96:** a step-limit stop uses `keep_tree` (`launcher.py:636-662`, `runner.py:505-510`) and `cleanup_ok` relaxes only the tree check (`runner.py:537-542`). `close()` still does a full stop because `stopped` stays False. `test_step_limit_stop_keeps_the_workspace_for_the_checkpoint` asserts the workspace is in the checkpoint and the tree is gone afterwards.
- **F97:** `open_inside`/`read_regular` (`tools.py:79-112`) and `share()` with fwalk and no-follow descriptors (`runner.py:102-137`). The Activity's output publishing goes through `read_regular` (`activity.py:547-553`). `test_symlinked_output_is_not_published` covers it.
- **F98:** `complete_task` takes the larger of the Workflow's totals and the ledger's settled tokens plus the D9 charge, and marks usage unknown when there are unobserved requests (`orchestrator/activities.py:739-760`). Covered by `test_complete_task_charges_what_the_ledger_left_unobserved`.
- **F100:** every `DshAttempt.stop` checks its own report, with a reply timeout (`runner.py:175-197`). Both fault variants are tested.
- **F101:** `_ledger_usage_sql` is applied in `close_unfinished` (`common/persistence/repositories.py:290-301, 344-367`). The table aliases scope correctly, and rows already unknown are left alone. Covered by a test with both closers.
- **F102:** `/run` and `/dev/shm` are private per attempt process, except for the IPC gap in M2.
- **R17:** the pin is re-checked in both `check()` and `open_attempt`, and the launcher's dirty set is reported in every `digests` reply (`launcher.py:303-313, 389`).
- **Workspace and session packing:** `harness_activity/workspace.py:19-44` skips symlinks. The check-then-open race there is covered by the D6 freeze at capture time.

<!-- Verbatim subagent report (impl-review-phase-02-round-3-scope, targeted follow-up); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. The run stopped once on a usage limit and was resumed. -->

## Scope review: phase 02 (DSH runner and worker pair), round 3 at 98835319

I reviewed the whole phase diff from 562733a7 to 98835319. Most attention went to 76dffd6e..98835319: fixes F96 to F102, the preflight, the launcher's DIRTY set, keep_tree, `_ledger_usage_sql`, complete_task reconciliation and the O_NOFOLLOW file bodies.

Most of the round-2 fixes hold at the scope the plan promises:
- **keep_tree (F96):** the step-limit stop keeps the tree, the final freeze and checkpoint see the workspace, and the full stop at close removes it.
- **DIRTY (F99):** it lives for the launcher's lifetime and every `digests` reply carries it.
- **Every stop checks its report (F100):** both the in-run path and the close path do.
- **F101 rows:** `close_unfinished` applies the ledger usage to the rows it closes.
- **No-follow (F97):** `share()`, read_file, write_file and output publishing never follow a link.

The findings below are in order of severity: one Major, then Nits.

### 1. Major: commands share SysV IPC and POSIX message queues across attempts and tasks (R15, D4; same class as F63 and F102)
- **Location:** `infra/dsh/launcher.py:146-163` (`_isolate`). The only new namespace is `unshare(CLONE_NEWNS)`; there is no `CLONE_NEWIPC`. Commands of every attempt and task run as one fixed UID, `COMMAND_UID = 4242` (`launcher.py:47`, used at `:222`).
- **Failure scenario:**
  1. An attempt of task A runs `ipcmk -M 4096` (util-linux), or a python3 ctypes `shmget`/`msgget`/`mq_open`, and writes data into it.
  2. The attempt ends. `destroy()` kills the cgroup, but SysV segments and message queues outlive their processes, and nothing removes them (`destroy`/`reap` only touch cgroups and trees).
  3. A later attempt of task B on the same container runs `ipcs -m` and attaches the segment. It belongs to the same UID, so a 0600 mode does not protect it.
- **Why it is reachable:** Docker's default seccomp profile (compose does not override it, `docker-compose.yml:192`) allows shmget, msgget and mq_open.
- **Why it matters:** this is exactly the cross-attempt channel F102 closed for `/dev/shm`. R15 says "Commands only see their own attempt's workspace." It also leaks memory that persists until the container restarts.
- **Fix:** add `CLONE_NEWIPC` to the unshare, at least for commands.
- **Test that would expose it:** extend `test_commands_get_their_own_tmp` so attempt 1's command creates a SysV shm segment or message queue, then assert attempt 2's command finds nothing in `ipcs`.

### 2. Nit (borderline Major): a refusal turns earlier rows `lost` without applying the ledger usage (D7, R12; F68 and F101 at a narrower scope)
- **Location:** `common/persistence/repositories.py:233-245` (`record_refusal`) sets earlier `started` rows of the turn to `outcome='lost'` and leaves tokens 0 and `usage_known = true`.
- **What normally repairs the row:** only `close_unknown` in the next real attempt's `_charge` (`activity.py`, `_open`). F99 made the preflight refusal a new DSH path into this function.
- **Failure scenario:**
  1. Attempt 1 dispatches a request, then worker A is SIGKILLed. Attempt 1's row is `started`.
  2. Attempt 2 lands on a worker whose container is dirty or pinned wrong. The preflight records `dsh_unserviceable`, which turns row 1 into `lost (0, 0, usage_known = true)`, and that worker exits.
  3. The default deployment has only one DSH pair (`docker-compose.yml:185-214`), so no real attempt follows before schedule_to_close.
  4. `complete_task`'s `close_unfinished` only touches `started` rows, so row 1 keeps 0 tokens and known usage for a request that was never observed.
- **What still holds:** the TaskResult is right, because F98 reconciles it.
- **Why it is a Nit:** it needs every DSH worker to be unserviceable until schedule_to_close.
- **Test that would expose it:** start attempt 1 with a dispatched-but-unsettled ledger row, call the preflight-refusal path for attempt 2, then `close_unfinished(task, None, "task_completed")`, and assert row 1 is `(NULL, NULL, false)`.

### 3. Nit: two different rules for an attempt row's usage (D7, notes.md#d7 F69 rule)
- `_ledger_usage_sql` (`repositories.py:344-367`) sets a row to NULL when any request of the turn up to that attempt was unobserved, including earlier attempts' requests.
- `_runner_failed` (`activity.py`, `own_unknown`) sets NULL only for the attempt's own unobserved requests. Otherwise it writes the cumulative heartbeat numbers, D9 charge included, with `usage_known = false`.
- **Scenario:** in one turn, attempt 1 is lost with an unknown request. Attempt 2 then either fails retryably (its row gets numbers) or is closed by `close_unfinished` (its row gets NULL). The same history gives different rows depending on the closing path.
- The F69 rule says "NULL when an own request was unobserved"; the shared SQL does not follow it.
- **Test:** compare the row from those two closing paths after the same ledger history.

### 4. Nit: complete_task reconciles tokens but not inner turns or tool calls (D11, R11, R18)
- **Location:** `orchestrator/activities.py:42-60` updates only `tokens_in`, `tokens_out` and `usage_known`.
- **Scenario:** in a cancelled turn, or one whose worker died, requests settle after the last heartbeat. The TaskResult then has tokens from the ledger but `inner_turns` from the heartbeat, which is lower than the ledger's request count. D11 makes inner turns cumulative and counted from the ledger, as `_charge` does with `settled_count + unknown`.
- **Test:** the F98 test with `inner_turns=1` and two ledger rows; assert `result.inner_turns == 2`.

### 5. Nit: F98 reconciliation is tested only with a single turn (F98 test scope)
- `test_complete_task_charges_what_the_ledger_left_unobserved` (`tests/integration/test_dsh_usage.py`) has one turn and one attempt.
- The `max()` against task-wide `task_totals` is not exercised with turn 1 already D9-charged by its Activity plus turn 2 cancelled, which is where double counting or undercounting would show.
- I found no actual double count by reading the code, but nothing pins it at task scope.

### 6. Nit: complete_task can raise KeyError (R11)
- **Location:** `orchestrator/activities.py:50`, `self.registry.templates[payload.resolved.template]`.
- It raises KeyError when the orchestrator's registry no longer has that template. The Activity uses `.get` plus a refusal for the same case.
- It also uses the current template version's `context_window`, not the task's pinned version.
- Unverified whether this can happen in deployment.

### 7. Nit: an Unserviceable error from `open_attempt` after `attempts.start` uses up an attempt and does not stop polling (R17, R10, F99)
- `_verify` still runs inside `open_attempt` (`dsh/runner.py:246`), after `attempts.start` and `_charge`.
- If the container is recreated or turns dirty between the preflight and open, `RuntimePinMismatch` or `LauncherUnhealthy` propagates as a generic retryable error. It counts as a real attempt, leaves the row `started`, and `on_unserviceable` is not called.
- The next turn's preflight catches it, so the window is narrow.

### 8. Nit: the worker shutdown is fire-and-forget and untested (F99)
- **Location:** `workers/main.py:165-170` calls `asyncio.get_running_loop().create_task(worker.shutdown())` without keeping a reference. The asyncio docs warn that such a task can be garbage-collected before it runs.
- The engineer already noted that this wiring has no automated test.
- In the one-pair deployment, "another worker takes the turn" does not hold. The worker restarts (`unless-stopped`), and its start-up check refuses while the launcher's DIRTY set persists, so the turn waits until schedule_to_close. Nothing restarts the launcher automatically.

### 9. Nit: list_files can still follow a link swapped in after its check (D4, F97)
- **Location:** `harness_activity/tools.py:183-197`.
- The function checks `base` with `inside()` (which resolves) and then runs `os.walk(base)` by name. A directory swapped for a symlink after the check, or between `os.walk` listing and descending, is followed. `full.is_file()` also follows.
- Only file names leak, not contents, and the DSH barrier freezes commands only during captures. Read and write are fixed.

### 10. Nit: the cumulative `_ledger_usage_sql` is tested only on single-attempt rows (F101 test scope)
- `test_rows_closed_without_a_finish_hold_the_ledger_usage` has one attempt per turn.
- The "through each attempt" sum (`l.attempt <= a.attempt`) with several attempts closed by `close_unfinished` is not exercised.
- The older F68 test covers the same SQL for `lost` rows only.

### Not repeated
F103 to F112 are still open as recorded in reviews.md. I saw nothing in this range that changes them, apart from finding 7 above, which relates to F111 and F110.

### Files
- <repo>/infra/dsh/launcher.py
- <repo>/common/persistence/repositories.py
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/dsh/runner.py
- <repo>/harness_activity/tools.py
- <repo>/orchestrator/activities.py
- <repo>/workers/main.py
- <repo>/infra/docker-compose.yml
- <repo>/tests/integration/test_dsh_usage.py
- <repo>/tests/integration/test_dsh_activity.py

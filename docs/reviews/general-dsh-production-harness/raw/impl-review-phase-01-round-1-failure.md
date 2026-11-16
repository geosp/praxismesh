<!-- Verbatim subagent report (impl-review-phase-01-round-1-failure); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## Phase 01 review: what happens when a run stops partway and runs again

**Scope:** `git diff 0f32d7dd..bc8e97b`, checked against plan.md (R1–R3, D1, D3, D5, D7, D8, D10) and phases/01-harness-seam.md. I ran nothing; this is a read-only review.

**Verdict:** R1 and R2 are met, and their registry tests are fine. The D10 fence (task 1.1) is sound for the attempt-finish write. It is not serialized for the checkpoint insert. The 0.1 probe does not prove what its Verify line claims. The session store lacks two of its four required operations. The conformance suite never touches the store.

### The units I traced
- **`run_harness_turn` → `_attempt` → `_run` → `_finish`** (`<repo>/harness_activity/activity.py`), in order:
  1. Template refusal heartbeat.
  2. `attempts.start`: marks lower `started` rows of the same turn `lost`, then upserts its own row (`<repo>/common/persistence/repositories.py:134-160`).
  3. `checkpoints.latest`.
  4. `blobs.get` and unpack.
  5. `store.restore(position)` or `store.reset()` (`activity.py:264`, `:278`).
  6. For each model call: `newer_attempt_exists` (`:311`), then `checkpoint()`. That is pack, then `blobs.put` (`:285`), then `store.position`, then `insert_fenced` (`:289`).
  7. A final `checkpoint(finish)`.
  8. `_finish`: artifact `blobs.put` (`:370`), then a fenced `attempts.finish` (`:383`).
  9. `finally`: rmtree.
- **`infra/dsh/isolation-probe.sh`**: one pass, no persisted state.

These cases are fine:
- **Death after the finish checkpoint but before `attempts.finish`:** the next attempt's `start` marks the old row lost, `latest.finish` is set, and it goes straight to `_finish`.
- **Death halfway through `restore`'s pop loop:** this is idempotent, because the next run recomputes from the same position.
- **Cancellation inside `insert_fenced` or `finish`:** each runs in one transaction and rolls back.
- **A stale finish racing a new `start`:** this is serialized by the row lock. `start`'s UPDATE takes a lock on the stale row and sets it to `lost`. The stale UPDATE then re-checks `outcome = 'started'`, fails, and the follow-up SELECT raises `FenceRejected` (`repositories.py:200-206`).

### Findings

**1. Major (D10; task 1.1; also R6 later): the fenced checkpoint insert can still commit after a newer attempt has started.**
- **Where:** `repositories.py:283-307` and `:273-276`.
- **Why:** `INSERT … SELECT … WHERE NOT EXISTS (…)` takes no lock. Under Postgres READ COMMITTED, its snapshot cannot see a concurrent `attempts.start` that has not committed yet.
- **Scenario:**
  1. Attempt 1 heartbeat-times out but keeps running.
  2. Attempt 2 on worker B begins `start`.
  3. Attempt 1 runs `insert_fenced` while that is in flight, so its NOT EXISTS sees no newer row.
  4. Both commit. Attempt 1's commit can land after attempt 2's `start` commit and after its `latest()` read (`activity.py:262`).
  5. Attempt 2 dies before its first checkpoint. Attempt 3 then restores a checkpoint that a stale attempt wrote after the newer attempt started.
- **Evidence:** this is the race the plan rejects: "Rejected: a separate pre-check (races with a new attempt)", and "one transaction that checks no newer (turn, attempt) exists". The finish path avoids it only because `start` happens to update the same row.
- **Possible fix:** inside `insert_fenced`, take `SELECT … FROM task_attempts WHERE task_id=:t AND turn=:turn AND attempt=:a AND outcome='started' FOR UPDATE` first, and refuse if it is missing. That orders the insert against `start`'s same-turn UPDATE. A newer turn needs a task-level lock, or SERIALIZABLE.
- **Test:** on Postgres, hold attempt 2's `start` transaction open (begin, insert the row, do not commit). Run attempt 1's `insert_fenced` from another connection, then commit attempt 2. Today the insert succeeds; it should be rejected or block. The existing test (`tests/integration/test_persistence_phase1.py:189-224`) is purely sequential.

**2. Major (task 0.1; D3; Assumptions): the probe does not show that a process tree is frozen and killed.**
- **Where:** `<repo>/infra/dsh/isolation-probe.sh:17-29`.
- **Why:** `sh -c 'sleep 30 & sleep 30' & parent=$!` runs and, after `sleep 0.2`, only `$parent` is written to `probe-attempt/cgroup.procs` (`:19`). Writing a PID moves that one process. Children already forked stay in `launcher/`.
- **Consequences:**
  - `cgroup_freeze` freezes only the parent shell.
  - `cgroup_kill` counts only `probe-attempt/cgroup.procs` (`:27`). It reports `remaining=0` while both `sleep 30` processes survive.
  - The notes.md "Probe result" row ("freeze, `cgroup.kill` … yes") therefore rests on a check that cannot fail for the tree.
- **Same gap in the SIGSTOP fallback (`:36-40`):** it checks only that `kill -STOP` returned 0. It never checks that members are in state `T`.
- **Minor:** line 13 (`echo "+freeze" > /dev/null`) does nothing.
- **Test or fix:**
  - Have the process join the cgroup before it forks: `sh -c 'echo $$ > …/cgroup.procs; exec sh -c "sleep 30 & sleep 30"'`.
  - After the freeze, assert every descendant is in state `T`/frozen, and after the kill assert `pgrep -f "sleep 30"` is empty.
  - For SIGSTOP, check `/proc/<pid>/stat` state for every group member.

**3. Major (D1; task 1.1): the session store has no capture or commit, so the checkpoint is still assembled and committed outside the seam.**
- **Where:** `<repo>/harness_activity/session_store.py:21-34` defines `session`, `restore`, `reset` and `position` only.
- **Evidence:** task 1.1 says "Add the session store (load, truncate, capture, commit)". D1 says "`run_harness_turn` calls a session store for load, truncation, capture and commit".
- **What still happens in the Activity:** `activity.py:281-307` packs, puts, builds the `Checkpoint` and calls `insert_fenced` itself.
- **Scenario:** a DSH store must put a session blob (`session_ref`, `session_digest`) and have it land in the same fenced insert. The current interface cannot return a ref into `Checkpoint`, and `Checkpoint` has no session-ref field. A store that puts its blob on its own and dies before `insert_fenced` leaves an orphan session blob, and no seam operation owns the ordering.
- **Test:** a fake store whose capture returns a ref, with an assertion that the ref is passed to the fenced insert (and is absent when the fence rejects).

**4. Major (R3): the conformance suite does not run "on the seam".**
- **Where:** `<repo>/tests/test_runner_conformance.py:39-41`, `:67`.
- **Why:** the new fixture only swaps the runner class. Every test still passes `SQLiteSession(...)` straight into `runner.run`. Neither `SessionStore`/`SQLAlchemySessionStore` nor `run_harness_turn` is involved.
- **Evidence:** R3 says "when the conformance suite runs on the seam, then it passes". The task's Verify line ("runs through a runner fixture") is met literally.
- **Scenario:** a bug in `SQLAlchemySessionStore.restore` or `position` (an off-by-one truncation after a resume) passes the whole conformance suite.
- **Coverage elsewhere:** only the Postgres integration tests reach the store, and only through the default.
- **Test:** parametrize the fixture over `(runner, store factory)` and draw the session from `store.session`, including a resume-with-truncation case.

**5. Nit (D10; R7, which is due in phase 02): blobs are written before the fence check, so a rejected stale attempt still records blobs.**
- **Where:** `activity.py:285` (workspace, `task` retention) and `:370` (artifacts, `audit` retention), both before the fenced write.
- **Scenario:** a stale attempt that has finished uploads its outputs as audit blobs (recorded in `blob_objects` by `RecordingBlobStore`), then `attempts.finish` raises `FenceRejected` and then `Superseded`.
- **Evidence:** D10 says "artifact publication … in one transaction that checks no newer (turn, attempt)". R7: "no blob or outcome is recorded".
- **Why Nit:** R7 is scheduled for phase 02.

**6. Nit (D10): a fenced finish silently succeeds when its row is no longer `started` and nothing newer exists.**
- **Where:** `repositories.py:200-206`. With rowcount 0 and no newer row, it returns normally.
- **Scenario:** the task completes or is cancelled, and `close_unfinished(turn=None)` closes the row while the attempt is still running. The attempt's `_finish` then "succeeds" and returns a `TurnOutcome` whose outcome was never recorded.
- **Why Nit:** the unfenced version behaved the same way.

**7. Nit (D10 scope; not new): session writes are not fenced.**
- **Where:** `session_store.py:37-55` and `activity.py:262-264`.
- **Why:** the session id is `task_id` for every attempt.
- **Scenario:**
  1. Attempt 2 runs `restore`, which pops back to the position.
  2. Stale attempt 1, mid-tool, then has the SDK append tool-output items to the same `SQLAlchemySession`.
  3. Attempt 2's conversation now holds attempt 1's items. Attempt 1 is stopped only at its next `before_model_call`.
- **Why Nit:** D10 lists only checkpoint, finish and artifact writes, and this existed before the diff. The new seam would be the natural place to fence it.

**8. Nit (D8; R16, later): event order can diverge from `seq` under concurrent emitters.**
- **Where:** `<repo>/harness_activity/events.py:43-54`. `seq` is assigned under the lock, but `sink.emit` is called outside it.
- **Scenario:** two threads (executor and gateway) emit at once and `MemorySink.events` ends up as seq `[1, 0]`.
- **Also:** `payload: dict[str, Any]` (`<repo>/common/schemas/events.py`) does not enforce "no prompt text".
- **Test:** emit from N threads and assert the list order equals the seq order.

**9. Nit (R1; task 2.1): no test uses a harness value outside the `Harness` Literal.**
- **Where:** `<repo>/tests/test_registry.py:118-124` uses `claude_sdk`, which is a valid Literal value that the loader refuses as unsupported.
- **Why Nit:** pydantic rejects an outside value such as `harness: foo`, but no test pins that behaviour.

**10. Nit (task 2.2): the harness check was copied to load time, not moved.**
- **Where:** `<repo>/registry/loader.py:101-105` still exists, and the load-time check uses `or []` although `allowed_templates` has `min_length=1`.
- **Why Nit:** keeping both is harmless defence in depth, but it differs from the word "Move".

**11. Nit (D5): a task submitted with profile `dsh` in this phase hangs instead of failing fast.**
- **Why:** the `dsh` profile now resolves and routes to `tpl.local-dsh`. `<repo>/workers/main.py:71-77` makes any dsh worker refuse to start.
- **Scenario:** the task waits on an unserved queue until timeouts or `max_wall_time`.
- **Why Nit:** I did not verify whether the API layer gates the `dsh` profile.

**Not reviewed:** the R4 benchmark. Nothing in this diff should affect it beyond the seam refactor.

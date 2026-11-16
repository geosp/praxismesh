<!-- Verbatim subagent report (impl-review-phase-01-round-1-scope); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## Scope review of phase 01: Harness seam and registry (diff 0f32d7dd..bc8e97b)

I found no Blockers. There are 5 Major findings and 8 Nits. R1 and R2 hold at load time, including `make registry-lock`, and their tests are adequate. The problems are in the D10 fence's concurrency scope, the reach of the D1 seam, the R3 "on the seam" test, the D8 ordering, and the task 0.1 probe.

### Major

**M1. The checkpoint fence is not atomic under concurrency (D10, task 1.1; sets up R6 for phase 02)**
- Location: `common/persistence/repositories.py`, `insert_fenced` and `_NO_NEWER_ATTEMPT` (the `INSERT ... SELECT ... WHERE NOT EXISTS (SELECT 1 FROM task_attempts n ...)`).
- The cause: under Postgres READ COMMITTED, the `NOT EXISTS` subquery reads the statement's snapshot and takes no lock. It cannot see a newer attempt's `task_attempts` row that is not yet committed, and nothing serializes the two transactions.
- Failure scenario:
  1. Stale attempt 1 runs `insert_fenced` for seq k. Its snapshot has no attempt-2 row.
  2. Attempt 2 commits `attempts.start`, then reads `checkpoints.latest` and gets seq k-1, because seq k is not committed yet.
  3. Attempt 1 commits seq k.
  4. Attempt 2 dies before its first checkpoint.
  5. Attempt 3 resumes from seq k. That checkpoint was written by a stale attempt after a newer one started.
- Evidence: the plan rejects "a separate pre-check (races with a new attempt)", and a single unlocked statement has the same race.
- The finish fence is mostly safe within one turn: `start`'s UPDATE that marks attempt 1 `lost` row-locks the row that `finish` updates.
- Possible fixes: take `SELECT ... FOR UPDATE` on the task row (or an advisory lock per task) in both `start` and `insert_fenced`, or use SERIALIZABLE.
- Test that would expose it: two connections. One opens a transaction and inserts the attempt-2 row without committing. The other calls `insert_fenced` for attempt 1, then the first commits. Assert `FenceRejected`. Today it succeeds. The new test `test_stale_attempt_cannot_checkpoint_or_finish` (`tests/integration/test_persistence_phase1.py`) is purely sequential.

**M2. The fence covers the checkpoint row, but the session it points at is shared and unfenced (D1 + D10)**
- Location: `harness_activity/session_store.py` (`SQLAlchemySession(task_id, ...)`) and `activity.py` (`store = self.session_store(turn.task_id, self.engine)`).
- The cause: every attempt of a task writes to the same SDK session, keyed by `task_id`. A checkpoint records only `position = len(items)`.
- Failure scenario:
  1. Attempt 2 restores and truncates to position P.
  2. Stale attempt 1 is still inside `runner.run`. It gets a model response and the SDK appends items to the shared session, before its next `before_model_call` raises `Superseded`.
  3. Attempt 2's next fenced checkpoint records a position that counts attempt 1's items.
  4. A later resume replays a conversation mixed from both attempts.
- Two mechanisms are each correct alone and wrong together: the row fence and the session write.
- This behaviour predates the diff, but the seam now claims D10 covers the commit.
- Test that would expose it: a runner stub that appends a session item after a newer attempt has started and restored. Then assert attempt 2's checkpointed session holds only its own items.

**M3. The session store has no capture/commit, so the D1 seam cannot carry a DSH session (D1, task 1.1)**
- Location: the `SessionStore` protocol in `harness_activity/session_store.py`.
  - It exposes `session` (typed as the SDK `agents.memory.Session`), `restore`, `reset` and `position` only.
  - The commit is still built inline in `activity.py` `checkpoint()`: it hard-codes `session_id=turn.task_id` and `position` and calls `checkpoints.insert_fenced` directly.
- Contract: D1 says "`run_harness_turn` calls a session store for load, truncation, capture and commit", and DSH sessions are "a separate session blob (`session_ref`, `session_digest`) ... `session_position` stays 0". Task 1.1 names "(load, truncate, capture, commit)".
- Failure scenario: the phase 02 `DshSessionStore` has no way to put its session blob into the fenced commit. It also has to pretend to be an OpenAI SDK `Session`. So phase 02 must reopen `run_harness_turn`, which is what D1's rejected alternative warned about.
- Test that would expose it: a fake store whose capture returns a session ref, asserting the committed checkpoint carries it. Today this cannot be expressed at all.

**M4. R3 "through the new seam" is tested only at runner level**
- Location: `tests/test_runner_conformance.py` lines 35-41, 64-67, 271-282, 347 and 433. The fixture swaps `make_runner`, but every test still passes a raw `SQLiteSession(...)` straight to `runner.run`.
- Contract: R3 says "when the conformance suite runs on the seam, then it passes."
- What the suite does not reach: `SessionStore`, `run_harness_turn` and the fence.
- What does reach them: `tests/integration/test_harness_activity.py` (`pytestmark = integration`, excluded in CI by `addopts = "-m 'not integration'"`).
- Failure scenario: a regression in `SQLAlchemySessionStore.restore`/`position`, or in the fenced checkpoint path, passes CI and the "conformance" gate.
- Test that would expose it: run the conformance cases (at least done, resume after a lost attempt, and superseded) through `HarnessActivities.run_harness_turn` with the default store.

**M5. The activity's new fence paths have no test (D10, task 1.1)**
- Location: `activity.py`, the `except FenceRejected` blocks in `checkpoint()` and `_finish`.
- What exists: `test_superseded_attempt_writes_nothing` inserts the newer row before the run, so the early `newer_attempt_exists` pre-check fires and the fence is never reached. `test_finish_does_not_overwrite_a_lost_row` marks the row lost but adds no newer row.
- Untested scenario: a newer attempt starts after `before_model_call` and before the final `checkpoint(finish)` or `_finish`. That path, which is what the fence exists for, never runs in any test.
- Test that would expose it: a runner stub that calls `AttemptRepository.start(task, 1, 2, ...)` and then returns `done`. Assert `Superseded` is raised, no checkpoint row was added, and attempt 1's row still reads `lost`.

### Nit

**N1. Artifact publication is not fenced (D10; R7 is phase 02)**
- Location: `activity.py` `_finish`. It calls `blobs.put(..., retention="audit")` for every output before the fenced `attempts.finish`. `checkpoint()` likewise puts the workspace blob before `insert_fenced`.
- Contract: D10 says "artifact publication each run in one transaction that checks no newer (turn, attempt) exists."
- Failure scenario: a stale attempt finishing `done` leaves audit-retention blobs behind, then gets rejected. The outcome is discarded, so no artifact is recorded, but the blobs are orphaned.
- Rated Nit because R7 belongs to phase 02.

**N2. The probe does not exercise freeze/kill on a process tree (task 0.1)**
- Location: `infra/dsh/isolation-probe.sh`.
  - It runs `sh -c 'sleep 30 & sleep 30' & parent=$!; sleep 0.2; echo $parent > .../probe-attempt/cgroup.procs`.
  - Writing to `cgroup.procs` moves only that one process. Its already-forked `sleep` children stay in `launcher/`.
  - So `frozen=1` and `remaining=0` are proven for a single process. The orphaned sleeps are never checked.
- Contract: task 0.1's verify step says "a probe script freezes and kills a process tree".
- Fix: start the child after moving the shell into the cgroup, or check that the children are frozen and dead.
- Similarly, `sigstop_group` reports true when `kill -STOP` returns 0, without checking that the group is in stop state (`T`).
- Rated Nit because the plan's conclusion is probably still correct.

**N3. The probe's user-namespace check fails, and the fix is deferred**
- `command_userns_blocked` failed; `notes.md` marks it "**no**". The seccomp requirement is moved to phase 02 task 1.1.
- The gate's "stop and return to the owner" condition covered only freeze and SIGSTOP, so this is within the contract.
- The new `SYS_ADMIN` grant is a material change to D3, recorded only in the plan's decision log line. The owner should explicitly accept it.

**N4. The `dsh` profile can be submitted, but no worker serves `tpl.local-dsh` (D5)**
- Location: `registry/profiles/dsh.yaml`, `orchestrator/submit.py:33` (`resolve`), and `workers/main.py` (refuses non-`openai_agents`).
- Failure scenario: a request with `profile: dsh` is accepted and dispatched to `tpl.local-dsh`. No poller ever starts it, so it fails only after `schedule_to_close_timeout = turn_timeout * 6` (1 hour, `orchestrator/workflow.py:124`).
- Possible fixes: reject `dsh` at submit until phase 02, or document the behaviour.

**N5. Ordering is guaranteed only for numbering, not delivery (D8; R16 in phase 02)**
- Location: `harness_activity/events.py` `AttemptEvents.emit`. The lock covers `seq` assignment only; `self.sink.emit(event)` runs outside it.
- Failure scenario: R16 has both the executor and the gateway emitting. With concurrent emitters, thread B can hand seq 1 to the sink before thread A hands seq 0, so `MemorySink.events` is out of order.
- Test: `test_events_are_ordered_and_carry_attempt_identity` is single-threaded.
- Fix: move `sink.emit` inside the lock, or add a threaded test.

**N6. Event `seq` restarts at 0 for every attempt (D8)**
- Location: `AttemptEvents` builds `attempt_id = f"{task_id}:{turn}:{attempt}"` and starts `seq = 0`. So `seq` is per attempt, not per task or workflow. The contract does not define the scope; roadmap Phase 2 asks for "monotonic `seq` ... reset semantics".
- It is also unspecified whether `attempt` is the Temporal attempt or `real_attempt`.
- "No prompt text" is only a comment: `payload: dict[str, Any]` accepts `emit("status", text=<prompt>)`, and the test checks only unknown types and unknown top-level fields.

**N7. The fence also rejects writes when a higher turn exists (D10)**
- The fence checks all turns, while `before_model_call`'s `newer_attempt_exists` checks only the same turn.
- Failure scenario: after a Temporal workflow reset to an earlier turn, rows from higher turns remain. Every checkpoint and finish of the replayed turn raises `Superseded`, which is not `NonRetryableError`, so the turn retries until `schedule_to_close`.
- Rated Nit because the plan says nothing about resets.

**N8. The resolve-time harness check was kept (task 2.2)**
- Location: `registry/loader.py` `resolve` still holds the harness comparison. Task 2.2 says "Move ... from resolve time to load time".
- It is now redundant, not harmful. The load-time check is correct, and `make registry-lock` runs it too.

### Requirements that hold
- **R1:** `Harness`, `SUPPORTED_HARNESSES` and `schemas.md` are updated. The lock pins `local-dsh@1`. `test_unsupported_harness_template_rejected` covers rejection.
- **R2:** checked at load in `load_registry`. Covered by `test_harness_mismatch_fails_at_load` and `test_dsh_profile_cannot_allow_an_openai_template`.
- **D5/D7 template fields:** `concurrency_per_pod: 1` and `context_window: 32768` are present and tested.

### Files
- <repo>/common/persistence/repositories.py
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/session_store.py
- <repo>/harness_activity/events.py
- <repo>/infra/dsh/isolation-probe.sh
- <repo>/registry/loader.py
- <repo>/registry/profiles/dsh.yaml
- <repo>/workers/main.py
- <repo>/tests/test_runner_conformance.py
- <repo>/tests/integration/test_persistence_phase1.py
- <repo>/tests/integration/test_harness_activity.py
- <repo>/tests/test_agent_events.py

<!-- Verbatim subagent report (impl-review-phase-01-round-1-contract); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## Phase 01 review: DSH harness seam (0f32d7dd..bc8e97b)

**Verdict:** R1 and R2 are met. R3 is met in the form its task asks for. The D10 fence and the task 0.1 probe do not fully keep their promises. I found five Major findings and twelve Nits. I made no writes; checks were read-only (`git show`/`grep`, plus one `sha256sum`).

### Promise map

| Promise | Enforcing code | Test that would fail without it |
| --- | --- | --- |
| R1: only `Harness` values that have a runner load | `common/schemas/base.py:10`; `registry/loader.py:30,129-133`; lock check at `loader.py:148-159` | `tests/test_registry.py` `test_unsupported_harness_template_rejected` (uses `claude_sdk`); `test_registry_lock_is_current`. The `local-dsh@1` lock hash matches: I recomputed `sha256(template + \0 + prompt)` and got `54ef665b…` |
| R2: profile and template harness checked at load time | `registry/loader.py:165-172` | `test_harness_mismatch_fails_at_load`, `test_dsh_profile_cannot_allow_an_openai_template` (this is exactly the R2 scenario) |
| R3: conformance suite through a runner fixture | `tests/test_runner_conformance.py:35-41`; every run goes through `make_runner()` | Every conformance test is parametrised by `RUNNERS` |
| D1 / task 1.1: session store seam | `harness_activity/session_store.py`; `activity.py:256-286` | `test_restore_truncates_session`, `test_restore_without_checkpoint` (both use the default store) |
| D10: fenced checkpoint insert | `repositories.py:283-308`, used at `activity.py:289` | Repository level only: `test_stale_attempt_cannot_checkpoint_or_finish`, `test_older_turn_is_fenced_by_a_newer_turn`. Not at Activity level (see M3) |
| D10: fenced attempt finish | `repositories.py:177-206`, used at `activity.py:374-386` | Repository level only (see M3) |
| D10: fenced artifact publication | **none** (see M2) | none |
| D5: `local-dsh` template and `dsh` profile | `registry/templates/local-dsh.yaml`, `registry/profiles/dsh.yaml`, `registry.lock:5` | `test_dsh_profile_resolves_the_dsh_template` |
| D7: `context_window` on templates | `common/schemas/capability.py:66-68` | `test_dsh_profile_resolves_the_dsh_template` (truthy check only) |
| D8: AgentEvent sink | `common/schemas/events.py`, `harness_activity/events.py` | `tests/test_agent_events.py` |
| Task 0.1: freeze and kill a process tree | `infra/dsh/isolation-probe.sh` | It is a probe, not a test (see M4) |

### Major

**M1 · D10: the fence still races with a new attempt.**
- **Location:** `common/persistence/repositories.py:273-276`, `283-308`, `177-206`; `AttemptRepository.start` at `134-160`.
- **Why:** the check is a `NOT EXISTS` subquery inside the write, running under Postgres's default READ COMMITTED (`make_engine` at line 21-22 sets no isolation level). Nothing takes a lock, and `start` locks nothing either.
- **Failure scenario:**
  1. Stale attempt 1 runs the final `checkpoint(finish)` (`activity.py:339`). Its INSERT…SELECT takes its snapshot.
  2. Attempt 2's `attempts.start` commits.
  3. Attempt 2 runs `checkpoints.latest` and does not see attempt 1's uncommitted row.
  4. Attempt 1 commits.
- **Result:** a checkpoint row is written after a newer attempt started, and attempt 2 resumed without it. If attempt 2 is then lost before its first checkpoint, attempt 3's `latest()` (ordered by turn, attempt, seq) picks attempt 1's stale `finish` checkpoint.
- **Contract:** D10 rejects "a separate pre-check (races with a new attempt)". This narrows that race but does not close it.
- **Observability:** the tests are sequential on one connection, so they cannot see this. A test that holds attempt 2's `start` transaction open on a second connection while attempt 1's fenced insert runs would show it.
- **Fix:** take a per-task lock in `start` and in every fenced write (`SELECT … FROM tasks WHERE task_id = :t FOR UPDATE`, or `pg_advisory_xact_lock`), or use SERIALIZABLE.

**M2 · D10 (and R7, delivered later): artifact publication is not fenced.**
- **Location:** `harness_activity/activity.py:365-371` runs before the fenced finish at `374-386`.
- **Failure scenario:** a stale attempt reaches `_finish` with `status == "done"` after attempt 2 started. It runs `blobs.put(..., retention="audit")` for every output. In production that is `RecordingBlobStore` (`workers/main.py`), which inserts `blob_objects` rows (`repositories.py` around line 392). Only then does `finish(fenced=True)` raise.
- **Result:** audit-retention blobs and their DB rows are recorded for a stale attempt.
- **Contract:** "Checkpoint insert, attempt finish and artifact publication each run in one transaction that checks no newer (turn, attempt) exists."
- **Test that would expose it:** a scripted runner that starts attempt 2 and then returns `done` with an output file. Assert there are no `blob_objects` rows with `retention_class = 'audit'` for the task.

**M3 · D10 / task 1.1: no test shows the Activity uses the fence.**
- **Location:** `activity.py:289` and `383`.
- **Why:** `test_superseded_attempt_writes_nothing` inserts the newer attempt before the run, so the old `newer_attempt_exists` pre-check (`activity.py:311`) catches it first. `test_terminal_failure_does_not_close_a_newer_attempt` raises before any checkpoint.
- **Failure scenario:** revert `insert_fenced` to `insert`, or drop `fenced=True`. Every test still passes. A stale attempt that returns after attempt 2 started (with no further `before_model_call`) then writes its `finish` checkpoint unfenced. That was the pre-diff behaviour.
- **Test that would expose it:** a scripted runner that calls `AttemptRepository.start(task, 1, 2, …)` and then returns `done`. Assert `Superseded`, and that attempt 1 has no checkpoint with `finish`.

**M4 · Task 0.1 / D3: the probe does not show that a process tree is frozen and killed.**
- **Location:** `infra/dsh/isolation-probe.sh:12,17,19,27-28`.
- **Why:** the shell moves itself into `launcher/` (line 12) and forks `sh -c 'sleep 30 & sleep 30'` (line 17). After 0.2 s it moves only `$parent` into `probe-attempt` (line 19). In cgroup v2, writing a PID to `cgroup.procs` does not move descendants that already exist.
- **Result:** the background `sleep` stays in `launcher/`. Freeze and `cgroup.kill` act on the parent alone. `cgroup_kill` reports `remaining=0` because it counts only `probe-attempt/cgroup.procs`, while the child survives.
- **Contract:** "Verify: a probe script freezes and kills a process tree". The `notes.md` probe-result table is built on this probe.
- **Fix:** start the tree from inside the cgroup (`sh -c 'echo $$ > …/cgroup.procs; exec sh -c "sleep 30 & sleep 30"'`). Then check every descendant's `/proc/<pid>/status` State for `T` while frozen, and that none exist after the kill.

**M5 · D1 / task 1.1: the session store has no load, capture or commit operations.**
- **Location:** `harness_activity/session_store.py:21-34`; `activity.py:260-264,286-301`.
- **What it has:** `session` (an OpenAI SDK `Session`), `restore(position)`, `reset()` and `position()`. The checkpoint commit goes straight to `CheckpointRepository.insert_fenced`, not through the store. `restore` gets only an int, so a store cannot load a `session_ref`. `capture` returns only a position, so a store cannot produce a session blob for the checkpoint.
- **Failure scenario:** the phase 02 DSH store has to load its session blob from `latest.session_ref` and upload one at each checkpoint. This interface gives it no hook for either, so `run_harness_turn` has to change again.
- **Contract:** D1: "`run_harness_turn` calls a session store for load, truncation, capture and commit". Task 1.1: "Add the session store (load, truncate, capture, commit)".
- **Severity note:** phase 02 task 2.1 adds the session refs to `Checkpoint`, so you may decide the interface is meant to grow then. As written, task 1.1 is not met.

### Nits

1. **D3: `concurrency_per_pod: 1` is not enforced for DSH templates.** Only the YAML sets it (`local-dsh.yaml:21`); `loader.py` does not check it. A future `harness: dsh` template with `concurrency_per_pod: 4` would load, and `workers/main.py` would set `max_concurrent_activities=4`, so several attempts would share one DSH container (against ADR-0006). No later task plans this check either; you may want to treat it as Major.
2. **D3 / governance: a security change is recorded only in the plan.** Giving `SYS_ADMIN` to the DSH container, plus the failed `command_userns_blocked` check, appears only in the plan's decision log and `notes.md`. It is not in `docs/roadmap/decision-log.md` or ADR-0006. ADR-0006 still says "Good, because no component gets root-equivalent rights" and never mentions `SYS_ADMIN`. AGENTS.md says constraint changes go in the roadmap decision log. I rated this Nit because it is documentation, but it changes the security posture.
3. **D10: `newer_attempt_exists` is still in the seam** (`activity.py:311`). D10 says the fence "replaces `newer_attempt_exists` in the seam". It stays as an early exit, and it checks only the same turn, not newer turns.
4. **Task 2.2: the resolve-time harness check is still there** (`loader.py:102-106`). The task says "move"; the check was duplicated. This is harmless.
5. **D10 / R6: `close_unfinished` is not fenced.** It runs on a stale attempt's `NonRetryableError` path (`activity.py:212-218`). `through_attempt` bounds it, but it is still an attempt-row write by a stale attempt.
6. **R6 (later phase): session items are shared and unfenced.** Stale and current attempts share one `SQLAlchemySession(task_id)`. A stale attempt's runner can keep appending items that the current attempt's `position()` then counts. D10 does not list session writes, and this predates the diff.
7. **D10: the stale attempt's checkpoint blob is recorded before the fence check.** `activity.py:285` writes a `RecordingBlobStore` row before the fenced insert rejects it.
8. **`dsh` profile tasks have no worker.** The profile now resolves, so the orchestrator accepts tasks for it and queues them on `tpl.local-dsh`. `workers/main.py:71-77` refuses to start a worker for that queue, so the tasks sit until timeout. The guard also has no test.
9. **D7 / D9: `context_window` is optional for every harness** (`capability.py:68`). A DSH template without it would load, and D9's charge would then be undefined.
10. **D8 / R16 (later phase): events are not fully specified or ordered.**
    - `AgentEvent` has no durability or retention metadata (`schemas.md:15`).
    - `payload: dict[str, Any]` is neither size-bounded nor text-free; the docstring is the only guard.
    - `AttemptEvents.emit` assigns `seq` under its lock but calls `sink.emit` outside it (`events.py:418-429`). Two threads can therefore deliver seq 1 before seq 0. The single-threaded test cannot see this.
11. **Probe housekeeping.** Line 13 (`echo "+freeze" > /dev/null`) does nothing. The exact `docker run` or Compose settings used for the recorded results are not saved, so the table cannot be reproduced.
12. **Test coverage of R1 and R3.**
    - R1's test uses `claude_sdk`, a valid `Literal` value with no runner. No test tries a value outside the `Literal`; Pydantic would reject one.
    - R3's conformance suite calls the runner with `SQLiteSession` and bypasses the session store. The seam with the real `OpenAIAgentsRunner` is covered only by the CI stack checks (`make workers-check`, `make recovery-check`).

### Files
- <repo>/common/persistence/repositories.py
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/session_store.py
- <repo>/harness_activity/events.py
- <repo>/common/schemas/events.py
- <repo>/registry/loader.py
- <repo>/registry/templates/local-dsh.yaml
- <repo>/infra/dsh/isolation-probe.sh
- <repo>/workers/main.py
- <repo>/tests/integration/test_harness_activity.py
- <repo>/tests/integration/test_persistence_phase1.py
- <repo>/docs/adr/0006-per-attempt-isolation-boundary-for-dsh.md

<!-- Verbatim subagent report (impl-review-phase-01-round-2-scope); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## Scope review: phase 01 (harness seam and registry), diff 0f32d7dd..9f9f1da

I found no Blockers. There is one Major: the fence's idea of "newer attempt" covers only attempts that wrote a row. The rest are Nits about scope or test coverage. I did not repeat round-1 findings that `reviews.md` already resolves or accepts, except where the scope is still wrong in a new way.

### Major

**M1. The fence misses a newer attempt that never wrote a row (D10; sets up R6 in phase 02)**
- **Location:** `harness_activity/activity.py` `run_harness_turn`, the refusal branch at about lines 177-186, together with `_NO_NEWER_ATTEMPT` / `_TASK_LOCK` in `common/persistence/repositories.py:292-296`.
- **Scope mismatch:**
  - The plan defines a stale attempt as lower than "the highest (turn, attempt) seen for a task" (plan Terms).
  - D10 says each write "checks no newer (turn, attempt) exists".
  - The fence only counts attempts that have a `task_attempts` row. A `TemplateVersionUnavailable` refusal advances Temporal's `info.attempt` but never calls `attempts.start`.
- **Failure scenario:**
  1. Turn 1, attempt 1 on worker A misses its heartbeat (GC stall or a network partition) but the process stays alive.
  2. Temporal schedules attempt 2 on worker B, which runs a different template version and refuses without writing a row.
  3. During the retry backoff before attempt 3, worker A reaches `checkpoint(finish)` and `_finish`.
  4. `insert_fenced`, `assert_current` and `finish(fenced=True)` all pass, because no row is higher than (1, 1).
  5. A stale attempt has now written a checkpoint, a `done` attempt row and audit artifact blobs, which is exactly what R6 and R7 forbid.
  6. Attempt 3 then resumes from that finish checkpoint. A's row stays `done` rather than `lost`, so per-attempt accounting disagrees with Temporal's count.
- **Fix options:** have the refusal path record a marker row (for example outcome `refused`) under `_TASK_LOCK` before raising, or fence on the Temporal attempt number some other way.
- **Test that would expose it:** start (1, 1), run a refusal as attempt 2 through `run_harness_turn` with a mismatched `template_hash`, then call `insert_fenced` and `finish(fenced=True)` for (1, 1). Both should raise `FenceRejected` and currently don't.

### Nits

**N1. Artifact publication relies on the pre-check that D10 rejects (D10, R7)**
- **Location:** `activity.py` `_finish` (`assert_current`, then `blobs.put(..., retention="audit")`, then the fenced `finish`).
- **Contract:** D10 asks for "artifact publication ... in one transaction", and its Rejected line reads "a separate pre-check (races with a new attempt)". `assert_current` is that separate pre-check.
- **Scenario:** a newer attempt starts between `assert_current` and the fenced finish. The stale attempt has already written audit-retention blobs, the longest-lived class. R7 says "no blob or outcome is recorded".
- **Why a Nit:** round-1 F6 accepted this as an unreferenced blob, but the blob class is `audit`, not `task`. No test covers a start inside that window. One would wrap `blobs.put` to call `start_newer` on the first audit put.

**N2. The early exit and the fence disagree about newer turns (D10)**
- **Location:** `activity.py:315` calls `newer_attempt_exists`. That query checks the same turn only (`repositories.py:272-281`), while `_NO_NEWER_ATTEMPT` also checks `n.turn > :turn`.
- **Scenario:** a stale turn-N attempt still runs after turn N+1 has started. It passes the early exit, packs and uploads a workspace blob, and only then gets rejected.
- **Why a Nit:** the outcome is still correct, so the cost is wasted work and an orphaned blob. The check is "cheap early exit" in name only, because it covers a narrower scope than the fence.

**N3. The fence is opt-in, and the unfenced paths remain (D10)**
- **Location:** `AttemptRepository.finish(..., fenced: bool = False)` and `CheckpointRepository.insert` (unfenced), both still public.
- **Contract:** D10 says the fence "replaces `newer_attempt_exists` in the seam".
- **Scenario:** a phase 02 `DshRunner` path or barrier that calls `finish()` or `insert()` without the flag writes unfenced, and no test catches it.
- **Why a Nit:** production currently only uses the fenced forms (`activity.py:391`; `insert` is used only in tests). Defaulting `fenced=True`, or removing `insert`, would make the promise hold by construction.

**N4. Fence tests miss two scopes (D10)**
- `test_older_turn_is_fenced_by_a_newer_turn` (`tests/integration/test_persistence_phase1.py`) covers only `insert_fenced`. Nothing tests `finish(fenced=True)` or `assert_current` against a newer turn.
- The newer-turn case is the only one where the fence clause inside `finish`'s UPDATE does real work. For a newer attempt of the same turn, `start()` has already flipped the old row to `lost`, so `outcome = 'started'` alone makes the UPDATE miss. The post-check then raises whether or not the UPDATE was fenced.
- So `test_stale_attempt_cannot_checkpoint_or_finish` would still pass with the `AND NOT EXISTS` removed from the UPDATE.
- **Test to add:** start (1, 1), start (2, 1), then assert `finish(1, 1, fenced=True)` raises and that the (1, 1) row is still `started`.

**N5. The store contract is checked on one instance, not across attempts (D1; R3 now, R5 in phase 02)**
- **Location:** `tests/support/session_stores.py` `store_contract`.
- **The gap:**
  - The contract uses one store instance, and its checkpoint has no `session_ref`.
  - `run_harness_turn` builds a fresh store per attempt (`activity.py:256`) and restores from the checkpoint row.
  - The contract never checks that a new instance, standing in for a new worker, restores from what `capture()` returned.
- **Why a Nit:** `SQLAlchemySessionStore` persists in Postgres, so this is harmless for `openai_agents`. But the contract is the R3 vehicle that `DshRunner` and its store join in phase 02, and in its current shape a DSH store that never reads `session_ref` would pass it.
- Separately, `MemorySessionStore` duplicates the truncation logic and lacks the "shorter than checkpoint" handling, so the conformance runs exercise a copy of the store rather than the production one.

**N6. The `SessionStore` interface has no commit step (task 1.1, D1)**
- **Contract:** task 1.1 asks for "load, truncate, capture, commit", and D1 says "a session store for load, truncation, capture and commit".
- **Implementation:** `harness_activity/session_store.py` has only `session`, `load` and `capture`. The commit lives in the Activity's `checkpoint()`, which raises `NotImplementedError` when `session_ref` is set (`activity.py` checkpoint closure).
- **Why a Nit:** round-1 F3 resolved this deliberately. Still, the D6 barrier (freeze, capture, commit, thaw) needs the store to control commit, and the Activity packs the workspace before `capture()`, so that ordering has to move in phase 02.

**N7. Stale writes to the shared openai_agents session are unfenced (D10)**
- **Location:** `SQLAlchemySession` is keyed by `task_id` (`session_store.py:51`). The phase Goal says both runners sit behind "one fenced session store", but appends from the runner go straight to the shared session.
- **Scenario:** attempt 2's `load` truncates the session. Stale attempt 1's in-flight response then appends items, and attempt 2's next `capture()` counts them.
- **Why a Nit:** this was accepted in round-1 F7 and is pre-existing (threat model R5). I list it again only because the Goal wording over-promises.

**N8. The advisory lock key is a 32-bit hash (D10)**
- **Location:** `_TASK_LOCK = pg_advisory_xact_lock(hashtext(:t))` (`repositories.py:292`).
- **Effect:** two task IDs with the same hash serialize each other's start and fenced writes, and the lock shares the single-key advisory space with any other user of the database.
- **Why a Nit:** this is a throughput issue, not a correctness one, and I found no other advisory-lock users in the repository. The two-key form `pg_advisory_xact_lock(<namespace>, hashtext(:t))` would isolate the namespace.

**N9. Event `seq` is scoped per `AttemptEvents` object, not per attempt (D8; R16 in phase 02)**
- **Location:** `harness_activity/events.py` `AttemptEvents`. The counter starts at 0 per instance.
- **Scenario:** R16 has two emitters: the executor emits `tool_call`/`tool_result` and the gateway emits `token`. The plan calls the executor a worker-side "process". If each builds its own `AttemptEvents`, both produce `seq` 0, 1, … for the same `attempt_id`, so "ordered events" doesn't hold.
- **Why a Nit:** round-1 F19 accepted per-attempt `seq` assuming one instance per attempt. Nothing enforces a single instance, and the only test uses one object.

**N10. The workspace blob is written before the fenced insert (D10)**
- **Location:** the `checkpoint()` closure does `blobs.put` first, then `insert_fenced`.
- **Why a Nit:** a stale attempt leaves a task-retention blob with no checkpoint row. Round-1 F22 accepted this, and I note it only for completeness.

### Properties whose test scope matches the promise
- **R1:** `test_unknown_harness_value_is_rejected`.
- **R2:** `test_dsh_profile_cannot_allow_an_openai_template`, which exercises the new load-time check with a valid lock. `test_harness_mismatch_fails_at_load` also passes.
- **Task 2.3:** the `local-dsh@1` lock entry and `test_dsh_profile_resolves_the_dsh_template`. The lock hash is file-based (`loader.py:52-57`), so the new `context_window` field leaves the `local-default@1` digest unchanged.
- **Concurrent start vs fenced insert:** `test_fenced_insert_waits_for_a_concurrent_start`.
- **Activity-level fence:** `test_newer_attempt_mid_run_fences_the_finish`.
- **Ordered concurrent emit:** `test_concurrent_emitters_deliver_in_seq_order`.
- **Fence key:** turn numbers only increase within a workflow, and task IDs cannot be reused (`orchestrator/submit.py` uses `REJECT_DUPLICATE`), so keying the fence on (turn, attempt) per task is sound, apart from workflow resets (accepted as round-1 F17).

### Relevant files
- <repo>/common/persistence/repositories.py
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/session_store.py
- <repo>/harness_activity/events.py
- <repo>/registry/loader.py
- <repo>/tests/integration/test_persistence_phase1.py
- <repo>/tests/integration/test_harness_activity.py
- <repo>/tests/support/session_stores.py
- <repo>/tests/test_runner_conformance.py

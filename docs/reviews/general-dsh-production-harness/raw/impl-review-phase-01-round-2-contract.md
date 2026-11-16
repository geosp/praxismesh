<!-- Verbatim subagent report (impl-review-phase-01-round-2-contract); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## Phase 01 contract review (diff 0f32d7dd..9f9f1da)

I found no Blockers and two Majors. Both are gaps in the D10 fence: one is a check-then-write window in the production path, the other is a lock that no test would catch being removed. Everything else is a Nit. Several Nits match items the round-1 resolution table already accepted; I list them anyway so they aren't lost. Tests were not run: this review was read-only.

### Promise map

| Promise | Enforced at | Test that fails without it |
|---|---|---|
| R1: only `Harness` values load, and they are lock-pinned | `common/schemas/base.py:10`, `registry/loader.py:30,129-133`, lock check `loader.py:~150-163`, `registry/registry.lock` (local-dsh@1) | `test_unknown_harness_value_is_rejected`; `test_dsh_profile_resolves_the_dsh_template` (loads with check_lock=True) |
| R2: profile and template harness checked at load | `registry/loader.py:172-180` | `test_dsh_profile_cannot_allow_an_openai_template`, `test_harness_mismatch_fails_at_load` |
| R3: conformance suite runs on the seam | `tests/test_runner_conformance.py` RUNNERS/make_store; `harness_activity/session_store.py` | `test_memory_store_contract`, `test_session_store_contract` (Postgres); activity integration tests |
| D1: store does load, truncate and capture | `harness_activity/activity.py:256-290`, `session_store.py:49-71` | `store_contract`, plus existing resume tests |
| D3: `concurrency_per_pod: 1` | `registry/loader.py:134-140` | `test_dsh_template_needs_one_attempt_and_a_context_window` |
| D5: new template and profile; `default` unchanged | `registry/templates/local-dsh.yaml`, `registry/profiles/dsh.yaml` | `test_dsh_profile_resolves_the_dsh_template` |
| D8: no-op and in-memory sinks | `harness_activity/events.py` | `tests/test_agent_events.py` |
| D10: checkpoint insert is fenced | `repositories.py:303-330` | `test_stale_attempt_cannot_checkpoint_or_finish`, `test_newer_attempt_mid_run_fences_the_finish` |
| D10: attempt finish is fenced | `repositories.py:163-209`, `activity.py:381-394` | repository-level only (see N1) |
| D10: artifact publication is fenced | `repositories.py:211-224`, `activity.py:369-379` | `test_newer_attempt_before_publication_blocks_artifacts` (only partly, see M1) |

### Major

**M1. Artifact publication is check-then-write, not one transaction (D10; R7 follows later).**
- **Where:** `harness_activity/activity.py:369-379`. `assert_current` runs in its own transaction and releases the lock. Only then do the `blobs.put(..., retention="audit")` calls run.
- **Contract:** D10 says "Checkpoint insert, attempt finish and artifact publication each run in one transaction that checks no newer (turn, attempt) exists", and it rejects "a separate pre-check (races with a new attempt)". This code is that pre-check.
- **Failure scenario:**
  1. Attempt 1 returns `done` and its finish checkpoint commits.
  2. `assert_current` passes.
  3. Temporal starts attempt 2 (heartbeat timeout), and `attempts.start` commits.
  4. Attempt 1 still writes audit blobs for every output.
  5. The fenced finish then raises Superseded.

  The result is audit-retention blobs from a stale attempt, which R7 later forbids: "no blob or outcome is recorded".
- **Test gap:** `test_newer_attempt_before_publication_blocks_artifacts` starts the newer attempt before `assert_current`, so it never opens this window.
- **Test that would expose it:** wrap `h.blobs.put` so the first audit put calls `start_newer`, then assert there are no audit blobs.
- **Note:** round 1 (F6) recorded this as a residual. It is still a mismatch with D10 as written. Either change D10's wording, or make publication content-addressed staging that is only promoted inside the fenced finish transaction.

**M2. No test covers the lock in `attempts.start`, which is the side of the race that actually matters (D10).**
- **Where:** `common/persistence/repositories.py:138`, `await conn.execute(_TASK_LOCK, {"t": task_id})` in `start`.
- **Test gap:** `test_fenced_insert_waits_for_a_concurrent_start` (`tests/integration/test_persistence_phase1.py:227-249`) does not call `AttemptRepository.start`. It takes the advisory lock itself and inserts the row by hand.
- **Mutation that survives:** delete line 138 and every test still passes, but the round-1 F1 race comes back:
  1. `start` for attempt 2 is mid-transaction, with its row inserted but not committed.
  2. Attempt 1's `insert_fenced` gets the lock without contention.
  3. Under READ COMMITTED its NOT EXISTS check does not see the uncommitted row, so the stale checkpoint commits.
- **Test that would expose it:** run the real `start` concurrently, for example with an event-loop hook or a `pg_sleep` in a wrapped connection, so its transaction stays open across the stale `insert_fenced`.
- The code itself is correct today; the gap is the missing regression guard.

### Nit

**N1. The Activity's fenced finish has no Activity-level test, and the turn-level fence on finish has none at all (D10).**
- `activity.py:391` passes `fenced=True`. Remove it and no test fails:
  - The mid-run test stops at `insert_fenced`.
  - The publication test stops at `assert_current`.
  - For a newer attempt of the same turn, the `outcome='started'` predicate already makes the update a no-op, because `start` marked the row lost.
- The fence only matters for a newer turn. `start` for turn 2 does not mark turn-1 rows lost, so an unfenced finish would overwrite a stale turn-1 row.
- `test_older_turn_is_fenced_by_a_newer_turn` (`test_persistence_phase1.py:217`) only covers `insert_fenced`, not `finish`.
- **Tests to add:** a needs_input resume that goes straight to `_finish` with a newer attempt started; and a repository finish with a newer turn.

**N2. `SessionStore` has no commit operation (D1, task 1.1).**
- Task 1.1 says "Add the session store (load, truncate, capture, commit)", and D1 says the seam "calls a session store for load, truncation, capture and commit".
- The protocol (`harness_activity/session_store.py:35-46`) has only `session`, `load` and `capture`. The commit is `checkpoints.insert_fenced` in the Activity (`activity.py:292-307`).
- A DSH store needs to upload its session blob before the fenced insert. With the current shape it has to do that inside `capture()`, so a stale attempt can write a session blob before the fence rejects it.
- `activity.py:287-289` raises NotImplementedError for any `session_ref`, so none of this is reachable yet.

**N3. The conformance suite uses the seam only as a session factory (R3, observability).**
- `run()` and the other call sites in `tests/test_runner_conformance.py` use `make_store(...).session`. They never call `load` or `capture`, and the store is `MemorySessionStore` (SQLite), not `SQLAlchemySessionStore`.
- Deleting `SQLAlchemySessionStore.load` or `capture` would not fail the conformance suite. It would fail `test_session_store_contract` and the Activity integration tests.
- R3's "when the conformance suite runs on the seam" is therefore only met by those tests together. A suite fixture that calls `store.load(None)` before each run and `capture()` after, with the production store on Postgres, would observe it directly.

**N4. `newer_attempt_exists` is still in the seam (D10).**
- D10: "It replaces `newer_attempt_exists` in the seam." It is still called at `activity.py:315` as an early exit.
- It also only checks the same turn (`repositories.py:272-281`), unlike the fence, which checks turn or attempt. It is harmless because the fenced insert follows. Round 1 accepted this as F15.

**N5. `close_unfinished` writes attempt rows without the fence on a stale attempt's failure path (D10).**
- `activity.py:212-218` to `repositories.py:225-249`: there is no lock and no newer-attempt check.
- For a newer attempt of the same turn, `start` has already marked the stale row lost, so it does nothing.
- For a newer turn, a stale turn-1 attempt that hits HarnessInputError would update its own still-'started' row to failed. That is an attempt-row write by a stale attempt, which D10 and R6 (phase 02) forbid. It is edge-only. Round 1 accepted this as F16.

**N6. The stale checkpoint's workspace blob is written before the fence rejects it (D10).**
- `activity.py:284-285` stores the tarball before `insert_fenced`. The blob is orphaned with task retention and has no row. Round 1 accepted this as F22.

**N7. The resolve-time harness check was duplicated, not moved (task 2.2).**
- `registry/loader.py:102-106` is kept, and after the load-time check it is unreachable. No test covers its CapabilityError path any more.
- Task 2.2 says "Move". Round 1 accepted this as F10.

**N8. `docs/roadmap/schemas.md` was not updated for the new fields (D7, D8).**
- The `WorkerTemplate` entry (schemas.md:10) does not list the new `context_window` field added at `common/schemas/capability.py:66-68`.
- The `AgentEvent` entry (schemas.md:15) lists "Durability/retention metadata" that `common/schemas/events.py` doesn't have. Round 1 accepted the AgentEvent part as F24.

**N9. The `dsh` profile resolves, but no worker can serve it (D5).**
- `workers/main.py:71-77` refuses non-`openai_agents` templates.
- A request with profile `dsh` passes `resolve` and is dispatched to `tpl.local-dsh`, which has no poller, so it waits until timeouts.
- The worker guard has no test. Round 1 accepted these as F9 and F21.

**N10. Nothing enforces "no prompt text" in `AgentEvent.payload` (D8; R16 is phase 02).**
- `payload: dict[str, Any]` accepts any text. `test_unknown_event_type_and_fields_are_rejected` only rejects unknown top-level fields and types. Round 1 accepted this as F19.

**N11. The probe is a manual gate, not automated (task 0.1).**
- `infra/dsh/isolation-probe.sh` runs by hand and its results are recorded in `notes.md#d3`. Nothing in CI reruns it.
- The user-namespace check still fails, and the probe counts `unshare -Urm` as a mount-namespace success (lines 613-617), which needs exactly the capability that is supposed to be blocked.
- This is acceptable under the gate wording ("if both fail, stop"), but the recorded result relies on phase 02 adding the seccomp filter. Round 1 accepted this as F23.

### Files
- `<repo>/harness_activity/activity.py`
- `<repo>/harness_activity/session_store.py`
- `<repo>/common/persistence/repositories.py`
- `<repo>/registry/loader.py`
- `<repo>/tests/integration/test_persistence_phase1.py`
- `<repo>/tests/integration/test_harness_activity.py`
- `<repo>/tests/test_runner_conformance.py`
- `<repo>/docs/roadmap/schemas.md`

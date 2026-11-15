<!-- Verbatim subagent report (impl-review-phase-01-round-2-failure); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## Phase 01 failure and retry review (diff 0f32d7dd..9f9f1da)

I found no Blocker and no Major issues. R1 and R2 hold. Three things hold on every restart path I traced, under the per-task advisory lock (`repositories.py:292`):
- **Checkpoint insert:** a stale attempt's insert is rejected (`insert_fenced`, `repositories.py:304-329`).
- **Attempt finish:** a stale attempt's finish is rejected (`finish(fenced=True)`, `repositories.py:177-209`).
- **Artifact pre-check:** `assert_current` (`repositories.py:211-223`) runs before the audit blobs (`activity.py:370-378`).

The workflow runs turns one after another (`orchestrator/workflow.py:106-112`), so a newer row only ever comes from a later Temporal attempt.

### Units traced
**`run_harness_turn` / `_attempt` / `_run` / `_finish`** (`harness_activity/activity.py`), in order:
1. Template check, then a refusal heartbeat.
2. `attempts.start`: lock, mark lower started rows lost, upsert (`:236`).
3. `checkpoints.latest`.
4. Workspace blob get and unpack.
5. `store.load(latest)` truncates, or `store.load(None)` clears (`:264`, `:278`).
6. `runner.run`. Before each model call:
   - `newer_attempt_exists`;
   - `checkpoint()`: pack, `blobs.put` (`:285`), `store.capture`, `insert_fenced`;
   - the budget check.
7. The final `checkpoint(finish)` (`:343`).
8. `_finish`: `assert_current`, audit `blobs.put`, `finish(fenced=True)`, `rmtree`.

How each failure point plays out:
- **Death before the first checkpoint:** the next attempt finds no checkpoint, clears the session and starts fresh. Correct.
- **Death after the finish checkpoint but before the attempt row is written:** the next attempt replays `_finish` from `latest.finish` under its own fenced row. Correct.
- **Cancellation inside an `engine.begin()` transaction:** it rolls back and the transaction-level lock is released. No partial write.
- **Overlap with a newer attempt:**
  - Its `start` marks the old row lost and inserts its own row while holding the lock.
  - Every later fenced write by the old attempt then fails and raises `Superseded`, which is retryable and not in `NON_RETRYABLE` (`workflow.py:29`).
  - The concurrency test (`test_persistence_phase1.py:224-249`) would fail if the lock in `insert_fenced` were removed.

**Other units:**
- **`AttemptEvents.emit`** (`harness_activity/events.py:42-55`): builds the event, increments `seq`, calls `sink.emit`, all under one lock.
- **`infra/dsh/isolation-probe.sh`**: a one-shot probe run in a `--rm` container.

### Findings (all Nit)

**N1 · `AttemptRepository.start` takes the task lock but does no fence check, so a stale attempt that starts late can rewrite the shared session (D10, D1; R6 wording)**
- **Location:** `common/persistence/repositories.py:134-161`; `harness_activity/activity.py:236`, `:264`, `:278`; `harness_activity/session_store.py:57-68`.
- **Scenario:**
  1. Attempt 1 of turn 1 stalls between `heartbeat.running()` and `attempts.start`, for example during an event-loop pause or while cut off from Temporal but not from Postgres.
  2. Temporal starts attempt 2, which inserts its row, resumes from checkpoint seq k (position P) and appends conversation items to the shared `SQLAlchemySession`.
  3. Attempt 1 wakes up. `start` inserts a `started` row for attempt 1 (a stale attempt row; R6 says that never happens).
  4. `store.load(latest)` then pops every item after P from attempt 2's live session. On a fresh start, `load(None)` → `clear_session()` wipes it instead.
  5. Attempt 1 is only rejected at its first `insert_fenced`, after the damage.
  6. Attempt 2's next `capture()` records a shorter position, and a later resume replays a conversation with items missing.
- The stale `started` row for attempt 1 stays open until `complete_task` (`orchestrator/activities.py:93`).
- **Why Nit:** the old code behaved the same way, and the review already accepted F7 (session items are shared and unfenced). DSH sessions are per-attempt blobs, so this does not carry over to DSH.
- **Cheap fix:** `start` already holds the lock. It could check `_NO_NEWER_ATTEMPT` there and raise `FenceRejected` before `load` runs.
- **Test:** start attempt 2 and add items past the latest position, then run attempt 1. Assert the item count is unchanged and no row exists for attempt 1.

**N2 · The fence does not require the writer's own row to still be `started`, so the newest attempt can write after it has been closed (D10)**
- **Location:** `_NO_NEWER_ATTEMPT` (`repositories.py:293-296`), used by `insert_fenced` and `assert_current`.
- **Scenario:**
  1. `TURN_ATTEMPTS = 0` (`workflow.py:43`) and the schedule-to-close limit is `turn_timeout * 6` (`workflow.py:124`).
  2. The turn's last attempt overruns that limit while still running. The workflow gets an `ActivityError` and `complete_task` closes every open row (`close_unfinished(turn=None)`).
  3. The zombie attempt is still the highest (turn, attempt), so:
     - its `insert_fenced` succeeds and adds checkpoint rows to a completed task;
     - its `assert_current` passes and audit blobs are written;
     - its `finish` updates nothing and returns normally (F18).
- **Why Nit:** D10 literally only asks that no newer (turn, attempt) exists. No artifact or outcome is recorded, because Temporal drops the result. The cost is leftover checkpoint rows and blobs after completion.
- **Test:** start attempt 1, call `close_unfinished(task, None, ...)`, then `insert_fenced` for attempt 1. Today it succeeds.

**N3 · A failed sink call leaves a gap in `seq` (D8)**
- **Location:** `harness_activity/events.py:53-54`.
- `self.seq += 1` runs before `self.sink.emit(event)`. If the sink raises (relevant once roadmap Phase 2 adds a transport), that number is used up but never delivered. The next event gets `seq + 1`, so a consumer checking for consecutive numbers sees a gap.
- The lock is a `threading.Lock` held while the sink runs. A sink that blocks on I/O would stall the event loop.
- **Why Nit:** both sinks today are in memory.
- **Test:** a sink that raises once; check the `seq` values delivered.

**N4 · The `session_ref` stub fails after the workspace blob is already uploaded, and the failure is retryable (D1)**
- **Location:** `activity.py:285-289`.
- When `capture()` returns a `session_ref`, the code raises `NotImplementedError` after `blobs.put`. That is a plain retryable exception, so every Temporal retry uploads another workspace blob that no row references and fails the same way, until `MAX_REAL_ATTEMPTS`.
- **Why Nit:** no store in phase 01 returns a ref; it is a stub until phase 02.
- **Test:** none needed until phase 02. Phase 02 should remove the stub, not rely on it.

**N5 · `hashtext` gives a 32-bit lock key, so unrelated tasks can share a lock (D10)**
- **Location:** `repositories.py:292`.
- Two task IDs with the same hash serialize their `start` and fenced writes, and the key space is shared with any other advisory-lock user on the same database. Only a little latency is at stake; correctness is not.
- **Why Nit:** I found no other advisory-lock user in the repository. The only other occurrence is the test at `test_persistence_phase1.py:237`.

**N6 · The conformance suite takes the store's session but never calls `load` or `capture` (R3, task 1.1)**
- **Location:** `tests/test_runner_conformance.py:73-76` and the other `make_store(...).session` call sites.
- The suite drives `OpenAIAgentsRunner` on `MemorySessionStore(...).session`, which is a `SQLiteSession` as before. It never calls `load` or `capture` before or after `runner.run`.
- **Coverage elsewhere:**
  - restore and truncation through the production `SQLAlchemySessionStore` with the scripted runner: `test_restore_truncates_session`, `tests/integration/test_harness_activity.py:206`;
  - the store contract on both stores: `:637-642`.
- **Gap:** no test runs the real `openai_agents` runner after a truncating `load`.
- **Why Nit:** each piece is covered separately, and this was review round 1 finding F4, marked fixed.

**Already accepted in round 1, and confirmed from the failure side:**
- F6: the gap between `assert_current` and the fenced finish can leave a blob no artifact references.
- F7: session items are shared across attempts.
- F9: no worker serves `tpl.local-dsh` until phase 02. The resolved task then waits until the turn's schedule-to-close limit, `turn_timeout * 6` (60 min for `local-dsh`).
- F16: `close_unfinished` is unfenced on a stale attempt's failure path, but `through_attempt` bounds it.
- F18: a fenced finish returns normally when its row is already closed and nothing is newer.
- F22: a stale attempt's checkpoint blob is uploaded before the fenced insert rejects it.

I found nothing that contradicts those resolutions.

### R1, R2, R3
- **R1:** a harness outside the `Harness` Literal is rejected when the profile or template is parsed (`common/schemas/base.py:10`). Lock pinning is enforced at `registry/loader.py:155-166`, and `local-dsh@1` is in `registry.lock`.
- **R2:** load-time check at `registry/loader.py:172-179`. `allowed_templates` has `min_length=1` (`capability.py:96`), so the `or []` can never skip a profile.
- **R3:** the suite is parametrized over `RUNNERS`, with the seam caveat in N6.
- **D3 / D7 guard:** dsh templates must have `concurrency_per_pod: 1` and a `context_window` (`loader.py:134-140`).
- **Worker guard:** a worker refuses any template whose harness is not `openai_agents` (`workers/main.py:71-77`).

Files: <repo>/common/persistence/repositories.py, <repo>/harness_activity/activity.py, <repo>/harness_activity/session_store.py, <repo>/harness_activity/events.py, <repo>/tests/test_runner_conformance.py, <repo>/tests/integration/test_persistence_phase1.py, <repo>/tests/integration/test_harness_activity.py, <repo>/orchestrator/workflow.py

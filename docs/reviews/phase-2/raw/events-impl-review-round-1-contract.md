<!-- Verbatim subagent report (events plan impl-review round 1, contract, diff 41c0bcf..c7dcbcd); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Review of phase 01 (Event table and agentctl tail), diff 41c0bcf..c7dcbcd, judged against the contract.

**Verdict:** two Major findings and twelve Nits. No Blockers. Most promises have enforcing code and a real-database test that would fail without it.

## Promise map (enforcing code, then the test that would fail)
- **R1, stored once on re-send:** `common/events/table.py:86-94` (event_batches `ON CONFLICT ... RETURNING`) and the frozen batch in `harness_activity/events.py:158-192`. Tests: `test_a_resent_batch_is_stored_once` (table and memory), `test_a_lost_reply_is_resent_and_stored_once`, `test_a_frozen_batch_survives_failed_tries...`.
- **R1, gap-free offsets:** `table.py:69-102`, a `FOR UPDATE` on event_logs, then the insert and the `next_offset` advance. Tests: `test_resume_after_an_offset`, `test_publish_and_fenced_checkpoint_never_deadlock`. Scenario 2 (two attempts, both finish, table) has no test; see Nits.
- **R2:** `transport.py:65-82` (`guarded`) and `table.py:110-143`. Tests: `test_resume_after_an_offset`, `test_a_cancelled_follower_stops...`, and `test_tail_resumes_after_an_offset` (in-memory transport).
- **R3:** `transport.py:57-62`, `table.py:123-128`, `guarded`. Tests: `test_pruned_events_are_reported_first`, `test_pruning_during_a_read_is_reported`, `test_tail_reports_pruned_events_first`.
- **R4:** `table.py:63-68`; workers build `TableTransport(engine)` with `fenced=True` (`workers/main.py:113,123`). Test: `test_a_superseded_attempt_publishes_nothing` (real PostgreSQL).
- **R5:** `activity.py:613-621`, where close() runs before `finish_checkpoint`, `assert_current` and `attempts.finish`. Tests: `test_a_refused_final_flush_makes_no_finish_write` and `..._on_the_finish_shortcut_...`. With the order inverted, these tests would see `(1, "done")` instead of `(0, "lost")`, because `Superseding` starts attempt 2 only at the first publish.
- **R6:** emit sites `runner.py:182,204,216`, `activity.py:446,484,613`, and the DSH gateway and executor. Tests: `test_tool_and_token_events` and `test_dsh_turn_through_the_activity`.
- **R7:** `events.py:136-171`. Tests: `test_640_events_at_once_are_ten_batches` and `test_a_few_events_wait_for_the_delay...` (real clock).
- **R8:** `events.py:119-134` and `activity.py:440-453,613-620`. Tests: `test_close_flushes_the_last_event`, `test_close_completes_when_its_caller_is_cancelled`, `test_a_runner_failure_stores_its_events...`, `test_a_cancelled_attempt_stores_its_events`.
- **R9:** `activity.py:484`. Test: `test_a_retried_attempt_resets_from_its_checkpoint`. The "first event" claim fails on some paths; see Major 2.
- **D1:** migration 0005 and `table.py`. Retention defaults are `'task'`. NOTIFY at `table.py:103`. LISTEN plus the 1 s poll at `table.py:120-140`.
- **D2:** fence order at `table.py:63-75`; `fence.py` is used by every fenced repository write (`repositories.py:146,203,219,270,392,494`).
- **D3:** `activity.py:613` (status = `result.status`) and the openai hooks.
- **D4:** `table.py:170-209`. Test: `test_prune_older_than_deletes_an_old_prefix`.
- **D5:** `agentctl` and `orchestrator/cli.py` (`print_events`, `tail`, `prune`). Test: `test_tail_follows_until_the_workflow_closes...`.

## Major

**1. A final flush that times out raises `CancelledError` instead of `EventsUnavailable` (R8, D2).**
- **Where:** `harness_activity/events.py:131-133`, with `activity.py:440-447` and `activity.py:619-620`.
- **Scenario:**
  1. The database stalls, so a publish hangs longer than the 10 s bound during the final flush in `_finish`.
  2. `close()` hits `TimeoutError`, calls `self.task.cancel()` and returns at once. The task is not done yet, because there has been no `await` since the cancel.
  3. `_finish` raises `EventsUnavailable`.
  4. The outer `except BaseException` in `_attempt` checks `publisher.closed`. That is `task.done()`, which is still False.
  5. So it emits a second `status` (failed / EventsUnavailable) after the stored-or-not `status: done`, and calls `close()` again.
  6. The second `close()` awaits `asyncio.shield(self.task)` on a task that is now cancelled, so it raises `CancelledError` (only `TimeoutError` is caught).
  7. That `CancelledError` replaces `EventsUnavailable`.
- **Outcome:** no cancel was requested, so temporalio (`.venv/.../temporalio/worker/_activity.py` around lines 500-510, "Completing activity as failed") reports a failure typed `CancelledError`. It is still retryable as far as I can tell. But this contradicts the decision-log entry ("a flush that fails for good raises the retryable `EventsUnavailable`") and the runbook ("the attempt fails with the retryable `EventsUnavailable`"). It also logs a misleading cancellation.
- **Test that would expose it:** a transport whose `publish` sleeps longer than the timeout, with `close(timeout_s=0.1)` reached from `_finish` via `HarnessActivities`. Assert that the raised error is `EventsUnavailable` and that no finish write was made.
- **Related gap:** no activity-level test covers the `EventsUnavailable` path at all, not even with a plain `ConnectionError`. Only the unit test `test_a_database_that_stays_down_is_returned_from_close` covers `close()`.

**2. An attempt's first event is not always a `reset` (R9, D3).**
- **Where:** `harness_activity/activity.py:428-433` and `:478-484`.
- **Rule broken:** R9 says "An attempt's first event is a `reset`"; D3 says "The Activity emits `reset` at attempt start".
- **Scenario:**
  1. The publisher and `AttemptEvents` are created at `activity.py:413-425`.
  2. Several calls run before `reset` is emitted at line 484: `_open` (`_charge` and DSH `open_attempt`, e.g. a launcher or pin failure), `build_config`, and `self.checkpoints.latest(...)` (a DB error).
  3. If any of them raises, the outer handler emits `status` as seq 0 and flushes it (`activity.py:445-447`).
- **Outcome:** `tail` shows that attempt's events with no `reset`. `schemas.md` ("`reset` ... first event of every attempt") is then wrong too.
- **Test that would expose it:** an `open_attempt` that raises (or a `ScriptedRunner` harness with `build_config` patched to raise). Assert that the stored events start with `reset`.
- **Possible fix:** emit `reset` (after looking up `latest`) before `_open`, or do not emit `status` when no `reset` was emitted.

## Nits
- `events.py:168`: after a cut, `oldest` is reset to the cut time, not the leftover events' emit time. Events left over from a burst larger than 64 can wait up to 200 ms after the cut instead of 200 ms after they were emitted (R7 "200 ms after the oldest unpublished event"). It is only latency.
- `orchestrator/cli.py:208-211`: `print_events` does not advance `last` on an `Expired`. If the follow reader is cancelled after printing `Expired(15)` but before printing offset 15, the final read prints the `Expired` line again (R3/D5: duplicated output, no duplicated events).
- `orchestrator/cli.py:236-241`: `closed()` returns True on any describe exception, so a transient Temporal outage ends `tail --follow` while the Workflow is still running. D5 says it stops "once the task's Workflow has closed".
- `orchestrator/cli.py:233`: `tail` connects to Temporal even with `--no-follow`, which D5 says only "reads to the end and exits". With Temporal down, `--no-follow` fails needlessly.
- No real-database test for R1 scenario 2: two attempts, each emitting and both finishing, with offsets 1..N and N equal to the events emitted. Only the in-memory `test_batch_ids_name_the_attempt` (one event each) comes close.
- `activity.py:268` and `events.py:169`: batch IDs depend on Temporal's `info.attempt`. If a turn's Activity is re-run with the same (turn, attempt) within 600 s (e.g. a Workflow reset; `attempts.start` uses ON CONFLICT DO UPDATE), its batches collide with stored IDs and are silently dropped (R1/D2). This is rare.
- `events.py:185`: `except Exception` treats any error, including a non-JSON-serialisable payload (`TypeError` from `table.py:_row`), as a database error. The batch is re-sent forever, every later event queues behind it, and every attempt fails with `EventsUnavailable` (D2 "after a database error"). Current payloads are all JSON-safe.
- `events.py:186-189`: re-sends during a run have no age cap. A commit whose reply was lost, followed by a database outage longer than 600 s, is stored twice when the re-send arrives, because that publish first deletes its own batch row (`table.py:80-85`). This is outside R1's "within 600 s", but nothing enforces it.
- `table.py:93-94`: a deduplicated re-send returns before `pg_notify`. D1 says "Each publish NOTIFYs". This is harmless.
- `harness_activity/dsh/gateway.py:337-338` (code from before this diff): refused-tool events store the model-chosen `function.name` verbatim. That is model-generated text of unbounded length, now persisted. R6 allows only "counts, names, IDs and statuses".
- `docs/roadmap/schemas.md` (new table): it says `status` is the "last event of every attempt" and `reset` the "first event of every attempt". A superseded attempt emits no `status`, and see Major 2 for `reset`.
- `docs/operations/runbook.md` ("--older-than 7d # delete the oldest week") misdescribes D4: it deletes the longest prefix older than 7 days. Also `plan.md`'s Phases table still shows "0/11" while 9 tasks are checked.

## Observability
- R4, the D2 lock order, R1 deduplication and R3 are tested on real PostgreSQL (`tests/integration/test_event_table.py`).
- R7 and R8 use a real clock with `MemoryTransport`. The table's own behaviour is covered separately.
- The CLI tail tests use `MemoryTransport`. The table's follow mode (LISTEN, notify during a fetch, cancellation) is covered by the suite.
- Not observed by any test: `close()`'s 10 s timeout path (Major 1) and the activity-level database-error final flush.

## Files
- /home/geo/develop/praxismesh/harness_activity/events.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/common/events/table.py
- /home/geo/develop/praxismesh/common/events/transport.py
- /home/geo/develop/praxismesh/orchestrator/cli.py
- /home/geo/develop/praxismesh/harness_activity/dsh/gateway.py
- /home/geo/develop/praxismesh/docs/roadmap/schemas.md
- /home/geo/develop/praxismesh/docs/operations/runbook.md
- /home/geo/develop/praxismesh/tests/integration/test_harness_activity.py
- /home/geo/develop/praxismesh/tests/integration/test_event_table.py
- /home/geo/develop/praxismesh/tests/test_event_publisher.py

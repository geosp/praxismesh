<!-- Verbatim subagent report (events plan design-review round 2, codebase fit, at 910be44); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Review of docs/plans/2026-11-18-phase-2-agent-events (plan at 910be44, code = main 73801ea)

I found 2 Majors and 10 Nits, and no Blockers. Both Majors are gaps in how the plan says it will do things. The decisions themselves are sound. Most of what the plan and notes say about the code checks out:
- The fence code: `_TASK_LOCK` and `_NO_NEWER_ATTEMPT` are at `repositories.py:380-384`; `FenceRejected` is at `:372`.
- The events code: `AttemptEvents`, `NoOpSink` and `MemorySink` are in `harness_activity/events.py`. DSH emits token events with counts only (`gateway.py:319-324`) and tool events from `executor.py:171-177`. The openai-agents hooks are in `runner.py:146-206`.
- The spike: `transport.py` has `Expired`, `expiry_for` and `guarded`, `table.py` does the batch-row dedup, and `test_table_notify.py` exists.
- The CLI and packaging: `orchestrator/cli.py` exists and `pyproject.toml` sets `package = false`.
- The workflow and the database: the workflow ID is the task ID (`submit.py:60`), and the engine uses asyncpg (`settings.py`).

The lock order in notes.md#d2 holds: nothing takes an `event_logs` row lock and then the task lock, and prune takes no task lock. I found no Decision that contradicts an ADR in force (0002, 0003, 0005-0009).

## Major

**M1 · Task 2.2 and notes.md#d2 (success path) leave out the restore short-circuit path.**
- **What's wrong:** The plan sequences the final flush as "runner returns; emit `status`; `close()`; ... otherwise the finish checkpoint, artifacts and outcome" (notes.md#d2). Task 2.2 says "run the flush before the finish checkpoint". But `_run` has a second success path that never calls the runner and writes no finish checkpoint. When the newest checkpoint already has a finish report, it goes straight to `_finish`, which publishes artifacts and writes the fenced outcome.
- **Evidence:** `harness_activity/activity.py:441-450` (`if latest.finish is not None: ... return await self._finish(...)`). Compare `:496-520`, where the flush would go between the runner returning and `checkpoint(finish)`.
- **Consequence:** This is the "worker lost after finish_task" recovery case. Implemented as written, the attempt's `reset` and `status` are never explicitly flushed and the background task is never closed before the outcome is written. That breaks R8 and the ordering R5 claims, and it is exactly what the R9 and demo 4.1 scenario (kill the worker mid-turn) can hit.
- **Fix:** Have the plan put the `status`, `close()` and Superseded-on-refusal step at the entry of `_finish`, or in one try/finally that covers both paths. Add a test for the short-circuit attempt.

**M2 · notes.md#d2 and Decisions › D2: a batch that fails all its re-sends is not frozen.**
- **What's wrong:** The notes say "After the last try the batch stays buffered for the next trigger." Nothing says that batch keeps its ID and its exact events. ADR-0009 names this hazard directly: "a retried publisher that reuses batch IDs has its new events dropped as re-sends".
- **How it loses events:** Say a "failed" try actually committed and only the reply was lost, which is R1's own scenario. If the next trigger merges new events into the still-buffered batch under the same ID, those new events are silently dropped as a re-send. If it re-cuts the buffer under a new ID, the batch that already committed is stored twice. Either breaks R1 and R8.
- **Fix:** State that a batch is immutable once cut, keeps its ID and contents until it is acknowledged, and that new events go only into later batches. Add a test in task 2.1: all tries fail with commit-but-lost-reply, more events arrive, then a successful publish stores every event exactly once.

## Nits

- **Plan › Phases table:** it says "0/12" tasks, but the phase file has 11 (1.1-1.3, 2.1-2.3, 3.1-3.3, 4.1-4.2).
- **Task 1.1:** "the table list in `retention.py`" is `PHASE1_TABLES`, documented as "Phase 1 tables ... (migration 0003)" (`common/persistence/retention.py:20-31`). Rename it or update the comment when adding event tables; the test that checks it is at `test_persistence_phase1.py:26,77`.
- **notes.md Evidence:** the round-1 E18 "fix" made the citation wrong. `NoOpSink` is defaulted at `harness_activity/dsh/runner.py:238`; line 237 is `self.ledger_store, self.blobs = ...`.
- **Task 2.2, list of call sites:** it leaves out several places the change touches:
  - `tests/integration/test_dsh_capabilities.py:90`, which also calls `runner.run(...)` with six arguments.
  - The `DshRunner(sink=...)` constructor parameter, which D2's "Rejected: the runner owning events" implies is removed. `tests/support/dsh_container.py:112-115` and `tests/integration/test_dsh_activity.py:127,143,212` depend on it.
  - How `HarnessActivities` gets its transport, and the wiring in `workers/main.py:103,114`.
  - Whether `events` is a required or a defaulted parameter.
- **D2 vs task 2.1:** "re-sends ... up to 3 times" (D2, and three backoffs in the notes means 4 tries) against "3 tries" (task 2.1). Pick one.
- **R1, second scenario:** "offsets run 1..N with no gap" cannot detect a batch-ID collision between attempts, because a dropped batch still leaves the offsets gap-free. Assert N equals the number of events emitted. ADR-0009 Confirmation requires a test of attempt-named batch IDs, and no task names one.
- **R7, first scenario:** "640 events ... when the turn ends ... 10 batches" conflicts with D3, which gives every attempt a `reset` and a `status` (642 events, 11+ batches). State it at the publisher level (task 2.1's fake transport).
- **D4 `--older-than`:** deleting by time can leave holes, because `stored_at` (transaction `now()`) need not grow with offset when publishes wait on the lock. Prune should delete an offset prefix. Also, "lowest remaining offset" is undefined when every event is pruned; use `next_offset`, as the spike's `LEAST($2, next_offset)` does (`spikes/event-transport/event_transport/table.py`).
- **D5 end signal:** the `tasks` row stays `running` if a workflow is terminated, and the row does not exist before `record_task` (`orchestrator/workflow.py:83` comment; `complete` is only called from `orchestrator/activities.py:131`). `tail --follow` then never stops, and the plan does not define what happens when the row is missing.
- **Task 2.3:** results go under `tests/benchmarks/results/`, but the existing benchmark records results under `docs/benchmarks/` (`tests/benchmarks/run.py:58,226`). Also, `FenceRejected` stays in `repositories.py:372` while task 1.2 moves only the lock and the predicate into `fence.py`. Moving it too would keep `common/events/` from importing the repositories module.

Files referenced:
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/plan.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/phases/01-event-table-and-tail.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/notes.md
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/dsh/runner.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/persistence/retention.py
- /home/geo/develop/praxismesh/spikes/event-transport/event_transport/table.py
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/workers/main.py

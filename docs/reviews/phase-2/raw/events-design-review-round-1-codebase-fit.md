<!-- Verbatim subagent report (events plan design-review round 1, codebase fit, at aa6580f); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Review of /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events (plan.md, phases/01-event-table-and-tail.md, notes.md) against main at 73801ea. I did not change anything.

Summary: almost every code claim checks out. These all exist and behave as described: `EventSink`, `NoOpSink`, `MemorySink` and `AttemptEvents` in harness_activity/events.py; `AgentEvent` in common/schemas/events.py; `_TASK_LOCK` and `_NO_NEWER_ATTEMPT` in repositories.py:380-384, used by start, assert_current and insert_fenced. `DshRunner` builds its own `AttemptEvents` (dsh/runner.py:360), and workers/main.py:97 passes no sink. `HarnessRunner.run` has no events argument (runner.py:123-133). The openai_agents `_Hooks` emit no events. The spike's transport.py and table.py match D1/D2. The pinned versions are sqlalchemy 2.1.8 and asyncpg 0.32. The project is not a package (`package = false`). Migrations go up to 0004. No Decision contradicts an ADR in force, and ADR-0007's follow-up (Phase 2 events must take the fence) is honoured. I found four Major gaps and eight Nits.

**Major**

M1. Migration 0005 tables have no `retention_class` (plan.md Decisions › D1; notes.md#d1; Phase 01 task 1.1).
- The project rule is that every stored row has a retention class from its first write.
- Evidence: common/persistence/migrations/versions/0003_phase1_tables.py:4 says "Every table has `retention_class NOT NULL` limited to ephemeral, task or audit." 0004 follows the same rule for `usage_ledger` (0004:51-52). common/persistence/retention.py:1-3 says "Every blob and stored row carries one from its first write", and design-decisions.md §4.13 says "every `BlobRef` and stored record carries a retention class from the first write".
- notes.md#d1 lists the columns of `event_logs`, `agent_events` and `event_batches` without it. No task adds the tables to the table list in retention.py (`PHASE1_TABLES` or a Phase 2 counterpart). Phase 3A's event retention, which the plan defers to, depends on this column.

M2. Where the final flush runs relative to the final checkpoint, the fenced finish and the `status` event is not specified, and the plan's "raise Superseded at the final flush" rule breaks two existing contracts (Decisions › D2, D3; notes.md#d2; R5, R8; task 2.1, 2.2).
- Current order in `_run`/`_finish`: `checkpoint(finish)` at activity.py:517, then `assert_current` and artifact upload at :545-555, then the fenced `attempts.finish` at :558.
- D3 says the Activity emits `status` "at turn end". If that event's flush lands after `attempts.finish` commits and a newer attempt starts in between, the flush is refused. The Activity then raises `Superseded` after its finish row and artifacts are already written. That contradicts notes.md#d2 ("the Activity skips its finish writes") and R5 ("ends Superseded and stores no checkpoint").
- On the runner-failure path (`_runner_failed`, activity.py:292-343) and the cancel path, turning a refused final flush into `Superseded` would replace the `RunnerFailure` or `CancelledError`. ADR-0007 says: "When a runner fails, ... the failure still propagates to Temporal."
- The plan should:
  - name the flush point, for example before the final checkpoint, with `status` carrying `result.status`;
  - say that a refusal on a failure or cancel path is only logged;
  - say that the cancel-path flush runs shielded, as `scope.close()` already is at activity.py:416.

M3. A publish that fails for a reason other than a fence refusal has no defined behaviour (Decisions › D2; R1, R8; task 2.1). Examples are a database error, a timeout or a lost reply.
- R1's first scenario ("a batch publish retried after a lost reply ... stored once") assumes the publisher retries with the same batch ID. R8 says "Every event an attempt emitted before it ended is stored".
- Task 2.1 specifies only the flush trigger and the refusal flag. It does not say:
  - whether the background flush retries, how often, and with the same batch ID;
  - whether the buffer is bounded while the database is unavailable;
  - whether a final flush that keeps failing fails the attempt (retryable) or drops the events.
- The R8 test for task 2.1 cannot be written until this is decided.

M4. Publishes are not stated to be serialized per attempt (Decisions › D2; R9; task 2.1).
- notes.md#d2 says "The flush runs in a background task". If a timer flush and a size flush can be in flight together, batch n+1 can commit before batch n. Offsets then stop following `seq`, and R9 ("`reset` before its other events") can fail.
- Batch IDs `<n>` and the R9 ordering both assume one publish in flight at a time, in batch order. The plan never says so, and no Verify step checks that offset order equals `seq` order within an attempt.

**Nits**

- R7 / task 2.1: the cap of 64 events per batch is only implied. "640 events emitted at once → 10 batches" requires each batch to hold at most 64 even when the buffer is larger. State the cap.
- D1 / D2 / task 1.2: the spike interface `publish(workflow_id, batch_id, events)` (spikes/event-transport/event_transport/transport.py:56) carries no task, turn or attempt for the fence, and the in-memory reference does not fence. Say how the fence identity reaches the table transport, for example parsed from `attempt_id` or passed as extra arguments.
- D5 / task 3.1: "stops following when the task ends" does not name the end signal (Temporal describe, as `status` uses at orchestrator/cli.py:135-139, or the `tasks` row). It also does not require a final read up to the latest offset, so the last events are not missed.
- R1: "stored exactly once" is unqualified, but dedup holds only within the 600 s horizon (ADR-0009: "Dedup holds within a re-send horizon ..., not forever"). Qualify R1.
- notes.md Evidence: `harness_activity/dsh/runner.py:238` should be `:237`. Line 237 is `self.sink = sink or NoOpSink()`; line 238 is `relay_port`.
- D1 Rejected: "per-task offsets (not what observers address)". The workflow ID equals the task ID today (orchestrator/cli.py:83, `workflow_id=start.task_id`), so the reason given is misleading.
- Impact / task 2.2: other `HarnessRunner.run` implementations also need the new `events` argument but are not named: the test fakes at tests/integration/test_harness_activity.py:71 and tests/integration/test_dsh_usage.py:84, the call at tests/test_runner_conformance.py:136, and `DshRunner(..., sink)` at tests/integration/test_dsh_activity.py:143.
- Task 2.1: `EventSink.emit` is synchronous, and `AttemptEvents` locks with a `threading.Lock` because emitters may be threads (events.py:40; tests/test_agent_events.py concurrent test). `BatchingPublisher.emit` must schedule its background flush in a loop-safe way. Say so.

**Other checks that passed**
- Task order builds: 1.1, then 1.2, then 1.3, then 2.1, 2.2 and 2.3, then 3.x, then 4.x.
- Every requirement R1-R9 in `delivers` is covered by a task.
- Apart from the R1 qualifier and the R7 cap above, the Given/When/Then scenarios are testable as written.
- The roadmap's batching and history demo item is covered by the messaging plan (phases/03-acceptance.md task 2.1).
- The rollout is correct: `TaskWorkflow` and the `run_harness_turn` input are unchanged, and the migration is additive.

Relevant files:
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/plan.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/notes.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/phases/01-event-table-and-tail.md
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/events.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0003_phase1_tables.py
- /home/geo/develop/praxismesh/common/persistence/retention.py
- /home/geo/develop/praxismesh/spikes/event-transport/event_transport/transport.py
- /home/geo/develop/praxismesh/spikes/event-transport/event_transport/table.py
- /home/geo/develop/praxismesh/docs/adr/0007-fence-harness-attempts-in-one-transaction.md

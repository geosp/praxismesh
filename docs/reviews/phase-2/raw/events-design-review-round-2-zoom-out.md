<!-- Verbatim subagent report (events plan design-review round 2, zoom out, at 910be44); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

I found two Major findings and five Nits. The plan does fix the root cause: today events go to a no-op sink, only DSH emits them, and nothing stores or shows them. Placement fits the codebase. The new `common/events/` package follows ADR-0009's interface, `fence.py` pulls out the existing `_TASK_LOCK` and `_NO_NEWER_ATTEMPT` (common/persistence/repositories.py:380-383), and the DSH `AttemptEvents` is already built inside `run` (harness_activity/dsh/runner.py:360), so passing `events` into `HarnessRunner.run` works for both runners. The lock-order claim in notes.md#d2 holds: every other fenced write takes only the advisory lock and never touches `event_logs`, and prune holds only the row lock. Rollout & rollback is adequate: the migration only adds tables, there is no backfill, `TaskWorkflow` does not change, and rolling back means redeploying the old workers and leaving the tables unused.

## Major

**M1. A batch kept for retry has no fixed contents, so dedup can lose or duplicate events (R1, R9).**
- **Where:** notes.md#d2 (the `BatchingPublisher` bullet), plan Decisions › D2, phase 01 task 2.1.
- **Evidence:** notes.md#d2 says "a database error re-sends the same batch ID with backoff (0.25 s, 0.5 s, 1 s). After the last try the batch stays buffered for the next trigger." Dedup works only by batch ID within 600 s (notes.md#d1; spike `spikes/event-transport/event_transport/table.py:81-88` returns early on a seen ID).
- **What goes wrong:** Suppose the first send committed but its reply was lost, then three re-sends fail. When the next trigger fires, the "buffered" batch may be rebuilt with newer events added up to 64.
  - If the publisher keeps the old ID, the table treats the whole batch as a re-send and silently drops the new events.
  - If it takes a new ID, the already-stored events are stored again at new offsets, which repeats `seq` and makes readers raise the repeated-offset error.
  - A database outage longer than 600 s inside one long attempt also goes past the dedup horizon.
- **Fix:** Pick one of these.
  - Freeze each batch (ID and exact events) until it is acknowledged or refused, and say so in D2 and in task 2.1's tests ("a failed batch is re-sent unchanged at the next trigger").
  - Simpler: dedup on the identity each event already carries. Under the lock, skip events whose `(workflow_id, attempt_id, seq)` is already stored, using a unique index. Dedup then never expires, a rebuilt batch is safe, and `event_batches`, its 600 s horizon and its cleanup go away. This departs from ADR-0009's "batch-ID row" mechanism, so it needs a decision-log line.

**M2. The final flush is tied to the finish checkpoint, which one recovery path never writes (R8, R5).**
- **Where:** plan Decisions › D2 ("The final flush runs shielded, before the finish writes"), phase 01 task 2.2 ("run the flush before the finish checkpoint"), notes.md#d2 ("the success path is: runner returns; emit `status`; `close()`").
- **Evidence:** When the latest checkpoint already holds a finish report, `_run` skips the runner and the finish checkpoint and calls `_finish` directly (harness_activity/activity.py:441-449, "lost after finish_task: go straight to finish"). The normal path flushes nowhere else: it runs `checkpoint(finish)` and then `_finish` (activity.py:505-520).
- **What goes wrong:** An implementer following "runner returns … before the finish checkpoint" puts the flush at line ~517. A retried attempt that recovers this way then writes its outcome without flushing its `reset` or `status`, and never checks the fence through a flush. That is exactly the "lost after finish" retry the demo and R9 exercise.
- **Fix:** State that the final flush runs before `_finish` on every path, or at the start of `_finish`. Add the short-circuit case to task 2.2's Verify list.

## Nits

- Plan Decisions › D3 / notes.md#d2: `status` is emitted and flushed before the finish writes, so a stored `status: done` can belong to an attempt whose finish is then refused or fails (`assert_current` / `attempts.finish`, activity.py:543-571). Readers see an outcome that was never recorded; label it "runner result" or document it in schemas.md.
- Plan Decisions › D5: `tail` stops only when the `tasks` row leaves `running`. A run that ends without `complete_task` (orchestrator/workflow.py:82-83) or is terminated leaves the row `running` forever, so `--follow` never exits. Also, `_NO_NEWER_ATTEMPT` checks only for newer attempts, so a stale attempt can still publish after the task completes, past the final read.
- notes.md#d2, `close()` "~2 s": the bound assumes errors come back fast. Pool checkout, connect and advisory-lock waits are unbounded, and on the failure and cancel paths `close()` runs after `heartbeat.running()` has exited (activity.py:265 runs outside the scope at :397). That can delay cancellation (`WAIT_CANCELLATION_COMPLETED`, workflow.py:127) or hit the heartbeat timeout. Put an overall `asyncio.wait_for` on `close()`.
- Plan Decisions › D4: "advances the retained base to the lowest remaining offset" has no defined value when every event is pruned (`--older-than` covering all of them). Specify `next_offset` for that case.
- Phase 01 task 2.3 / Risks: "database CPU at most double the spike's table runs" compares against numbers taken in another session and setup, with the spike's `spike76` schema and asyncpg pool. To get a valid ratio, run the same load with the fence off in the same session.

Files reviewed:
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/plan.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/phases/01-event-table-and-tail.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/notes.md
- /home/geo/develop/praxismesh/docs/adr/0007-fence-harness-attempts-in-one-transaction.md
- /home/geo/develop/praxismesh/docs/adr/0009-use-a-postgresql-event-table-for-agent-events.md
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/events.py
- /home/geo/develop/praxismesh/harness_activity/dsh/runner.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/spikes/event-transport/event_transport/table.py

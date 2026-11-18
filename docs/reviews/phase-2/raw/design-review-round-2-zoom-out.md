<!-- Verbatim subagent report (design-review round 2, zoom out, at 4c992ea); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Review of /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms (plan files at 4c992ea)

Overall: the plan goes after the real cause. Events go to a no-op sink, only DSH emits them, and a `TaskWorkflow` cannot wait for anything. New logic sits where similar logic already lives: fenced writes reuse `_TASK_LOCK` and `_NO_NEWER_ATTEMPT` in repositories.py, MCP servers follow `sample_mcp`, and the registry handles grants. I found nothing to remove for simplicity. The lock order in D10 and notes.md#d2 holds up: no path takes a task lock while it holds the request lock or the `event_logs` row. Six findings follow.

**F1. Major: the `praxis_comms` role is never created on an existing database, so migration 0006 fails there.**
- Where: plan.md › Rollout & rollback; notes.md › D6 ("Role: `infra/db/init.sh` creates `praxis_comms`"); phases/02 task 1.1.
- What is wrong: the plan creates the role only in init.sh, and init.sh runs only on a fresh volume.
  - /home/geo/develop/praxismesh/infra/db/init.sh:3-6: "Creates PraxisMesh's roles and databases on a fresh `pgdata` volume ... It never runs again on an existing volume".
  - Migrations run as the app role `praxismesh` (init.sh:24), which has no CREATEROLE, so 0006 cannot create the role itself.
  - init.sh:30 also revokes CONNECT from PUBLIC. The new role then needs `GRANT CONNECT ON DATABASE praxismesh`, and neither the plan nor the notes mention it.
- Effect: the "migrate" step in Rollout fails on every existing deployment and dev volume. So does task 1.1's own check ("upgrade and downgrade on a copy of the dev database").
- Rollout needs:
  - a superuser step, run before migrating, that creates the role with its password and grants CONNECT, written so it is safe to run twice;
  - the new password variable in `infra/.env.example`;
  - a downgrade that revokes the grants.

**F2. Major: `claim_inbox` returns message rows into Workflow history, which contradicts R28.**
- Where: notes.md › D7 ("assign pending rows ... return them"); phases/02 task 3.3 ("returns the claimed rows and the next deadline"); plan.md › D7 ("the woken turn's input lists the claimed rows").
- Evidence: R28 says "Events and message bodies never enter Temporal history". A claim of several 16 KB bodies (D6) puts them in an Activity result, which Temporal stores in history.
- Fix: the claim returns only a count or the message IDs, plus the next deadline. The turn Activity then reads the bodies by `(task, claimed_turn)`. That read is also safe to run twice.

**F3. Major: a message accepted for a task that never runs a woken turn is silently lost, so R13 and R15 overclaim.**
- Where: plan.md › R13 ("An accepted message reaches exactly one turn of its recipient"), R15, R24; notes.md › D7 (endings).
- Case 1: messages are claimed only after a `waiting` outcome. Suppose A sends to B while B's turn 1 runs, and B then finishes `done`.
  - The plan only claims after `waiting`; it never claims before ending, and the current `done` path goes straight to `complete_task` (/home/geo/develop/praxismesh/orchestrator/workflow.py:154-157).
  - `cancel_for` (R24) cancels questions only, so the `send` row stays `pending` forever and A was already told it succeeded (R12).
- Case 2: a claim that succeeds but whose turn never runs or fails for good leaves rows `claimed` for a turn that delivered nothing. Examples are `max_wakes` reached, wall time running out, or a failed `run_harness_turn`.
- Fix: make `cancel_for` also close pending and claimed-but-undelivered sends (`cancelled`, with a reason). Either let the sender see that through `get_task_context`, or weaken R13 to "at most one turn, and never after the recipient ends". Add a test for "send to a running task that then finishes `done`".

**F4. Major: cancelling a task while it waits probably skips `complete_task` and `cancel_for`, so the main R24 case fails.**
- Where: plan.md › R24; phases/02 task 3.4 ("`cancel_for` on every ending"); phases/03 task 1.3 ("B is cancelled while A waits").
- Evidence: today a cancellation reaches `complete_task` only because it arrives as an `ActivityError` from the turn (/home/geo/develop/praxismesh/orchestrator/workflow.py:128-148). A cancellation during the new wait instead raises `asyncio.CancelledError` out of the wait on a signal or timer. That is not caught, so the run ends cancelled.
- Effect: `tasks.status` stays `running`, so R25 still accepts sends to B. A's question is not cancelled, so A waits out its 5-minute deadline instead of hearing "B ended without replying". B waiting is the normal state for a responder, so this is the main R24 case, not an edge case.
- Fix: the plan should say the wait handles cancellation and runs `complete_task` (with `cancel_for`) on that path. Test 1.3 should cancel B while B is waiting, not only while B is in a turn.

**F5. Major: a task that ends `waiting` and then times out returns `succeeded` with no artifacts.**
- Where: plan.md › R20, R21, D7; notes.md › D7 (`TaskState` carries "the last summary", nothing else).
- Evidence: outputs are collected only for `done`: /home/geo/develop/praxismesh/harness_activity/activity.py:543 (`if result.status == "done":`). The finish checkpoint is also written only for `done` and `needs_input` (activity.py:508-516).
- Effect: a worker that does its repository work, replies and waits, then times out, completes `succeeded` with `artifacts=[]`. Its workspace files are never delivered.
- Fix: decide whether the idle and wall-time endings collect `outputs` from the newest checkpoint's workspace (for example in an Activity before `complete_task`), or state that they don't. `waiting` also needs its own finish record, so a turn lost after `finish_task("waiting")` does not run the model again.

**F6. Major: R13's "delivered once after a retried sender" holds only with the fake model.**
- Where: plan.md › R13 first scenario; D13 ("a retried attempt repeating a send stores nothing"); phases/03 task 1.3.
- Evidence: the key is "sender task, turn, tool and canonical arguments" (notes.md › D6). Checkpoints are taken in `before_model_call` (activity.py:487-491). A worker killed between a send and the next checkpoint restores to before the model call that produced the send. A real model then usually writes different text, which makes a new key and a second message.
- Effect: the 1.3 test passes only because the fake model is deterministic.
- Fix: narrow R13 to "a repeat with identical arguments", or record the outcome under the call's own ID if DSH journals tool calls (executor.py:117-150 records every call). Say in Assumptions that a regenerated send can arrive twice.

**Nits (one line each)**
- plan.md › D11 and notes.md › D7: the plan never says how `run` takes `TaskState`. It must be an optional second parameter of `run(start)`, or Phase 1 histories fail to replay (R29).
- plan.md › Rollout & rollback: "drain every task started on the new code" doesn't say how to drain waiting tasks, which can idle up to `max_wall_time` (PT1H cap). Cancelling them depends on F4.
- plan.md › R19 and notes.md › D7: "open" should also exclude questions past their deadline that no claim has expired yet. Otherwise `finish_task("done")` is refused for a question already dead.
- notes.md › D1: batch rows are deleted only by a later publish to the same workflow, so each finished workflow keeps its last batch rows. This is harmless but unbounded until Phase 3A.
- plan.md › R25 and D9: a terminated workflow never runs `complete_task`, so its `tasks` row stays `running` and sends to it are accepted. Name this as a known limit.

**Risks section:** each listed mitigation would work as described. The fence-cost threshold sends the plan back to design review, which is a real trigger. Rollout & rollback covers deploy order, draining and the leftover `message_wakes` rows. It is missing the role step (F1), and it does not say that the patch plus drain has to be repeated for any later rollback past Phase 2.

Files:
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/plan.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/notes.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/phases/02-inbox-and-comms.md
- /home/geo/develop/praxismesh/infra/db/init.sh
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py

<!-- Verbatim subagent report (design-review round 1, zoom out, at 3e9df4a); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Review of /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms (plan files at 3e9df4a)

**Root cause (Q1):** The plan fixes the cause. It replaces the no-op sink with the ADR-0009 table, and it makes `TaskWorkflow` able to wait and receive messages. It does not only patch symptoms. The findings below are about correctness gaps in how it does this.

## Major

**M1. The message idempotency key includes the attempt, so a retried sender delivers the message twice (breaks R11).**
- Where: notes.md#d6, "Idempotency key"; phase 02, task 1.2 ("idempotency key from task, turn, attempt and call number").
- Problem: the notes claim the key works "like `sample_mcp`'s `record_order`. A retried attempt that repeats the same call stores nothing new." But `sample_mcp` keys only on task, tool and arguments (`/home/geo/develop/praxismesh/sample_mcp/server.py:39-41`). Attempt 2 of the same turn has a different `PRAXIS_ATTEMPT`, so it gets a different key and a second message is stored. Attempt 1 is not stale at that point; it really sent.
- A second problem: "tool call number" is not something the MCP subprocess is told. It would count calls itself, and that count restarts in every subprocess. Each attempt starts its own (`build_config` runs per `_run`, `/home/geo/develop/praxismesh/harness_activity/activity.py:429`).
- Fix: drop the attempt and call number from the key, or define a key that stays the same across attempts.

**M2. A woken turn will replay the previous turn's `waiting` finish report instead of running.**
- Where: phase 02, task 3.1 (accept `waiting` in both runners and in `TurnOutcome`); D7.
- Problem: `_run` restores the task's newest checkpoint across all turns. If that checkpoint has a finish report, it skips the model and goes straight to finish (`/home/geo/develop/praxismesh/harness_activity/activity.py:434-449`). Finish reports are written for terminal statuses (`activity.py:508-516`).
- If `waiting` gets a finish report (needed so a turn lost after `finish_task` does not rerun), turn N+1 restores turn N's checkpoint and returns `waiting` again without reading its inbox. That loops until the budget runs out.
- If `waiting` gets no finish report, a lost-after-finish attempt reruns the model.
- Also, the restore path always uses `CONTINUE_MESSAGE` as input (`activity.py:450`). The claimed messages have to replace or extend it.
- Fix: the plan must scope the short-circuit to `latest.turn == turn.turn` and say how claimed messages enter the input.

**M3. The Signal is "a hint", but the plan only claims the inbox after a wake, so lost hints can strand messages.**
- Where: D6, D7, D11.
- Plan quotes: "The Signal is a hint" and "On a `waiting` outcome the Workflow waits for an `inbox` Signal … It then runs `claim_inbox`".
- How hints get lost:
  - The D8 protocol makes this the normal case. A asks B, B replies, and the wake reaches A while A is still in its turn, before it calls `finish_task(waiting)`.
  - A Signal handled in a run that then continues as new: `TaskState` carries no pending flag.
  - The dispatcher deletes the wake row once the Signal is accepted, so nothing re-sends it.
- Effect: with an open question, the reply waits until the deadline. With none, the task idles for `idle_timeout` and may complete `succeeded` with a pending message (R16 versus R11/R12).
- Fix:
  - Claim, or count pending rows, before every wait and before idle completion.
  - Keep a "woken" flag that survives across turns.
  - Claim first in a run that started by Continue-As-New.
  - An empty claim should go back to waiting without spending a turn.

**M4. The turn and wall-time budgets conflict with waiting, and the plan does not reconcile them.**
- Where: D7, D11, R9, R16.
- Profiles set `max_turns: 6`, and templates cap it at 10 (`/home/geo/develop/praxismesh/registry/profiles/default.yaml`, `/home/geo/develop/praxismesh/registry/templates/local-dsh.yaml`, `max_turns_cap: 10`). Every wake runs a turn.
- So R9's "task woken 100 times" and D11's "after 40 wakes" cannot happen for a real task.
- A task that ends a turn `waiting` at `turns == max_turns` breaks out of the loop with "turn budget exhausted" and status `failed` (`/home/geo/develop/praxismesh/orchestrator/workflow.py:98-100,93`). Its reply is never delivered.
- When the wall-time deadline (PT30M) fires during a wait, the result is also `failed` (`workflow.py:105-108`), where R16 implies `succeeded`.
- Fix: the plan must say whether wakes count as turns, what status a waiting task gets when a budget runs out (and that `cancel_for` runs then), and the test-only caps used for R9.

**M5. Migration 0005 is split across two phases.**
- Where: phase 01, task 1.1 ("the event part of migration 0005"); phase 02, task 1.1 ("the message part of migration 0005"); "Rollout & rollback".
- Problem: each phase has its own branch and review. If phase 01 merges and any database (dev, CI stack, the demo) runs `upgrade head`, editing 0005 in phase 02 is never applied there. Alembic considers 0005 already done.
- Fix: use 0006 for the inbox tables, or state that 0005 is not applied anywhere until phase 02.

**M6. "Rollout & rollback" misses template-version routing and old-code replay.**
- **Template versions.** The plan says "running tasks keep their template version". But a worker loads exactly one version per template (`/home/geo/develop/praxismesh/registry/loader.py:206`) and refuses other hashes (`/home/geo/develop/praxismesh/harness_activity/activity.py:216-229`). Once `local-dsh`/`local-default` v2 workers replace v1, every in-flight v1 task's next turn is refused until `schedule_to_close` (turn_timeout x 6 = 60 min) and then fails. The plan must either drain v1 tasks or run v1 and v2 workers side by side, and say which.
- **Deploy order inside "workers".** `TurnOutcome.status` is `Literal["done","continue","needs_input"]` (`/home/geo/develop/praxismesh/common/schemas/task.py:75`). An old orchestrator that receives `waiting` from a new harness worker fails to decode it and gets stuck in workflow-task retries. The orchestrator worker must go before the harness workers, and the plan should say so.
- **Rollback.** "tasks already waiting stay waiting until their idle timeout fires on the new code" contradicts the rollback itself: the new code is gone. Old code cannot replay any history that took the patched branch (Signals, timers, `claim_inbox`), nor a run whose input is a `TaskState`. The plan should require draining every task started on new code, not only waiting ones. It should also cover wake rows left behind and tasks on v2 templates, which v1 workers refuse.

**M7. Questions to a task that is finishing or already finished wait out the full deadline.**
- Where: R18, D6, phase 02 task 1.2 (`cancel_for`), task 3.4.
- Problem: `cancel_for` only touches questions that are open when the task ends. Nothing makes `send`/`ask` check the recipient's status under a lock that `cancel_for` also takes. An ask that commits after B's `complete_task` stays pending; the dispatcher "drops and records" the wake for the closed Workflow. A then learns only at the deadline (PT5M) that "no answer came", not that B ended.
- Fix: refuse sends to completed tasks, and serialize that check with `cancel_for`. This also needs a stated lock order for message writes (task lock, then request lock, then recipient). D2 states a lock order for events, but nothing states one for messages.

**M8. Events for one attempt have more than one producer, so `seq` and batch IDs collide.**
- Where: D1, D2, D3, phase 01 task 2.2, `post_status` (D13).
- Problem 1: today the DSH runner builds its own `AttemptEvents` (starting at seq 0) from a sink the worker sets (`/home/geo/develop/praxismesh/harness_activity/dsh/runner.py:360`, `/home/geo/develop/praxismesh/workers/main.py:91`). D3 adds Activity-level `reset`/`status` events. Unless the Activity owns the single per-attempt `AttemptEvents`/`BatchingPublisher` and passes it into `Runner.run` (an interface change in `harness_activity/runner.py` the plan does not mention), one attempt gets two seq sequences, and R8's "first event is reset" is not guaranteed.
- Problem 2: the plan never says where `post_status` writes. If `comms_mcp` publishes to the event table with the same `attempt_id` and its own `<n>` counter, its batch IDs `<workflow>:<attempt_id>:<n>` match the Activity's and are dropped as re-sends (ADR-0009: "a retried publisher that reuses batch IDs has its new events dropped").
- Fix: the plan should name a single owner per attempt, or give `comms_mcp` a separate batch-ID namespace.

**M9. Message bodies in blobs add cost and new failure paths that nothing requires (simplicity and placement).**
- Where: D6 ("body in a blob, `task` retention"); Assumptions ("message body at most 16 KB").
- Problem: R9 only needs bodies kept out of Temporal history, and a text or jsonb column in `agent_messages` does that. Putting bodies in the blob store means:
  - `comms_mcp`, an agent-facing subprocess, needs S3 credentials as well as app-database credentials;
  - every send does an upload outside the fenced transaction, which orphans blobs on refused or rejected sends (more of the ADR-0007 orphan problem, deferred to issue #74);
  - every delivery does an extra fetch.
- Separately, the plan never says how `comms_mcp` gets app-database access. Today only `PRAXIS_TASK_ID` and template-granted `secret_env` reach MCP servers (`/home/geo/develop/praxismesh/harness_activity/config.py:47-55`). Design §4.4 asks for "a scoped service/client" (`/home/geo/develop/praxismesh/docs/roadmap/design-decisions.md:34`). Passing the full app DSN that way needs to be stated, or replaced with a scoped role.

**M10. The Risks mitigation for "asks but does not call `waiting`" does not work.**
- Where: Risks, bullet 3; D8.
- Plan quote: "the reply is delivered at its next wait". If the turn ends `done` or `needs_input`, there is no next wait: the task completes and the reply is lost. If it ends `continue`, the next turn runs without a claim.
- Fix: a simple rule, such as treating a turn that ends with its own open questions as `waiting`, or having `finish_task` refuse `done` while questions are open. A fake model in tests does not mitigate production behaviour.

## Nits

- Risks bullet 1 and R6: "publish fewer, larger batches" contradicts R6's fixed 64 events / 200 ms. Changing the batching means changing R6, so the plan should say so.
- notes.md#d1: `event_batches` "kept 600 s", but only manual `prune` deletes rows, so the table grows with every batch until Phase 3A. Say so, or delete expired rows during publish.
- D10 and D2: a request lock `hashtext(request_id)` shares the 32-bit key space with task locks `hashtext(task_id)`, so a collision can invert lock order. Use the two-key `pg_advisory_xact_lock(int, int)` with a namespace.
- notes.md#d6 (`expire_due`) and R14: expiry uses the database's `now()`, but the Workflow timer uses Temporal time. Time-skipping tests (phase 02, task 3.3) and clock skew make a timer fire with nothing expired. Pass the Workflow's time to `expire_due`.
- D3 and phase 01 task 2.2: DSH already emits one `token` event per response (`/home/geo/develop/praxismesh/harness_activity/dsh/gateway.py:318-324`). Say the new token emission is for `openai_agents` only, or R5's count doubles.
- Phase 03 task 2.1: the roadmap requires demo evidence in `docs/demos/phase-2.md` (`/home/geo/develop/praxismesh/docs/roadmap/phases/phase-2.md`), but the task names `infra/demo/phase-2.sh` or a walkthrough and omits that file.
- Phase 03 task 1.2: R18 (cancellation) is cited for the worker-kill and Continue-As-New cases, which do not exercise cancellation.
- Phase 02 task 3.4: with more than one orchestrator replica, each runs a dispatcher and duplicates Signals. That is harmless because the Signal is a hint, but say so, or use `FOR UPDATE SKIP LOCKED`.

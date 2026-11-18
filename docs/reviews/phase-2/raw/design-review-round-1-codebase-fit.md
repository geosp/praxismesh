<!-- Verbatim subagent report (design-review round 1, codebase fit, at 3e9df4a); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Review of /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms (plan at 3e9df4a, code identical to main)

I checked every path and symbol the notes name. Most hold: `EventSink`/`NoOpSink`/`MemorySink`/`AttemptEvents`, `_TASK_LOCK`/`_NO_NEWER_ATTEMPT`/`FenceRejected`, the `TurnOutcome` statuses, `MCP_CALL_TIMEOUT_S = 120`, the bridge's 150 s timeout, the new `request_id` minted on every submit, the DSH gateway's token events, the time-skipping tests, `package = false`, and the docs paths. No Decision contradicts an ADR in force (0002, 0003, 0005-0009). The batch-ID format, the fence, the reader rule and the open items all match ADR-0009, and comms writes are fenced as ADR-0007 requires. The findings below are about gaps and internal contradictions.

## Major

**M1 · The idempotency key includes the attempt, which breaks R11's "delivered exactly once"**
- Where: notes.md#d6 and phase 02 task 1.2.
- What: the notes define the key as "sha256 of sender task, turn, attempt, tool call number and the canonical arguments, like `sample_mcp`'s `record_order`", then claim "A retried attempt that repeats the same call stores nothing new." Task 1.2 also says "idempotency key from task, turn, attempt and call number".
- Why it fails: with the attempt in the key, attempt 2 hashes differently from attempt 1. Attempt 2 restores from the checkpoint taken before the model call (`harness_activity/activity.py:483-489`), repeats the send and stores a second message. Phase 03 task 1.2's "worker killed after a send … delivered once" would fail.
- Evidence: `sample_mcp/server.py:37-39` keys on task, tool and arguments only, with no attempt, precisely so that retries dedupe.

**M2 · Migration 0005 is split across two phases**
- Where: phase 01 task 1.1 ("Add the event part of migration 0005") and phase 02 task 1.1 ("Add the message part of migration 0005").
- What: each phase has its own `branch`/`base` in its frontmatter and its own review. If phase 01 merges and a database runs `alembic upgrade head`, phase 02 then has to edit a migration that was already applied. Databases already at 0005 never get `agent_messages` or `message_wakes`.
- Fix: add messages as 0006, or state that both phases ship as one migration before either merges.

**M3 · D5's `task submit --request REQ` collides with an existing flag, and no task implements it**
- Where: Decisions › D5.
- Collision: `orchestrator/cli.py:186` already defines `--request` as "submit this JSON request file instead of the flags", and `cli.py:58-60` reads it as a file path.
- Missing work: `TaskRequest` has no `request_id`, and `prepare_task` always mints a new one (`orchestrator/submit.py:46`). No task in any phase changes either; phase 02 task 4.1 only documents "submit into a request". Phase 03 needs this join to build two tasks in one request.
- Also worth saying: R10 rests on request scope, so letting a client name its request is a scoping decision, not just a flag.

**M4 · Turn budgets make D11's 40-wake Continue-As-New and R9's scenario unreachable**
- Where: Decisions › D11 ("after 40 wakes"), R9 ("a task woken 100 times"), phase 02 task 3.3 ("100 wakes under 2,000 events per run"), phase 03 task 1.2.
- What: every wake runs a turn, and the Workflow stops at `turns >= resolved.max_turns` (`orchestrator/workflow.py:94-96`). That limit is `min(profile.max_turns, t.max_turns_cap)` (`orchestrator/activities.py:83`), which is 6 for every profile (`registry/profiles/*.yaml`) and capped at 10 by both templates (`max_turns_cap: 10`).
- Result: a real task fails with "turn budget exhausted" long before its 40th wake. Continue-As-New never happens in production, and phase 03 task 1.2's "continues as new while waiting" cannot pass on the Compose stack with the shipped registry.
- The plan needs to say one of three things: whether wakes count against `max_turns`, whether the v2 templates raise the caps, or what test registry and threshold the acceptance tests use.

**M5 · The wait loop has no source for question deadlines or for messages that arrived before the wait**
- Where: D7, D11, notes.md#d6 ("The Workflow's wait timer is the minimum of: the earliest deadline of its own open questions…").
- Deadlines: questions are created inside the Activity by `comms_mcp`, and the Workflow sees only `TurnOutcome` (`common/schemas/task.py:73-89`), which carries no deadlines. Phase 02 task 3.1 adds only the `waiting` status.
- Early messages: an `inbox` Signal that lands while a turn runs (D8: "a reply that arrives while the asker still runs") must be remembered. Otherwise the Workflow sleeps until the deadline or the idle timeout.
- Across Continue-As-New, which D11 places "before each wait": a flag the old run set is lost unless `TaskState` carries it, or unless the new run claims before it waits.
- Needed: specify that the wait starts with an inbox or deadline check (an Activity or `TurnOutcome` fields), and add those fields to tasks 3.1 and 3.3.

**M6 · The restore path skips the model on the turn after a `waiting` turn, and the turn input path is unspecified**
- Where: phase 02 tasks 3.1 and 3.2.
- Short-circuit: `_run` restores the task-wide latest checkpoint and, `if latest.finish is not None`, returns that finish without running the model (`harness_activity/activity.py:441-452`). It does not check `latest.turn == turn.turn`. Today `finish` is written only for terminal statuses (`activity.py:508-516`), so this is harmless.
- Effect: if `waiting` is recorded in `finish` (which it should be, so a lost attempt after `finish_task` does not rerun the model), the next turn immediately returns `waiting` again, never sees its messages, and loops.
- Input: otherwise the next turn's input is the fixed `CONTINUE_MESSAGE` (`activity.py:453`). No task says how claimed messages reach that input (for example, the Activity reading `claimed_turn = turn`).

**M7 · Assumption: "the fake model can script two agents" is false today**
- Where: Assumptions, bullet 3.
- What: `tests/support/fake_model/__init__.py:67-70` serves one script, and picks the step by how many tool-calling responses the history holds. Two tasks on `tpl.local-dsh` share one endpoint and would replay the same steps.
- Also: a static script cannot supply the dynamic correlation ID that `send_to_agent(reply_to=ID)` needs.
- No task extends the fake model, yet phase 03 tasks 1.1 and 1.2 depend on it.

**M8 · The runner interface has no way to receive the per-attempt publisher**
- Where: D3 and phase 01 task 2.2 ("Wire it into `run_harness_turn` for both runners").
- What: `HarnessRunner.run` takes no events argument (`harness_activity/runner.py:123-134`). `DshRunner` builds its own `AttemptEvents` from a per-worker `self.sink` (`harness_activity/dsh/runner.py:238` and `:360-362`).
- Effect: if the Activity emits `reset` and `status` through a second `AttemptEvents`, one attempt gets two `seq` counters, both starting at 0. That contradicts D1's "`seq` stays per attempt".
- A per-attempt `BatchingPublisher` cannot be injected into a per-worker runner without an interface change, which the plan does not name.

**M9 · `post_status` has no defined target**
- Where: D13 and phase 02 task 2.1.
- What: no Decision or requirement says what `post_status` writes. If it publishes an `AgentEvent` from the `comms_mcp` subprocess, it becomes a second publisher for the same attempt. It would have its own `seq` and its own batch counter `n`.
- Effect: a batch named `<workflow>:<attempt_id>:<n>` that matches one of the Activity's is dropped as a re-send, because dedup runs on the batch ID (`spikes/event-transport/event_transport/table.py:80-88`).

**M10 · The rollout claims running tasks keep their template, but v2 workers refuse v1 turns**
- Where: Rollout & rollback.
- What: the plan says "New template versions start new tasks only; running tasks keep their template version."
- Why that is not enough: a worker loads one version per template name (`registry/loader.py:198`). It refuses a turn whose hash differs (`activity.py:215-225`), and such a turn fails after `schedule_to_close`, 60 min for `local-dsh` (`docs/operations/runbook.md:102-117`).
- Needed: the deploy order must drain v1 tasks or keep v1 workers running; "migrate, then workers" alone breaks in-flight tasks.

## Nits

- notes.md Evidence, bullet 1: "`workers/main.py` gives it `NoOpSink`" is wrong; `DshRunner` defaults to `NoOpSink` itself (`dsh/runner.py:238`), and `workers/main.py:96` passes no sink.
- notes.md Evidence and D12/task 3.3 (reuse): a `TaskWorkflow` replay test and its Phase 1 fixture already exist (`tests/test_task_workflow.py:228-233`, `tests/fixtures/task_workflow_history.json`); extend them rather than following `test_hello_replay.py`.
- D11: a continued run must skip `record_task`, because `TaskRepository.record_task` raises `TaskAlreadyExists` when the run ID differs (`common/persistence/repositories.py:80-81`). Say so explicitly.
- Phase 03 task 1.2: R18 (cancellation) is cited for the worker-kill case and the Continue-As-New case, which test R11 and R9.
- Phase 01 task 1.2: the suite runs "against … the in-memory reference", but the port list omits `spikes/event-transport/event_transport/memory.py`.
- Phase 03 task 2.1: the roadmap requires demo evidence in `docs/demos/phase-2.md` (`docs/roadmap/phases/phase-2.md`, last checklist item); no task produces it.
- Phase 02 task 1.2 (R15): `expire_due` runs only inside the asker's `claim_inbox`, so `reply` must compare the deadline itself, not only the status. Otherwise a late reply before the asker's claim is accepted.
- Phase 02 task 1.2 (R18): `cancel_for` must write wake rows for the waiting askers; otherwise they sleep until their deadline. The plan does not say it does.
- R11 and D6: nothing says what happens to pending (non-question) messages to a recipient that completes `done`. R11 promises delivery.
- D10: the order of the request lock and the task fence lock inside an ask is unstated. Both use single-key `hashtext`, so request and task locks share one namespace; the two-key `pg_advisory_xact_lock(int, int)` form would separate them.
- Rollback: old Workflow code cannot replay histories with the `phase2-wait` marker or a `TaskState` Continue-As-New input. Drain every task the new code touched, not only waiting ones.
- Phase 02 task 3.1: `AttemptOutcome` (`common/schemas/task.py:110-112`) and `RunResult.status` (`harness_activity/runner.py:53`) also need `waiting`, since `attempts.finish` writes `result.status`.

Files: the review covered /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/plan.md, its three phase files under /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/phases/, and /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/notes.md. The code cited above:
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/orchestrator/cli.py
- /home/geo/develop/praxismesh/orchestrator/submit.py
- /home/geo/develop/praxismesh/sample_mcp/server.py
- /home/geo/develop/praxismesh/tests/support/fake_model/__init__.py
- /home/geo/develop/praxismesh/harness_activity/dsh/runner.py
- /home/geo/develop/praxismesh/harness_activity/runner.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/registry/profiles/
- /home/geo/develop/praxismesh/registry/templates/

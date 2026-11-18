<!-- Verbatim subagent report (design-review round 2, fresh reader, at 4c992ea); reviewers: fresh-subagent (design-reader); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Report on /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/plan.md (I read all 400 lines and opened no other file.)

## Pass 1

### From the Summary
The change makes agents observable and lets them talk to each other. Each harness attempt writes its events in batches to a PostgreSQL table, and `agentctl tail` follows a task live, can resume from an offset, and reports events that were pruned. A new stdio MCP server, `comms_mcp`, lets an agent send messages to, or ask questions of, other tasks in the same request. Messages are stored in the database, and a dispatcher wakes the recipient's workflow with a Temporal Signal. A turn can end "waiting", which means the workflow sleeps until a message, a deadline, an idle timeout or its wall-time budget, and it uses Continue-As-New while it waits. Woken turns have their own budget. The main risks are the cost of taking the fence lock on every event batch, and a model that asks a question but never waits. Rollout and rollback also both need tasks to be drained first.

## Pass 2

### 1. From the whole plan
Phase 2 replaces today's no-op event sink with a durable event log. Each workflow has gap-free offsets, publishes are fenced against superseded attempts, and payloads hold no model text. A CLI wrapper (`agentctl`) can tail and prune this log. Phase 2 also adds messaging between tasks in the same request: a durable inbox, wake rows that a dispatcher turns into Signals, and a `claim_inbox` Activity that hands messages to exactly one turn. `TaskWorkflow` gains a `waiting` state with timers, its own wake budget, Continue-As-New, and a Phase-1-compatible patch. The goals are to deliver Roadmap Phase 2 and to settle the items ADR-0009 left open. Questions get strict semantics: ask-then-wait, deadlines, refusing late replies, refusing cycles, and cancelling questions when a task ends.

### 2. How the existing system works, per this plan
Events go to a no-op sink. Only the DSH runner emits them, and nothing stores or displays them. A `TaskWorkflow` resolves its capabilities, runs turns as Activity attempts that restore checkpoints, and ends when its turns finish, so it cannot receive messages or wait for them. Every attempt write is guarded by ADR-0007's per-task advisory-lock fence. There is a CLI (`orchestrator.cli`) with `task submit --request <file>`. A worker serves one template version, and there is a `sample_mcp` stdio server to use as a model. `finish_task` already has statuses including `done` and `needs_input`.

### 3. Summary vs plan
- Major (Summary vs R4/R5/D2): The Summary leaves out that a refused event publish now ends the attempt with `Superseded` at its next model call or final flush. This is a new way for attempts to end, not just a detail of event storage.
- Major (Summary vs R23-R25, D10): The Summary leaves out cycle refusal, the cascade when a task ends (its questions are cancelled and its waiters are woken), and refusal of messages to tasks that have ended. These rules decide whether waiting tasks can ever hang.
- Nit (Summary vs R19): The Summary says `finish_task` refuses `done`, but R19 also refuses `needs_input`.
- Nit (Summary vs R21): The Summary doesn't say that running out of wall time gives `failed` when questions are open and `succeeded` when none are.
- Nit (Summary vs R6/D3): "Events" doesn't make clear that payloads never carry model text, only counts (an owner decision).
- Nit (Summary vs Risks): The fence-lock risk doesn't give the 250 ms p95 threshold that would send the plan back to design review.
- Nit (Summary "R1-R8"): R9 (the `reset` event) is also part of the event work but isn't cited.
- Nit (Summary vs Rollout): The rollback steps leave out deleting leftover `message_wakes` rows.
- Nit (Summary vs D13): The Summary doesn't mention the new restricted `praxis_comms` database role.

### 4. Sections I couldn't paraphrase
No Blockers. I could paraphrase every section, although D1 ("on the app engine") and D7 (the `woken` flag) were only partly clear. Both are listed below.

### 5. Terms used but never explained
- Major (throughout, D13/D14/Rollout): "profile", "template", "template version", "registry" and "test registry" are never defined, but budgets, grants and the drain argument depend on them. One example is "a worker serves one template version and refuses others".
- Nit (D1): "the app engine". This is presumably the SQLAlchemy engine or app DB role, but that isn't stated.
- Nit (D2): `AttemptEvents`, `BatchingPublisher` and "the counter row" are named but not described. The tables `event_logs` and `event_batches` appear only in Impact, without their roles.
- Nit (D10): `cancel_for` is never explained.
- Nit (D10): "request lock" and "a two-key advisory lock in its own namespace" don't say what the two keys are.
- Nit (D11): `record_task` is never explained.
- Nit (D14): `max_wakes_cap` is a template field that is introduced in passing.
- Nit (D15): "fixed stage name" doesn't say which set of stages. "The Activity's tool-call hook" isn't defined, though `before_model_call` is.
- Nit (R19/D8): `needs_input` is an existing status but isn't explained.
- Nit (R21/R20): "wall-time budget" and "idle timeout" are not in Terms (`idle_timeout` appears only as a profile field).
- Nit (D13): `local-dsh` and `local-default` templates and `sample_mcp` are named without saying what they are.
- Nit (Assumptions/Risks): "phase 01 task 2.3" points to a task list that isn't in this file.
- Nit (R16/D8): "correlation ID" is not in Terms. It is only inferable from D8.
- Nit (D8): The DSH 150 s tool-call timeout is stated as a fact without a source.

### 6. Places where the parts don't connect
- Major (Rollout & rollback vs R29/D12): Rollout drains all running tasks before the switch. Yet R29 and D12 patch the Workflow so that in-flight Phase 1 histories replay. The plan doesn't say why both are needed. Either the drain makes the patch unnecessary, or the patch exists for a case the drain doesn't cover (for example, waiting or long-running tasks), and that case should be named.
- Major (R24/D10): There's no mechanism for what happens when a task ends. The plan doesn't say who calls `cancel_for` when a task is cancelled, fails or completes from outside `comms_mcp`, or which Activity or role does it (`praxis_comms` only covers comms). It also doesn't say how waiters are woken (wake rows? the dispatcher?). Impact lists no such Activity.
- Major (D7/D11): A Signal "sets a `woken` flag", and `TaskState` carries it, but the plan never says what the flag changes. Claims read the database, so the flag's role in R15 (claim before sleeping) is unclear.
- Major (D6): The plan doesn't say what the dispatcher does when the Signal fails, for example because the workflow has completed or the ID is unknown. Its only rule is "deletes a row once the Signal is accepted", so such rows may pile up. Rollback's "delete leftover `message_wakes` rows" hints at the problem but doesn't solve it.
- Major (D9/D13/R27): Fencing comms writes depends on `PRAXIS_TURN` and `PRAXIS_ATTEMPT` being right for each attempt. The plan never says that `comms_mcp` is spawned per attempt, or how the worker sets these variables for both runners.
- Nit (D15 vs D3): `post_status` relies on "the Activity's tool-call hook" for both runners, but D3 only describes hooks for `openai_agents`. It doesn't say how the DSH path sees `comms_mcp` tool results.
- Nit (D2 vs Terms "Fence"): The fence covers "no newer turn or attempt", but D2 and R4 check only "a newer attempt".
- Nit (R17/R18 vs D7): Expiry uses "the Workflow's time" during claims, while R18 refuses replies "after its deadline", presumably by the database clock. The plan doesn't say how the two clocks agree near a deadline.
- Nit (D1 vs R1): Batch dedupe rows are deleted after 600 s, but the plan doesn't say why 600 s is longer than any retry gap.
- Nit (D10/R23): A cycle check is required "directly or through others", but no algorithm or data source is given.
- Nit (D13/Assumptions): The plan doesn't say what an identical repeated `ask_agent` in one turn returns. Presumably it's the same correlation ID.
- Nit (Phases/Decision log): Phase task details live elsewhere, and the decision log is empty even though the front matter says design-review round 1 requested changes.

### 7. Readability
- Nit (Summary): "A turn may end `waiting`: the Workflow then checks ... while it waits (D7, D11)." This is about 38 words with five triggers and two actions. I had to reread it.
- Nit (Why, last sentence): "seven behaviour questions" are listed with D7 and D8 counted twice ("D7, D8 ... and the budget and refusal rules in D7 and D8"), so you can't count to seven.
- Nit (D7): "A non-empty claim starts ... then claims again." This is over 40 words and has several clauses.
- Nit (Rollout & rollback): The rollback sentence is about 40 words with a nested parenthetical.
- Nit (D1): "on the app engine". I had to reread it.
- Nit (D7, D8): The terse rejections "(owner)" and "a fresh task per message (owner)" took a reread.
- Nit (Assumptions vs D8/D14): The defaults (PT5M, `max_wakes` 50) are stated twice.
- Nit (Assumptions vs D13): "Two identical sends in one turn are one message" restates D13's idempotency key as an assumption.
- Nit (Terms vs R3): The reader rule appears in both places in different words.
- Nit (R5): Two rules in one requirement: end `Superseded` at a given point, and write nothing more.
- Nit (R6): Two rules: no model text, and token events carry counts.
- Nit (R18): Three refusal conditions in one requirement.
- Nit (R21): Two outcomes in one requirement.
- Nit (R24): Three rules in one requirement: cancel its own questions, cancel questions to it, wake the waiters.
- Nit (R28): Two rules: nothing enters history, and the 2,000-event cap.
- Nit (D8): The `wait?` parameter name is easy to confuse with the `waiting` status.

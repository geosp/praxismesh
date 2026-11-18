<!-- Verbatim subagent report (design-review round 1, fresh reader, attempt 2, at 3e9df4a); reviewers: fresh-subagent (design-reader); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

I read /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/plan.md all the way through (316 lines). I opened no other file.

## Pass 1

### From the Summary
Phase 2 makes agents observable and lets them message each other. Each harness attempt writes its events in batches to a PostgreSQL table, under the same per-attempt fence as other writes, and `agentctl tail` follows a task live, can resume from an offset, and reports when older events have been pruned. A new stdio MCP server, `comms_mcp`, lets an agent post status, send a message, or ask a question of another task in the same request. Messages are stored durably and a dispatcher wakes the recipient's Workflow with a Signal. A turn can now end in a "waiting" state, where the Workflow sleeps until a message, a question deadline or an idle timeout, and uses Continue-As-New to keep history bounded. The main risks are the cost of taking the fence lock on every event batch, and a local model that asks a question but does not then end its turn as waiting.

## Pass 2

### From the whole plan
The plan replaces the no-op event sink with a fenced, batched publisher. It writes to a PostgreSQL table that the event-transport spike chose. Offsets are per workflow ID and have no gaps, and the reader rule guarantees a reader either gets events without gaps or is told they expired. It adds `agentctl` (a wrapper around the existing CLI) with `tail`, `events prune` and `task submit --request`. It adds `comms_mcp` for request-scoped messaging and questions, and the identity it acts as comes from the worker. The plan's main addition is that `TaskWorkflow` gains a waiting state: a durable inbox plus wake rows, a dispatcher that turns wake rows into Signals, a `claim_inbox` Activity, deadlines, idle timeouts, a cycle check and Continue-As-New. All of this sits behind a Workflow patch so Phase 1 histories still replay. The reason given is that roadmap Phase 2 is next: events are currently invisible, and agents cannot receive or wait for messages.

### How the existing system works, per this plan
`AgentEvent`s go to a no-op sink in `harness_activity/events.py`, and only the DSH runner emits them. Nothing stores or shows them. A `TaskWorkflow` runs turns through the `run_harness_turn` Activity, each turn runs as one or more Temporal attempts, and the Workflow ends when its turns finish. Each attempt's writes are fenced by a per-task advisory lock (ADR-0007), so a superseded attempt cannot write. There is an existing CLI (`orchestrator.cli`), a registry of MCP servers and templates (`sample_mcp`, templates `local-dsh` v1 and `local-default` v1 by implication), profiles, checkpoints that turns restore from, and a blob store. There is one tenant, and nothing yet creates multi-task requests.

### Summary vs plan
- Major, Summary vs D8: "Asking ends the asker's turn" reads as something the system enforces. Per D8, `ask_agent` only stores the question, and the system prompt asks the agent to call `finish_task(status="waiting")`. The turn ends only if the model complies. The risk line hints at this, but the mechanism sentence states it as fact.
- Major, Summary vs Rollout & rollback: the Summary leaves out that rollback requires draining waiting tasks first. That is the main operational constraint of this change.
- Major, Summary vs D5 / Non-goals: the Summary says tasks "of the same request" can talk, but not how two tasks come to share a request. That only happens through the new `task submit --request` CLI flag, because there is no planner. A reader of the Summary alone would not know how a multi-agent setup is formed.
- Nit, Summary: it leaves out what happens after the idle timeout: the task completes as `succeeded` (R16).
- Nit, Summary: it does not mention cycle refusal (R17/D10), cancellation propagation (R18) or late-reply refusal (R15).
- Nit, Summary: it lists the wait triggers as message, question deadline and idle timeout. D7 also has the wall-time deadline, and waits count against the wall-time budget.
- Nit, Summary: "(R1-R9)" is attached to tail and expiry, but R9 is about Temporal history and Continue-As-New, not events.
- Nit, Summary: "(R10, R19)" is cited for request scoping, but R19 is about identity and fencing.

### Sections I couldn't paraphrase (Blockers)
None. Every section could be paraphrased. The gaps below are about missing mechanisms, not unreadable sections.

### Terms used but never explained
- Major, D6: "against §4.4". The section is in an unnamed document, so this rejection reason cannot be checked.
- Major, D2: `before_model_call` is a hook in an unnamed runner or harness. It is unclear how it applies to both runners.
- Major, R8 / D11: "checkpoint" ("the checkpoint it restored from", "Turns restore from checkpoints"). It is central to why no session state is carried, and it is never described.
- Major, D11: `TaskState` and "resolved task". Only a parenthetical list is given; it is unclear what "resolved" means.
- Nit, Why / D8: "DSH" (runner) is never expanded.
- Nit, D3: `openai_agents` runner and its "run hooks".
- Nit, R4 / D2: `Superseded`. Is it an exception or an outcome status?
- Nit, D13: `sample_mcp`, the pattern `comms_mcp` copies.
- Nit, D13: templates `local-dsh` / `local-default` and what "granting" means.
- Nit, D13: `registry/mcp/comms.yaml`.
- Nit, D6: "`task` retention" (a blob retention class).
- Nit, D9: `PRAXIS_*` variables (no names given).
- Nit, D7 / What changes: "profile" and its existing fields.
- Nit, D7: "wall-time deadline / budget".
- Nit, D2: "the counter row", which may be the `event_logs` table from Impact; the two are never tied together.
- Nit, D1: `seq`.
- Nit, D1: "the spike's interface".
- Nit, Assumptions: "phase 01 task 2.3". The task numbering does not match the phase numbering.
- Nit, Why / D3 / D7 / D8 / D9: "owner" is not identified.
- Nit, D5: `infra/.env`.
- Nit, D5: `task submit`, an existing CLI command that is never introduced.

### Where the parts don't connect
- Major, What changes / D13: `post_status` and `get_task_context` have no requirement or decision describing what they do. Relatedly, nothing says how an agent learns the task IDs it can message. Presumably `get_task_context` does this, but the plan never says so.
- Major, R18 (and R15 "cancelled"): no decision gives the mechanism for "when a task ends, its open questions are cancelled and askers waiting on it are told". Which Activity cancels them, and does it write wake rows for the askers? D7 consumes cancelled questions but nothing produces them.
- Major, R12 / D8: delivery is defined only for a waiting task, or for a running task at its next wait. The plan does not say what happens to a message sent to a task that has completed, or to a task that ends `succeeded` without ever waiting again. Are these refused, dropped or stored?
- Major, Rollout & rollback: "tasks already waiting stay waiting until their idle timeout fires on the new code, so drain waiting tasks before rolling back" does not hold together. After rollback the new code is not running. It is unclear whether patched histories would fail on the old workers, or whether the tasks would simply hang. The reason for draining needs stating.
- Major, R6 vs D2: R6 says publish "200 ms after its oldest unpublished event". D2 says "every 200 ms". These are different timers.
- Major, R4 vs D2: R4 says the superseded attempt "ends `Superseded`". D2 only makes it raise at the next `before_model_call`. If no model call follows, for example a refused end-of-attempt flush or a long tool call, it is not stated how or when the attempt stops.
- Nit, D11 vs R9: "40 wakes" has no stated link to the 2,000-event limit, such as history events per wake.
- Nit, Assumptions vs Risks: the publish lock is assumed to cost "under 20 ms", while the risk trigger is "p95 publish exceeds 250 ms". The gap between the two thresholds is not explained.
- Nit, D6: the dispatcher `LISTEN`s, but nothing says who issues the `NOTIFY`.
- Nit, D9: refusals are stored as "`rejected` rows" without naming the table (`agent_messages`?).
- Nit, D7: it is not stated what happens when the wall-time deadline fires during a wait (fail? complete?).
- Nit, Assumptions: "question deadline PT5M" is presumably the default when `wait` is omitted from `ask_agent`, but D8 does not say `wait` is optional.
- Nit, D2 / Risks: several rationales point to notes.md#d1, #d2 and #d6. The decisions read on their own, but the deadlock-ordering claim in D2 depends on "the same order as every fenced write", which is not shown here.

### Readability
- Nit, Summary lines 15-17: a roughly 37-word sentence joins two unrelated clauses with different subjects (publish; tail). I had to reread it.
- Nit, D6 Rejected: "(a worker subprocess with a Temporal client, against §4.4)". I had to reread it, and the reference is opaque.
- Nit, D7: "It then runs `claim_inbox`, which assigns ... to the next turn, once (keyed by task and turn), and the turn's input lists them". I had to reread it.
- Nit, Rollout & rollback: the rollback sentence. I had to reread it, and it contradicts itself (see above).
- Nit, Terms "Reader rule": two rules (before-read and during-read) in one definition.
- Nit, R4: two rules (refuse the batch; stop the attempt).
- Nit, R9: two rules (no events or bodies in history; Continue-As-New before 2,000 events).
- Nit, R10: two rules (refuse; record the refusal).
- Nit, R11: two rules (store before ack; deliver exactly once).
- Nit, R18: two rules (cancel open questions; notify askers).
- Nit, R19: two rules (identity from the worker; fenced writes).
- Nit, D5: `tail` behaviour and `task submit --request` are bundled in one decision.
- Nit, D9 / D13 / R19: the same fact (identity comes from the worker as task, turn and attempt, and writes are fenced) is stated three times.
- Nit, R10 / D9: request scoping and stored refusals are stated twice.
- Nit, R16: "~60 s" gives no tolerance for a testable criterion.

If you want this report saved somewhere, that is your call; I haven't written it to any file.

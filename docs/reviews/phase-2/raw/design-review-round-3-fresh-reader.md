<!-- Verbatim subagent report (messaging plan design-review round 3, fresh reader, at 88ea037); reviewers: fresh-subagent (design-reader); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Report on /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/plan.md. I read the whole file (347 lines) and opened nothing else.

## From the Summary

The change lets agents (tasks) in the same request send messages and ask questions through a new stdio MCP server, `comms_mcp`. A new `task submit --join` option lets a task join an existing request. Messages are stored durably in PostgreSQL, and a dispatcher turns them into Temporal Signals that wake a task. A turn can end in a "waiting" state: the task sleeps until a message arrives, a question's deadline passes, it has been idle too long or it runs out of wall time. When a task ends, its questions are closed and its waiters are woken. The Summary names three risks: a model that rewrites a send after a crash causes a duplicate delivery; waiting tasks must be drained before workers are switched; and the new database role needs a superuser to create it.

## From the whole plan

This is the messaging half of roadmap Phase 2; the events half was merged in PR #85. It adds four things:
- **`comms_mcp`**: tools to send, ask, post a status and read context. Each tool is fenced to its own attempt and gets its identity from the worker.
- **Storage**: the `task_messages` and `message_wakes` tables, plus a narrowly scoped `praxis_comms` role.
- **A dispatcher**: it uses LISTEN and polling to turn wake rows into `inbox` Signals.
- **A patched `TaskWorkflow`**: after a `waiting` turn it claims its inbox, sleeps, wakes, counts woken turns against a separate `max_wakes` budget, and continues as new to keep history bounded.

The goal is to deliver the Phase 2 roadmap items: durable inbox, correlated replies, idle wake-up, timeouts and cycle protection. The owner's decisions fix the behaviour: asking ends the asker's turn, messages stay inside a request, and a task cannot finish while it has open questions.

## How the existing system works, per this plan

A `TaskWorkflow` runs one task as a series of turns (Activity `run_harness_turn`), and each turn may be retried as several Temporal attempts. Every attempt's writes are guarded by the per-task fence from ADR-0007. At start, `resolve_capabilities` fixes the task's template, limits and queue. Each worker serves exactly one version of each template. The runner is either DSH or `openai_agents`. A turn ends with `finish_task`, which today offers at least `done` and `needs_input`, and its checkpoint stores the finish report. Today the Workflow ends when its turns finish, so a task cannot receive or wait for a message, and every `task submit` starts a new request. Events (the event table, the publisher and `agentctl tail`) already exist from the events plan. A recorded Phase 1 history is replayed in a test.

## Summary vs plan

- **Major (Summary / Risks).** The Summary's "Risks" line does not match the Risks section. Risks lists dispatcher downtime, a model that ignores the ask-then-wait instruction, and many waiting tasks; the Summary mentions none of them. The duplicate-send risk the Summary does name is sourced to Assumptions, which presents it as accepted behaviour, not as a risk.
- **Major (Summary vs R21/R31).** The Summary says a waiting task sleeps "until ... its wall-time budget". It never says how the task then ends: `succeeded` with no open question (R21), `failed` with one (R31). These are owner decisions and change the result the user sees.
- **Major (Summary vs Rollout).** The Summary leaves out that rollback also needs a drain, because the old code cannot replay new histories, and that leftover `message_wakes` rows must be deleted.
- **Nit (Summary vs R30/D17).** The Summary says "messages it never took are marked undelivered", but R30 also covers "claimed-but-unread" messages, which a task has taken.
- **Nit (Summary).** It leaves out deduplication of identical repeated sends (R13) and treats fencing and worker-supplied identity (R26/R27) only as "(fenced)" in the diagram.
- **Nit (Summary).** It does not mention `post_status` or `get_task_context` (D15), or that undelivered messages are reported back to senders.
- **Nit (Summary).** "D11, D14" are cited in the reverse order of the clause they support.

## Sections I couldn't paraphrase (Blockers)

None of the prose sections are unparaphrasable. The closest is **Phases**: it gives only titles and task counts ("0/15", "0/7"), with no task content, and it starts at "02" without saying where phase 01 is. I rate it Major under item 6, not Blocker, but a reader cannot follow the work plan from this file alone.

## Unexplained project-specific terms

- **Major.** `complete_task` (D17, Impact) is central to R24/R30, but it is not in Terms. The plan never says whether it is an Activity or what it did before this change.
- **Major.** The "wall-time budget" / "wall-time deadline" (D7, R21, R31) is never explained: where it is set, or whether it runs from task start or across Continue-As-New. `TaskState` "deadline" suggests the latter but does not say so.
- **Nit.** `max_turns` is never defined as an existing profile limit.
- **Nit.** The `needs_input` finish status (R19) is never explained.
- **Nit.** `record_task` (D11) is unexplained.
- **Nit.** The `tasks` and `task_attempts` tables (D13) are unexplained.
- **Nit.** The "app role" (D13) is unexplained.
- **Nit.** "Orchestrator worker" vs "harness workers" (D6, Rollout) is not in Terms.
- **Nit.** "Publisher", "attempt's publisher" and "tool-event paths" (D15) are inherited from the events plan and not explained.
- **Nit.** "v2 templates" (Rollout) is not tied to "new template versions grant `comms`" (What changes).
- **Nit.** The "request lock ... in its own namespace" (D10) does not say what the namespace is.
- **Nit.** "Canonical arguments" (D13) does not say how arguments are made canonical.
- **Nit.** "Fake model" (D16) is not defined; it is presumably a test model endpoint.
- **Nit.** Which CLI owns `task submit` (D5) is unclear, since `agentctl` is also named.
- **Nit.** "DSH calls time out at 150 s" (D8) is a fact without context.
- **Nit.** "Phase 3A" and "Phase 4 gateway" (Non-goals, Assumptions) are unexplained.
- **Nit.** The ID numbering starts at R10 and D5, and the plan never says R1-R9 and D1-D4 live in the events plan.

## Disconnects

- **Major (R23).** The rule text points the wrong way. It refuses a question "whose recipient is waiting ... on a question from the asker". In the example, the recipient (A) is waiting on a question *to* the asker (B). As written, the rule would not catch its own example.
- **Major (R17 / D7).** The plan has no mechanism for expiry. D7's claim returns row IDs, a count and the next deadline, and only "a count above zero" starts a woken turn. Nothing says who marks a question expired, or how an expiry becomes a claimable row so that the asker's next turn "is told so".
- **Major (R30 / D17).** "Claimed-but-unread" needs a read marker, and none is described. D7 only says the Activity reads bodies by task and turn.
- **Major (R22 / D14).** The plan never says what happens when `max_wakes` runs out (does the task fail or succeed, and with what message?). It also never says how `max_wakes_cap` relates to `max_wakes` (clamp or reject?) or what its default is.
- **Major (R33 / D11).** Continue-As-New happens only "before sleeping". A task that receives messages fast enough that every claim returns rows never sleeps, so its history is not bounded by this mechanism.
- **Major (R20).** The plan never says when the idle timeout starts: from the last turn, or from each wake.
- **Major (Rollout).** The forward rollout says to "cancel waiting ones with `temporal workflow cancel`". Before deployment no task can be `waiting`, because that state is new, so the step only makes sense for some other case. The Summary's "waiting tasks must be drained before workers switch" has the same confusion.
- **Major (Phases).** There is no task breakdown, and phase 01 is missing or unexplained.
- **Major (D6, D7, D11).** The dispatcher and claim/wait details are deferred to `notes.md#d6` and `#d7`. The polling, deletion and claim algorithm are only sketched here, so an implementer needs the notes.
- **Nit (D15).** `post_status` is a `comms_mcp` tool, yet `comms_mcp` must not publish events. The plan never says outright that the tool itself does nothing and that the runners publish by watching the call.
- **Nit (D8 / R11).** A deadline above `max_ask_wait` might be clamped (D8 says "at most") or refused (R11 lists "deadline rules" among refusals). The plan doesn't say which.
- **Nit (R11 / R18).** It is unclear whether a late reply is stored as a `rejected` row; R11's list of rules does not include closed questions.
- **Nit (D5).** The CLI's check that the joined request exists runs on the client and races with the request ending; there is no server-side check.
- **Nit (Rollout).** "Stop new submissions" has no mechanism.
- **Nit (front matter).** `design_review` says "changes-requested", yet Open questions says "None" and the Decision log is empty.

## Readability

- **Major (Summary).** "A turn may end `waiting`: the Workflow claims its inbox, and sleeps only if nothing came, until a Signal, a question deadline, its idle timeout or its wall-time budget (D7)." I had to reread this; "sleeps only if nothing came, until ..." mixes a condition with the list of ways to end the sleep.
- **Major (R23).** I had to read the rule sentence three times, and its direction is wrong (see the disconnect above).
- **Nit (Why).** The owner-decision sentence is about 70 words long and holds six decisions.
- **Nit (D6).** The "Rejected:" sentence is over 40 words, with nested parentheses.
- **Nit (Rollout).** The "Order:" sentence is about 60 words long.
- **Nit (Summary).** "When a task ends, by any path including cancellation, ..." is long and holds three rules.
- **Nit (D7).** The last sentence, about a `waiting` turn writing a finish record and outputs, is a separate rule placed in the claim decision.
- **Nit (duplication).** R10 and D9 state request scope in nearly the same words.
- **Nit (duplication).** R22, D14 and the Why section all state "woken turns count against `max_wakes`, not `max_turns`".
- **Nit (duplication).** R24/R30 and D17 restate the end-of-task closure.
- **Nit (multi-rule).** R13 combines at-most-one-turn delivery with deduplication of identical sends.
- **Nit (multi-rule).** R24 combines closing questions with waking waiters.
- **Nit (multi-rule).** R30 combines marking messages undelivered with showing them in `get_task_context`.
- **Nit (multi-rule).** R28 combines "no body in history" with "claims and Signals carry only IDs and counts".
- **Nit (multi-rule).** R19 combines an error to the model with the run continuing.
- **Nit (ordering).** Requirement IDs are out of order (R31 after R21, R32 and R33 between R30 and R26, R29 last), which makes the section hard to scan.

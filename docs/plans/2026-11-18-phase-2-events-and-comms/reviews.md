# Reviews · Phase 2 - real-time events and the comms MCP

## 2026-11-18 · design-review · plan · round 1 · changes-requested
Reviewers: fresh reader ✅ (attempt 1 read only ~41 of 316 lines and was retried) · codebase fit ✅ · zoom out ✅ (plan at 3e9df4a; raw: docs/reviews/phase-2/raw/design-review-round-1-*.md)

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | codebase fit, zoom out | Message idempotency key includes the attempt (and an unknowable call number), so a retried attempt stores the message twice (R11) | fixed: D13, notes.md#d6 (key without attempt or call number) |
| F2 | Major | codebase fit, zoom out | Migration 0005 is split across phases 01 and 02 | fixed: migrations 0005 (phase 01) and 0006 (phase 02) |
| F3 | Major | codebase fit, fresh reader | `task submit --request` collides with the existing JSON-file flag; no task lets a task join a request | fixed: D5 `--join`, phase 02 task 2.3 |
| F4 | Major | codebase fit, zoom out | Wakes run turns, so `max_turns` (6, cap 10) ends tasks long before D11's 40 wakes; status when a budget runs out while waiting is unstated | fixed: D14 and R22 (owner: separate `max_wakes`); R21 (owner); test profile in phase 03 task 1.4 |
| F5 | Major | codebase fit, zoom out | The wait loop has no source for question deadlines, and a wake that lands during a turn or before Continue-As-New is lost | fixed: D7, R15, notes.md#d7 (claim before sleeping, `woken` flag in `TaskState`, deadlines from the claim) |
| F6 | Major | codebase fit, zoom out | The restore path replays a checkpoint's finish report across turns, so a woken turn would return `waiting` again; how claimed messages reach the turn input is unstated | fixed: phase 02 task 3.2, notes.md#d7 |
| F7 | Major | codebase fit | The fake model serves one script and cannot use a dynamic correlation ID, so it cannot script two agents | fixed: D16, phase 03 task 1.1 |
| F8 | Major | codebase fit, zoom out | The runner interface cannot take the Activity's per-attempt publisher; two producers per attempt give two `seq` counters and colliding batch IDs | fixed: D2 (Activity owns the publisher; `HarnessRunner.run` gains `events`), phase 01 task 2.2 |
| F9 | Major | codebase fit, zoom out, fresh reader | `post_status` has no defined target | fixed: D15 |
| F10 | Major | codebase fit, zoom out, fresh reader | Rollout: v2 workers refuse v1 turns; orchestrator must deploy before harness workers; rollback must drain every task started on new code | fixed: Rollout & rollback (drain, orchestrator first, rollback drains new-code tasks) |
| F11 | Major | zoom out, codebase fit | Sends to a finished task wait out the deadline; `cancel_for` writes no wake rows; no lock order for message writes | fixed: R24, R25, D10, notes.md#d6 |
| F12 | Major | zoom out | Message bodies in blobs add S3 access and orphan blobs for no requirement; how `comms_mcp` reaches the database is unstated | fixed: D6 (text column), D13 and notes.md#d6 (`praxis_comms` role) |
| F13 | Major | zoom out, fresh reader | "Asking ends the turn" depends on the model; the risk mitigation (deliver at next wait) fails when the turn ends `done` | fixed: R19 and D8 (owner: refuse `done` with open questions); Summary and Risks |
| F14 | Major | fresh reader | R6 (200 ms after the oldest unpublished event) and D2 ("every 200 ms") differ | fixed: D2 points to R7 |
| F15 | Major | fresh reader | R4 says the superseded attempt stops; D2 stops it only at the next model call | fixed: R5, D2 |
| F16 | Major | fresh reader | `get_task_context` is not specified, so how an agent learns whom it may message is unstated | fixed: D15 |
| F17 | Major | fresh reader | Summary omits how tasks share a request and the rollback constraint | fixed: Summary |
| F18 | Major | fresh reader | Terms used but not defined: checkpoint, `TaskState`, resolved task, `before_model_call`, §4.4 | fixed: Terms |
| F19 | Nit | zoom out | Risk "publish fewer, larger batches" contradicts R6 | fixed: Risks (returns to design review to change R7) |
| F20 | Nit | zoom out | `event_batches` grows until manual prune | fixed: D1, notes.md#d1 |
| F21 | Nit | codebase fit, zoom out | Request and task advisory locks share one `hashtext` key space | fixed: notes.md#d6 two-key request lock |
| F22 | Nit | zoom out | `expire_due` uses database time while the Workflow timer uses Temporal time | fixed: notes.md#d7 (`now` from the Workflow) |
| F23 | Nit | zoom out | DSH already emits one token event per response; D3 would double it | fixed: D3 |
| F24 | Nit | codebase fit, zoom out | No task writes `docs/demos/phase-2.md` | fixed: phase 03 task 2.1 |
| F25 | Nit | codebase fit, zoom out | Phase 03 task 1.2 cites R18 for cases that do not cancel | fixed: phase 03 task 1.3 |
| F26 | Nit | zoom out | Several orchestrator replicas would each run a dispatcher | fixed: notes.md#d6 (`SKIP LOCKED`) |
| F27 | Nit | codebase fit | notes.md says `workers/main.py` gives the DSH runner `NoOpSink`; the runner defaults to it | fixed: notes.md evidence |
| F28 | Nit | codebase fit | Reuse the existing `TaskWorkflow` replay test and Phase 1 fixture | fixed: D12, R29 |
| F29 | Nit | codebase fit | A continued run must skip `record_task` (it refuses a different run ID) | fixed: D11, notes.md#d7 |
| F30 | Nit | codebase fit | The port list omits the in-memory reference (`memory.py`) | fixed: phase 01 task 1.2 |
| F31 | Nit | codebase fit | `reply` must compare the deadline itself, not only the status | fixed: R18, notes.md#d7 |
| F32 | Nit | codebase fit | `AttemptOutcome` and `RunResult.status` also need `waiting` | fixed: phase 02 task 3.1 |
| F33 | Nit | fresh reader | R4, R9, R10, R11, R18, R19 each hold two rules | fixed: split into R4/R5, R10/R11, R12/R13, R26/R27; R24 and R28 kept as one rule each about one outcome |
| F34 | Nit | fresh reader | Smaller undefined terms and rereads (DSH, `Superseded`, `PRAXIS_*`, profile, owner, task numbering); facts repeated across D9, D13, R19 | fixed: Terms; D9, D13 and R26 now state identity once each with distinct points |
| F35 | Nit | fresh reader | Summary nits: R-number citations, wall-time trigger, idle completion status; R16 has no tolerance | fixed: Summary; R20 tolerance 60-65 s |

## 2026-11-18 · design-review · plan · round 2 · changes-requested
Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ (plan at 4c992ea; raw: docs/reviews/phase-2/raw/design-review-round-2-*.md). No round 1 finding came back.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F36 | Major | codebase fit, zoom out | `praxis_comms` is created only by `init.sh`, which never runs on an existing volume; it also needs `CONNECT` and schema `USAGE`; 0006 fails there | fixed: `infra/db/roles.sh` and rollout step, D13, phase 02 task 2.1, notes.md#d6 |
| F37 | Major | codebase fit, zoom out | `claim_inbox` returns message bodies into Workflow history (R28) | fixed: D7, R28 (claim returns IDs; the turn reads bodies), phase 02 tasks 4.1-4.2 |
| F38 | Major | codebase fit | R19's refusal has no database path in `finish_task`, and `openai_agents` stops the run on any `finish_task` call | fixed: D8 (check injected into `finish_task`; `openai_agents` stops only on an accepted finish), R19, phase 02 task 3.2 |
| F39 | Major | codebase fit | R11 (every refusal stored) contradicts R27 (fenced-out send stores nothing) | fixed: R11 covers rule refusals only; R27 stores nothing |
| F40 | Major | codebase fit | New profile and template fields never reach `ResolvedTask` or `comms_mcp`; task 2.2 edits templates before the schema accepts `max_wakes_cap`; new fields need defaults for R29 | fixed: D14, phase 02 task 1.1 (fields with defaults first, before task 3.3 edits templates) |
| F41 | Major | codebase fit, zoom out | Cancelling a waiting task raises `CancelledError` in the wait, skipping `complete_task` and `cancel_for` (R24) | fixed: R24, D17, notes.md#d7 (cancellation caught in the wait runs `complete_task`) |
| F42 | Major | zoom out | A send to a task that then ends `done`, or rows claimed for a turn that never runs, are never delivered or closed (R13, R15) | fixed: R13 (at most one turn), R30 and D17 (undelivered rows, shown by `get_task_context`) |
| F43 | Major | zoom out | A task that ends by idle timeout or wall time completes `succeeded` with no artifacts; `waiting` has no finish record | fixed: R32, D7, phase 02 task 1.2 (finish record and outputs for `waiting`) |
| F44 | Major | zoom out | A retried attempt with a real model regenerates the send text, so the key differs and the message arrives twice; R13 holds only for the fake model | accepted: Assumptions (only identical repeats deduplicate); R13 scoped to identical sends |
| F45 | Major | fresh reader | Summary omits the new `Superseded` ending and the cycle, end-of-task and ended-recipient rules | fixed: Summary |
| F46 | Major | fresh reader | Profile, template, template version and registry are not in Terms | fixed: Terms (registry, profile, template, template version) |
| F47 | Major | fresh reader | Why the Workflow patch is needed when rollout drains running tasks is not said | fixed: D12 |
| F48 | Major | fresh reader | Who runs `cancel_for` and how waiters are woken is not in plan.md | fixed: D17, Terms (`cancel_for`) |
| F49 | Major | fresh reader | What the `woken` flag changes is not said | fixed: notes.md#d7 (claim-before-sleep covers Signals during a turn; the flag only ends a sleep) |
| F50 | Major | fresh reader | What the dispatcher does when a Signal fails is not in plan.md | fixed: D6 |
| F51 | Major | fresh reader | How `PRAXIS_TURN` and `PRAXIS_ATTEMPT` are set per attempt for both runners is not said | fixed: D9 |
| F52 | Nit | codebase fit | "The Activity's tool-call hook" does not exist; `post_status` needs handling in both runners' tool paths | fixed: D15, phase 02 task 3.2 (both runners' tool-event paths) |
| F53 | Nit | codebase fit | `prepare_task` has no database access for `--join`'s check | fixed: D5 (the CLI checks before submitting), phase 02 task 3.4 |
| F54 | Nit | codebase fit | Nothing `NOTIFY`s on a `message_wakes` insert | fixed: D6, notes.md#d6 |
| F55 | Nit | codebase fit | Terms' reader rule omits "fails on a repeated offset" | fixed: events plan Terms (reader rule fails on a repeated offset) |
| F56 | Nit | codebase fit | Bound Continue-As-New by history length, not only by woken turns | fixed: D11 (history length over 1,000 events) |
| F57 | Nit | codebase fit | `PRAXIS_ATTEMPT` must be Temporal's attempt (the fence key) | fixed: D9 (Temporal's attempt number) |
| F58 | Nit | codebase fit | New variables also belong in `check-prereqs.sh` and the compose harness env | fixed: phase 02 task 2.1 |
| F59 | Nit | codebase fit | `complete_task` runs `tasks.complete` and `cancel_for` with no stated order | fixed: D17 (one transaction) |
| F60 | Nit | zoom out | `TaskState` must be an optional second `run` parameter for R29 | fixed: D11, notes.md#d7 (`run(start, state=None)`) |
| F61 | Nit | zoom out | How to drain waiting tasks is not said | fixed: Rollout & rollback (`temporal workflow cancel`) |
| F62 | Nit | zoom out | R19's "open" should exclude questions past their deadline | fixed: Terms (open question), notes.md#d7 |
| F63 | Nit | zoom out | A finished workflow keeps its last batch rows until Phase 3A | fixed: events plan Assumptions |
| F64 | Nit | zoom out | A terminated workflow's `tasks` row stays `running`, so sends to it are accepted | accepted: Assumptions (terminated Workflows) |
| F65 | Nit | fresh reader | Smaller undefined terms, rereads, defaults stated twice, multi-rule requirements (R5, R6, R18, R21, R24, R28) | fixed: R21 and R31 split, R28 and R33 split; R18 reduced to one rule ("not open"); R5 and R6 are in the events plan |

Round 1's Majors are resolved. Round 2's new Majors (F36-F44) are all in the messaging part (phase 02); none is in the event part (phase 01). The design review stops after two rounds (design-review skill) with these open.

## 2026-11-18 · split
Owner decision: the event part (R1-R9, D1-D5, phase 01) moved to `docs/plans/2026-11-18-phase-2-agent-events`, with the same IDs. This plan keeps messaging (phases 02 and 03) and is to be revised against round 2 before a fresh design review.

## 2026-11-18 · design-review · plan · round 3 · passed
After the split and rework, a fresh round (owner decision when splitting). Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ (plan at 88ea037; raw: docs/reviews/phase-2/raw/design-review-round-3-*.md). No earlier finding came back. Recorded changes-requested; every Major below was then fixed.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F66 | Major | codebase fit, zoom out, fresh reader | Continue-As-New ran only before a sleep, so a task woken back to back never continued (R33) | fixed: D11 checks after every `waiting` outcome; R33 scenario "back to back"; task 4.3 test |
| F67 | Major | zoom out | One wake row and Signal per message grows history during a long turn | fixed: D6, a wake only for a sleeping recipient, one per recipient (`task_inbox`, unique `message_wakes`); R33 second scenario; phase 03 task 1.5 |
| F68 | Major | zoom out | A failed or cancelled claim ended the Workflow without `complete_task` (R24, R30) | fixed: D7 (claim retried until the wall-time deadline), D17 (every ending), R24, Risks; task 4.3 test |
| F69 | Major | zoom out | R19 let a task finish with an unread reply, which was then discarded; an ask in the same step escaped the check | fixed: R19 and D8 add unread replies and run the check under the request lock (extends the owner decision; flagged to the owner) |
| F70 | Major | codebase fit | `max_ask_wait` had no path to the Activity | fixed: D14, `TurnInput.max_ask_wait` with a default; task 1.1; Impact |
| F71 | Major | codebase fit, zoom out | `praxis_comms` wiring: the `db` service lacks the password, `roles.sh` is not mounted, `make db-roles` does not exist | fixed: task 2.1, notes.md#d6, Rollout |
| F72 | Major | fresh reader | R23's rule pointed the wrong way | fixed: R23 rewritten; self-ask refused |
| F73 | Major | fresh reader | No expiry mechanism or read marker in plan.md | fixed: Terms (Claim, Unread reply), D7 (expiry, `read` marking as a fenced write) |
| F74 | Major | fresh reader | `max_wakes` outcome and cap undefined | fixed: R22 (fails "wake budget exhausted"), D14 (cap default 100, the smaller applies; which turns count) |
| F75 | Major | fresh reader | Idle-timeout start undefined | fixed: R20, D7 (restarted at each sleep) |
| F76 | Major | fresh reader | Summary risks, R21/R31 outcomes and the rollback drain missing | fixed: Summary |
| F77 | Major | fresh reader | Forward rollout drained `waiting` tasks that cannot exist yet | fixed: Rollout & rollback (forward drains running tasks; rollback cancels waiting ones) |
| F78 | Major | fresh reader | `complete_task` and the wall-time budget undefined | fixed: Terms |
| F79 | Major | fresh reader | Phases: no task content, phase 01 missing | fixed: Phases note (phase 01 is the events plan's; tasks in `phases/`) |
| F80 | Nit | codebase fit | Which message writes are fenced | fixed: D10, task 2.2 |
| F81 | Nit | codebase fit | Marking rows read is an attempt write | fixed: D7, D10 (fenced) |
| F82 | Nit | codebase fit | v2 prompt must be a new file | fixed: D13, task 3.3 |
| F83 | Nit | codebase fit, zoom out | Sequence grant for `message_wakes` | fixed: identity column (notes.md#d6) |
| F84 | Nit | codebase fit | A stale attempt of an ended task could open a question | fixed: R25, notes.md#d6 (sender status) |
| F85 | Nit | codebase fit | Cancel during the claim | fixed: F68 |
| F86 | Nit | codebase fit | Which budget pays a `continue` after a woken turn | fixed: D14 |
| F87 | Nit | codebase fit | Test profile needs a template cap of 200 | fixed: phase 03 task 1.5 |
| F88 | Nit | codebase fit | R28 too broad | fixed: R28 limited to claims and Signals |
| F89 | Nit | zoom out | D12's rationale wrong | fixed: D12 (guards command order on the restructured loop) |
| F90 | Nit | zoom out | A rerun of the same turn would show claimed rows twice | fixed: task 4.1 |
| F91 | Nit | zoom out | `openai_agents` `sh` can read the comms URL | accepted: Assumptions (the same holds for `PRAXIS_SAMPLE_DB_URL`; DSH isolates commands) |
| F92 | Nit | fresh reader | Terms, multi-rule requirements, duplication, ordering, `post_status` mechanics, clamp vs refusal, late-reply recording, the `--join` race, submit gate | fixed: Terms, D8 (clamped), R11 (closed questions recorded), D15, Assumptions (`--join`), Rollout (no submit gate), requirements in ID order; multi-rule requirements R13, R19, R24, R30 accepted as one rule with its observable outcome |
| F93 | Nit | fresh reader | plan.md is 375 lines (budget 250) | accepted: 24 requirements each with scenarios; mechanics are in notes.md |

## 2026-11-18 · approved · plan (phases 02 and 03)

Owner approved, including the two extensions flagged with round 3: finish_task also waits for unread replies (R19); a used-up wake budget fails the task (R22).

## 2026-11-18 · impl-review · phase 02 · round 1 · changes-requested
Diff base: `7f0ed8538119ca7de512a73d3341ef24d0a31cf7`. Reports: `docs/reviews/phase-2/raw/messaging-impl-review-round-1-{contract,failure,scope}.md`.
Reviewers: contract ✅ · failure and retry ✅ · scope and composition ✅

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F94 | Major | contract | A reply's recipient was never checked against the question's asker (R16, R11) | fixed: `_question_for_reply` refuses a reply not sent to the asker; `test_messages.py` (734346a) |
| F95 | Major | contract, failure, scope | Paths that reach the wall-time deadline after a `waiting` turn ended without looking at open questions (R21, R31) | fixed: `_ending_at_wall_time` runs one last claim on every path; `test_a_waiting_turn_past_the_deadline_fails_with_an_open_question` |
| F96 | Major | contract, scope | `post_status` never became a `status` event on `openai_agents`: the SDK passes a text item, not a string (D15) | fixed: `tool_text` in `runner.py`; `test_an_mcp_status_result_is_published_on_openai_agents` (MCP failures now count as failed too) |
| F97 | Major | contract, scope | With parallel tool calls, `finish_task`'s check could run before the same step's `ask_agent` committed (R19, D8) | fixed: the Activity checks again after the run and turns a blocked finish into `continue`; `test_a_done_alongside_a_same_step_ask_does_not_finish` |
| F98 | Major | contract, failure, scope | `complete_task` gave up after 5 attempts, and a cancel during it was not rerun (R24, D17) | fixed: unlimited retries and one rerun after a cancel in `_complete`; `test_complete_task_is_retried_until_it_succeeds` |
| F99 | Major | failure | The dispatcher dropped a wake sent while its old row was being signalled (D6, R14) | fixed: delete before the Signal, one savepoint per row, Signal RPC timeout; `test_a_wake_sent_while_its_row_is_signalled_is_kept` |
| F100 | Major | failure, scope, contract | The dispatcher ended silently if its first connect failed (D6, Risks) | fixed: connect inside the retry loop; `tests/test_dispatcher_supervision.py` |
| F101 | Nit | contract, scope | R26 test passed when nothing was stored | fixed: asserts `senders == {a}` |
| F102 | Nit | contract, failure, scope | `deadline_seconds` 0 became 300 and a negative one gave a past deadline (D8) | fixed: refused below 1; `test_each_tool_through_the_client` |
| F103 | Nit | contract, failure, scope | notes.md#d6 gave `task_inbox` more grants than migration 0006 | fixed: notes.md#d6 (SELECT only) |
| F104 | Nit | contract | notes.md#d6 gave the wrong `roles.sh` mount | fixed: notes.md#d6 |
| F105 | Nit | contract | Phases table showed 0/15 | fixed: plan.md Phases |
| F106 | Nit | failure | `remove_listener` on a dead connection could mask the cancel | fixed: suppressed in `dispatcher.py` |
| F107 | Nit | contract | No test that a `continue` after a woken turn spends `max_turns` (D14) | fixed: `test_a_continue_after_a_woken_turn_spends_max_turns` |
| F108 | Nit | failure, scope | A claim cut off near the deadline ended "inbox unavailable" with the inbox back (R21) | fixed: waits for the deadline, then the F95 ending; `test_a_claim_cut_off_by_the_deadline_still_ends_by_open_questions` |
| F109 | Nit | contract | A woken turn at the deadline failed with no open question (R21) | fixed: F95 |
| F110 | Nit | contract | A comment said the comms role cannot read wake rows | fixed: the comment now gives the real reason (no RETURNING needed) |
| F111 | Nit | contract, scope | R12: no test of a database fault during a send | accepted: the send returns inside its transaction, so success follows the commit |
| F112 | Nit | contract, scope | R28: no history test with three 16 KB messages | accepted: phase 03's history test |
| F113 | Nit | contract | R32: Workflow fakes carry no outputs | accepted: the Activity test covers it; phase 03's two-agent test checks artifacts end to end |
| F114 | Nit | contract | R20: the 60-65 s window is not asserted | accepted: the ending is the idle timer, which the time-skipping test drives |
| F115 | Nit | contract | `render_inbox` text for expired and cancelled questions is untested | accepted: phase 03's failure cases assert what the asker is told |
| F116 | Nit | contract | Rejected rows asserted only for cross-request refusals (R11) | accepted: every refusal goes through the one `_refusal` path |
| F117 | Nit | contract, failure | Rows a woken turn read stay `read` if the turn then fails (R30) | accepted: they were rendered into the model's input |
| F118 | Nit | contract, scope | The 16 KB body limit counts characters, not bytes (D6) | accepted: it still bounds each row; characters are what the model sends |
| F119 | Nit | contract, failure | A cancel during `record_task` skips `complete_task` (R24) | accepted: a narrow window unchanged since Phase 1 |
| F120 | Nit | contract, scope | Sends during one sleep can add several wakes (R33) | accepted: bounded by the sends; a Signal is only a hint |
| F121 | Nit | contract, failure, scope | Expiry uses `<` and the Workflow's clock, costing an extra claim (R17) | accepted: harmless, noted in notes.md |
| F122 | Nit | failure, scope | A refusal is replayed for identical calls in the same turn (R13) | accepted: idempotency within a turn; the next turn's key differs |
| F123 | Nit | failure | `tasks.run_id` keeps the first run's ID after continue-as-new (D11) | accepted: informational only |
| F124 | Nit | scope | An idle timeout ends without a final claim (R20) | accepted: a late message becomes `undelivered`, which its sender sees |
| F125 | Nit | scope | 50 rows that keep failing stop a drain (D6) | accepted: Signals fail together only when Temporal is down; the next poll retries |
| F126 | Nit | scope | The closed-workflow test uses a never-started workflow | accepted: closed and missing workflows both return NOT_FOUND on one path |
| F127 | Nit | scope | The wake-budget test runs at a smaller scale than the plan's example (R22) | accepted: the counters do not depend on scale |
| F128 | Nit | scope | The R13 rerun test calls `read_claimed` directly | accepted: `read_claimed` is keyed by turn, not attempt |

## 2026-11-19 · impl-review · phase 02 · round 2 · changes-requested
Targeted follow-up (docs/reviews/README.md rules 6 and 8): one failure-and-retry reviewer over the fixes, `3ca9f3d..bd10edc`, given the round 1 correction list. Report: `docs/reviews/phase-2/raw/messaging-impl-review-round-2-failure.md`. It confirmed F94-F97, F99, F100, F102 and F106-F108; F98's cancel half came back as F129.
Reviewers: failure and retry ✅

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F129 | Major | failure | F98 reopened: a cancel during `complete_task` arrives as an `ActivityError` caused by `CancelledError`, so it was not rerun (R24, D17) | fixed: `_complete` reruns on it; `test_a_cancel_while_complete_task_retries_still_completes_it` |
| F130 | Nit | failure | A cancel during the final wall-time claim ended as "wall-time budget exhausted" | fixed: `_ending_at_wall_time` re-raises it, so the task ends "cancelled" |
| F131 | Nit | failure | A failed final claim fails a task that may have had no open question (R21) | accepted: the wall time did run out and the ending cannot be known; failing is the safe ending |
| F132 | Nit | failure | `_run_v2`'s woken-turn branch at the deadline is untested (F109) | accepted: reachable only when the Workflow task that sees a claim's rows starts after the deadline; it uses the same `_ending_at_wall_time` as the tested paths (`test_a_slow_claim_with_rows_at_the_deadline_runs_no_woken_turn` covers the cut-off claim) |
| F133 | Nit | failure | No `workflow.patched` marker for the new commands (D12) | accepted: the v2 path has run only on dev stacks and is unmerged; `phase2-wait` still guards Phase 1 histories |
| F134 | Nit | failure | `complete_task` retries without a `schedule_to_close`, so a permanent bug keeps the Workflow open | accepted: by design for outages (D17); the failing attempts show as a pending Activity and in the worker log |
| F135 | Nit | failure | The final claim can end up to 60 s after the deadline | accepted: R21 sets no timing |
| F136 | Nit | failure | A batch's deletes stayed uncommitted, so senders could wait for many Signals (D6) | fixed: one transaction per wake row in `drain` |
| F137 | Nit | failure | A non-RPC error from `_signal` rolled back the whole batch | fixed: F136 (only that row's transaction) |
| F138 | Nit | failure | Phase front matter said passed while round 2 was running; plan.md disagreed | fixed: front matter and Phases table after this round |

After the fixes, no Blocker or Major is open: the review passes. Per the impl-review skill, rounds stop at two.

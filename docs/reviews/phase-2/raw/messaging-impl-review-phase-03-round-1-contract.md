Review of phase 03 (Acceptance and demo), diff c1dbee7..132e2df. The contract is plan.md, phases/03-acceptance.md and roadmap phase-2.md.

Note: the brief names `phases/03-acceptance-and-demo.md`, but the file at the review commit is `/home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/phases/03-acceptance.md`. I reviewed that file.

## Promise map (promise: what enforces it, and the test that would fail without it)

- **D16, script picked by a `[script:NAME]` marker.** `tests/support/fake_model/__init__.py` `pick_script` and `FakeModelState.reply`. Test: `tests/test_fake_model_scripts.py::test_a_marker_picks_the_script...` and `test_a_request_without_a_marker_gets_the_default_script`.
- **D16, `${result.N.field}`.** `_step_results`, `_field` and `_resolve`. Test: `test_a_result_reference_reads_an_earlier_tool_result`.
- **D16, `${input:REGEX}` (the decision-log extension).** `_resolve.lookup`. Test: `test_the_newest_input_wins` and the marker test.
- **D16, scripts files may name other files (decision log).** `load_scripts`. Test: `test_a_scripts_file_may_name_other_script_files`. `infra/docker-compose.yml:271` now points at `scripts.json`, whose `default` is `order_script.json`.
- **R14 and R16.** Covered by `tests/integration/test_two_agents.py`, which asserts the answer and the message rows `answered`/`read`. The ordering is not observed (Finding 1).
- **R17.** `test_messaging_failures.py::test_an_unanswered_question_times_out`, which asserts the summary and the `expired` row. The deadline timer may not be observed (Finding 2).
- **R10.** `::test_a_cross_request_message_is_refused`: a `rejected` row with its reason, the model told, and nothing in B's request.
- **R13 (scenario 1).** `::test_a_send_before_a_killed_worker_is_delivered_once`: attempts `[(1,'lost'),(2,'done')]`, the step was served twice, one message row, and B read it. This test would fail if dedupe broke.
- **R13 (scenario 2).** Covered in phase 02 (`tests/integration/test_messages.py:89`), not in this diff.
- **R24.** `::test_a_cancelled_recipient_tells_the_waiting_asker`. It waits until both tasks are sleeping, cancels B, then asserts A's "told" summary and the `cancelled` row. Good setup.
- **R19 (scenario 1).** `test_messaging_endings.py::test_done_with_an_open_question_is_refused_and_the_task_waits`: the refusal is seen, `turns == 2`, and the summary is the price. Scenario 2 (unread reply) is in phase 02 (`test_messages.py:145-151`).
- **R30.** `::test_an_unread_message_to_an_ended_task_is_listed_as_undelivered`. It uses two workers so the turns run at the same time, and asserts the `get_task_context` result and the `undelivered` row. Only the pending case is covered here; the claimed-but-unread case is in phase 02 (`test_messages.py:265`).
- **R33 (scenario 1).** `test_messaging_history.py::test_a_task_woken_100_times_keeps_every_run_bounded`: every run has fewer than 2,000 events, the chain has at least 2 runs, at least 100 Signals arrived, and the final summary is "now". This is not vacuous: it waits for sleeping before each send.
- **R33 (scenario 2).** `::test_50_messages_during_one_turn_bring_at_most_one_signal`: at most 1 Signal, `turns == 2`, summary "50". This is not vacuous: if D6's sleeping gate broke, the dispatcher would deliver many Signals and the test would fail.

## Findings

**1. Major (R14, task 1.2, observability). B is not shown to be waiting before A asks.**
- Location: `/home/geo/develop/praxismesh/tests/integration/test_two_agents.py:62-69`.
- Scenario: A is submitted right after B, with no wait for B to sleep. The single `local-dsh` worker runs one turn at a time (`concurrency_per_pod: 1`). If A's first turn is scheduled before B's, or A's ask commits while B's first turn is still running, then B's post-turn `claim_inbox` picks up the question without any wake row or `inbox` Signal. That is the R15 path.
- Wrong outcome: the test passes even if the dispatcher, the Signal or the sleeping-wake path is broken.
- Evidence: R14 says "Given task B waiting, when A sends to B". Task 1.2 says "B is waiting and wakes". The comment at line 72 reads "B slept until the question woke it", but nothing asserts it.
- Contrast: the R24 and R13 tests do wait (`eventually(... sleeping(b.task_id))`).
- Fix: `await eventually(lambda: sleeping(b.task_id), ...)` before submitting A. Optionally assert that B's history has at least one `inbox` Signal.
- Mitigation: `test_messaging_history` does observe Signal wakes, so R14's mechanism is covered there, just not by its own acceptance test. The same missing wait affects the R19 test (`test_messaging_endings.py:118-125`), which there only weakens its precondition.

**2. Major (R17, observability; I could not fully verify the timing). The 3 s deadline may expire before A ever sleeps.**
- Location: `/home/geo/develop/praxismesh/tests/integration/test_messaging_failures.py:93-97` ("within 3 s").
- Scenario: after the ask commits, A still has to run its `finish_task("waiting")` step, end the DSH turn (checkpoint and outputs), complete the Activity and run `claim_inbox`. If that takes 3 s or more, the claim expires the question itself, and the asker's woken turn starts without the Workflow sleeping until `claim.next_deadline` (`orchestrator/workflow.py:365-378`).
- Wrong outcome: a broken deadline timer (for example, the deadline left out of the sleep's limits) would still pass this test.
- Evidence: R17 says "when 30 s pass, then the asker runs a turn saying no answer came".
- Fix: use a deadline of 15-20 s (as the demo does), and assert `sleeping(a.task_id)` before the deadline passes.

**3. Nit (task 1.5).** `test_messaging_history.py:runs` reports run IDs, event counts and Signal counts, not history sizes in bytes. "History sizes" may well mean event counts, so this is a Nit.

**4. Nit (R19).** `test_messaging_endings.py:138` checks only `"open question" in told[0]`. R19 says the error names the question. `messages.py:226` includes the correlation ID, but no test here asserts it.

**5. Nit (R16).** `test_two_agents.py` takes A's answer with the pattern `Reply from \S+ to your question \S+: ...`. It never checks that the token after "question" is A's correlation ID. R16 requires "the reply and the correlation ID", so a render that showed a wrong ID would still pass.

**6. Nit (R10).** `test_messaging_failures.py:122-126` checks that the tool message text contains the refusal, but not that it was an error result. The code does raise a `ToolError` (`comms_mcp/server.py:64-66`).

**7. Nit (D16 docstring).** `fake_model/__init__.py` says "A string that is only a placeholder takes the value's own type", but `${input:...}` always yields a string. For example, `deadline_seconds` becomes `"3"` (in the `ASK` step of `test_messaging_failures.py` and in `scripts.json`'s demo-asker), and the tests depend on the MCP layer coercing it to an int.

**8. Nit (D16).** The `PLACEHOLDER` regex `input:(.+?)\}(?!\})` truncates any REGEX that contains a `{n}` quantifier. The resulting `re.error` is not among the exceptions `lookup` catches, so it escapes into the HTTP handler. This only affects test scripts.

**9. Nit (plan bookkeeping).** The phase table in `plan.md` still shows phase 03 as `0/7`, while the phase file has 6 of 7 tasks checked. `check_plans.py` does not compare the two, so nothing catches it.

**10. Nit (task 2.2, overview).** The task asks for "components, data, failure and recovery, limits, deviations". The new section in `docs/architecture/overview.md` has no Deviations part. Deviations such as the 16 KB body limit counting characters, `TaskStart.carried` and the D16 `${input}` extension are only partly mentioned under Known limits or the component rows.

**11. Nit (overview, Dispatcher row).** The row says "a closed or missing Workflow keeps it (logged)". The code keeps the delete, so the row goes (`orchestrator/dispatcher.py:108-112` returns True for NOT_FOUND, and the module docstring says "keeps the delete"). Read as "keeps the row", the sentence contradicts both the code and D6. Reword to "the row is dropped (logged)".

**12. Nit (demo record, task 2.1 verify).** `docs/demos/phase-2.md` says the clean-worktree dry run passed at `5b68eb6`. The recorded run is at `90ad371`, which changed the demo's D instructions and stop logic in `infra/demo/phase-2-messaging.sh`. That final script never had a clean-worktree dry run.

**13. Nit (roadmap demo checklist).** The checklist's "event batching under a busy response" is shown only as "A: 13 events in 7 batches", which is not a busy response. The record defers to `phase-2-events.md` for this, which is reasonable.

## Facts checked and consistent with the code

- **Overview, Message tables row:** `task_messages` with `claimed_turn`, `notice_turn`, `length(body) <= 16384` and a unique idempotency key; `task_inbox.sleeping`; `message_wakes` unique per recipient.
- **Overview, Comms role row:** the grants in migration 0006 and `roles.sh`, and the skip when `PRAXIS_COMMS_DB_PASSWORD` is unset.
- **Overview, Comms MCP row:** the `ask_agent` deadline (at least 1, default 300); refusals as `ToolError`; templates `local-dsh` v2 and `local-default` v2 granting `comms`.
- **Overview, Waiting Workflow row:** `HISTORY_LIMIT` 1000; the idle timeout only with no open question; `COMPLETE_RETRY maximum_attempts=0`; the last claim at the wall-time deadline deciding `succeeded` or `failed`.
- **Overview, Harness and Tests:** `render_inbox`, and every referenced test file and runbook anchor exists.
- **Demo record:** D's cancel gives `failed`/"cancelled" with the Workflow COMPLETED (`workflow.py:292-293`).

Verdict: changes-requested

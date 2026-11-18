# Reviews · Phase 2 events - the event table and agentctl tail

Split on 2026-11-18 (owner decision) from `docs/plans/2026-11-18-phase-2-events-and-comms`, whose design review rounds 1 and 2 covered this content as its R1-R9, D1-D5 and phase 01 (raw: `docs/reviews/phase-2/raw/design-review-round-{1,2}-*.md`). Round 2 raised no Major against it; this plan keeps those IDs.

## 2026-11-18 · design-review · plan · round 1 · changes-requested
Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ (plan at aa6580f; raw: docs/reviews/phase-2/raw/events-design-review-round-1-*.md)

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| E1 | Major | codebase fit | The new tables carry no `retention_class` and are not in `retention.py` | fixed: D1, task 1.1, notes.md#d1 |
| E2 | Major | codebase fit, zoom out | Where the final flush and `status` run against the finish writes, and on failure and cancel paths, is unspecified; shutdown of the background task is undefined | fixed: R5, R8, D2, D3, task 2.2, notes.md#d2 |
| E3 | Major | codebase fit, zoom out | A publish that fails for a database reason has no retry or end state; R1's re-send case has no mechanism | fixed: R1, D2, task 2.1, Assumptions, notes.md#d2 |
| E4 | Major | codebase fit, zoom out | Publishes are not serialized per attempt, so offsets can contradict `seq` and break R9 | fixed: D2, R9, task 2.1 |
| E5 | Major | fresh reader | Summary states no limit and omits R8 and R9 | fixed: Summary |
| E6 | Major | fresh reader | "Keying" unexplained | fixed: Why |
| E7 | Major | fresh reader | The three tables' roles and the 600 s re-send horizon are unexplained; dedup mechanism not shown | fixed: D1 |
| E8 | Major | fresh reader | "Task 2.3" does not match anything in plan.md | fixed: "phase 01 task 2.3" in Summary and Risks |
| E9 | Major | fresh reader | 20 ms assumption and 250 ms threshold measure different things | fixed: assumption removed; Risks state the gate |
| E10 | Major | fresh reader | LISTEN and the 1 s poll have no decision | fixed: D1 |
| E11 | Major | fresh reader, codebase fit, zoom out | Task ID versus workflow ID: they are equal today, so the rejected alternative and the lookup are misleading | fixed: Terms, D1, D5, notes.md#d1 |
| E12 | Major | fresh reader | Whether DSH's token events meet R6 | fixed: D3 (counts only, `gateway.py`) |
| E13 | Major | fresh reader | Where attempts are recorded and how a publish knows its attempt | fixed: Terms, task 1.3 (`publish` takes task, turn and attempt) |
| E14 | Nit | codebase fit | R7's 64-event cap implied only | fixed: R7 |
| E15 | Nit | codebase fit | How the fence identity reaches the transport | fixed: task 1.3 |
| E16 | Nit | codebase fit, zoom out | `tail`'s end signal and final drain | fixed: D5, task 3.1 |
| E17 | Nit | codebase fit | R1 unqualified against the 600 s horizon | fixed: R1 |
| E18 | Nit | codebase fit | notes.md cites `runner.py:238` for `:237` | fixed: notes.md |
| E19 | Nit | codebase fit | Other `HarnessRunner.run` implementations not named | fixed: task 2.2 |
| E20 | Nit | codebase fit | `emit` is synchronous and may be called from threads | fixed: task 2.1, notes.md#d2 |
| E21 | Nit | zoom out | The refusal flag duplicates existing checks | fixed: flag dropped (notes.md#d2) |
| E22 | Nit | zoom out | A unique key on `(workflow, attempt, seq)` could replace `event_batches` | contested: ADR-0009 names batch-ID dedup and the spike's suite tests it |
| E23 | Nit | zoom out | R8 should exempt a killed worker | fixed: R8 |
| E24 | Nit | zoom out | Where `BatchingPublisher` lives; the fence predicates are private | fixed: What changes, task 1.2 (`fence.py`) |
| E25 | Nit | zoom out | Database CPU had no gate | fixed: Risks, task 2.3 |
| E26 | Nit | fresh reader | Smaller terms, rereads and repetition (Expired, run hooks, Phase 3A, `--older-than`, reset with no checkpoint, Decision log empty) | fixed: Terms, R9, D4, Non-goals, Decision log |

## 2026-11-18 · design-review · plan · round 2 · passed
Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ (plan at 910be44; raw: docs/reviews/phase-2/raw/events-design-review-round-2-*.md). No round 1 finding came back. Recorded changes-requested; every Major below was then fixed, so the review passes without a third round (design-review step 5).

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| E27 | Major | codebase fit, zoom out | The restore short-circuit path reaches `_finish` without the final flush or its fence check | fixed: D2 (flush at the start of `_finish`), R5 second scenario, task 2.2, notes.md#d2 |
| E28 | Major | codebase fit, zoom out | A batch kept after failed re-sends is not frozen, so new events can be dropped under its ID or stored events duplicated under a new one | fixed: D2 (frozen batches), task 2.1 test, notes.md#d2; the zoom-out alternative (dedup on attempt and `seq`) not taken: it departs from ADR-0009's batch-ID rows |
| E29 | Major | fresh reader | Summary cites R7 and R8 for the finish ordering; R5 is the rule | fixed: Summary |
| E30 | Major | fresh reader | "Retention class" undefined | fixed: Terms |
| E31 | Major | fresh reader | "Phase 01 task 2.3" not findable from plan.md | fixed: Summary and Risks name the phase file |
| E32 | Major | fresh reader | R8 omits the failed-final-flush case | fixed: R8 |
| E33 | Major | fresh reader, codebase fit | R7's 640-event scenario ignores `reset` and `status` | fixed: R7 scenario at the publisher |
| E34 | Major | fresh reader | Batch-row cleanup appears only in Assumptions | fixed: D1 |
| E35 | Major | fresh reader | Whether existing fenced writes move to `fence.py` | fixed: D2, task 1.2 |
| E36 | Nit | codebase fit | Phases table says 12 tasks; the phase has 11 | fixed |
| E37 | Nit | codebase fit | `PHASE1_TABLES` naming | fixed: task 1.1 |
| E38 | Nit | codebase fit | The E18 fix was wrong; `NoOpSink` is at `runner.py:238` | fixed: notes.md (E18 reopened and corrected) |
| E39 | Nit | codebase fit | Missed call sites, `DshRunner`'s `sink`, worker wiring, required `events` | fixed: task 2.2 |
| E40 | Nit | codebase fit | "3 times" versus "3 tries" | fixed: D2, task 2.1 (backoff then each trigger) |
| E41 | Nit | codebase fit | R1 cannot detect a batch-ID collision; no attempt-named batch-ID test | fixed: R1 scenario, task 2.1 |
| E42 | Nit | codebase fit, zoom out | `--older-than` may leave holes; retained base when all pruned | fixed: D4 |
| E43 | Nit | codebase fit, zoom out | `tail`'s end signal fails for terminated or unrecorded tasks | fixed: D5 (Temporal describe) |
| E44 | Nit | codebase fit | Benchmark results path; `FenceRejected` placement | fixed: task 2.3 (`docs/benchmarks/`), task 1.2 |
| E45 | Nit | zoom out | `status` may report an outcome that was then refused | fixed: D3, task 3.3 (`status` is the runner's result) |
| E46 | Nit | zoom out | A stale attempt can publish after the task completed | accepted: Assumptions |
| E47 | Nit | zoom out | `close()` has no overall bound and runs outside the heartbeat | fixed: task 2.1, notes.md#d2 |
| E48 | Nit | zoom out | Database CPU compared across sessions | fixed: Risks, task 2.3 (fenced and unfenced in one session) |
| E49 | Nit | fresh reader | Smaller terms, rereads and multi-rule requirements (`before_model_call` unused, shielded, Why vs front matter, outcome and artifact) | fixed: Terms, Why |

## 2026-11-18 · approved · plan (phase 01)

## 2026-11-18 · impl-review · phase 01 · round 1 · passed
Diff base 41c0bcf; review commit c7dcbcd. Reviewers: contract ✅ · failure and retry ✅ · scope ✅ (the first scope subagent returned without reviewing; retried, not counted). Raw: docs/reviews/phase-2/raw/events-impl-review-round-1-*.md. Recorded changes-requested; every Major below was fixed with a test that fails without the fix.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| I1 | Major | contract, scope | A timed-out final flush: the failure path saw the publisher open, emitted a second status and closed again, and the cancelled task's `CancelledError` replaced `EventsUnavailable` | fixed: `close()` runs once and `closed` is true from its first call (`harness_activity/events.py`); tests `test_close_is_bounded_and_runs_once`, `test_a_final_flush_that_times_out_raises_events_unavailable` |
| I2 | Major | contract, failure, scope | An attempt failing before `_run` (opening the attempt, config, checkpoint lookup) stored `status` with no `reset` (R9) | fixed: `reset` is emitted right after the checkpoint lookup, before `_open`; the failure path emits one if none was; test `test_an_attempt_that_fails_early_still_opens_with_reset` |
| I3 | Major | scope | The 10 s close bound and its timeout path were untested | fixed: the I1 tests (bound set through `CLOSE_TIMEOUT_S`) |
| I4 | Nit | failure, scope | Every later trigger re-ran the full backoff | fixed: the backoff runs once per batch, then one try per trigger; test `test_the_backoff_runs_once_per_batch` |
| I5 | Nit | contract, failure, scope | Leftover events after a 64-cut got a fresh 200 ms timer | fixed: the buffer keeps each event's emit time |
| I6 | Nit | scope | A close during a backoff gave up after one cycle | fixed: while closing it keeps trying once per trigger until the close bound; test `test_a_database_that_stays_down_is_returned_from_close` |
| I7 | Nit | failure | A cancel during the final flush stored a second status | fixed: by I1 (`closed` from the first call) |
| I8 | Nit | failure | An emit after close was dropped silently | fixed: logged |
| I9 | Nit | contract, failure, scope | `tail` ended on any Temporal describe error | fixed: only not-found ends it; other errors are logged and following continues |
| I10 | Nit | contract, failure | `tail --no-follow` connected to Temporal; the engine leaked if connect failed | fixed: `--no-follow` reads the table only; the engine is disposed in `finally` |
| I11 | Nit | contract, scope | `tail` could print an `Expired` line twice | fixed: the position moves to the expiry's base |
| I12 | Nit | failure, scope | Parallel calls to one tool reported the wrong call number (`openai_agents`) | fixed: open calls are kept per tool, oldest first |
| I13 | Nit | failure, scope | `openai_agents` emitted no events for refused tools, unlike DSH | fixed: `tool_call`/`tool_result` `refused`, as DSH |
| I14 | Nit | contract | DSH refused-tool events stored a model-chosen name of any length (R6) | fixed: names capped at 64 characters in both runners |
| I15 | Nit | contract, scope | No table test for two attempts each emitting; prune tested only in memory | fixed: `test_two_attempts_publishing_get_gap_free_offsets`, `test_tail_on_the_table_reports_pruning_first` |
| I16 | Nit | contract | schemas.md said every attempt ends with `status`; runbook misdescribed `--older-than`; Phases table counts | fixed |
| I17 | Nit | contract | A non-database error (for example an unserialisable payload) is retried as a database error | accepted: payloads are built by our code from counts and names; the attempt then fails retryably with `EventsUnavailable`, which surfaces the bug |
| I18 | Nit | contract, failure | A re-run of the same Temporal attempt number within 600 s (a Workflow reset) reuses batch IDs | accepted: rare; a Workflow reset is an operator action |
| I19 | Nit | contract, failure, scope | A lost-reply commit followed by over 600 s of database errors is stored twice | accepted: outside R1's 600 s horizon, as the plan states |
| I20 | Nit | contract | A deduplicated re-send sends no NOTIFY | accepted: nothing new to notify |
| I21 | Nit | failure | An emit after the worker's loop closed raises in the emitting thread | accepted: shutdown only |
| I22 | Nit | failure | `status: done` can precede a finish checkpoint that then fails | accepted: D3 (`status` is the runner's result) |
| I23 | Nit | scope | The benchmark has no concurrent same-task fenced writers | accepted: lock order under concurrency is pinned by `test_publish_and_fenced_checkpoint_never_deadlock` (200 pairs) |

## 2026-11-18 · impl-review · phase 01 · targeted follow-up · passed
Diff c7dcbcd..4463f52, one fresh impl-reviewer (raw: docs/reviews/phase-2/raw/events-impl-review-round-1-follow-up.md). I1, I2 and I3 confirmed fixed. Recorded with its findings open; resolutions:

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| I24 | Major | follow-up | With I6, a caller cancelled during `close()` skipped the timeout branch, so a publisher facing a failing database retried forever and reported success | fixed: `close()` runs its bound in its own task (`_close_within`); test `test_the_close_bound_holds_when_the_caller_is_cancelled` (fails before the fix) |
| I25 | Nit | follow-up | The fallback reset for a failed checkpoint lookup had no test | fixed: `test_a_failed_checkpoint_lookup_still_opens_with_reset` (fails without the fallback) |
| I26 | Nit | follow-up | The timeout test could not observe a second status; its fake was misnamed | fixed: `HangsAlways` records what it was asked to store; the test asserts one status |
| I27 | Nit | follow-up | An emit racing the publisher's stop was dropped without the warning | fixed: the stop is decided under the buffer lock (`stopped`), so a racing emit is either published or logged |

## 2026-11-18 · verification · phase 01 · pass

Code 499eb63, docs 965e8e8. Report: docs/reviews/phase-2/verification-events.md (acceptance failed once on a test expectation, V1, fixed in 499eb63; re-run, as-built and follow-up passed). Demo: docs/demos/phase-2-events.md.

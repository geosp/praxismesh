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

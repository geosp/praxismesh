# Reviews · Choose Phase 2's event transport

## 2026-11-17 · design-review · plan · round 1 · changes-requested

- Plan at bace810. Three fresh subagents run one at a time, each report committed before the next. Raw reports: docs/reviews/general-event-transport-spike/raw/design-review-round-1-{fresh-reader,codebase-fit,zoom-out}.md.
- Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅. Structure check: 0 errors, 0 warnings.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | zoom out, fresh reader | D2's "no new component, no preview API" ranks Streams below the table, reversing design §4.4 and the decision log's Streams preference without logging it. | fixed: D2 follows §4.4 (owner decision): Streams wins if it passes R1-R7, then the table, then NATS |
| F2 | Major | zoom out, fresh reader | NATS is scope no roadmap document asks for, and under D2 it can win only if both other options fail. | fixed: NATS is a correctness probe (owner decision): R1-R4 and R7 only, load runs only if both others fail (D2, Non-goals) |
| F3 | Major | codebase fit, zoom out, fresh reader | `read()` yields `AgentEvent`s with no offset (`seq` is per attempt and the schema is frozen); R1 treats `from_offset` as exclusive, R2 and the notes as inclusive. | fixed: D1 `read(after)` yields (offset, event) pairs; offsets start at 1; R1/R2 define after-N semantics with a B-1 case; R7 compares events offsets aside |
| F4 | Major | zoom out | One JetStream stream for all workflows gives shared, gappy sequences, not per-workflow gap-free offsets; message-per-event vs per-batch undecided. | fixed: D5 and notes.md#d5 use a stream per workflow and one message per event |
| F5 | Major | zoom out | R3's dedup mechanism is fixed for no option (table has no batch_id record; Streams dedup is per client; JetStream's 2 min window is shorter than Streams' 600 s retry); a long-delay re-send is untested. | fixed: D5 names each option's dedup mechanism; one re-send horizon (600 s, 60 s in tests) for all; R3 adds a near-horizon re-send |
| F6 | Major | codebase fit, zoom out, fresh reader | No route to capture the recorded turn without changing `workers/main.py` (R9); the spike's own uv project cannot import `AgentEvent`. | fixed: D4 and task 1.4 capture through tests/support/dsh_container.py in the root environment; D1 copies AgentEvent, checked in task 1.2 |
| F7 | Major | codebase fit, zoom out, fresh reader | R4 has no interface hook, and R4 and R5 are trivially true for the table and JetStream; D2 doesn't say how a non-applicable requirement counts. | fixed: D1 adds roll_over and expire_below hooks; D2 counts a non-applicable requirement as passed, shown N/A |
| F8 | Major | codebase fit | ADR-0007 requires new attempt write paths (Phase 2 events) to take the fence or justify why not; the plan ignores it, and the options differ. | fixed: R10 and phase 02 task 2.1 assess fencing per option (ADR-0007) |
| F9 | Major | zoom out | R5 checks one 5-min window without Continue-As-New, so it can pass while longer runs or more tailers (Updates) grow history without bound; Continue-As-New is never tested under load. | fixed: R5 measures growth per minute per agent and per tailer and passes with roll-over at the derived interval; notes.md#d5 runs Streams with roll-over off and on |
| F10 | Major | fresh reader | The Summary omits that the spike is isolated, why §4.4's preference isn't simply adopted, and cites D3/D5 for thresholds held in R5/R6. | fixed: Summary states isolation, the §4.4 preference being tested, and cites D1/D5 |
| F11 | Major | fresh reader | DSH, DSH pair and the `default` profile are used but never defined; Why sentence 4 can't be explained from the plan. | fixed: Terms define DSH, the default profile and a DSH pair; Why rewritten |
| F12 | Major | fresh reader, zoom out | D4 says the spike uses the stack's Temporal and PostgreSQL; Risks and tasks say a disposable Compose project. | fixed: D4 uses a disposable Compose project for every run |
| F13 | Major | fresh reader | D5's fairness parameters and R2's expiry hook live only in notes.md; "extra code counts in the report" is not one of D2's criteria. | fixed: D5 lists the mechanisms in the plan; D1 names the hooks; extra code counts in the report (D5, D6) |
| F14 | Nit | codebase fit | `git diff --stat main` should be `main...HEAD`. | fixed: main...HEAD in R9 and tasks |
| F15 | Nit | codebase fit | Links' "(9, 10, 14)" are line numbers, not item numbers. | fixed: Links name the items by text |
| F16 | Nit | codebase fit | No decision-log or §10 record of verified versions is planned. | fixed: D6 and phase 02 task 2.2 add a decision-log entry with verified versions |
| F17 | Nit | codebase fit | Name `asyncpg` 0.32.0, the driver Phase 2 would port to. | fixed: asyncpg 0.32.0 in task 1.1 and notes.md#d5 |
| F18 | Nit | zoom out, fresh reader | R8's rerun can flip R6 near 1 s; no margin or repeat count. | fixed: R6 and R8 require the same result in 3 runs; median and range reported |
| F19 | Nit | zoom out | Load runs publish Streams events from outside an Activity; production publishes from Activities. | fixed: D5 publishes Streams events from an Activity |
| F20 | Nit | zoom out | Rollout omits removing the spike schema, JetStream volume and NATS project. | fixed: Rollout covers make reset and removing the NATS project and volume |
| F21 | Nit | fresh reader | Readability: Why sentence 2 is long; R2, R5, R9 hold several rules; the synthetic load is defined three times; D6's assessment has no role in D2. | fixed: Why split into a list; R2 scenarios explicit; R9 one rule; synthetic load defined in D3 only, D6 assessment feeds the report |

## 2026-11-17 · design-review · plan · round 2 · passed

- Targeted follow-up (docs/reviews/README.md rule 6) on e4dc61d; one fresh `design-reviewer` subagent, checking round 1's fixes and the revised plan against the pinned `temporalio` 1.36.0 source. Raw report: docs/reviews/general-event-transport-spike/raw/design-review-round-2-targeted.md.
- Reviewer: targeted ✅. Round 1's F1, F2 (owner decisions) are stated consistently; F3, F4, F6-F21 confirmed resolved. F5 reopened for Streams (M1 below). Recorded as passed after the fixes below; no third round per the skill's two-round limit.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F22 | Major | targeted (reopens F5) | The Streams client deduplicates only by a random per-client publisher ID and appends in its own Signal handler, so a batch-ID set cannot be checked; the spike's batcher in front of the client's timer also handicaps R6. | fixed: D5 and notes.md#d5 publish each batch as one `publish_batch` Update to the hosting Workflow, which checks the batch-ID set and appends Workflow-side; one transport call per batch for every option |
| F23 | Major | targeted | No reader is fixed for Streams or NATS; Streams' `subscribe()` silently restarts at 0 on a truncated offset (fails R2 by construction), Streams offsets start at 0 and no query gives the retained base. | fixed: D1 expiry by comparing with the retained base; D5 and notes.md#d1, #d5 name each reader (Streams poll Update by Workflow ID with a `retained_base` Query, offset + 1; NATS pull consumer by start sequence); notes.md#verified records the source-level behaviour |
| F24 | Major | targeted | R5 with a roll-over interval derived from results cannot fail, and ignores the carried log against the payload size limit. | fixed: D5 fixes the roll-over trigger (suggested or every 2,000 batches) and retention (last 500 events); R5 uses that policy; new R11 caps the carried state at 50% of the payload limit; task 1.1 records it |
| F25 | Nit | targeted | Task 1.3's suite needs the R7 fixture captured in task 1.4. | fixed: capture is now task 1.3, the suite 1.4 |
| F26 | Nit | targeted | notes.md#d3 says payloads hold SKUs; DSH events hold request IDs, token counts, tool names, call numbers and outcomes. | fixed: notes.md#d3 |
| F27 | Nit | targeted | The capture route (activity or runner) and how a script under the spike imports `tests.support` are unstated. | fixed: notes.md#d3 drives `DshRunner.run` through `DshContainer.runner(sink)` with `PYTHONPATH=.` |
| F28 | Nit | targeted | R8 needs 3 runs of every requirement, but only the load is repeated. | fixed: phase 02 task 1.2 runs the suite 3 times too |
| F29 | Nit | targeted | Whether the roll-over-off Streams run repeats 3 times is unclear. | fixed: one informational run (growth rate), not judged |
| F30 | Nit | targeted | D2 gives no outcome when no option passes. | fixed: D2, a no-go report and the owner decides |

## 2026-11-17 · approved · plan

Approved by the owner after design review passed (2 rounds); phases 01 and 02 approved with it.

## 2026-11-17 · impl-review · phase 01 · round 1 · changes-requested

- Diff f43c2ffafb79bd2cfc6791398cf32acb4d61867d..dfc16fd74dce39d91918c49882d5907d693d7ee5 (code_sha dfc16fd). Three fresh `impl-reviewer` subagents, one at a time; each report committed before the next. Raw reports: docs/reviews/general-event-transport-spike/raw/impl-review-phase-01-round-1-{contract,failure,scope}.md.
- Reviewers: contract ✅ · failure ✅ · scope ✅

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F31 | Major | contract, failure, scope | Streams never maps `TruncatedOffset` to `Expired`: a tailer behind a roll-over's truncation crashes; every option checks expiry only when a read starts, so mid-read truncation skips silently. | fixed: transport.guarded() reports any offset jump as Expired for every option; Streams maps TruncatedOffset to the retained base; test_r2_mid_read (failed on dfc16fd for all four) |
| F32 | Major | contract, failure | No publishing Activity for Streams, as D5 and task 2.2 name. | fixed: notes.md#d5 clarifies that the long-running producing Activity calls the Update (no Activity per batch, so no extra round trip); phase 02's load runner publishes from inside an Activity |
| F33 | Major | contract | Streams catch-up reads use the poll Query (no history, silent clamp to the base), not the poll Update D5 fixes. | fixed: Streams reads only through the poll Update |
| F34 | Major | contract, failure, scope | The R4 check passes with a no-op `roll_over` and never proves a reader crossed a run, or exercises the >500-event truncation and the carried base. | fixed: roll_over returns once a new run started; check_r4_roll_over asserts it while the reader waits; check_r4_truncating_roll_over (600 events, Expired(106), no gap); validated against NeverRolls |
| F35 | Major | contract, failure, scope | R3 never crosses a roll-over, so carrying the batch-ID set across Continue-As-New is untested. | fixed: check_r3_resend re-sends after a roll-over |
| F36 | Major | failure | `close()` terminates Streams Workflows and deletes NATS streams other instances use; a new Streams instance's random queue cannot serve an existing run. | fixed: fixed Streams task queue; close() no longer terminates runs or deletes NATS streams; runs carry a 2 h execution timeout |
| F37 | Major | contract, failure, scope | No Streams or NATS results files; results name a HEAD that lacks the code (no dirty-tree check); infrastructure errors read as `fail`; partial runs overwrite. | fixed: results record commit, dirty flag, horizon, partial runs and setup errors; full results for all four committed at bd6ea37 |
| F38 | Major | contract, scope | The table reader clears its NOTIFY flag after fetching, so a wake-up is lost and the 1 s poll becomes the delivery path (handicaps R6). | fixed: the table reader clears its wake-up before fetching; test_table_notify (1.05 s before the fix) |
| F39 | Nit | contract, failure | R4 is `n/a` for a non-hosted option only when its check passes. | fixed: R4 is n/a for any option without a Workflow |
| F40 | Nit | failure, scope | A JetStream non-follow read loops forever if a purge removes everything through `last` mid-read. | fixed: a purged non-follow JetStream read ends |
| F41 | Nit | failure | `expire_below` past the end sets the table and memory base above the next offset, unlike Streams. | fixed: expire_below caps the base at the next offset (table, memory) |
| F42 | Nit | failure | `capture.py` overwrites the fixture whatever the turn's status; probes use fixed IDs. | fixed: capture.py keeps the fixture unless at least 10 events were captured and writes atomically; probes use unique names |
| F43 | Nit | contract, failure, scope | Unused `StreamInput.batches_this_run` and `ROLL_TIMEOUT`. | fixed: removed |
| F44 | Nit | contract, scope | Streams imports the private `_types._decode_payload` from a preview API. | accepted: recorded as a fragility in notes.md#d5 for the report |
| F45 | Nit | contract, failure, scope | Table pool `max_size=20` and JetStream `inactive_threshold=60` are not D5 parameters; follow readers pin pool connections. | accepted: recorded in notes.md#d5; phase 02 reports them if the load reaches them |
| F46 | Nit | contract | The fixture scan checks payloads only; `blob_ref` is a plain dict and the copy is not `Strict`. | accepted: the copy keeps the root schema's field names (tested); the spike never sets blob_ref |
| F47 | Nit | failure | Temporal limits Updates per run (`TOO_MANY_UPDATES`), including poll Updates; not recorded. | accepted: recorded in notes.md#d5 for phase 02 to verify |
| F48 | Nit | failure, scope | `_retry` swallows every `RPCError` for ~20 s; R7's fixture fits one batch; the R1 tailer is abandoned, not cancelled; task 1.1's "Compose overlay" is an env file. | accepted: spike-scope test and wording details; R1 multi-batch ordering covers R7's single batch |

## 2026-11-17 · impl-review · phase 01 · round 2 · passed

- Targeted follow-up (docs/reviews/README.md rule 6) on dfc16fd..a2c6e0c; one fresh `impl-reviewer` subagent (contract lens, with fairness). Raw report: docs/reviews/general-event-transport-spike/raw/impl-review-phase-01-round-2-contract.md.
- Reviewer: contract ✅. Round 1's F31, F33-F36, F38-F43 confirmed enforced; F32 confirmed as a documentation clarification; F37 reopened in part (F50). No fix favours or handicaps one option. Recorded as passed after the fixes below (69c95c4), per the skill's two-round limit; suite results for all four options at 69c95c4.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F49 | Major | contract | `check_r2_mid_read` accepted an expiry naming any base, so a reader losing retained events after a removal would pass. | fixed: the check requires `Expired(50)` then 50-110; ResumesPastBase validation variant fails it (passed the old check) |
| F50 | Major | contract (reopens F37) | A test-ID, `-x` or `--deselect` run wrote `"partial": false` and a synthesized full-suite command. | fixed: partial whenever any requirement test of tests/test_suite.py did not report for an option; the command is recorded as run; tests/test_results_file.py |
| F51 | Nit | contract | The Streams docstring still described Query reads. | fixed |
| F52 | Nit | contract | R3 ignored whether the roll-over happened. | fixed: hosted options assert it |
| F53 | Nit | contract | Teardown failures are not recorded. | accepted: close() releases connections only; a failure would surface in the pytest output |
| F54 | Nit | contract | All results files come from one multi-transport session. | fixed: the command records SPIKE_TRANSPORTS as run |
| F55 | Nit | contract | A removal through the end of the log during a read yields no expiry until a later event arrives. | accepted: the same for every option; recorded for the report |
| F56 | Nit | contract | F40 and F41 have no failing test. | accepted: edge cases of test hooks outside the load path |
| F57 | Nit | contract | capture.py's guard checks only the event count. | accepted: a failed turn raises before writing; a normal end with ≥ 10 events is a valid recording |
| F58 | Nit | contract | Streams' fixed queue and 2 h run timeout are not listed with the other added parameters. | fixed: notes.md#d5 |

## 2026-11-18 · phase 01 verification deferred

Owner decision: phase 01 stays in-progress (impl review passed) and one `verify-phase` run covers both phases at the end of phase 02, which adds the load runs and the report that verification checks anyway.

## 2026-11-18 · impl-review · phase 02 · round 1 · changes-requested

- Diff 5371368db80b232b2f155fd5ef0a8c6dd3c0df16..4d6c4cae9e55134bce942e0202e4955549d636d1 (code_sha 4d6c4ca). Three fresh `impl-reviewer` subagents, one at a time; each report committed before the next (the scope reviewer was resumed once after a usage-limit stop). Raw reports: docs/reviews/general-event-transport-spike/raw/impl-review-phase-02-round-1-{contract,failure,scope}.md.
- Reviewers: contract ✅ · failure ✅ · scope ✅. None of the findings changes the D2 outcome or the owner's choice.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F59 | Major | contract, failure, scope | The report gives medians without ranges; container CPU is from run 1 only, and "4x" database CPU is the most favourable run (3 runs: 1.7-4.1x). | fixed: the report gives median (range) over 3 runs for every figure, CPU included; database CPU 3.2x (1.7-4.1x), Temporal 20-23x |
| F60 | Major | contract, failure, scope | The growth results file has no commit or command, mixes 12 entries from earlier runs with the 4 growth entries, comes from a probe added after c1fda62, and the growth load in measure.sh never wrote its file; task 1.1's per-tailer growth metric was never built. | fixed: results/streams-growth-norollover.provenance.json keeps the 4 growth runs with the probe's commit and command; the report says the run stalled and wrote no file, and that per-tailer growth was inferred from Update counts |
| F61 | Major | contract (failure, scope as Nits) | The load generator is closed-loop: Streams' slower publishes gave it ~5% less load (54.9k vs 58.0k events) and hide latency during stalls; the comparison is not at equal offered load. | fixed: load.py is open-loop (test_a_slow_transport_still_gets_the_offered_rate failed on the old runner: 69 of 100); three open-loop table runs at 5854ca2 pass at the full offered load; the report and ADR-0009 disclose the closed-loop bias, which favoured Streams |
| F62 | Major | contract (failure, scope as Nits) | measure.sh never resets the stack between runs, as the plan's Rollout and Risks promise; earlier Streams runs stay Running and table rows accumulate. | fixed: measure.sh resets the stack before every run; the report discloses that the c1fda62 runs had no reset |
| F63 | Major | contract (scope as Nit) | R11's 298 KB was measured before the batch-ID set reached steady state (5 min < 600 s horizon) and is not only "the last 500 events". | fixed: the report describes the carried state (last 500 events plus the batch-ID set) and its extrapolation to ~360 KB at the 600 s horizon, not measured |
| F64 | Major | failure | Agent Activities retry forever with no Workflow timeout; after a stalled run is killed, orphaned agents are picked up by the next run's worker and add hidden load. | fixed: one attempt per agent, a Workflow timeout and cleanup on exit; test_a_failing_transport_ends_the_run_and_leaves_no_agent_running found 8 orphaned agents on the old code |
| F65 | Major | scope | The report and notes extrapolate roll-over timing (~100 s, ~36 s) past the measured load and treat the 2,000-Update cap as the roll-over interval; measured roll-over was every ~40 s, driven by Temporal's size suggestion. | fixed: the report and notes state only the measured roll-over (~40 s, on Temporal's size suggestion; the 2,000-batch trigger cannot fire first) and give other loads as an unmeasured risk |
| F66 | Nit | contract | NATS's committed suite result predates `check_r1_cancel`. | fixed: the report's R8 row says NATS's suite result predates check_r1_cancel |
| F67 | Nit | contract | Some operating-cost cells cite facts not in notes.md#verified. | fixed: unsourced claims removed; the Helm deployment added to notes.md#verified with its source |
| F68 | Nit | contract | "Owner attention" still opens as if the ADR were for Streams. | fixed: the section is now 'Weighing the outcome' |
| F69 | Nit | contract | R5's "4.50 MB" is decimal while the bound in load.py is 5 MiB. | fixed: units stated (decimal MB against a 5 MiB bound) |
| F70 | Nit | contract | Summed `ByteSize()` approximates Temporal's history-size accounting; the agent Workflows' runs are not measured. | accepted: the report states the approximation and that the agents' own runs (one Activity each) were not measured |
| F71 | Nit | contract, scope | load.py keeps dead `hosted` branches (which would raise on None) and the NATS container name. | fixed: dead branches and the NATS container name removed; judge() treats a missing value as a fail |
| F72 | Nit | contract | "Extra code" counts are whole-file line counts. | fixed: labelled whole-file line counts at 1bfac67 |
| F73 | Nit | contract | probes/README.md's last row is detached from its table. | fixed |
| F74 | Nit | contract | The decision-log entry lacks the winner's server versions. | fixed: ParadeDB 0.26.6 (PostgreSQL 16) and Temporal server 1.32.2 added |
| F75 | Nit | contract | R5/R6/R11 judging and `percentile()` have no unit test. | fixed: judge() with test_judging_applies_the_thresholds |
| F76 | Nit | failure, scope | Batch IDs restart per Activity attempt, so a retried attempt's events would be dropped as re-sends. | fixed: batch IDs are <workflow>:<attempt>:<n>; test_batch_ids_name_the_attempt |
| F77 | Nit | failure | The Activity heartbeats only after a flush; a long-blocked publish times out while its coroutine keeps running. | accepted: an agent now has one attempt, so a timed-out attempt is not retried alongside a running one |
| F78 | Nit | failure | An aborted measure.sh leaves a results directory mixing invocations; results files are overwritten in place, non-atomically. | fixed: results are written atomically; measure.sh resets before each run |
| F79 | Nit | failure | load.py has no try/finally around its run; check_r1_cancel can hang rather than fail on a reader that swallows cancellation. | fixed: load.py's run is in try/finally; accepted: check_r1_cancel hanging on a swallowing reader is itself the observable failure (it caught the Streams bug) |
| F80 | Nit | failure | Nothing shows task 3.1's reset happened; the table fence's lock order against ADR-0007's writers is unstated. | fixed: the stack was reset before the open-loop runs (5854ca2 results); accepted: the fence's lock order is for Phase 2 to set, as the report now says |
| F81 | Nit | scope | Streams' RUN_TIMEOUT covers the whole Continue-As-New chain, not each run; the report's limits row omits it and the fixed queue. | fixed: notes and the report's limits row |
| F82 | Nit | scope | The table uses one global NOTIFY channel, so every follower wakes for every workflow's batch; with the pool at 20, 17+ followers in one process block publishers. | fixed: ADR-0009's consequences and the report's limits row |

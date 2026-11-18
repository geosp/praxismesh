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

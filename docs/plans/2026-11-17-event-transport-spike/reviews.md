# Reviews · Choose Phase 2's event transport

## 2026-11-17 · design-review · plan · round 1 · changes-requested

- Plan at bace810. Three fresh subagents run one at a time, each report committed before the next. Raw reports: docs/reviews/general-event-transport-spike/raw/design-review-round-1-{fresh-reader,codebase-fit,zoom-out}.md.
- Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅. Structure check: 0 errors, 0 warnings.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | zoom out, fresh reader | D2's "no new component, no preview API" ranks Streams below the table, reversing design §4.4 and the decision log's Streams preference without logging it. | open |
| F2 | Major | zoom out, fresh reader | NATS is scope no roadmap document asks for, and under D2 it can win only if both other options fail. | open |
| F3 | Major | codebase fit, zoom out, fresh reader | `read()` yields `AgentEvent`s with no offset (`seq` is per attempt and the schema is frozen); R1 treats `from_offset` as exclusive, R2 and the notes as inclusive. | open |
| F4 | Major | zoom out | One JetStream stream for all workflows gives shared, gappy sequences, not per-workflow gap-free offsets; message-per-event vs per-batch undecided. | open |
| F5 | Major | zoom out | R3's dedup mechanism is fixed for no option (table has no batch_id record; Streams dedup is per client; JetStream's 2 min window is shorter than Streams' 600 s retry); a long-delay re-send is untested. | open |
| F6 | Major | codebase fit, zoom out, fresh reader | No route to capture the recorded turn without changing `workers/main.py` (R9); the spike's own uv project cannot import `AgentEvent`. | open |
| F7 | Major | codebase fit, zoom out, fresh reader | R4 has no interface hook, and R4 and R5 are trivially true for the table and JetStream; D2 doesn't say how a non-applicable requirement counts. | open |
| F8 | Major | codebase fit | ADR-0007 requires new attempt write paths (Phase 2 events) to take the fence or justify why not; the plan ignores it, and the options differ. | open |
| F9 | Major | zoom out | R5 checks one 5-min window without Continue-As-New, so it can pass while longer runs or more tailers (Updates) grow history without bound; Continue-As-New is never tested under load. | open |
| F10 | Major | fresh reader | The Summary omits that the spike is isolated, why §4.4's preference isn't simply adopted, and cites D3/D5 for thresholds held in R5/R6. | open |
| F11 | Major | fresh reader | DSH, DSH pair and the `default` profile are used but never defined; Why sentence 4 can't be explained from the plan. | open |
| F12 | Major | fresh reader, zoom out | D4 says the spike uses the stack's Temporal and PostgreSQL; Risks and tasks say a disposable Compose project. | open |
| F13 | Major | fresh reader | D5's fairness parameters and R2's expiry hook live only in notes.md; "extra code counts in the report" is not one of D2's criteria. | open |
| F14 | Nit | codebase fit | `git diff --stat main` should be `main...HEAD`. | open |
| F15 | Nit | codebase fit | Links' "(9, 10, 14)" are line numbers, not item numbers. | open |
| F16 | Nit | codebase fit | No decision-log or §10 record of verified versions is planned. | open |
| F17 | Nit | codebase fit | Name `asyncpg` 0.32.0, the driver Phase 2 would port to. | open |
| F18 | Nit | zoom out, fresh reader | R8's rerun can flip R6 near 1 s; no margin or repeat count. | open |
| F19 | Nit | zoom out | Load runs publish Streams events from outside an Activity; production publishes from Activities. | open |
| F20 | Nit | zoom out | Rollout omits removing the spike schema, JetStream volume and NATS project. | open |
| F21 | Nit | fresh reader | Readability: Why sentence 2 is long; R2, R5, R9 hold several rules; the synthetic load is defined three times; D6's assessment has no role in D2. | open |

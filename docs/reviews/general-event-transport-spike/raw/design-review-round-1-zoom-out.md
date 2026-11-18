<!-- Verbatim subagent report (design-review round 1, zoom out, plan at bace810); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Design review round 1 (zoom-out): event-transport spike, plan at bace810

Scope: plan.md, phases/01, phases/02 and notes.md at bace810 (the working tree matches), ADRs 0001-0008, and the code they touch.

## Findings

### F1 · Major · plan.md › Decisions › D2 (and Why); phase-2 item 9
**What's wrong.** D2 reverses the project's recorded transport preference, and the plan doesn't log that as a decision change. The roadmap asks one question: are Streams suitable, and if not, what is the fallback? The plan turns that into a three-way bake-off whose tie-break rule ranks Streams below the PostgreSQL table.

**Evidence.**
- D2 says: "Among those that pass, prefer no new component and no preview API". Streams is the preview API and NATS is the new component. So whenever the table passes R1-R7, it wins before any number is compared.
- That reverses design §4.4 ("Prefer Temporal Python Workflow Streams where supported and stable enough ... narrow fallback behind an event-transport interface"). It also reverses decision-log line 87 ("Prefer Workflow Streams (verify preview API) for observation").
- docs/roadmap/phases/phase-2.md:9 says: "Verify and adopt Temporal Python Workflow Streams if suitable; otherwise add a minimal offset-based transport". PROJECT_PLAN.md:222 makes the fallback's trigger a measured one: "history per busy run above the set bound".
- The plan's "Decision log" section is empty. AGENTS.md says changes to architecture and constraints must go into docs/roadmap/decision-log.md.

**Fix.** Do one of two things:
- State the reversal openly, with the reason ("preview API" alone is already known and was accepted in §4.4), and log it.
- Or make D2 match §4.4: Streams wins if it passes R1-R7, and the fallback is chosen only when Streams fails.

### F2 · Major · plan.md › What changes / D5 / Risks; notes.md#d5 (NATS JetStream)
**What's wrong.** NATS JetStream is extra scope that no document asks for, and D2 almost guarantees it can't win.

**Evidence.**
- `grep -i nats` over PROJECT_PLAN.md and docs/roadmap/ finds nothing.
- Under D2, NATS can win only if both Streams and the table fail R1-R7. It is also the option that needs the most new machinery: a Compose file, a pinned image, an operating-cost assessment for a new service (phase 02 task 2.1), and deletion in task 3.1.

**Smaller change.** Implement Streams and the table. Add JetStream only if both fail a must-pass requirement, and write that condition into D2. This removes roughly a third of phase 01 and part of phase 02 without changing any outcome D2 can reach.

### F3 · Major · plan.md › Decisions › D1; notes.md#d1; Requirements R1/R7
**What's wrong.** The interface never gives the reader the offset it needs to resume.

**Evidence.**
- `read()` yields `AgentEvent | Expired`.
- `AgentEvent` has no offset field. Its only counter is `seq`, which counts per attempt (common/schemas/events.py:31, 35; harness_activity/events.py:38-53 restarts `seq` at 0 for each `AttemptEvents`).
- Notes say "Offsets are per workflow, assigned by the transport".

**Consequences.**
- A tailer can't learn its "last offset" for R1 unless implementations overwrite `seq`.
- If they do overwrite `seq`, R7 ("the events equal the recording") fails by construction, and the attempt-level `seq` that phase-2.md:10 requires is lost.
- The three implementations will each improvise an answer to this, which is exactly the uneven effort D5 is meant to prevent.

**Fix.** Have `read` yield `(offset, AgentEvent)` or a wrapper type, and say that R7 compares the events with the offsets removed.

### F4 · Major · notes.md#d5 (NATS row) vs notes.md#d1
**What's wrong.** The JetStream configuration can't produce the offsets D1 promises.

**Evidence.**
- D1 requires per-workflow, gap-free offsets.
- D5 puts every workflow into one stream (`events`, subject `events.<workflow_id>`) and resumes with `by_start_sequence`. JetStream stream sequences are shared across all subjects in the stream, so one workflow's sequence numbers have gaps wherever another workflow published.
- It is also undecided whether a batch is one message (offsets would count batches, not events) or N messages with N `Nats-Msg-Id`s.

**Consequence.** Either the JetStream option fails R1/R4 for a configuration reason, or it needs an offset-mapping layer that the other options don't. Both outcomes skew the comparison.

**Fix.** Decide the mapping in notes.md#d5 before any code is written: stream per workflow, or a transport-side offset in a header, and message-per-event versus message-per-batch.

### F5 · Major · notes.md#d5; plan.md › Requirements R3; Risks bullet 1
**What's wrong.** The deduplication mechanism behind R3 is fixed for only one option. Risk 1's mitigation ("D5 fixes mechanisms and parameters before measuring") doesn't hold for the requirement where the options differ most.

**Evidence.**
- **PostgreSQL row:** "`(workflow_id, offset)` primary key, a per-workflow counter row". Nothing records `batch_id`, so a re-sent batch gets new offsets and duplicates. The fix (a batch-ID table or a unique key written in the same transaction as the counter bump) is left for the implementer to invent.
- **Streams:** notes describe a client-internal "dedup table" and say "A retried attempt is a fresh publisher". Nothing says how the interface's caller-supplied `batch_id` reaches `WorkflowStreamClient`. If the wrapper calls `publish` again after a timeout, the client will most likely treat it as new data.
- **JetStream:** the 2-minute duplicate window is shorter than Streams' 600 s `max_retry_duration`, which notes list as an installed default. A re-send after 2 minutes duplicates silently.

**Consequence.** R3 tests a re-send right after the first send, so all three options pass, and the difference that matters in production (a re-send after a long timeout) goes unmeasured.

**Fix.** Write each option's R3 mechanism into D5. Add an R3 case that re-sends after the longest retry delay the publisher allows.

### F6 · Major · phases/01 task 1.4; plan.md › Requirements R9, Decisions › D4
**What's wrong.** No mechanism is given for capturing the recorded turn "on the `dsh` profile with a JSON-lines recording sink", and every obvious route breaks a constraint.

**Evidence.**
- The production worker builds `DshRunner(control, UsageLedgerRepository(engine), blobs, pinned=pinned)` with no sink (workers/main.py:97), so it falls back to `NoOpSink` (harness_activity/dsh/runner.py:238).
- Running the benchmark profile with a recording sink therefore means changing workers/main.py, which R9 forbids.
- The other route is driving `DshRunner` directly from the spike. But the spike is a separate uv project, and the root project can't be installed as a dependency (pyproject.toml `[tool.uv] package = false`). Task 1.1's dependency list also omits pydantic and any path to `common`/`harness_activity`.

**Smaller route.** The repository already captures DSH events with `MemorySink` through `tests/support/dsh_container.py:112-115` and tests/integration/test_dsh_activity.py:127. A small root-side script or test that dumps that sink, or a hand-built fixture, would meet R7. The phase file should name the route.

### F7 · Major · plan.md › Requirements R5; notes.md#d5 (Streams row)
**What's wrong.** R5 doesn't measure what "bounded" means, and it can pass while a real run grows without limit.

**Evidence.**
- D5 disables Continue-As-New during load runs ("so R5 measures one run's growth"). R5 then checks a fixed 5-minute window against 10% of the per-run limit.
- Streams history grows linearly with time. Per notes, it also grows with observers ("subscriptions as long-poll Updates"), and accepted Updates are recorded in history.
- An agent that streams for an hour, or has more than 3 observers, can exceed the limit even though R5 passed.
- The only mechanism that keeps a Streams history bounded is Continue-As-New. That is tested only in the idle R4 test, never under load with tailers attached.
- PROJECT_PLAN.md:72 explicitly warns: "bound the number of events, Signals, Updates ... use Continue-As-New deliberately".

**Fix.** Report the growth rate (events and bytes per minute, per tailer). Derive the Continue-As-New interval it implies. Run one load pass with Continue-As-New on, so R4 is checked under load.

## Nits

- plan.md › R1 vs R2 / notes.md#d1: is `from_offset` inclusive or exclusive? R1 reads "reconnects from N ... receives N+1" (exclusive), while R2 reads "asks for B-10 ... events from B" and notes say "`Expired` when from_offset < retained_base". Under exclusive semantics, `from_offset = B-1` loses nothing but would still be reported as expired. Pin one convention before writing the shared suite.
- plan.md › D4 vs Risks / phase 01 task 2.1: D4 says "uses the stack's existing Temporal and PostgreSQL", while Risks and the tasks say "disposable Compose project". The plan should say which one, and if it is the shared stack, how the spike schema is dropped afterwards.
- plan.md › D1 / phase 01 task 1.1: `AgentEvent` lives in the root project, which isn't installable. The plan should say whether the spike copies the schema (and accepts drift) or imports it by path.
- plan.md › R4: PostgreSQL and NATS sit outside the Workflow, so R4 passes for them trivially. The report should say R4 tells the options apart only for Streams, so the result isn't read as evidence for the others.
- plan.md › R8: the p95 latency in R6 measured on a shared dev machine can flip pass/fail near 1 s when rerun. Require reruns to reproduce only pass/fail with a stated margin, or record how many runs were done.
- notes.md#d5 (Streams): the load runner publishes from outside an Activity, but production publishes with `from_within_activity()`. Note the difference, or publish from an Activity in the load run.
- plan.md › Rollout & rollback: "N/A" is acceptable for a spike, but it should also cover removing the spike PostgreSQL schema, the JetStream volume and the NATS Compose project, since D4 allows the shared stack.

## Summary

The spike answers the right question: Streams versus a fallback, decided by measurement. But D2's ordering reverses the recorded preference without logging the change (F1), and NATS adds scope that D2 makes nearly unwinnable (F2). Four gaps in the interface and mechanism definitions (F3-F6) would make each implementer improvise, which is the uneven-effort risk the plan itself names. R5 needs to measure growth rate and Continue-As-New under load to support a claim of bounded history (F7). Rollout is correctly N/A apart from the cleanup nit.

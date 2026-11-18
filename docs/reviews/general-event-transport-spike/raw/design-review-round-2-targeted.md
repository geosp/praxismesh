<!-- Verbatim subagent report (design-review round 2, targeted follow-up, plan at e4dc61d); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Design review round 2 (targeted follow-up) · event-transport spike plan @ e4dc61d

Scope: plan.md, phases/01, phases/02, notes.md, reviews.md round 1, ADRs 0001-0008, AGENTS.md. Code evidence is from the commit, plus the `temporalio` 1.36.0 source installed in the root `.venv`. That is the same version the spike pins (uv.lock:2314-2315).

## Round 1 resolutions

- **F1, F2 (owner decisions).** Stated the same way everywhere: Summary ("Streams wins if it passes every must-pass requirement; otherwise the table, then NATS (D2)"), the diagram ("NATS JetStream ── suite only"), Non-goals, D2, and the phase 02 Goal. They stay closed.
- **F3, F4, F6-F8, F10-F21.** Resolved as written. F6 has a small gap (Nit N3).
- **F5: reopened for Streams only** (Major M1). The table and NATS dedup mechanisms are fine. The Streams mechanism D5 names cannot be built on the publish path D5 also names.
- **F9.** Its fix introduces a new problem (Major M3).

## Findings

### M1 · Major · plan.md Decisions › D5 (Streams), notes.md#d5 "Workflow Streams" row · reopens F5

**What is wrong.** D5 fixes two things for Streams that cannot work together:
- publishing through "`WorkflowStreamClient.from_within_activity()` in a publishing Activity"
- dedup through "a batch-ID set in Workflow state"

**Evidence.** In the pinned SDK, the client sends every flush as the built-in `__temporal_workflow_stream_publish` Signal (`temporalio/contrib/workflow_streams/_client.py:463-470`). Its dedup identity is a random per-client `publisher_id` and a sequence number (`_client.py:158-159`). Neither can be set by the caller. `WorkflowStream.__init__` registers the Signal's handler itself (`_stream.py:158`). `_on_publish` appends the items straight to the log after checking only `(publisher_id, sequence)` (`_stream.py:368-394`). The hosting Workflow has no hook to consult a batch-ID set before the append.

**Consequences.**
- R3 re-sends a batch with the same batch ID, which means a new client and a new `publisher_id`. Built as D5 says, Streams stores that batch twice and fails R3 because of the plan, not because of the option.
- To dedup, the spike has to bypass the client's publish path: either a custom Signal or Update into the Workflow, which then publishes Workflow-side through `stream.topic(...)`, or filtering at read time. Either way it departs from D5's fixed mechanism.
- Fairness: the client also buffers on its own `batch_interval` timer. The spike's own 200 ms / 64-event batcher (notes.md#d5 "All" row) sits in front of it. Without `force_flush=True`, a Streams event can wait up to two 200 ms intervals, while the table and NATS wait one. That handicaps Streams on R6.

**Fix.** D5 should name the actual Streams publish and dedup path, and say how a spike batch maps to one client flush (for example `force_flush` per batch).

### M2 · Major · plan.md D5; notes.md#d5; notes.md#verified (Streams bullet "whether the caller is told is not documented")

**What is wrong.** D5 fixes a read mechanism only for the table ("`NOTIFY` per batch; readers fall back to a 1 s poll"). It fixes none for Streams or NATS. For Streams the choice decides R2, R4 and R6.

**Evidence.** The pinned source answers the question notes.md#verified leaves open:
- The poll Update raises `ApplicationError` type `TruncatedOffset` for a nonzero `from_offset` below the base (`_stream.py:411-416`).
- `from_offset == 0` never raises.
- `WorkflowStreamClient.subscribe()` catches `TruncatedOffset` and silently restarts at offset 0 (`_client.py:606-608`).

So a Streams reader built on `subscribe()` fails R2 by construction. A reader that calls the poll Update directly can meet R2, but then loses `subscribe()`'s automatic Continue-As-New following (`_client.py:612-624`), which R4 depends on. It also chooses its own poll cooldown (default 100 ms, `_client.py:523`), which moves R6.

Smaller points the reader also has to handle:
- Streams offsets start at 0 (`_stream.py:154`, `:427`); D1 says offsets start at 1.
- No query returns the retained base. `__temporal_workflow_stream_offset` returns base plus length (`_stream.py:472-475`). So `Expired(retained_base)` for `after=0` has to be inferred.

The NATS reader is also left open: an ordered consumer, or `by_start_sequence` on a plain consumer.

**Fix.** Fix each option's reader in D5 before measuring: the Streams poll path, the CAN-following, the cooldown, and the NATS consumer type. Update notes.md#verified with the source-level behaviour.

### M3 · Major · plan.md Requirements › R5; Decisions › D5; notes.md#d3, notes.md#d5; phase 02 task 1.2

**What is wrong.** R5 as revised cannot fail, and it leaves out the limit most likely to bind.

**Evidence, part 1: the criterion is circular.**
- R5 passes "with roll-over at the interval the measured growth implies".
- Task 1.2 derives that interval from a roll-over-off run.
- If the interval is chosen so that each run stays under 10%, every run stays under 10% by definition, however short the interval.
- No rule for deriving the interval is fixed ahead of time, and nothing says an impractically short interval counts as a fail. That conflicts with D5's own "Rejected: tuning after first results".

**Evidence, part 2: the carried log is ignored.**
- `WorkflowStream.continue_as_new` carries the whole retained log in the next run's arguments (`_stream.py:259-269`, `get_state`).
- The synthetic load produces about 15k events per agent in 5 minutes (notes.md#d3). At a few hundred bytes per serialized `AgentEvent`, that is several MB.
- Unless the load truncates the log, the carried state soon passes Temporal's per-payload size limit (2 MB by default). A run's first event alone would also approach the 10% history-bytes threshold.
- Neither D3 nor D5 says whether the load truncates the Streams log (`expire_below`) before roll-over, or how much it retains.
- Task 1.1 records only the "per-run history limits", not the payload size limit.

As written, R5's result for Streams depends on a retention choice made after the first results, which is the unfairness D5 exists to prevent. It also bears on AGENTS.md's hard constraint: "bounded histories that carry references rather than large payloads".

**Fix.** Fix these up front:
- the roll-over trigger: a fixed event or byte threshold, or `workflow.info().is_continue_as_new_suggested()`
- the Streams retention policy under load
- a fail condition, for example a minimum roll-over interval or a maximum carried-state size

Also add the payload size limit to task 1.1.

### Nits

- N1 · phase 01 tasks 1.3/1.4: task 1.3's suite includes R7 and must pass on the reference implementation, but the R7 fixture only appears in task 1.4. Reorder, or let 1.3 use a stand-in fixture.
- N2 · notes.md#d3 "Payloads hold SKUs, tool names and token counts only": the DSH events carry `request_id`, `input_tokens` and `output_tokens` (`harness_activity/dsh/gateway.py:319-323`), and `tool`, `call` and `status` (`harness_activity/dsh/executor.py:175-177`). There are no SKUs.
- N3 · plan.md D4 / phase 01 task 1.4 (F6 residue): "drives `t01-order-total` once through `tests/support/dsh_container.py`" does not say whether the capture goes through `HarnessActivities`, which needs PostgreSQL (`harness_activity/activity.py:207-208`, as in `tests/integration/test_dsh_activity.py:127-150`), or through `DshRunner.run` directly. It also does not say how a script under `spikes/event-transport/` imports `tests.support` (the hyphen rules out `-m`).
- N4 · plan.md R8 vs phases: R8 needs each requirement's result to match across 3 runs, but only the load (phase 02 task 1.2) runs 3 times. No task reruns the suite (R1-R4, R7) 3 times.
- N5 · phase 02 task 1.2: "3 times per measured option … once with roll-over off … then with roll-over at the derived interval" does not say whether the roll-over-off Streams run is also repeated 3 times.
- N6 · plan.md D2: no outcome is stated for the case where no option passes R1-R7 (report a no-go or a §4.4 fallback?).

Verdict: changes-requested

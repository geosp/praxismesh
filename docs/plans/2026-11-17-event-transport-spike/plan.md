---
title: Choose Phase 2's event transport
status: implemented
created: 2026-11-17
updated: 2026-11-17
design_review: { status: passed, rounds: 2, last: 2026-11-17 }
approved: 2026-11-17
adr_review: null
---

# Choose Phase 2's event transport

## Summary

Phase 2 streams agent progress, token and tool events to observers (`agentctl tail`, later the
gateway and the UI). Design §4.4 prefers Temporal Workflow Streams, with a fallback behind an
interface, but Streams is still a preview API and its expiry and history behaviour is not
documented well enough to adopt it blind. This isolated spike tests that preference: it builds
one event-transport interface for Streams and for a PostgreSQL event table, probes NATS JetStream
on correctness only, and runs one shared suite and two workloads. Streams wins if it passes every
must-pass requirement; otherwise the table, then NATS (D2). Nothing in production changes; Phase 2
ports the winner. The main risk is an unfair comparison, so mechanisms and parameters are fixed in
D1 and D5 before code.

```text
recorded DSH turn ─┐                     ┌─ Workflow Streams ── suite + load ─┐
synthetic load ────┼─> EventTransport ───┼─ PostgreSQL table ── suite + load ─┼─> report -> ADR
                   │   (D1)              └─ NATS JetStream ──── suite only ───┘
```

## Why

Design §4.4 says to "prefer Temporal Python Workflow Streams where supported and stable enough",
with a narrow fallback behind an event-transport interface. A check on 2026-11-17 (notes.md#verified)
found four open questions:
- Streams is still Public Preview.
- Each Streams batch adds history events, with no documented rate.
- Streams does not deduplicate a retried attempt's events.
- Neither Streams nor JetStream documents what a reader sees for an expired offset, which §4.4
  requires us to report.

The DSH harness now runs the `default` profile, so the OpenAI Agents SDK plugin, which can publish
model events to a stream for free, no longer covers the main path. These questions need
measurement before Phase 2's first phase builds on the answer.

## What changes

- A new isolated spike, `spikes/event-transport/`, with its own uv project: the interface, three
  implementations, a shared suite, two workloads and a load runner.
- A committed recording of one real DSH benchmark task's events.
- A comparison report in `docs/spikes/` and a proposed ADR for the winner.

### Non-goals

- The agent-to-agent inbox and `comms_mcp` (Phase 2's agent messaging tools): they stay
  PostgreSQL (§4.4) and belong to Phase 2.
- Production code: no worker, Workflow, schema, lock or Compose service changes.
- Streaming token deltas from the DSH runner: the synthetic load models them (D3).
- NATS load runs, unless both other options fail (D2).

## Terms

- **DSH**: DeepSeek Harness, the agent runtime running inside Temporal Activities (ADR-0005).
- **`default` profile**: the agent profile a task uses when it names none; it runs on DSH.
- **DSH pair**: one worker plus its paired DSH container; it runs one attempt at a time. The local
  stack has two.
- **Event transport**: stores `AgentEvent`s per workflow and serves them to readers from an offset.
- **Offset**: a per-workflow, gap-free event number assigned by the transport, starting at 1.
- **Retained base**: the lowest offset a transport still holds for a workflow.
- **Batch**: events published together, identified by a batch ID; the unit of deduplication.
- **Re-send horizon**: the longest time after which a publisher may re-send a batch: 600 s,
  Streams' default retry duration, for every option.
- **Roll-over**: Continue-As-New of the Workflow that hosts a Streams log; a no-op for the others.
- **Tailer**: a reader following one workflow's events live.
- **Recorded turn**: the events of one real DSH benchmark task, captured once and replayed.
- **Synthetic load**: the D3 workload of streamed token deltas and tailers.
- **`AgentEvent`**: the existing event schema: `seq` (per attempt), timestamp, workflow, task and
  attempt IDs, type, small payload.
- **Fence**: ADR-0007's rule that a superseded attempt's writes are refused.

## Requirements

### R1 · Readers resume after their offset

A reader that asks for events after offset N must receive every retained event with a higher
offset, in order, and none with offset N or lower.
- **Given** a tailer killed after offset N, **when** it reads after N, **then** it gets N+1 onwards in order with no repeat.

### R2 · An expired offset is reported

When an event after the requested offset is no longer retained, the reader must first get an
expiry report naming the retained base.
- **Given** events below offset B removed, **when** a reader asks for events after B-10, **then** it gets an expiry report naming B, then B onwards.
- **Given** events below B removed, **when** a reader asks for events after B-1, **then** it gets B onwards and no expiry report.

### R3 · A re-sent batch is stored once

A batch re-sent with the same batch ID within the re-send horizon must not create a second copy.
- **Given** a batch published, **when** it is re-sent at once and again just inside the horizon, **then** each event appears once.

### R4 · Offsets survive roll-over

A workflow's offsets must stay continuous across a roll-over.
- **Given** a reader at offset N during a roll-over, **when** more events arrive, **then** it gets N+1 onwards with no gap or repeat.

### R5 · History stays bounded

Under the synthetic load, with D5's fixed roll-over policy, no Workflow run may exceed 10% of
Temporal's per-run history limits.
- **Given** the synthetic load with D5's roll-over policy, **when** it finishes, **then** every run's history events and bytes are under 10% of the limits recorded in task 1.1.

### R11 · The carried state stays small

The state a Streams run carries into its next run must stay under 50% of Temporal's per-payload
size limit.
- **Given** the synthetic load with D5's roll-over policy, **when** a run continues as new, **then** its carried state is under 50% of the payload limit recorded in task 1.1.

### R6 · Events reach tailers quickly

Under the synthetic load, publish-to-display latency must be at most 1 s at the 95th percentile.
- **Given** the synthetic load, **when** tailers record arrival times, **then** p95 latency is ≤ 1 s in each of 3 runs.

### R7 · The recorded turn replays exactly

The recorded turn, published and read back, must equal the recording, offsets aside.
- **Given** the recorded turn, **when** it is published and read back, **then** the events equal the recording in content and order.

### R8 · Results are reproducible

Each requirement's pass or fail must be the same in all 3 runs of a committed command.
- **Given** the report, **when** its commands run 3 times on its commit, **then** every pass/fail result matches; measurements are reported as median and range.

### R9 · Production stays unchanged

The spike's diff must stay inside `spikes/` and `docs/`.
- **Given** the spike branch, **when** `git diff --stat main...HEAD -- . ':!spikes' ':!docs'` runs, **then** it is empty.

### R10 · Stale attempts are assessed

The report must state, for each option, how a superseded attempt's events would be fenced, or
why they need not be (ADR-0007).
- **Given** the report, **when** it is read, **then** each option has a fencing statement with the mechanism or the reason.

## Decisions

### D1 · One interface, with test hooks
`EventTransport` has `publish(workflow_id, batch_id, events)`, `read(workflow_id, after)` yielding
`(offset, event)` pairs or one `Expired(retained_base)` first, and `latest(workflow_id)`. Test hooks:
`expire_below(workflow_id, offset)` for R2 and `roll_over(workflow_id)` for R4. Every reader finds
expiry by comparing `after` with the transport's retained base. Attempt resets stay above the
interface. The spike keeps its own copy of the `AgentEvent` schema. Rejected: each option's native
API (tests would differ). Details: notes.md#d1

### D2 · Follow §4.4: Streams first
Streams wins if it passes R1-R7 and R11. Otherwise the table wins if it passes them. NATS is a
probe: it runs R1-R4 and R7 only, and gets load runs and the chance to win only if both fail. A
requirement that does not apply to an option (R4, R5, R11 without a Workflow) counts as passed,
shown as N/A. If no option passes, the report is a no-go and the owner decides. Rejected:
simplest-first (would reverse §4.4 without new evidence); a weighted score.

### D3 · Two workloads, no model in the loop
The recorded turn is one real DSH run of `t01-order-total`, captured with a recording sink (R7).
The synthetic load is 4 agents streaming ~50 token deltas/s each for 5 min, with 3 tailers per
agent (R5, R6). Rejected: live model runs (noise); 16 agents (beyond the stack's two DSH pairs).
Details: notes.md#d3

### D4 · An isolated spike in a disposable stack
Code lives in `spikes/event-transport/` with its own uv project and lock. Every run uses a
disposable Compose project with its own Temporal and PostgreSQL; NATS runs from a spike-only
Compose file (nats-server 2.15.3 by digest). The capture script runs in the root environment
through the existing DSH test support. Rejected: production packages now (Phase 2 reviews the
port anyway); the shared dev stack (load would disturb it).

### D5 · Each option's mechanisms fixed up front
- Streams: a publishing Activity sends each batch as one Update to the hosting Workflow, which
  checks a batch-ID set and appends through the stream's Workflow-side topic. Readers call the
  stream's poll Update directly. Roll-over happens when Temporal suggests it or every 2,000
  batches, and keeps the last 500 events.
- Table: one event table, a per-workflow counter, a batch-ID row in the same transaction,
  `LISTEN/NOTIFY` with a 1 s poll fallback.
- NATS: a stream per workflow, one message per event, message IDs `<batch_id>:<i>`, duplicate
  window 600 s, a pull consumer from a start sequence.
Extra code counts in the report. Rejected: tuning after first results; Streams' client publish
and `subscribe()` (no batch-ID dedup, no expiry report). Details: notes.md#d5

### D6 · Report, ADR, then delete the losers
The report (`docs/spikes/event-transport.md`) gives R1-R11 per option, the measurements, the extra
code and an operating-cost assessment. The winner gets a proposed ADR and a decision-log entry
with the verified versions; the losing implementations are deleted. Rejected: keeping all three.

## Assumptions

- Temporal's default per-run history and payload size limits apply
  (`infra/temporal/dynamicconfig.yaml` is empty); task 1.1 records the numbers from current docs.
- A 200 ms publish batch gives every option the same chance at R6 (Streams' 2 s client default
  would not apply, since D5 does not use the client's publish path).
- One real-model DSH run, done once for the recording, fits the no-model rule.
- A single-node stack is representative for this comparison.

## Risks

- Uneven implementation effort skews results → D1 and D5 fix the interface and mechanisms; extra
  code is reported.
- The preview Streams API changes during the spike → the spike lock pins `temporalio` 1.36.0.
- The load overloads the machine → runs use a disposable project, one option at a time.
- R6 near 1 s flips between runs → R8 requires the same result in 3 runs.

## Rollout & rollback

No production rollout. After each run, `make reset` on the disposable project removes its
Temporal and PostgreSQL data, including the spike schema; the NATS Compose project is removed with
its volume. The spike project can be deleted at any time.

## Open questions

- None

## Impact

- Packages / directories: `spikes/event-transport/` (new); `docs/spikes/`; `docs/adr/`;
  `docs/roadmap/decision-log.md`.
- Data: a spike schema and JetStream streams, in disposable projects only.
- Jobs / APIs: none in production.

## Links

- Issue #76: the spike's tracking issue.
- `docs/roadmap/phases/phase-2.md`: the items "Verify and adopt Temporal Python Workflow Streams",
  "Batch status/tool/token deltas" and "`agentctl tail`", and the Accept line.
- `docs/roadmap/design-decisions.md` §4.3, §4.4: bounded history; streams for observation, inbox in
  PostgreSQL, reported truncation.
- ADR-0005: DSH is the primary harness inside Temporal Activities.
- ADR-0007: new attempt write paths take the fence or justify why not.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | [Interface, suite and three transports](phases/01-interface-and-transports.md) | done | 7/7 |
| 02 | [Measure, decide and clean up](phases/02-measure-and-decide.md) | done | 5/5 |

## Decision log
2026-11-18 · D2 outcome: D2 selected Workflow Streams (both it and the table passed everything); the owner chose the PostgreSQL table on the measured costs, departing from §4.4 (ADR-0009, decision log).

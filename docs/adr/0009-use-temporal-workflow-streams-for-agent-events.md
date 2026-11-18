---
id: ADR-0009
title: Carry agent progress events in Temporal Workflow Streams, behind an event-transport interface
status: proposed
date: 2026-11-18
issue: "#76"
related:
  - docs/plans/2026-11-17-event-transport-spike/plan.md
  - docs/spikes/event-transport.md
  - docs/roadmap/design-decisions.md
  - docs/adr/0007-fence-harness-attempts-in-one-transaction.md
supersedes: null
superseded_by: null
---

# ADR-0009: Carry agent progress events in Temporal Workflow Streams, behind an event-transport interface

## Context and problem statement

Phase 2 streams agent progress, token and tool events to observers (`agentctl tail`, later the
gateway and the UI). Readers must resume from an offset without gaps or duplicates, learn when
events they asked for have expired, and keep Temporal histories bounded. Design §4.4 prefers
Temporal Workflow Streams "where supported and stable enough", with a fallback behind an
interface. Streams is still a Public Preview API whose expiry and history behaviour was not
documented well enough to adopt it untested, so a spike (issue #76) compared it with a
PostgreSQL event table and NATS JetStream against one test suite and one load.

## Considered options

- Temporal Workflow Streams (`temporalio.contrib.workflow_streams`), one hosting Workflow per
  agent workflow.
- A PostgreSQL event table with a per-workflow counter and `LISTEN/NOTIFY`.
- NATS JetStream with a stream per workflow.

## Decision outcome

Chosen option: "Temporal Workflow Streams, behind an event-transport interface", because it passed
every must-pass requirement of the spike (resume, expiry reporting, re-send dedup, offsets across
Continue-As-New, bounded history, latency, carried-state size) in all 3 runs, and the spike's
decision rule (plan D2) follows the recorded §4.4 preference. The PostgreSQL table also passed and
remains the fallback behind the same interface. NATS is not adopted.

How it is used (from the spike):
- Each batch is one `publish_batch` Update to the hosting Workflow, which deduplicates by batch ID
  (the client's own publish path cannot).
- Readers call the stream's poll Update directly, not `WorkflowStreamClient.subscribe()`, which
  hides truncation by restarting at offset 0.
- Every reader reports an offset jump as expiry and fails on a repeated offset.
- The hosting Workflow continues as new when Temporal suggests it, keeping the last 500 events.

### Consequences

- Good, because no new storage service is added and reads follow Continue-As-New natively.
- Good, because the interface keeps the PostgreSQL table available as a drop-in fallback.
- Bad, because cost grows with observers: every tailer adds one poll Update per batch, and a run
  holds at most 2,000 Updates, so a busy agent rolls over every ~100 s with 3 tailers and every
  ~36 s with 10. Temporal used ~20x the table's CPU in the spike's load.
- Bad, because the API is Public Preview; the spike imports a private decoder and needs ~314 lines
  of workaround code, against ~183 for the table.
- Bad, because events cannot be fenced in the same transaction as attempt rows (ADR-0007); the
  hosting Workflow can only refuse older attempts' batches, and Phase 2 must justify that.
- Follow-up: Phase 2 decides where token text lives (`AgentEvent` payloads hold no model text);
  re-check the Streams API at each `temporalio` upgrade; revisit this ADR if observer counts or
  Temporal load approach the measured limits.

### Confirmation

The spike's shared suite (`spikes/event-transport/tests/test_suite.py`) and load runner
(`spikes/event-transport/load.py`) run against the Phase 2 implementation behind the same
interface; Phase 2's implementation review checks the reader rule and the roll-over policy.

## Links

- [Spike report](../spikes/event-transport.md): measurements, operating cost and fencing per option.
- [Spike plan](../plans/2026-11-17-event-transport-spike/plan.md), D2 (decision rule), D5 (mechanisms).
- Design §4.4 (`docs/roadmap/design-decisions.md`): prefer Workflow Streams behind an interface.

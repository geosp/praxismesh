---
title: Choose Phase 2's event transport
status: draft
created: 2026-11-17
updated: 2026-11-17
design_review: { status: none, rounds: 0, last: null }
approved: null
adr_review: null
---

# Choose Phase 2's event transport

## Summary

Phase 2 streams agent progress, token and tool events to observers (`agentctl tail`, later the
gateway and the UI). Three transports could carry them: Temporal Workflow Streams, a PostgreSQL
event table, and NATS JetStream. This spike implements one event-transport interface three
ways, runs one shared test suite and two workloads against each, and picks the winner by a fixed
rule (D2). We decide now because the choice shapes Phase 2's first phase and everything that
reuses the interface. The main risk is a comparison skewed by uneven effort or tuning; the
requirements, workloads and thresholds are fixed here, before code (D3, D5).

```text
recorded DSH turn ─┐                    ┌─ Workflow Streams ─┐
synthetic load ────┼─> EventTransport ──┼─ PostgreSQL table ─┼─> shared suite -> report -> ADR
                   │   (one interface)  └─ NATS JetStream ───┘
```

## Why

Design §4.4 prefers Workflow Streams "where supported and stable enough", with a fallback
behind an interface. A check on 2026-11-17 found Streams still in Public Preview, adding
history events per batch, and not deduplicating retried attempts; neither Streams nor JetStream
documents what a reader sees for an expired offset, which §4.4 requires us to report. Since
phase 03 of the DSH migration, `default` runs on DSH, so the OpenAI Agents plugin's built-in
stream publishing no longer serves the main path. The question has to be answered by
measurement. Details: notes.md#verified

## What changes

- A new isolated spike, `spikes/event-transport/`, with its own uv project: the interface, three
  implementations, a shared test suite, two workloads and a measurement runner.
- A committed recording of one real DSH benchmark task's events.
- A comparison report in `docs/spikes/` and a proposed ADR for the winner.

### Non-goals

- The agent-to-agent inbox and `comms_mcp`: they stay PostgreSQL (§4.4) and belong to Phase 2.
- Production code: no worker, Workflow, schema or Compose service changes. Phase 2 ports the
  winner under its own review.
- Streaming token deltas from the DSH runner: the synthetic load models them (D3).

## Terms

- **Event transport**: the component that stores `AgentEvent`s for a workflow and serves them
  to readers from an offset.
- **Offset**: a reader's position in one workflow's event sequence; a reader resumes after it.
- **Retained base**: the oldest offset a transport still holds for a workflow.
- **Batch**: events a publisher sends together; the unit of storage and deduplication.
- **Tailer**: a reader following one workflow's events live.
- **Recorded turn**: the events of one real DSH benchmark task, captured once and replayed.
- **Synthetic load**: 4 agents streaming token deltas with 3 tailers each (D3).
- **`AgentEvent`**: the existing event schema (`common/schemas/events.py`): `seq`, timestamp,
  workflow, task and attempt IDs, type, small payload.

## Requirements

### R1 · Readers resume in order without duplicates

A reader that reconnects from its last offset must receive every retained later event, in order,
and none it already had.
- **Given** a tailer killed after offset N, **when** it reconnects from N, **then** it receives N+1 onwards in order with no event repeated.

### R2 · An expired offset is reported

A reader asking for an offset below the retained base must be told, with the retained base;
the transport never skips silently.
- **Given** events below offset B were removed, **when** a reader asks for offset B-10, **then** it gets an expiry report naming B, then events from B.

### R3 · A re-sent batch is stored once

A publisher that re-sends a batch with the same batch ID (after a timeout or a retry of the same
attempt) must not create duplicate events.
- **Given** a batch published and then re-sent with its ID, **when** a reader reads, **then** each event appears once.

### R4 · Offsets survive Continue-As-New

A workflow's offsets must stay continuous when its Workflow continues as new.
- **Given** a reader at offset N when the Workflow continues as new, **when** more events arrive, **then** the reader receives N+1 onwards with no gap and no repeat.

### R5 · History stays bounded under token load

One synthetic agent's 5-minute stream must add no more than 10% of Temporal's per-run history
limits (events and bytes) to any single Workflow run.
- **Given** the synthetic load, **when** it finishes, **then** each run's history events and bytes are measured and are under 10% of the limits verified in task 1.1.

### R6 · Events reach tailers quickly

Under the synthetic load, publish-to-display latency must be at most 1 s at the 95th percentile.
- **Given** the synthetic load, **when** tailers record arrival times, **then** p95 publish-to-display latency is ≤ 1 s.

### R7 · The recorded turn replays exactly

Replaying the recorded turn through a transport must deliver the same events, in the same order,
as recorded.
- **Given** the recorded turn, **when** it is published and read back, **then** the events equal the recording.

### R8 · Results are reproducible

Every number in the report must come from a committed command run on the committed code.
- **Given** the report, **when** its commands are rerun on its commit, **then** each requirement's pass/fail result is the same.

### R9 · Production stays unchanged

The spike must not change production packages, migrations, the registry or Compose services.
- **Given** the spike's diff, **when** it is filtered to production paths, **then** it is empty.

## Decisions

### D1 · One interface, three implementations
`EventTransport` offers `publish(workflow_id, batch_id, events)`, `read(workflow_id, from_offset)`
yielding events or one expiry report, and `latest(workflow_id)`. The shared suite tests only this
interface. Attempt resets (`reset` events, `attempt_id`) stay above it, the same for all three.
Rejected: comparing each option through its native API (tests would differ per option).
Details: notes.md#d1

### D2 · Must-pass, then simplest
An option must pass R1-R7. Among those that pass, prefer no new component and no preview API,
then lower measured cost (history, latency, database or broker load). The owner decides a close
call. Rejected: a weighted score (weights would be argued after the numbers are known).

### D3 · Two workloads, no model in the loop
The recorded turn is one real DSH benchmark task captured once with a recording sink (R7). The
synthetic load is 4 agents, each streaming ~50 token deltas/s for 5 min, with 3 tailers each (R5,
R6). Rejected: live model runs (noise in transport numbers); a 16-agent stress level (beyond
today's capacity of two DSH pairs). Details: notes.md#d3

### D4 · An isolated spike project
All code lives in `spikes/event-transport/` with its own uv project and lock, like the DSH spike.
NATS runs in a spike-only Compose file with a pinned image (nats-server 2.15.3). The spike uses
the stack's existing Temporal and PostgreSQL (a spike-only schema). Rejected: production packages
now (Phase 2 must review the winner as production code anyway).

### D5 · Each option at its documented minimum
Each implementation uses its option's documented mechanisms: Streams with
`WorkflowStreamClient` and its Continue-As-New helper; the table with a per-workflow sequence and
`LISTEN/NOTIFY`; JetStream with one stream, a subject per workflow, `Nats-Msg-Id` and
`by_start_sequence`. Tuning is limited to the parameters listed in notes.md#d5, set once before
measuring. Rejected: per-option tuning after first results (biases the comparison).
Details: notes.md#d5

### D6 · Report, ADR, then delete the losers
The report (`docs/spikes/event-transport.md`) records each requirement's result per option, the
measurements and an operating-cost assessment. The winner gets a proposed ADR; the losing
implementations are deleted from the spike in its last task. Rejected: keeping all three (unused
code and dependencies).

## Assumptions

- Temporal's per-run history limits are its documented defaults; task 1.1 verifies the numbers R5
  uses.
- A batch interval of ~200 ms gives Streams a fair chance at R6 (its 2 s default would not).
- One real-model DSH run, done once for the recording, is acceptable under the no-model rule.
- The local stack's PostgreSQL and Temporal are representative for a single-node comparison.

## Risks

- Uneven implementation effort skews results → D5 fixes mechanisms and parameters before
  measuring; the design review checks them.
- The preview Streams API changes during the spike → pin `temporalio` 1.36.0 in the spike lock.
- Expiry behaviour needs code each option lacks → the extra code counts in the report.
- The synthetic load overloads the shared dev stack → run measurements in a disposable Compose
  project (as phase 03 verification did).

## Rollout & rollback

N/A: no production change. The spike project can be deleted at any time.

## Open questions

- None

## Impact

- Packages / directories: `spikes/event-transport/` (new); `docs/spikes/`; `docs/adr/` (one
  proposed ADR).
- Data: a spike-only PostgreSQL schema and JetStream stream, in a disposable project.
- Jobs / APIs: none in production.

## Links

- Issue #76: the spike's tracking issue.
- `docs/roadmap/phases/phase-2.md`: Phase 2's event items (9, 10, 14) and Accept line.
- `docs/roadmap/design-decisions.md` §4.3, §4.4: bounded history; streams for observation,
  inbox in PostgreSQL, reported truncation.
- ADR-0005: DSH is the primary harness inside Temporal Activities.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | [Interface, suite and three transports](phases/01-interface-and-transports.md) | draft | 0/7 |
| 02 | [Measure, decide and clean up](phases/02-measure-and-decide.md) | draft | 0/5 |

## Decision log

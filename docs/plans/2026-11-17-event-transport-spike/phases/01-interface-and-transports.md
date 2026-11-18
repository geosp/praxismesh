---
phase: 1
title: Interface, suite and three transports
status: draft
branch: null
base: null
delivers: [R1, R2, R3, R4, R7, R9]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-17 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · Interface, suite and three transports

## Goal

The `EventTransport` interface exists with three implementations, and one shared suite reports
R1-R4 and R7 for each. A requirement an option fails is a result to record, not a task failure.

## Tasks

### 1. Groundwork

- [ ] 1.1 Create `spikes/event-transport/` as its own uv project (pins `temporalio` 1.36.0, `nats-py` 2.17.0, a PostgreSQL driver), with a README, and record Temporal's per-run history limits from current docs in notes.md#verified (D4, R5). Verify: `uv sync --locked` in the spike; the limits and their source are in notes.md.
- [ ] 1.2 Add the `EventTransport` interface, `Expired` and an in-memory reference implementation (D1). Verify: unit tests of the reference implementation.
- [ ] 1.3 Add the shared suite, parametrized by transport: resume (R1), expiry (R2), re-sent batch (R3), Continue-As-New (R4) and recorded-turn replay (R7). Write results per requirement and transport to a JSON file. Verify: the suite passes on the reference implementation, and fails when the reference drops an event, repeats one or skips an expiry report.
- [ ] 1.4 Capture the recorded turn: run `t01-order-total` once on the `dsh` profile with a JSON-lines recording sink, and commit the fixture (D3, R7). Verify: the fixture parses as `AgentEvent`s and holds no prompt text or credentials.

### 2. The three transports

- [ ] 2.1 PostgreSQL table transport, as notes.md#d5 (D5). Verify: the suite runs against it in a disposable Compose project and its results file is written.
- [ ] 2.2 Workflow Streams transport, with a minimal Workflow that hosts the stream and continues as new through its helper (D5, R4). Verify: as 2.1.
- [ ] 2.3 NATS JetStream transport and a spike-only Compose file running nats-server 2.15.3 by digest (D4, D5). Verify: as 2.1; `git diff --stat main -- . ':!spikes' ':!docs'` is empty (R9).

---
phase: 1
title: Interface, suite and three transports
status: in-progress
branch: spike/76-event-transport
base: f43c2ffafb79bd2cfc6791398cf32acb4d61867d
delivers: [R1, R2, R3, R4, R7, R9]
design_review: { status: passed, rounds: 2, last: 2026-11-17 }
impl_review: { status: none, rounds: 0, last: null }
approved: 2026-11-17
---

# Phase 01 · Interface, suite and three transports

## Goal

The `EventTransport` interface exists with three implementations, and one shared suite reports
R1-R4 and R7 for each. A requirement an option fails is a result to record, not a task failure.

## Tasks

### 1. Groundwork

- [x] 1.1 Create `spikes/event-transport/` as its own uv project (pins `temporalio` 1.36.0, `nats-py` 2.17.0, `asyncpg` 0.32.0, `pydantic`), with a README and a Compose overlay for a disposable project; record Temporal's per-run history limits and per-payload size limit from current docs in notes.md#verified (D4, R5, R11). Verify: `uv sync --locked` in the spike; the limits and their source are in notes.md.
- [x] 1.2 Add the `EventTransport` interface, `Expired`, the test hooks and the copied `AgentEvent`, plus an in-memory reference implementation (D1). Verify: unit tests of the reference implementation; a check that the copy's fields match `common/schemas/events.py`.
- [x] 1.3 Capture the recorded turn: `spikes/event-transport/capture.py`, run in the root environment as notes.md#d3, drives `t01-order-total` once through `DshContainer.runner(sink)` against the real model, and the fixture is committed (D3, R7). Verify: the fixture parses with the spike's `AgentEvent` copy and holds no prompt text or credentials.
- [x] 1.4 Add the shared suite, parametrized by transport: R1, R2 (both scenarios), R3 (immediate and near-horizon re-send), R4 and R7, writing pass, fail or N/A per requirement and transport to a JSON file. Verify: the suite passes on the reference implementation, and fails when the reference drops an event, repeats one, skips an expiry report or stores a re-sent batch twice.

### 2. The three transports

- [x] 2.1 PostgreSQL table transport, as D5 (D1, D5). Verify: the suite runs against it in a disposable project and its results file is written.
- [x] 2.2 Workflow Streams transport: a hosting Workflow with the batch-ID set, the `publish_batch` Update and the `retained_base` Query, a publishing Activity, and a reader on the poll Update, as notes.md#d5 (D1, D5, R4). Verify: as 2.1.
- [x] 2.3 NATS JetStream probe, as D5, with a spike-only Compose file running nats-server 2.15.3 by digest (D2, D4, D5). Verify: as 2.1; `git diff --stat main...HEAD -- . ':!spikes' ':!docs'` is empty (R9).

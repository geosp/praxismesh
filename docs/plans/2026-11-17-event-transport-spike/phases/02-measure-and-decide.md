---
phase: 2
title: Measure, decide and clean up
status: done
branch: spike/76-event-transport
base: 5371368db80b232b2f155fd5ef0a8c6dd3c0df16
delivers: [R5, R6, R8, R10, R11]
design_review: { status: passed, rounds: 2, last: 2026-11-17 }
impl_review: { status: passed, rounds: 2, last: 2026-11-18 }
approved: 2026-11-17
verification: { status: passed, last: 2026-11-18 }
demo: { status: passed, last: 2026-11-18 }
evidence:
  code_sha: 8153e7b8dd534da06fb4a16f9a7dd8c78ff4829a
  docs_sha: 1f2871d739412ec8847252c324b774d6bb8c0f70
  review: docs/plans/2026-11-17-event-transport-spike/reviews.md
  verification: docs/reviews/general-event-transport-spike/verification.md
  demo: docs/demos/general-event-transport-spike.md
---

# Phase 02 · Measure, decide and clean up

## Goal

Streams and the table are measured under the synthetic load (NATS only if both fail), the winner
is chosen by D2 and recorded in a report, a proposed ADR and a decision-log entry, and only the
winner's code remains.

## Tasks

### 1. Measure

- [x] 1.1 Add the load runner: the synthetic load of notes.md#d3, publish-to-display latency per event, Temporal history events and bytes per run, the size of each carried state, growth per minute per agent and per tailer, and database or broker resource use (R5, R6, R11). Verify: a 30 s dry run against the reference implementation writes a results file with every metric.
- [x] 1.2 For each measured option in a disposable project, with the parameters of notes.md#d5: run the shared suite 3 times and the load 3 times, plus for Streams one informational load run with roll-over off. Commit the raw results (R5, R6, R8, R11). Verify: each results file names its commit and command; every requirement's pass/fail matches across the 3 runs.

### 2. Decide

- [x] 2.1 Write the operating-cost and fencing assessment per option: new components, backups, authentication and row or subject scoping, upgrades, the Kubernetes path, extra code beyond D5, and how a superseded attempt's events would be fenced or why not (D2, R10). Verify: every option has every heading filled, with sources.
- [x] 2.2 Write `docs/spikes/event-transport.md` with R1-R11 per option, the measurements and the choice by D2; draft a proposed ADR for the winner and a decision-log entry with the verified versions (D6). Verify: every number in the report traces to a committed results file (R8).

### 3. Clean up

- [x] 3.1 Delete the losing implementations and their dependencies from the spike, and reset the disposable projects (D6). Verify: the suite still passes for the winner; `git diff --stat main...HEAD -- . ':!spikes' ':!docs'` is empty (R9).

---
phase: 2
title: Measure, decide and clean up
status: draft
branch: null
base: null
delivers: [R5, R6, R8, R10]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-17 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · Measure, decide and clean up

## Goal

Streams and the table are measured under the synthetic load (NATS only if both fail), the winner
is chosen by D2 and recorded in a report, a proposed ADR and a decision-log entry, and only the
winner's code remains.

## Tasks

### 1. Measure

- [ ] 1.1 Add the load runner: the synthetic load of notes.md#d3, publish-to-display latency per event, Temporal history events and bytes per run and their growth per minute per agent and per tailer, and database or broker resource use (R5, R6). Verify: a 30 s dry run against the reference implementation writes a results file with every metric.
- [ ] 1.2 Run the load 3 times per measured option in a disposable project, with the parameters of notes.md#d5: for Streams, once with roll-over off to measure growth, then with roll-over at the derived interval. Commit the raw results (R5, R6, R8). Verify: each results file names its commit and command; pass/fail matches across the 3 runs.

### 2. Decide

- [ ] 2.1 Write the operating-cost and fencing assessment per option: new components, backups, authentication and row or subject scoping, upgrades, the Kubernetes path, extra code beyond D5, and how a superseded attempt's events would be fenced or why not (D2, R10). Verify: every option has every heading filled, with sources.
- [ ] 2.2 Write `docs/spikes/event-transport.md` with R1-R10 per option, the measurements and the choice by D2; draft a proposed ADR for the winner and a decision-log entry with the verified versions (D6). Verify: every number in the report traces to a committed results file (R8).

### 3. Clean up

- [ ] 3.1 Delete the losing implementations and their dependencies from the spike, and reset the disposable projects (D6). Verify: the suite still passes for the winner; `git diff --stat main...HEAD -- . ':!spikes' ':!docs'` is empty (R9).

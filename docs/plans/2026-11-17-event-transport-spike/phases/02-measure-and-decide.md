---
phase: 2
title: Measure, decide and clean up
status: draft
branch: null
base: null
delivers: [R5, R6, R8]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-17 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · Measure, decide and clean up

## Goal

Each option's history growth and latency under the synthetic load are measured, the winner is
chosen by D2 and recorded in a report and a proposed ADR, and only the winner's code remains.

## Tasks

### 1. Measure

- [ ] 1.1 Add the load runner: the synthetic load of notes.md#d3, publish-to-display latency per event, Temporal history events and bytes per run (from the server's history), and database or broker resource use (R5, R6). Verify: a 30 s dry run against the reference implementation writes a results file with every metric.
- [ ] 1.2 Run the full load once per option in a disposable Compose project, with the parameters of notes.md#d5, and commit the raw results (R5, R6, R8). Verify: one results file per option, each naming the commit and command that produced it.

### 2. Decide

- [ ] 2.1 Write the operating-cost assessment per option: new components, backups, authentication and subject or row scoping, upgrades, Kubernetes path (D2). Verify: each option has every heading filled, with sources.
- [ ] 2.2 Write `docs/spikes/event-transport.md`: R1-R7 per option, the measurements, the assessment, and the choice by D2; draft a proposed ADR for the winner (D6). Verify: every number in the report traces to a committed results file (R8).

### 3. Clean up

- [ ] 3.1 Delete the losing implementations and their dependencies from the spike (D6). Verify: the suite still passes for the winner; `git diff --stat main -- . ':!spikes' ':!docs'` is empty (R9).

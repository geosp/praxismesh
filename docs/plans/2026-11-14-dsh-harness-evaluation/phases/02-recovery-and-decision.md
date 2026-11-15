---
phase: 2
title: Prove recovery and assess suitability
status: in-progress
branch: spike/62-dsh-recovery-evaluation
base: 99ad2d2ec1402768abf81dbe2dfc3dab785dee30
delivers: [R4, R5, R6, R7, R8, R9, R10]
design_review: { status: passed, rounds: 2, last: 2026-11-14 }
impl_review: { status: changes-requested, rounds: 1, last: 2026-11-15 }
approved: 2026-11-14
---

# Phase 02 · Prove recovery and assess suitability

## Goal

Establish whether DSH preserves our execution guarantees and merits a separate adoption proposal.

## Tasks

- [ ] 2.1 Probe consistent state barriers, clean-worker recovery and ownership/effect interruption points (R4; D3). Verify: acknowledged conversation/edits restore, controlled effects remain idempotent and superseded work cannot commit authoritative state.
- [ ] 2.2 Exercise limits, accounting and structured results through the isolated bridge (R5, R6, R7, R10; D2, D4). Verify: the pre-run manifest fixes limits and stop/cleanup oracles; independent gateway/executor ledgers pass the exhaustion/retry/auxiliary probes in notes; stalled/cancelled work stops without leaked processes; outcome/error paths validate.
- [ ] 2.3 Compare the ten existing benchmark checks on the local model (R8; D1). Verify: preserve the baseline, apply the existing regression rule, disclose prompt/composition differences and record failed/blocked cases and metrics.
- [ ] 2.4 Publish the report and reproduce recovery/denial walkthroughs (R9, R10; D5). Verify: independent review and execution evidence support the recommendation, teardown and limitations without substituting for owner adoption approval.

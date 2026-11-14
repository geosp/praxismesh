---
phase: 1
title: Establish an isolated controlled runtime
status: in-progress
branch: spike/62-dsh-harness-evaluation
base: 952d01e097332905ba56d6c26e1e342431f8f394
delivers: [R1, R2, R3, R10]
design_review: { status: passed, rounds: 2, last: 2026-11-14 }
impl_review: { status: none, rounds: 0, last: null }
approved: 2026-11-14
---

# Phase 01 · Establish an isolated controlled runtime

## Goal

Establish a reproducible isolated candidate and trusted local capabilities before recovery testing.

## Tasks

- [ ] 1.1 Create the separate spike environment and record matching artifacts, platform, composition and build prerequisites (R1; D1, D2). Verify: locked uv environment and explicit-home startup reproduce, or missing artifacts are blocked.
- [ ] 1.2 Exercise authority probes and the real local skill/MCP task using a bounded SDK bridge (R2, R3; D2, D4). Verify: allowed local work succeeds; poisoned discovery, native-command-shaped inputs and forbidden execution cannot expand grants.
- [ ] 1.3 Inventory services/auxiliary capabilities and publish phase evidence and teardown (R1, R10; D4). Verify: no unaccounted scheduling/delegation or unrelated credentials; independent review, checks and startup/denial walkthrough pass before completion.

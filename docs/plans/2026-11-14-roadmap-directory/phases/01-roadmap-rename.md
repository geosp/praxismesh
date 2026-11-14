---
phase: 1
title: Rename and verify roadmap navigation
status: draft
branch: null
base: null
delivers: [R1, R2, R3, R4, R5, R6]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · Rename and verify roadmap navigation

## Goal

Readers can distinguish the roadmap from implementation plans and reach the
renamed documents without changing their meaning or weakening existing checks.

## Tasks

- [ ] 1.1 Move the roadmap and update live documentation, instructions and path consumers (R1, R2, R3, R5; D1). Verify: inventory confirms 19 corresponding files, no docs/plan directory, unchanged implementation-plan discovery, valid anchors and path-only roadmap diffs plus the identified organization decision entry.
- [ ] 1.2 Repair historical navigation under the owner's exception and record its maintenance inventory (R3, R4; D2). Verify: frozen-baseline comparison permits only Markdown destination changes in historical records; decisions, labels, recorded paths, task states and SHAs are unchanged.
- [ ] 1.3 Maintain the bounded scan exception and verify the complete rename (R1–R6; D3). Verify: both approved paths pass the prose canary; unallowlisted dummy content and ordinary-file content are detected; offline links, actionlint, public/shared plan checks, generated agents and required repository checks pass; independent review and the navigation walkthrough are saved before checking tasks off.

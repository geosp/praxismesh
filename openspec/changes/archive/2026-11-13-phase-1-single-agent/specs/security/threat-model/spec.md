# Spec Delta

## Purpose

A living threat model that covers what exists so far and maps each control to a test; every later phase that adds a trust boundary extends it (plan Phase 1 task 6, rev 2.10).

## ADDED Requirements

### Requirement: Threat model with controls mapped to tests
`docs/security/threat-model.md` SHALL cover assets, trust boundaries, actors (hostile prompt, hostile file content, compromised worker, over-privileged profile) and controls, and SHALL map every control to the test that checks it. It SHALL list accepted risks with the phase that closes them. (Plan: Phase 1 task 6.)

#### Scenario: Every control has a test
- **WHEN** the threat model is reviewed
- **THEN** each listed control names an existing test, and each accepted risk names the phase that addresses it

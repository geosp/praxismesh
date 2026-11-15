---
title: Run production agents on DSH
status: draft
created: 2026-11-15
updated: 2026-11-15
design_review: { status: none, rounds: 0, last: null }
approved: null
adr_review: null
---

# Run production agents on DSH

## Summary

Make DeepSeek Harness (DSH) the harness that runs PraxisMesh agent turns, as
ADR-0005 decided, before runtime Phase 2 starts. Temporal keeps dispatch, retries
and coordination; each Activity attempt runs DSH in its own container. The work
turns the spike's isolated bridge into production code behind the existing
`HarnessRunner` seam, adds `dsh` as a versioned registry harness, and keeps
`openai_agents` selectable per template. Acceptance reuses the spike's recovery,
stop, accounting and outcome cases as production tests, plus `make benchmark`
within the existing regression limit. The main risk is the checkpoint barrier:
it is our own mechanism, not a DSH API, and must hold under real worker loss.

```text
TaskWorkflow -> run_harness_turn (Activity) -> DshRunner
                  |                              |- per-attempt container (DSH SDK + runtime)
                  |                              |- model gateway (budget ledger) -> vLLM
                  |                              '- tool executor (template tools, skills, MCP)
                  '- checkpoints, attempt rows, blobs (unchanged contracts)
```

## Why

ADR-0005 adopts DSH as the primary harness, with five adoption conditions. The
[spike](../../spikes/dsh-harness.md) proved those guarantees in isolation only:
production dispatch still runs `openai_agents`, and `registry/loader.py` accepts
no other harness. Runtime Phase 2 adds event streaming from the harness; doing
this migration first means Phase 2's event mapping is built once, against DSH.

## What changes

- A session/checkpoint abstraction in `harness_activity` that both runners use.
- A production `DshRunner` with per-attempt containers, gateway and executor.
- `dsh` as a supported, versioned harness value and a new `local-dsh@1` template.
- A pinned DSH worker image and its build/licence record.
- The spike's control cases ported to production tests; a DSH benchmark run.
- A harness event contract that Phase 2 will consume.

### Non-goals

- Runtime Phase 2 itself (event transport, comms MCP); its own phase file owns it.
- Removing `openai_agents`; it stays selectable until a later decision retires it.
- DSH scheduling, delegation, jobs, native discovery or its skill loader.
- Hosted model providers.

## Terms

- **DSH**: DeepSeek Harness, the agent runtime chosen in ADR-0005.
- **Runner**: an implementation of `HarnessRunner` in `harness_activity/runner.py`.
- **Attempt container**: one disposable container per Activity attempt that runs DSH.
- **Gateway**: the trusted host-side model proxy that admits requests and keeps the usage ledger.
- **Executor**: the trusted host-side process that runs every granted tool body and records it.
- **Barrier**: the steps that make a session/workspace checkpoint consistent before it is acknowledged.
- **Template**: a registry worker template (`registry/templates/*.yaml`) that grants capabilities.

## Requirements

### R1 · Templates choose the harness

Only a template's `harness` field selects the runner, and only versioned values in the registry lock are accepted.
- **Given** a template with `harness: dsh`, **when** the registry loads, **then** it is accepted and pinned in `registry.lock`.
- **Given** a template with an unknown harness, **when** the registry loads, **then** loading fails.

### R2 · Existing templates keep working

A template with `harness: openai_agents` must behave as it does today.
- **Given** `local-default@1`, **when** the conformance suite and benchmark run, **then** results match the current baseline rule.

### R3 · DSH turns keep the checkpoint contract

A DSH turn may acknowledge a checkpoint only after the barrier proves the session and workspace are consistent.
- **Given** worker loss after an acknowledged checkpoint, **when** a new worker resumes, **then** conversation and edits survive without the old disk.
- **Given** a stale attempt, **when** it resumes after a newer one, **then** it publishes no checkpoint, row, artifact or outcome.

### R4 · DSH turns stay bounded

Every DSH attempt must stop its container within 5 s of a deadline, cancellation or step limit.
- **Given** a stalled model or tool, **when** the deadline fires, **then** the container stops cooperatively and nothing survives a 10 s observation.
- **Given** a SIGTERM the runtime ignores, **when** the grace passes, **then** the attempt fails even though cleanup succeeds.

### R5 · Usage is counted at the gateway

Token and tool usage must come from the gateway ledger and the executor, never from the runtime's own report alone.
- **Given** retries, lost attempts or in-flight requests, **when** usage is reported, **then** settled tokens are never dropped and unknown usage is never shown as zero.

### R6 · Capabilities come only from the template

The attempt container must receive only template-granted tools, skills and MCP servers, presented with production semantics.
- **Given** task text or workspace files that name extra tools, **when** a DSH turn runs, **then** no new tool, plugin, skill or network route appears.

### R7 · Results follow the TaskResult contract

A DSH turn must report through `finish_task` and the existing `TurnOutcome`/`TaskResult` mapping.
- **Given** each spike outcome case (done, continuation, needs-input, invalid, retry, bad input, lost after finish), **when** it runs, **then** the TaskResult matches the spike's expected result.

### R8 · Turns emit harness events

A DSH turn must emit status, tool and token events through one interface that Phase 2 can stream.
- **Given** a DSH turn with two tool calls, **when** it runs, **then** the interface receives ordered events with attempt identity and no raw prompt content.

### R9 · The DSH benchmark meets the regression rule

A `dsh` template must pass the ten benchmark tasks within the existing at-most-one-lost rule.
- **Given** `make benchmark` on `local-dsh@1`, **when** it finishes, **then** at most one task is lost against the recorded baseline.

## Decisions

### D1 · One session abstraction, two runners

Move session load, truncation and checkpoint position behind a small interface in
`harness_activity`, with the current `SQLAlchemySession` path as one implementation
and DSH session files as the other. Rejected: a DSH-only Activity (duplicates
attempt, budget and checkpoint logic that already passed Phase 1 review).

### D2 · Port the spike bridge, not the spike harness

Reuse the spike's tested rules (`task_policy.py` classification, ordered ownership,
session-marker barrier, gateway ledger, executor) as production modules with their
tests. Rejected: calling the spike code from production (fixture-shaped, ignores
production config and observability). Details: notes.md#d2

### D3 · Container per attempt, built from a pinned image

Run DSH in a per-attempt container from an image that pins the DSH release, wheel
digests and native binary hashes: a scoped socket proxy starts it under Compose, a
per-attempt Pod under Kubernetes. Rejected: an unscoped Docker socket (root on the
host); DSH in the worker process beside DB/S3 credentials (no isolation); DinD
(privileged). Still open for design review: a one-attempt worker pod with the
gateway and executor in a credential-holding sidecar. Details: notes.md#d3

### D4 · Production skill and tool semantics

Present files, commands, MCP tools and the skill bundle exactly as
`harness_activity/tools.py` and `skills.py` do, over the executor. Rejected:
DSH native tools and skill loader (unobserved tool bodies; different semantics).

### D5 · New template version, opt-in default

Add `local-dsh@1` beside `local-default@1`; switch the `default` profile only after
R9 passes. Rejected: changing `local-default@1` in place (breaks the pinned lock
and the recorded baseline).

### D6 · Barrier stays ours until upstream offers one

Keep the held-request, session-marker and pause barrier, documented as a
PraxisMesh contract, and track an upstream flush/export API. Rejected: copying a
live home directory (no consistency proof).

## Assumptions

- DSH 0.2.2rc2 (the spike's pin) stays the first production pin; a newer release needs the spike's control cases rerun.
- Workers cannot start containers by default in either target. Compose needs a
  scoped Docker socket proxy (create/remove of the pinned image only) or rootless
  Docker; Kubernetes needs a per-attempt Pod created through a namespace-scoped
  service account. Phase 02 chooses one per target (D3).
- The existing Phase 1 tests and benchmark harness can be parameterised by template.

## Risks

- Barrier fails under real worker loss → R3 tests kill real workers, not only fixtures.
- Pre-release runtime changes behaviour → pin digests; rerun control cases on every bump.
- Container-start rights widen privilege → socket proxy or RBAC limited to one image, one namespace and the attempt tree.
- Cost and latency (~1.9x wall time in the spike) → measure in R9; owner judges.

## Rollout & rollback

Ship behind `local-dsh@1`; production profiles keep `local-default@1` until R9
passes and the owner switches the `default` profile. Rollback is reverting the
profile to `local-default@1`; no data migration is involved.

## Open questions

- None

## Impact

- Packages / directories: `harness_activity/`, `registry/`, `workers/`, `infra/`, `tests/`.
- Data: checkpoint blobs gain a DSH session encoding; attempt rows unchanged.
- Jobs / APIs: `run_harness_turn` Activity; template queues; no gateway API change.

## Links

- [ADR-0005](../../adr/0005-adopt-dsh-as-primary-agent-harness.md): adopt DSH inside Temporal Activities, with five adoption conditions.
- [DSH spike report](../../spikes/dsh-harness.md): evidence, limits and measured cost.
- [Spike bridge](../../../spikes/dsh-harness/README.md): the code and tests to port.
- [Runtime Phase 2](../../roadmap/phases/phase-2.md): event streaming that consumes R8.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | [Harness seam and registry](phases/01-harness-seam.md) | draft | 0/3 |
| 02 | [DSH runner and worker image](phases/02-dsh-runner.md) | draft | 0/4 |
| 03 | [Acceptance and default switch](phases/03-acceptance.md) | draft | 0/3 |

## Decision log

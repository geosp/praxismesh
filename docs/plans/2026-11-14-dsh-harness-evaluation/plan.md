---
title: Evaluate DSH as the primary agent harness
status: in-progress
created: 2026-11-14
updated: 2026-11-14
design_review: { status: passed, rounds: 2, last: 2026-11-14 }
approved: 2026-11-14
adr_review: null
---

# Evaluate DSH as the primary agent harness

## Summary

Evaluate DeepSeek Harness (DSH) as the primary runtime executing PraxisMesh agents
inside Temporal Activities. Build an isolated compatibility spike using our local
model, trusted capabilities and existing benchmark. Prove recovery, bounded
execution and policy enforcement before proposing adoption. Temporal continues to
own durable task coordination. The main risk is a runtime that works normally but
loses checkpoint consistency or control after interruption. The outcome is evidence
and a go/no-go recommendation; production replacement requires a separate reviewed
decision and implementation plan.

## Why

The owner identified DSH as a candidate for running PraxisMesh agents. Upstream
documents replaceable components, a Python client and persistent sessions. Our
Activity constructs OpenAI Agents SDK sessions directly, so integration involves
the session/checkpoint boundary as well as a runner adapter. Evaluate that boundary
before committing future designs to either runtime.

## What changes

- Add an isolated spike, locked dependencies, explicit composition and probes.
- Exercise local-model, skills, MCP and structured-result contracts.
- Test interruption, restoration, attempt ownership, usage and cancellation.
- Compare the ten-task benchmark and publish sanitized evidence and a recommendation.

### Non-goals

- Replace production dispatch or edit existing profiles, template locks or schemas.
- Start or close runtime Phase 2, change phase order or rewrite Phase 1 evidence.
- Add a DSH adapter to Skill Central or change personal harness installations.
- Adopt DSH scheduling/delegation as PraxisMesh orchestration.
- Add hosted model dependencies or use real business data in the experiment.

## Terms

- **DSH**: DeepSeek Harness, the candidate agent runtime.
- **Cordis**: its plugin framework for composing services and runtime hooks.
- **Activity**: Temporal's I/O boundary hosting a bounded agent invocation.
- **Composition**: explicit DSH profile, plugins and configuration for an experiment.
- **Trusted Cordis patch**: a spike-owned, reviewed configuration overlay, not an
  upstream source-code change. Any integration plugin is a separately identified,
  hashed bundle in the experiment inventory.
- **Local model**: spark is the existing model identifier in
  registry/templates/local-default.yaml, served through the configured vLLM endpoint.
- **Worker profile/template**: registry/profiles/default.yaml selects task policy;
  registry/templates/local-default.yaml grants execution capabilities and limits.
  registry/registry.lock pins template versions; this differs from a DSH profile.
- **TaskResult**: the validated task-level output in common/schemas/task.py, with
  succeeded, failed or needs_input status and artifact references. Runner outcomes
  done/continue/needs_input remain internal to the existing task lifecycle.
- **Runtime phases**: Phase 1 is the closed harness/session recovery baseline;
  Phase 2 is the unstarted events and agent-communications work.
- **Checkpoint**: consistent session state/position and workspace snapshot referenced durably.
- **Attempt fencing**: preventing superseded execution from publishing authoritative state.
- **Capability**: a tool, skill, MCP server or other access granted by a trusted template.
- **Hard gate**: a correctness or isolation condition performance cannot compensate for.

## Requirements

### R1 · Candidate runs are reproducible

Every experiment must identify its upstream revision, matching SDK/runtime artifacts,
dependency digests, platform and composition.
- **Given** an experiment record, **when** it is reproduced, **then** it uses the recorded artifacts and reports unavailable or mismatched prerequisites as blocked.

### R2 · Existing local capabilities work

DSH must execute a task using the local model and template-granted skill and MCP
capabilities without a hosted-provider fallback.
- **Given** the isolated candidate and granted fixtures, **when** a real task runs, **then** local requests, skill use and an allowed MCP operation are observed.

### R3 · Untrusted input cannot expand authority

Only trusted composition and template configuration may grant capabilities.
- **Given** poisoned discovery or native-command-shaped task text, **when** submitted, **then** it cannot grant tools, plugins, skills, credentials or network destinations.
- **Given** a forbidden MCP operation, **when** attempted, **then** execution is rejected rather than merely hiding its schema.

### R4 · Recovery preserves the checkpoint contract

A replacement worker must resume a consistent acknowledged session/workspace pair
under the existing side-effect and attempt-ownership guarantees.
- **Given** worker loss after edits and an acknowledged checkpoint, **when** a clean worker resumes, **then** conversation and edits survive without the old worker's disk.
- **Given** an idempotent fixture effect committed before result persistence, **when** interruption and retry occur, **then** its business effect is not duplicated.
- **Given** a newer attempt, **when** the old execution resumes, **then** it cannot publish authoritative checkpoints or outcomes.

### R5 · Activity execution remains bounded

Turn limits, cancellation and wall-time controls must stop the runtime and its
owned work within the predeclared [probe bounds and cleanup policy](notes.md#stop-and-cleanup-policy).
- **Given** a stalled provider request, **when** its wall deadline fires, **then** owned work stops within the declared grace and process observation checks for survivors.
- **Given** a blocked tool, **when** its wall deadline fires, **then** the same stop and observation rules apply to tool-owned descendants.
- **Given** a cancelled Activity, **when** cancellation is triggered at the declared barrier, **then** the same stop and observation rules apply.
- **Given** an exhausted model-step limit, **when** another step would begin, **then** admission is refused and owned work follows the declared cleanup policy.

### R6 · Usage covers admitted work

Accounting must include retries and auxiliary requests admitted by the composition,
with budget enforcement before further requests are admitted. The independent
[usage ledger](notes.md#independent-usage-ledger) defines the observation point,
units and exhaustion oracle.
- **Given** retries or compaction, **when** usage is reconciled against a model-boundary ledger, **then** totals match and exhaustion prevents another request.

### R7 · Completion follows the result contract

DSH output must map to validated TaskResult semantics through an explicit
completion mechanism rather than accepting arbitrary assistant text as success.
- **Given** each fixture in the [outcome checklist](notes.md#outcome-checklist), **when** the bridge returns or raises, **then** statuses, references and retry/error disposition match the existing contract.

### R8 · Benchmark comparison uses the existing regression rule

The candidate must run the same ten task checks and apply the existing
at-most-one-lost-task threshold against the recorded 10/10 baseline. Use the
labelled [comparison checks](notes.md#benchmark-comparison-checks) for evidence.
- **Given** benchmark outcomes, **when** two or more tasks are lost, **then** the existing regression limit is exceeded.
- **Given** a comparison, **when** recorded, **then** model, prompts, composition, hardware, pass counts, tokens, tool calls and time are identified without overwriting the baseline.

### R9 · Recommendation reflects observed evidence

The recommendation must distinguish passed, failed and blocked checks, integration
changes and unresolved risks before owner adoption approval.
- **Given** a failed hard gate, **when** recommending next steps, **then** immediate adoption is not recommended.
- **Given** an unavailable dependency, **when** a check cannot run, **then** it remains blocked instead of passing through a mock or hosted fallback.
- **Given** an evaluated runtime without a usable consistency barrier, **when** classified, **then** R4 fails; unavailable prerequisites preventing evaluation are blocked.

### R10 · Durable orchestration remains outside DSH

Temporal and PraxisMesh must retain durable task dispatch, retries and coordination
throughout the experiment.
- **Given** a composition inventory, **when** reviewed, **then** durable dispatch, retries and task coordination remain owned by PraxisMesh/Temporal, with competing paths disabled.
- **Given** admitted auxiliary work, **when** inventoried, **then** it has identified R5 bounds and R6 accounting checks.

## Decisions

### D1 · Explore replacement through an isolated spike

Keep experiment code under spikes/dsh-harness with a separate uv environment and
worker/bridge. Rejected: changing production dispatch during exploration, because
normal-session success does not establish recovery. Details: notes.md#scope

### D2 · Prefer the SDK with explicit composition

Evaluate a pinned SDK/runtime pair and trusted Cordis patches; add only the minimal
plugin needed to probe required hooks. Rejected: browser automation or a forked
agent loop, because neither evaluates the intended supported boundary.
Details: notes.md#upstream

### D3 · Prove session and workspace recovery together

Identify a verified flush/export or equivalent barrier before acknowledging a
checkpoint. Exclude credentials and unrelated home state from snapshots. Rejected:
copying an active home directory as proof of consistency.

### D4 · Preserve orchestration and template authority

Start with one controlled agent per Activity and explicitly granted capabilities.
Auxiliary work remains subject to R5/R6/R10. Rejected: inheriting personal DSH setup
or enabling unmeasured child agents for convenience.

### D5 · Make adoption a separate decision

Record the production changes required, including SDK-specific session coupling.
Rejected: making DSH the default after a smoke test. Apply R9 before a follow-up
ADR and reviewed migration contract.

## Assumptions

- Use existing local fixtures; unavailable infrastructure blocks live tests.
- The inspected upstream revision is the initial candidate; changes need refreshed evidence.
- The spike changes neither runtime phase sequence nor completed-phase guarantees.
- Measure latency/cost for owner review; invent no new acceptance threshold.

## Risks

- Observations arrive too late for enforcement: test admission hooks directly.
- Session/filesystem commits diverge: inject failures around acknowledgement.
- Hidden model work escapes accounting: reconcile model-boundary requests.
- Preview artifacts are unavailable: record pins and mark blocked prerequisites.
- Default discovery/commands expand authority: run R3 probes before real tasks.

## Rollout & rollback

Independently review this contract and obtain approval before installing or running
the candidate. Start with artifact/configuration and deterministic control probes,
then real local execution, recovery and benchmark. Preserve failed results and
record any remediation and rechecks against the pinned candidate.

Teardown stops the isolated worker/runtime and removes only identified disposable
fixtures. Production deployment, registry and user installations remain unchanged.
Use D5 for the adoption handoff.

## Open questions

- None for spike scope; suitability remains an experiment outcome.

## Impact

- Packages / directories: new spikes/dsh-harness, this contract and a docs/spikes report.
- Data: disposable fixture state and sanitized checkpoint artifacts.
- Jobs / APIs: isolated experiment worker/bridge; production APIs unchanged.

## Links

- [Issue #62](https://github.com/geosp/praxismesh/issues/62): spike scope, phases and acceptance.
- [Project plan](../../../PROJECT_PLAN.md): authoritative constraints and sequencing.
- [Harness/durability contracts](../../roadmap/design-decisions.md#41-harness-in-activity): bounded execution and recovery.
- [Recorded benchmark](../../benchmarks/2026-11-12-local-default.md): current 10/10 result.
- [Research and probe matrix](notes.md): pinned sources, integration seams and evidence.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | [Establish an isolated controlled runtime](phases/01-controlled-runtime.md) | done | 3/3 |
| 02 | [Prove recovery and assess suitability](phases/02-recovery-and-decision.md) | approved | 0/4 |

## Decision log

2026-11-14: Owner requested exploration of DSH for running PraxisMesh agents.

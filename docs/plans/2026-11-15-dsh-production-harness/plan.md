---
title: Run production agents on DSH
status: draft
created: 2026-11-15
updated: 2026-11-15
design_review: { status: changes-requested, rounds: 1, last: 2026-11-15 }
approved: null
adr_review: null
---

# Run production agents on DSH

## Summary

Make DeepSeek Harness (DSH) run PraxisMesh agent turns, as ADR-0005 decided, before
roadmap Phase 2 (events and comms). Temporal keeps dispatch, retries and coordination.
Each worker gets a paired DSH container with no credentials or network, where a
launcher runs one DSH process per attempt; the worker keeps the Activity,
credentials, model gateway and tool executor, so no container needs Docker access
(D3). The spike's rules become production modules behind `HarnessRunner`; `dsh`
becomes a versioned harness, and DSH turns emit `AgentEvent`s for roadmap Phase 2
(R11). `openai_agents` stays selectable, and the `default` profile moves to DSH only
after the benchmark passes and the owner approves (D5). The main risk is the
checkpoint barrier (D6): our own mechanism, not a DSH API, that must hold when a
real worker dies.

```text
worker container (credentials)            dsh container (no credentials, no network)
  run_harness_turn -> DshRunner  --unix-->  launcher -> one DSH process per attempt
  gateway (ledger) -> vLLM        <-unix--  model and tool requests
  executor (template tools)       shared volume: /attempts/<task>/<turn>/<attempt>
```

## Why

ADR-0005 adopts DSH, subject to five conditions:

| Condition | Requirement |
| --- | --- |
| Pin the DSH release and its digests | R12 |
| A reviewed checkpoint consistency contract | R4, R5 |
| One isolated boundary per attempt, with model and tool use observed outside it | R6, R8 |
| Production capability semantics; DSH discovery, skill loader, jobs and delegation off | R10 |
| `openai_agents` stays selectable | R3 |

The [spike](../../spikes/dsh-harness.md) proved these only in isolation; production
runs only `openai_agents`. Migrating before roadmap Phase 2 builds its event mapping
once, against DSH.

## What changes

- A session/checkpoint seam in `harness_activity/` used by both runners (D1).
- Production modules ported from the spike, in `harness_activity/dsh/` (D2).
- A DSH companion container and launcher per worker (D3).
- `dsh` added to the `Harness` type, the registry and `schemas.md`, plus a `local-dsh@1` template and a `dsh` profile.
- A nullable-usage migration for attempt rows (D7).
- The spike's control cases as production integration tests; a DSH benchmark run.
- An `AgentEvent` sink (D8).

### Non-goals

- Roadmap Phase 2 itself (event transport, comms MCP); [its phase file](../../roadmap/phases/phase-2.md) owns it.
- Retiring `openai_agents`.
- DSH scheduling, delegation, jobs, native discovery or its skill loader.
- Hosted model providers, or Kubernetes (roadmap Phase 7).

## Terms

- **DSH**: DeepSeek Harness, the agent runtime chosen in ADR-0005.
- **Runner**: an implementation of `HarnessRunner` (`harness_activity/runner.py`).
- **Profile**: a registry agent profile (`registry/profiles/`) that selects allowed templates and task limits.
- **Template**: a registry worker template (`registry/templates/`) granting capabilities and naming its harness.
- **DSH container**: the credential-free container paired with each DSH worker; it runs the launcher.
- **Launcher**: the process in the DSH container that starts, stops and reaps one DSH process per attempt.
- **Attempt tree**: `/attempts/<task>/<turn>/<attempt>` on a volume both containers mount; it holds the session, workspace and sockets.
- **Gateway**: the worker-side model proxy that admits requests and keeps the usage ledger.
- **Executor**: the worker-side process that runs every granted tool body and records it.
- **Barrier**: the steps in D6 that make a checkpoint consistent before it is acknowledged.
- **Stale attempt**: an attempt whose (turn, attempt) order is lower than the owner recorded for the task.
- **Lost attempt**: an attempt that ended without writing its attempt row (worker death or timeout).
- **`finish_task`**: the production tool through which a turn reports done or needs-input (`harness_activity/tools.py`).
- **Baseline rule**: at most one task lost against `docs/benchmarks/baseline.json` (10/10, openai-agents).
- **The owner**: the repository owner, who approves the profile switch and cost.

## Requirements

### R1 · Only versioned harness values load

A template's `harness` must be a value in the `Harness` type and the registry lock.
- **Given** a template with `harness: dsh`, **when** the registry loads, **then** it is accepted and pinned in `registry.lock`.
- **Given** a template with an unknown harness, **when** the registry loads, **then** loading fails.

### R2 · Profile and template harness match

A profile may only allow templates whose `harness` equals its own.
- **Given** a `dsh` profile allowing `local-default@1`, **when** the registry loads, **then** loading fails.

### R3 · Existing templates keep working

A template with `harness: openai_agents` must pass the conformance suite and the baseline rule.
- **Given** `local-default@1`, **when** the suite and `make benchmark` run, **then** both pass.

### R4 · Checkpoints are acknowledged only after the barrier

A DSH checkpoint may be acknowledged only after the D6 barrier succeeds.
- **Given** worker loss after an acknowledged checkpoint, **when** a new worker resumes, **then** conversation and edits survive without the old attempt tree.

### R5 · Stale attempts publish nothing

A stale attempt never writes a checkpoint, attempt row, artifact or outcome.
- **Given** attempt 1 resumes after attempt 2 has claimed the turn, **when** it tries to publish, **then** nothing is written.

### R6 · Attempts stop within 5 s

Every DSH process must exit within a 5 s grace after a deadline, cancellation or step limit, and nothing it started may run during the following 10 s observation window.
- **Given** a stalled model or tool, **when** the deadline fires, **then** the process exits cooperatively and the window is clean.
- **Given** a SIGTERM the runtime ignores, **when** the grace passes, **then** the attempt fails even though the launcher kills it.

### R7 · Worker death leaves no attempt running

When a worker dies, its in-flight DSH attempt must be stopped by the launcher.
- **Given** a worker SIGKILLed mid-turn, **when** 10 s pass, **then** no DSH process for that attempt remains.

### R8 · Usage is counted at the gateway

Token and tool usage must come from the gateway ledger and the executor, never from the runtime's own report alone.
- **Given** retries or lost attempts, **when** usage is reported, **then** settled tokens are never dropped.

### R9 · Unknown usage is never zero

Usage that cannot be observed must be stored as unknown and charged a conservative estimate (D9).
- **Given** a worker that dies mid-generation, **when** the next attempt starts, **then** the budget is charged the D9 estimate and the row is flagged unknown.

### R10 · Capabilities come only from the template

The DSH process receives only template-granted tools, skills and MCP servers, presented with production semantics.
- **Given** task text or workspace files naming extra tools, **when** a turn runs, **then** no new tool, plugin, skill or network route appears.

### R11 · Turns emit AgentEvents

A DSH turn must emit `status`, `tool_call`, `tool_result` and `token` `AgentEvent`s through the D8 sink.
- **Given** a turn with two tool calls, **when** it runs, **then** the sink receives ordered events with attempt ID and no prompt text.

### R12 · The DSH runtime is pinned

Workers must refuse to start DSH unless its release and file digests match the pins in the registry lock.
- **Given** a DSH image with a changed native binary, **when** the launcher starts, **then** it refuses with a blocked error.

### R13 · Results follow the TaskResult contract

DSH turns report through `finish_task` and must reproduce the spike's expected TaskResult for every outcome case.
- **Given** cases done, plain-text, inner-limit, needs-input, invalid-status, invalid-payload, invalid-reference, retry-model, retry-protocol, retry-infrastructure, bad-request, lost-after-finish, deadline and cancel (`docs/spikes/dsh-phase02-r2-evidence.json`), **when** each runs, **then** its TaskResult matches the spike's.

### R14 · The DSH benchmark meets the baseline rule

`local-dsh@1` must pass the ten benchmark tasks within the baseline rule.
- **Given** `make benchmark` on the `dsh` profile, **when** it finishes, **then** at most one task is lost.

## Decisions

### D1 · One seam, two runners

`run_harness_turn` calls a session store for load, truncation, capture and
acknowledgement. `SQLAlchemySession` backs `openai_agents`. DSH session files are
stored as a separate session blob, never inside the workspace tarball, where tools
would see them. For DSH, `session_position` is the session blob's digest. Rejected:
a DSH-only Activity (duplicates attempt, budget and checkpoint logic).

### D2 · Port the spike's rules

New modules in `harness_activity/dsh/`: failure classification, ownership by
(turn, attempt) order, the gateway ledger with admission denials, the executor
using production tool and skill code, and the barrier. Each keeps its spike tests. Rejected: calling spike code from production (it is
fixture-shaped and ignores production config). Details: notes.md#d2

### D3 · Paired container, no Docker access

Each DSH worker has a companion `dsh` container with no credentials, no network
and a read-only root. It shares a volume for attempt trees and Unix sockets. The
launcher runs one DSH process per attempt in its own process group and cgroup,
kills it when the worker's control socket closes, and reaps leftovers at start-up.
It works the same in Compose and a Kubernetes pod. Rejected: Docker socket or
proxy, per-attempt Pods, LXC/Incus, DinD (privilege, platform or runtime reasons in
notes.md#d3). Details: notes.md#d3

### D4 · Production skill and tool semantics

Files, commands, MCP tools and the skill bundle are presented as
`harness_activity/tools.py` and `skills.py` present them, over the executor.
Commands run in the DSH container through the launcher. Rejected: DSH's native
tools and skill loader (tool bodies would be unobserved).

### D5 · New template and profile, gated default

Add `local-dsh@1` and a `dsh` profile. Switch the `default` profile only after R14
passes and the owner approves. Rejected: editing `local-default@1` in place (it
breaks the pinned lock and the recorded baseline).

### D6 · The barrier

1. The gateway holds the next model request. DSH's checkpoint policy has already
   flushed the earlier tool results to session files before sending it.
2. The newest tool-call ID in that request must appear in the session files;
   otherwise the barrier fails.
3. The launcher freezes the attempt's cgroup, so no writer runs during capture.
4. The worker captures the session blob and workspace and acknowledges both under
   the ownership fence.
5. The cgroup is thawed and the request released.

Rejected: copying a live home directory (no consistency proof). We will adopt an
upstream flush/export API if DSH adds one.

### D7 · Nullable usage with a flag

A migration makes `tokens_in`/`tokens_out` nullable and adds `usage_known`.
Unknown usage is stored as null with `usage_known = false`, never as 0.
Rejected: storing 0 (the spike's F1/F2 failure).

### D8 · A minimal AgentEvent sink

Phase 01 adds an `AgentEvent` sink interface (`docs/roadmap/schemas.md`) with a
no-op and an in-memory implementation. Both runners emit `status`, `tool_call`,
`tool_result` and `token` events. Roadmap Phase 2 replaces the sink with its
transport. Rejected: deferring events (Phase 2 would then refit DSH).

### D9 · Lost mid-generation: retry, charged conservatively

A request with unknown usage is charged the context window plus its `max_tokens`.
The attempt is then retried and flagged unknown. Rejected: failing the turn (the
spike's fail-closed choice; it makes worker loss fatal). Rejected: charging 0
(hides spend).

## Assumptions

- DSH 0.2.2rc2 is the first pin; a newer release reruns the R13 cases first.
- cgroup v2 freeze and process-group kill work inside an unprivileged container on the Compose hosts (verified in phase 02 task 1.2).

## Risks

- The barrier fails under real worker loss → R4 and R7 tests SIGKILL real workers.
- The pre-release runtime changes behaviour → R12 pins; the R13 cases rerun on every bump.
- The launcher misses a leftover process → reap at start-up and verify with the R7 test.
- Cost and latency (~1.9x wall time in the spike) → measured in R14; the owner judges.

## Rollout & rollback

Deploy order: pinned DSH image, then the `dsh` worker pair on `tpl.local-dsh`, then
the `dsh` profile, then (after R14 and owner approval) the `default` profile.

Rollback reverts two fields of the `default` profile (`harness`, `allowed_templates`).
DSH workers keep running until in-flight DSH turns drain, or the owner cancels
those turns if DSH is at fault. No data migration is undone; D7's columns stay.

## Open questions

- Is the R14 cost (tokens and wall time) acceptable for switching the default? The owner decides at phase 03 task 2.1.

## Impact

- Packages / directories: `harness_activity/`, `common/schemas/`, `common/persistence/` (migration), `registry/`, `workers/`, `infra/`, `tests/`, `docs/roadmap/` (schemas, decision log), `docs/operations/`.
- Data: attempt rows gain nullable tokens and `usage_known`; checkpoints gain a DSH session blob.
- Jobs / APIs: `run_harness_turn`; new queue `tpl.local-dsh`; no gateway API change.

## Links

- [ADR-0005](../../adr/0005-adopt-dsh-as-primary-agent-harness.md): adopt DSH inside Temporal Activities, under five conditions.
- [DSH spike report](../../spikes/dsh-harness.md): evidence, limits and measured cost.
- [Spike bridge](../../../spikes/dsh-harness/README.md): the code and tests to port.
- [Roadmap Phase 2](../../roadmap/phases/phase-2.md): event streaming that consumes R11.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | [Harness seam and registry](phases/01-harness-seam.md) | draft | 0/5 |
| 02 | [DSH runner and worker pair](phases/02-dsh-runner.md) | draft | 0/6 |
| 03 | [Acceptance and default switch](phases/03-acceptance.md) | draft | 0/4 |

## Decision log

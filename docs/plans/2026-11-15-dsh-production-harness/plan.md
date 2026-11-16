---
title: Run production agents on DSH
status: in-progress
created: 2026-11-15
updated: 2026-11-15
design_review: { status: passed, rounds: 3, last: 2026-11-15 }
approved: 2026-11-15
adr_review: pending
---

# Run production agents on DSH

## Summary

Make DeepSeek Harness (DSH) run PraxisMesh agent turns (ADR-0005, as amended by
ADR-0006) before roadmap Phase 2, so Phase 2's event streaming is built once, on DSH.
Temporal keeps dispatch, retries and coordination. Each worker is paired with a DSH
container that has no credentials or network. Its launcher gives each attempt its
own cgroup, command UID and mount view. The worker keeps the Activity, credentials,
model gateway and the executor that runs file and shop tool bodies; commands run in
the attempt's cgroup. Both runners share one session/checkpoint seam with a
transactional fence (D1, D10). Workers check the pinned DSH digests (R17). A
migration makes unknown usage explicit and charges lost requests conservatively (D7,
D9). The `default` profile moves to DSH only after the benchmark passes and the
owner approves. Risks: the in-house barrier (D6) under real worker loss, and ~1.9x
wall time measured in the spike.

## Why

ADR-0005 adopts DSH under five conditions (condition 3 amended by ADR-0006). The
[spike](../../spikes/dsh-harness.md) proved them only in isolation:

| Condition | Requirements |
| --- | --- |
| Pin the DSH release and digests | R17 |
| A reviewed checkpoint consistency contract | R5, R6, R7 |
| One isolated boundary per attempt; model and tool use observed outside it | R8–R11, R15 |
| Production capability semantics; DSH discovery, skill loader, jobs, delegation off | R14 |
| `openai_agents` stays selectable | R3, R4 |

## What changes

- A session/checkpoint seam with a transactional fence, used by both runners (D1, D10).
- Production modules ported from the spike into `harness_activity/dsh/` (D2).
- A DSH container and launcher paired with each DSH worker (D3).
- `dsh` in the `Harness` type, registry and `schemas.md`; a `local-dsh` template and `dsh` profile.
- An additive migration for unknown usage, a usage ledger and session refs (D7, D9).
- An `AgentEvent` sink (D8); the spike's control cases as integration tests; a DSH benchmark.

### Non-goals

- Roadmap Phase 2 itself ([its phase file](../../roadmap/phases/phase-2.md)), retiring `openai_agents`, Kubernetes (roadmap Phase 7), hosted models.

## Terms

- **DSH**: DeepSeek Harness, the agent runtime chosen in ADR-0005.
- **Runner**: an implementation of `HarnessRunner` (`harness_activity/runner.py`).
- **Profile / template**: registry agent profile (allowed templates, limits) / worker template (capabilities, harness).
- **DSH container**: the credential-free container paired with a DSH worker.
- **Launcher**: the process in the DSH container that starts, freezes, stops and reaps attempts.
- **Attempt tree**: `/attempts/<task>/<turn>/<attempt>` on a tmpfs volume both containers mount.
- **Gateway**: the worker-side model proxy that admits requests and writes the usage ledger.
- **Executor**: the worker-side process that runs granted file, shop and skill tool bodies and records each call.
- **Barrier**: the D6 steps that make a checkpoint consistent before it is committed.
- **Committed checkpoint**: a checkpoint row written through the D10 fence.
- **Current / stale / lost attempt**: the highest (turn, attempt) seen for a task / any lower one / one that ended without writing its attempt row.
- **Session store**: the D1 interface; **`SQLAlchemySession`** is the OpenAI SDK session it wraps for `openai_agents`.
- **`session_position`**: the item count a checkpoint records for `SQLAlchemySession`; truncation pops items after it on resume.
- **Workspace tarball**: the packed workspace blob a checkpoint references (`harness_activity/workspace.py`).
- **`finish_task`**: the tool through which a turn reports done or needs-input.
- **Baseline rule**: at most one task failed against `docs/benchmarks/baseline.json` (10/10, openai-agents).
- **The owner**: the repository owner, who approves the profile switch and its cost.

## Requirements

### R1 · Only versioned harness values load
A template's `harness` must be a `Harness` value pinned in the registry lock.
- **Given** a template with an unknown harness, **when** the registry loads, **then** loading fails.

### R2 · Profile and template harness match at load time
A profile may only allow templates whose `harness` equals its own.
- **Given** a `dsh` profile allowing `local-default`, **when** the registry loads, **then** loading fails.

### R3 · openai_agents passes the conformance suite
`openai_agents` templates must pass the conformance suite through the new seam.
- **Given** `local-default`, **when** the conformance suite runs on the seam, **then** it passes.

### R4 · openai_agents meets the baseline rule
`openai_agents` templates must still meet the baseline rule.
- **Given** `local-default`, **when** `make benchmark` runs, **then** at most one task fails.

### R5 · Checkpoints are committed only after the barrier
A DSH checkpoint is committed only after the D6 barrier succeeds.
- **Given** worker loss after a committed checkpoint, **when** a new worker resumes, **then** conversation and edits survive without the old attempt tree.

### R6 · Stale attempts write no checkpoint or attempt outcome
A stale attempt never writes a checkpoint or an attempt outcome through the run path.
- **Given** attempt 1 resumes after attempt 2 started, **when** it writes, **then** the fence rejects it.

### R7 · Stale attempts return no artifact reference or outcome
A stale attempt never returns an artifact reference or outcome; staleness is judged at the fenced write.
- **Given** a stale attempt that finished, **when** it publishes, **then** it returns no `TurnOutcome` and the task result has none of its outputs.

### R8 · Attempts stop within the 5 s grace
Every DSH process must exit within 5 s of a deadline, cancellation or step limit, and nothing it started may run during the following 10 s.
- **Given** a stalled model or tool, **when** the deadline fires, **then** the process exits cooperatively and the window is clean.

### R9 · A forced stop is a failure
An attempt that needs the launcher's kill to stop is recorded failed.
- **Given** a SIGTERM the runtime ignores, **when** the grace passes, **then** the attempt is recorded failed; the launcher's kill is cleanup, not success.

### R10 · Worker death leaves no attempt running
When a worker dies, the launcher stops its attempt and removes its tree.
- **Given** a worker SIGKILLed mid-turn, **when** 10 s pass, **then** no process or attempt tree for that attempt remains.

### R11 · Usage comes from the gateway ledger
Token and tool usage come from the gateway ledger and executor, never from the runtime's report alone.
- **Given** retries in a turn, **when** usage is reported, **then** it equals the ledger's settled totals.

### R12 · Unknown usage is recorded, never zero
Unobserved usage is stored as null with `usage_known = false`, never as 0.
- **Given** an unsettled ledger row from a lost attempt, **when** the next attempt starts, **then** that attempt row has null tokens and `usage_known = false`.

### R13 · Unknown usage is charged conservatively
Each unsettled request is charged the D9 estimate before the turn retries.
- **Given** the R12 case, **when** the budget is computed, **then** it is charged the D9 estimate and the attempt is retried.

### R14 · Capabilities come only from the template
The DSH process gets only template-granted tools, skills and MCP servers, with the notes.md#r14 features off.
- **Given** task text or workspace files naming extra tools, **when** a turn runs, **then** no new tool, plugin, skill or network route appears.

### R15 · Commands cannot see the session or other attempts
Commands only see their own attempt's workspace and die with their attempt.
- **Given** a command that reads the session file or another attempt tree, or backgrounds itself, **when** it runs, **then** the read fails and the background process dies with the attempt.

### R16 · Turns emit AgentEvents
The executor emits `tool_call`/`tool_result` and the gateway emits `token` (per-response usage counts, no text) through the D8 sink.
- **Given** a turn with two tool calls, **when** it runs, **then** the sink gets ordered events with attempt ID and no prompt text.

### R17 · Workers verify the DSH pin
Workers serve a DSH queue only when the launcher's digests match the registry lock.
- **Given** a launcher reporting a digest that differs from the registry lock, **when** the worker starts, **then** it refuses to serve the queue.

### R18 · Results follow the TaskResult contract
DSH turns report through `finish_task` and must reproduce the spike's TaskResult for each outcome case.
- **Given** each spike outcome case (done, plain-text, inner-limit, needs-input, invalid-status, invalid-payload, invalid-reference, retry-model, retry-protocol, retry-infrastructure, bad-request, lost-after-finish, deadline, cancel), **when** it runs, **then** its TaskResult matches `docs/spikes/dsh-phase02-r2-evidence.json`.

### R19 · The DSH benchmark meets the baseline rule
`local-dsh` must meet the baseline rule.
- **Given** `make benchmark` on the `dsh` profile, **when** it finishes, **then** at most one task fails.

## Decisions

### D1 · One seam, two runners
`run_harness_turn` calls a session store for load, truncation, capture and commit.
DSH sessions are a separate session blob (`session_ref`, `session_digest`), never in
the workspace tarball where tools would see them; `session_position` stays 0.
Rejected: a DSH-only Activity (duplicates attempt, budget and checkpoint logic).

### D2 · Port the spike's rules
Classification, attempt order, gateway ledger, executor and barrier move to
`harness_activity/dsh/` with their tests. Rejected: importing spike code (it is
fixture-shaped and ignores production config). Details: notes.md#d2

### D3 · Paired DSH container per worker (ADR-0006)
No container gets Docker access; the launcher isolates each attempt by cgroup, UID
and mount namespace, and DSH templates pin `concurrency_per_pod: 1`. Rejected:
Docker socket (root on the host); socket proxy (another privileged component);
per-attempt Pods (Kubernetes only); LXC/Incus (second runtime); DinD (privileged).
Details: notes.md#d3

### D4 · Production tool semantics through the executor
Tool bodies split out of `FunctionTool` serve both runners; commands run in the
attempt cgroup as a separate UID; the image installs only the granted `cli_tools`.
Rejected: DSH native tools and skill loader (their bodies would be unobserved).

### D5 · New template and profile, gated default
Add `local-dsh` and a `dsh` profile in phase 01; switch `default` only after R19 and
owner approval. Rejected: editing `local-default` (breaks its lock and baseline).

### D6 · The barrier
Before every model request after the first, hold the request, require the newest
tool-call ID in the session files, freeze the attempt cgroup, capture, commit
through D10, thaw and release. A failed barrier is a retryable infrastructure
failure with no checkpoint. Rejected: copying a live home directory (no consistency
proof). Details: notes.md#d6

### D7 · Explicit unknown usage
An additive migration adds nullable tokens with `usage_known`, a `usage_ledger`
table, session refs, `usage_known` on the result schemas, and `context_window` on
templates. Rejected: storing 0 (spike findings F1/F2). Details: notes.md#d7

### D8 · A minimal AgentEvent sink
An `AgentEvent` sink (`docs/roadmap/schemas.md`) with no-op and in-memory
implementations; roadmap Phase 2 replaces it with its transport. Rejected:
deferring events (Phase 2 would refit DSH).

### D9 · Lost mid-generation: charge conservatively and retry
Unsettled ledger rows from a lost attempt are charged `context_window + max_tokens`
each, and the turn retries. This replaces the spike's fail-closed denial. Rejected:
failing the turn (makes worker loss fatal); charging 0 (hides spend). Details: notes.md#d9

### D10 · A transactional fence
Start, checkpoint insert and finish each check, under a per-task lock in one transaction,
that no newer (turn, attempt) exists. Artifact references leave the Activity only after the
fenced finish; unreferenced blobs can remain. Rejected: a separate pre-check as the guarantee
(races a new attempt). Details: notes.md#d10

## Assumptions

- DSH 0.2.2rc2 is the first pin; a newer release reruns the R18 cases first.
- DSH's checkpoint policy flushes earlier tool results to session files before each model request (observed in the spike).
- cgroup v2 freeze works in the DSH container with the notes.md#d3 settings; phase 01 task 0.1 checks it, with SIGSTOP as fallback.

## Risks

- The barrier fails under real worker loss → R5 and R10 tests SIGKILL real workers.
- The pre-release runtime changes → R17 pins; the R18 cases rerun on every bump.
- A process escapes the attempt boundary → R15 tests; launcher reaping at start.
- Cost and latency (~1.9x wall time, ~30% more input tokens in the spike) → measured in R19.

## Rollout & rollback

Order: additive migration, orchestrator, DSH image and worker pair, `dsh` profile;
then, after R19 and owner approval, the `default` profile. No backfill. Rollback
reverts the `default` profile's `harness` and `allowed_templates`. DSH tasks already
running finish on DSH, because `openai_agents` cannot resume a DSH checkpoint; the
drain is bounded by the profile's `max_wall_time`. Code rollback below D7 is not
supported.

## Open questions

- None. The owner judges the R19 cost when approving the switch in phase 03 task 2.1.

## Impact

- Packages / directories: `harness_activity/`, `common/schemas/`, `common/persistence/`, `registry/`, `workers/`, `infra/`, `tests/`, `docs/roadmap/`, `docs/operations/`.
- Data: attempt rows (nullable tokens, `usage_known`), new `usage_ledger`, checkpoint session refs.
- Jobs / APIs: `run_harness_turn`; queue `tpl.local-dsh`; result schemas gain `usage_known`.

## Links

- [ADR-0005](../../adr/0005-adopt-dsh-as-primary-agent-harness.md): adopt DSH inside Temporal Activities, under five conditions.
- [ADR-0006](../../adr/0006-per-attempt-isolation-boundary-for-dsh.md): condition 3 becomes one isolated boundary per attempt.
- [Spike bridge](../../../spikes/dsh-harness/README.md): the code and tests to port.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | [Harness seam and registry](phases/01-harness-seam.md) | done | 6/6 |
| 02 | [DSH runner and worker pair](phases/02-dsh-runner.md) | in-progress | 7/8 |
| 03 | [Acceptance and default switch](phases/03-acceptance.md) | approved | 0/4 |

## Decision log

2026-11-15 · D3 adopted after design review round 2: paired DSH container per worker; ADR-0006 amends ADR-0005 condition 3.
2026-11-15 · D7, D9, D10 adopted after round 2 (unknown usage, conservative charge, fence). Phase 01 gate: per-attempt cgroup, mount namespace and freeze need `SYS_ADMIN` in the DSH container, held by the launcher only; commands drop all capabilities and get a seccomp filter blocking user namespaces (notes.md#d3). D10, R7 clarified after phase 01 impl review round 2 (lock, refusal rows, artifact refs).

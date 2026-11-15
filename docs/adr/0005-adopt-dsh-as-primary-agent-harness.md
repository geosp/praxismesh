---
id: ADR-0005
title: Adopt DeepSeek Harness as the primary agent harness, inside Temporal Activities
status: accepted
date: 2026-11-15
issue: "#62"
related:
  - docs/plans/2026-11-14-dsh-harness-evaluation/plan.md
  - docs/spikes/dsh-harness.md
  - PROJECT_PLAN.md §2, §4.16
  - docs/roadmap/design-decisions.md §4.1
supersedes: null
superseded_by: null
---

# ADR-0005: Adopt DeepSeek Harness as the primary agent harness, inside Temporal Activities

## Context and problem statement

PraxisMesh runs each agent turn inside a Temporal Activity. The only production
harness is `openai_agents` (OpenAI Agents SDK, `harness_activity/runner.py`). The
owner asked whether DeepSeek Harness (DSH) should run agents instead.

The [DSH spike](../spikes/dsh-harness.md) ran DSH 0.2.2rc2 in an isolated container
per attempt, with Temporal and PraxisMesh still owning dispatch, retries and
coordination. At frozen commit `d2d782c`, all of these passed:

- clean-worker recovery and attempt fencing (R4);
- bounded stop and cancellation (R5);
- independent usage accounting (R6);
- TaskResult mapping, 14 cases through `TaskWorkflow` (R7);
- the ten-task benchmark, 10/10 against the 10/10 baseline (R8).

The spike's implementation review raised 10 Majors, all fixed and rerun. The
owner waived the second review round and verification, and closed the spike as a
success.

Constraints the decision must keep: Temporal stays the only durable coordinator;
all I/O stays in Activities; capabilities come only from trusted templates; the
default deployment stays local and self-hosted (§2).

Known limits from the spike:

- DSH is a release candidate, and upstream calls it experimental.
- Its native build provenance is unestablished; the upstream licence is MIT.
- Checkpoint consistency relied on a spike barrier (held request, session-marker
  check, container pause), not a DSH export API.
- Cost: ~30% more input tokens and ~1.9x wall time against the same-day
  production runner, partly from spike overhead.

## Considered options

- Keep `openai_agents` as the only harness.
- Adopt DSH as the primary harness, inside Temporal Activities, behind a
  versioned harness choice in the registry.
- Adopt DSH including its own scheduling and delegation as orchestration.

## Decision outcome

Chosen option: "Adopt DSH as the primary harness, inside Temporal Activities",
because the spike showed it meets every hard gate (R1–R7, R10) and the benchmark
regression rule (R8) while Temporal keeps durable coordination. Using DSH's own
scheduling would add a second durable coordinator, which §2 rules out.

Adoption conditions (the migration must satisfy all of them):

1. Pin an exact DSH release and its digests in the worker image; record its
   licence notices.
2. Make checkpoint consistency a reviewed contract: either a supported DSH
   flush/export API or the spike barrier, reimplemented as production code
   with tests.
3. Run one container per attempt with no host credentials. Keep model egress
   through a trusted gateway, and record tool-body execution in a trusted
   executor.
4. Present template capabilities (files, commands, MCP, skills) with production
   semantics; keep DSH native discovery, skill loading, jobs and delegation off.
5. Add DSH as a versioned `harness` value in the registry. Keep `openai_agents`
   available and selectable per template until DSH passes its own phase gate.

Sequencing: do the migration before runtime Phase 2, so Phase 2's event mapping
is built once, against DSH. This changes the phase order; see the
[decision log](../roadmap/decision-log.md).

### Consequences

- Good, because a single runtime serves agents with persistent sessions and
  replaceable components, while existing recovery, budget and result contracts
  are preserved.
- Good, because `openai_agents` stays available as a fallback per template.
- Bad, because the project depends on a pre-release runtime whose native binary
  provenance is not established.
- Bad, because per-attempt containers and checkpoint pauses add latency and token
  overhead (measured, no threshold set).
- Follow-up: a migration implementation plan in `docs/plans/` covering session
  and checkpoint abstraction, worker packaging, capability presentation, registry
  harness versioning, and Phase 2 event mapping. It needs design review before
  code.

### Confirmation

The migration plan's phase gates: the existing harness conformance tests
(`tests/test_runner_conformance.py`) extended to DSH; the recovery, bounded-stop,
accounting and outcome cases from the spike, ported to production tests; and
`make benchmark` on a DSH template within the existing regression limit.

## Links

- [Issue #62](https://github.com/geosp/praxismesh/issues/62)
- [Spike plan](../plans/2026-11-14-dsh-harness-evaluation/plan.md) and [reviews](../plans/2026-11-14-dsh-harness-evaluation/reviews.md)
- [Spike report](../spikes/dsh-harness.md) and [evidence](../spikes/dsh-phase02-r2-evidence.json)
- [Spike README](../../spikes/dsh-harness/README.md)

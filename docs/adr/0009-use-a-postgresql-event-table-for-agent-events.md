---
id: ADR-0009
title: Carry agent progress events in a PostgreSQL event table, behind an event-transport interface
status: accepted
date: 2026-11-18
issue: "#76"
related:
  - docs/plans/2026-11-17-event-transport-spike/plan.md
  - docs/spikes/event-transport.md
  - docs/roadmap/design-decisions.md
  - docs/adr/0007-fence-harness-attempts-in-one-transaction.md
supersedes: null
superseded_by: null
---

# ADR-0009: Carry agent progress events in a PostgreSQL event table, behind an event-transport interface

## Context and problem statement

Phase 2 streams agent progress, token and tool events to observers (`agentctl tail`, later the
gateway and the UI). Readers must resume from an offset without gaps or duplicates, learn when
events they asked for have expired, and keep Temporal histories bounded. Design §4.4 prefers
Temporal Workflow Streams "where supported and stable enough", with a fallback behind an
interface. Streams is a Public Preview API whose expiry and history behaviour was not documented
well enough to adopt it untested, so a spike (issue #76) compared it with a PostgreSQL event
table and NATS JetStream against one shared test suite; Streams and the table also ran two
workloads (a recorded DSH turn and a synthetic multi-agent load), and NATS ran the suite only, which includes
the recorded turn (R7) but not the synthetic load.

## Considered options

- Temporal Workflow Streams (`temporalio.contrib.workflow_streams`), one hosting Workflow per
  agent workflow.
- A PostgreSQL event table, behind an event-transport interface (a per-workflow counter and
  `LISTEN/NOTIFY`).
- NATS JetStream with a stream per workflow.

## Decision outcome

Chosen option: "A PostgreSQL event table, behind an event-transport interface". Both Workflow
Streams and the table passed every must-pass requirement of the spike in all 3 runs, and the
spike's rule (plan D2, following §4.4) selected Streams. The owner chose the table instead, a
deliberate departure from §4.4, because the measurements favour it on everything the rule did not
weigh:
- Temporal used ~20-23x less CPU (1.4% against 32.4%, medians over 3 runs), and the table has
  no per-run limit, while each Streams run holds at most 2,000 Updates, poll Updates included
  (derived from the Update counts, each following observer adds about one poll Update per batch;
  not measured per observer).
- A stable API and ~183 lines of code, against a Public Preview API with a private import and
  ~314 lines in the spike's two Streams files, which needed workarounds for batch-ID dedup,
  expiry reporting and cancellation.
- Event writes can take ADR-0007's fence in the same transaction as the attempt rows.
Latency did not decide it: at the spike's closed-loop load p95 was 187 ms for the table and 199 ms
for Streams, but that generator gave Streams ~5% less load; an open-loop rerun showed the table
passing at the full offered load with p95 204 ms, and Streams was not rerun at equal load (spike
report).

How it is used (from the spike):
- One event table keyed by workflow and offset, a per-workflow counter row locked on publish, so
  offsets are gap-free, and a batch-ID row written in the same transaction, so a re-sent batch is
  stored once.
- One `NOTIFY` per batch; following readers `LISTEN`, clear their wake-up before each fetch, and
  poll every 1 s as a fallback.
- Every reader reports an offset jump as expiry and fails on a repeated offset.

NATS JetStream passed the correctness suite (a run that predates the cancel check) but lost on
cost: it adds a new component (the documented Kubernetes deployment is a 3-replica StatefulSet)
and its writes cannot share a transaction with the attempt rows, so ADR-0007's fence would need a
justification. It stays the upgrade path if event volume or fan-out outgrows PostgreSQL; the
interface keeps the code change contained, and that switch would need its own fencing
justification under ADR-0007.

What Phase 2 commits to (from the spike report):
- Batch IDs name the attempt (`<workflow>:<attempt>:<n>`): a retried publisher that reuses batch
  IDs has its new events dropped as re-sends. Dedup holds within a re-send horizon (600 s in the
  spike's load runner; the suite checks it at 60 s), not forever.
- A publish from a superseded attempt is refused as ADR-0007 refuses other attempt writes
  (`FenceRejected`, then `Superseded`), never dropped silently.
- Readers use both expiry checks: the retained-base check before a read (`expiry_for`) and the
  offset-jump check during it.
- Events live outside Temporal history, so Continue-As-New carries no event state; offsets stay
  continuous because the table assigns them.

What Phase 2 must still decide:
- The fence's lock order against the counter row (to avoid deadlock) and its cost per publish;
  the spike measured neither.
- Tenant and repository scoping: the spike table has no tenant column (`docs/roadmap/schemas.md`).
- Keying: the spike keys offsets by workflow, while the fence is per task and `AgentEvent.seq`
  counts per attempt; Phase 2 sets how the table offset, `seq` and `attempt_id` relate.
- Where token text lives (`AgentEvent` payloads hold no model text).

### Consequences

- Good, because no new component and no preview API; the events will share the application
  database's backups (Phase 3A), access control and Kubernetes path.
- Good, because event writes can take ADR-0007's fence in the same transaction; the spike did not
  implement it, and Phase 2 must.
- Bad, because the table grows with every event and retention means `DELETE` churn: Phase 3A's
  retention work needs time-based partitioning or equivalent for it.
- Bad, because each following reader holds a database connection while it follows (derived from
  the code, not measured: the spike's pool allowed 20, so with the spike's 4 publishers sharing it,
  beyond 16 followers in one process the publishers queue for connections, and at 20 they all
  wait), and the spike uses one global
  `NOTIFY` channel, so every follower's connection receives every workflow's notification (only
  the matching workflow's reader fetches again). Fan-out to
  many observers (Phase 4 gateway, Phase 8 UI) needs a per-workflow channel or a reader that fans
  out in memory, or a pooler.
- Bad, because it departs from the §4.4 preference. The decision log records why; §4.3, §4.4,
  the core plan's architecture diagram and risk table, and Phase 2's first item were updated to
  match when this ADR was accepted.
- Follow-up: revisit this ADR if event writes become a visible share of database load or
  connection counts approach the limit.

### Confirmation

Phase 2 is to port the spike's shared suite (`spikes/event-transport/tests/test_suite.py`) and
load runner (`spikes/event-transport/load.py`) and the notify test
(`spikes/event-transport/tests/test_table_notify.py`, a notification during a fetch is not lost),
as of commit `bfa210b`; the spike folder may be
deleted later) into its own tests and run them against its implementation behind the same
interface. The suite does not exercise the fence or attempt-named batch IDs, so Phase 2 adds tests
for both, and its implementation review checks the reader rule, the batch dedup, the batch-ID
format, the fence and its lock order.

## Links

- [Spike report](../spikes/event-transport.md): measurements, operating cost and fencing per option.
- [Spike plan](../plans/2026-11-17-event-transport-spike/plan.md), D2 (decision rule), D5 (mechanisms).
- Design §4.4 (`docs/roadmap/design-decisions.md`): the Streams preference this ADR departs from.
- [ADR-0007](0007-fence-harness-attempts-in-one-transaction.md): new attempt write paths take the fence.

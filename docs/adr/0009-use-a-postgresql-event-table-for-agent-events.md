---
id: ADR-0009
title: Carry agent progress events in a PostgreSQL event table, behind an event-transport interface
status: proposed
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
table and NATS JetStream against one test suite and one load.

## Considered options

- Temporal Workflow Streams (`temporalio.contrib.workflow_streams`), one hosting Workflow per
  agent workflow.
- A PostgreSQL event table with a per-workflow counter and `LISTEN/NOTIFY`.
- NATS JetStream with a stream per workflow.

## Decision outcome

Chosen option: "A PostgreSQL event table, behind an event-transport interface". Both Workflow
Streams and the table passed every must-pass requirement of the spike in all 3 runs, and the
spike's rule (plan D2, following §4.4) selected Streams. The owner chose the table instead, a
deliberate departure from §4.4, because the measurements favour it on everything the rule did not
weigh:
- Temporal used ~20-23x less CPU (1.4% against 32.4%, medians over 3 runs), and the table has
  no per-run limit, while each Streams run holds at most 2,000 Updates and every observer adds one
  poll Update per batch.
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

NATS JetStream passed the correctness suite (a run that predates the cancel check) and stays the
upgrade path if event volume or fan-out
outgrows PostgreSQL; the interface keeps that switch contained.

### Consequences

- Good, because no new component and no preview API; the events will share the application
  database's backups (Phase 3A), access control and Kubernetes path.
- Good, because event writes can take ADR-0007's fence in the same transaction; the spike did not
  implement it, and Phase 2 must.
- Bad, because the table grows with every event and retention means `DELETE` churn: Phase 3A's
  retention work needs time-based partitioning or equivalent for it.
- Bad, because each following reader holds a database connection while it follows (the spike's
  pool allowed 20, so with the spike's 4 publishers sharing it, beyond 16 followers in one process
  the publishers queue for connections, and at 20 they all wait), and the spike uses one global
  `NOTIFY` channel, so every follower's connection receives every workflow's notification (only
  the matching workflow's reader fetches again). Fan-out to
  many observers (Phase 4 gateway, Phase 8 UI) needs a per-workflow channel or a reader that fans
  out in memory, or a pooler.
- Bad, because it departs from the §4.4 preference; the decision log records why.
- Follow-up: Phase 2 decides where token text lives (`AgentEvent` payloads hold no model text);
  revisit this ADR if event writes become a visible share of database load or connection counts
  approach the limit.

### Confirmation

Phase 2 is to run the spike's shared suite (`spikes/event-transport/tests/test_suite.py`) and load
runner (`spikes/event-transport/load.py`) against its implementation behind the same interface,
and its implementation review is to check the reader rule, the batch dedup and the fence.

## Links

- [Spike report](../spikes/event-transport.md): measurements, operating cost and fencing per option.
- [Spike plan](../plans/2026-11-17-event-transport-spike/plan.md), D2 (decision rule), D5 (mechanisms).
- Design §4.4 (`docs/roadmap/design-decisions.md`): the Streams preference this ADR departs from.
- [ADR-0007](0007-fence-harness-attempts-in-one-transaction.md): new attempt write paths take the fence.

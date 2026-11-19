---
id: ADR-0010
title: Keep agent messages in a durable PostgreSQL inbox, and use Temporal Signals only to wake the recipient
status: proposed
date: 2026-11-19
issue: "#79"
related:
  - docs/plans/2026-11-18-phase-2-events-and-comms/plan.md
  - docs/plans/2026-11-18-phase-2-events-and-comms/notes.md
  - docs/roadmap/design-decisions.md
  - docs/adr/0007-fence-harness-attempts-in-one-transaction.md
  - docs/adr/0009-use-a-postgresql-event-table-for-agent-events.md
supersedes: null
superseded_by: null
---

# ADR-0010: Keep agent messages in a durable PostgreSQL inbox, and use Temporal Signals only to wake the recipient

## Context and problem statement

From Phase 2, tasks of one request message and ask each other, and a task may end a turn
`waiting` and sleep until something arrives. The design calls for agent-to-agent messages in a
durable PostgreSQL inbox with a trigger that wakes the recipient (`docs/roadmap/design-decisions.md`,
§4.4 "Real-time agent communications"), but leaves open how a sleeping `TaskWorkflow` learns that its inbox
has rows. The answer has to hold under these requirements of the Phase 2 messaging plan:

- A message accepted by the sender is never lost, even when the recipient's worker or the
  dispatcher is down (R13, R14), and reaches at most one turn of the recipient (R13).
- A woken turn sees every message that arrived before it started, and none twice (R13, R15).
- A waiting task's Temporal history stays bounded however often it is woken or messaged
  (R33: no run above 2,000 events; R28: no message body in the history).
- The tool server the agent calls (`comms_mcp`, a stdio subprocess per attempt) has no Temporal
  client: design §4.4 keeps it on "a scoped service/client, not arbitrary Temporal admin APIs".

## Considered options

- The inbox is the source of truth, and a Signal is only a wake hint: the sender commits the
  message and, only if the recipient sleeps, a wake row; a dispatcher in the orchestrator worker
  turns wake rows into `inbox` Signals; the Workflow reads its inbox by claiming it in an Activity.
- Signals carry the messages: `comms_mcp` (or a service it calls) Signals the recipient's
  Workflow with the message.
- One long-polling Activity per waiting task waits on the inbox until a row arrives.

## Decision outcome

Chosen option: "The inbox is the source of truth, and a Signal is only a wake hint", because it
keeps every message durable before anyone is woken, keeps bodies out of Temporal histories, needs
no Temporal client in the tool server, and holds no worker slot while a task sleeps.

Rejected:
- Signals carrying the messages, because the tool server would need a Temporal client, against
  design §4.4, and each message body and Signal would land in the recipient's history, against
  R28 and R33.
- One long-polling Activity per waiting task, because each sleeping task would hold a worker slot
  (and its heartbeats) for as long as it waits, so waiting tasks would compete with running turns
  for worker capacity; a sleeping Workflow with a timer holds none.

As built (plan D6 and D7; the last bullet is context from D11 and D17, which this ADR does not
decide):
- A send commits the message row with its body (at most 16,384 characters) under the request
  lock. Only when the recipient is marked sleeping does the same transaction add its one wake row
  (unique per recipient) and `NOTIFY message_wakes`, so Signals scale with sleeps, not messages.
- The dispatcher `LISTEN`s and polls every 1 s. For each wake row, in that row's own transaction,
  it deletes the row and then sends the `inbox` Signal: a sender's concurrent wake insert waits
  for that transaction and adds a new row, so no wake is lost; a failed Signal rolls the delete
  back; a closed or missing Workflow drops the row.
- After a `waiting` turn the Workflow runs `claim_inbox` before it sleeps. The claim assigns
  pending rows to the next turn and returns their IDs, a count and the next question deadline,
  never bodies; with none it marks the task sleeping. A woken turn's Activity reads the rows
  assigned to its turn. A Signal carries no data: it only ends the sleep, and the Workflow claims
  again.
- A waiting run continues as new past 1,000 events or when Temporal suggests it, carrying its
  state in `TaskStart.carried`; every ending runs `complete_task`, which closes the task's
  messages and wakes those waiting on it.

### Consequences

- Good, because a message survives any worker, dispatcher or Temporal outage once its send
  returns; wake rows wait for a stopped dispatcher, and deadlines and timeouts still fire.
- Good, because histories hold only claim results and Signals: one task woken 100 times back to
  back ran in three runs of 1,009, 1,013 and 443 events, and 50 messages during one turn brought
  no Signal (`tests/integration/test_messaging_history.py`).
- Good, because every attempt's inbox write (a send, question, reply or marking rows read) shares
  a transaction with ADR-0007's fence and the request lock, as ADR-0009's event table does; the
  orchestrator's claim and `end_task` take the request lock only.
- Bad, because waking takes two hops (wake row, then Signal) and adds a component, the
  dispatcher, which must run beside the orchestrator worker; while the dispatcher is down, a
  sleeping task is woken only by its next deadline or timeout.
- Bad, because the sleeping flag stays set until the next claim, so several sends during one
  sleep can add several wakes; each is only a hint, and the claim reads everything once.
- Bad, because a Workflow that is terminated, not cancelled, never runs `complete_task`: its task
  stays `running`, new sends to it are still accepted, messages to it stay `pending`, and its
  questions stay open until their deadlines.
- Follow-up: Phase 3's multi-agent orchestration builds on this inbox and on `waiting` tasks;
  revisit this ADR if wake latency or dispatcher load matters there.

### Confirmation

The Phase 2 messaging acceptance suites check the decision: `tests/integration/test_two_agents.py`
asserts that a sleeping recipient is woken by an `inbox` Signal and answers;
`tests/integration/test_messages.py` (`test_the_claim_inbox_activity`) that a claim returns IDs,
never bodies (R28); `tests/integration/test_messaging_failures.py` that a send repeated after a
killed worker is stored once; `tests/integration/test_dispatcher.py` that a wake sent while its
row is being signalled is kept and that a stopped dispatcher's rows are delivered later;
`tests/integration/test_messaging_history.py` the history bounds; and the Workflow tests in Temporal's time-skipping server (`tests/test_task_workflow_waiting.py`) the
claim-before-sleep loop. Implementation reviews of later messaging changes check that no message
body reaches a Workflow history and that no component other than the dispatcher sends `inbox`
Signals.

## Links

- [Phase 2 messaging plan](../plans/2026-11-18-phase-2-events-and-comms/plan.md): D6, D7, D11, D17;
  R13-R15, R28, R33. Mechanics: [notes.md#d6](../plans/2026-11-18-phase-2-events-and-comms/notes.md#d6--messages-wake-rows-and-the-comms-role).
- [As-built overview, Phase 2 messaging](../architecture/overview.md#phase-2-messaging-the-inbox-the-comms-mcp-server-and-waiting-tasks).
- Design §4.4 (`docs/roadmap/design-decisions.md`): the durable inbox and the scoped tool server.
- [ADR-0007](0007-fence-harness-attempts-in-one-transaction.md): message writes take the fence.
- [ADR-0009](0009-use-a-postgresql-event-table-for-agent-events.md): events use the same database and notification pattern.

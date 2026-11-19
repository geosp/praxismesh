# Architecture decision records

One record per consequential architecture decision, written when the decision is made or superseded (plan §4.17). Trivial implementation details do not get ADRs.

- **Name:** `NNNN-<decision>.md`, numbered in order (`0001-...`).
- **Template:** [adr.md](../templates/adr.md) (MADR minimal plus Confirmation and Links).
- **Status:** `proposed`, `accepted` or `superseded`. A new ADR names the old one in `supersedes`; existing ADR files are not rewritten.
- **How:** the `docs-design` skill drafts ADRs on a draft pull request.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-keep-default-openspec-schema.md) | Keep OpenSpec's default `spec-driven` schema; review gates live in the review skills and CI | proposed |
| [0002](0002-paradedb-as-postgresql-server.md) | Use ParadeDB as the PostgreSQL server, shared by the application and Temporal in Compose | accepted |
| [0003](0003-early-compose-task-ui.md) | Deliver a Compose task UI in Phase 4A; keep Kubernetes administration in Phase 8 | accepted |
| [0004](0004-use-implementation-plans-for-development.md) | Use implementation plans in docs/plans for development | proposed |
| [0005](0005-adopt-dsh-as-primary-agent-harness.md) | Adopt DeepSeek Harness as the primary agent harness inside Temporal Activities | accepted |
| [0006](0006-per-attempt-isolation-boundary-for-dsh.md) | Isolate each DSH attempt by cgroup, UID and mount namespace in a paired container (amends 0005 condition 3) | accepted |
| [0007](0007-fence-harness-attempts-in-one-transaction.md) | Fence every harness attempt's writes in one locked transaction per task | accepted |
| [0008](0008-record-unobserved-model-usage-as-unknown.md) | Count ledgered model usage over every attempt, and record unobserved usage as unknown and charged, never as zero | accepted |
| [0009](0009-use-a-postgresql-event-table-for-agent-events.md) | Carry agent progress events in a PostgreSQL event table, behind an event-transport interface | accepted |
| [0010](0010-wake-agents-through-a-durable-inbox.md) | Keep agent messages in a durable PostgreSQL inbox, and use Temporal Signals only to wake the recipient | accepted |
| [0011](0011-scope-agent-messaging-to-the-request.md) | Confine agent messaging to the sender's request, through a separate tool server that takes the sender from the worker | accepted |

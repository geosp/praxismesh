---
id: ADR-0011
title: Scope agent messaging to the request, take the sender's identity from the worker, and run the tool server as a least-privilege role
status: proposed
date: 2026-11-19
issue: "#79"
related:
  - docs/plans/2026-11-18-phase-2-events-and-comms/plan.md
  - docs/plans/2026-11-18-phase-2-events-and-comms/notes.md
  - docs/roadmap/design-decisions.md
  - docs/adr/0007-fence-harness-attempts-in-one-transaction.md
  - docs/adr/0010-wake-agents-through-a-durable-inbox.md
supersedes: null
superseded_by: null
---

# ADR-0011: Scope agent messaging to the request, take the sender's identity from the worker, and run the tool server as a least-privilege role

## Context and problem statement

Phase 2 gives agents tools to message and ask other tasks (`comms_mcp`: `send_to_agent`,
`ask_agent`, `post_status`, `get_task_context`). Agents act on untrusted input (prompt content,
repository files, tool output; plan §9.5), so the tools must not let a model reach tasks it has no
business with, speak as another task, or write outside the message tables. The platform has one
tenant until the Phase 4 gateway adds tenant fields, and nothing yet names which tasks may talk to
which. The tool server runs as a stdio subprocess per attempt, started by the worker, on both
runners (`openai_agents` and DSH).

## Considered options

- Scope by request, identity from the worker, a least-privilege role: a task may message only
  tasks of its own `request_id`; the worker gives the tool server the sender's task, turn and
  attempt in its environment; the server connects as a role that may write only the message
  tables.
- Profile allow lists naming which profiles may message which (new registry fields).
- Allow any task to message any other and only audit it.
- The server connects as the application role, or each runner builds the tools in-process.

## Decision outcome

Chosen option: "Scope by request, identity from the worker, a least-privilege role", because the
request is the unit the owner chose for collaboration (plan D9), the worker is the only party that
knows which attempt is running, and a database role is enforced by PostgreSQL rather than by the
server's own code.

Rejected:
- Profile allow lists, because they need new registry fields and a policy to write before anyone
  knows which profiles should talk, and a request already groups the tasks that work together.
- Audit only, because it records an unwanted message after the fact and never rejects it.
- The application role, because it can write every table, so any flaw in the tool server, or a
  leaked URL, would reach all task, attempt and usage data.
- Tools built into each runner, because the two runners would carry two copies of the same
  tools and checks, which could drift apart.

As built (plan D9, D10, D13; R10, R11, R23, R25-R27):
- A send, question or reply to a task of another request, to an ended task, or that would close a
  wait cycle is refused; the refusal is stored as a `rejected` row with its reason and returned to
  the model as a tool error.
- `comms_mcp` reads `PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT`, set by the worker for
  each attempt. No tool argument names the sender, so a model cannot speak as another task. The
  attempt is ADR-0007's fence key: a superseded attempt's writes are refused.
- The server connects as `praxis_comms` (created by `infra/db/roles.sh`): `SELECT, INSERT, UPDATE`
  on `task_messages`, `SELECT, INSERT` on `message_wakes`, `SELECT` on `tasks`, `task_attempts` and
  `task_inbox`, and no other table grant of its own. Templates grant the server through
  `registry/mcp/comms.yaml`, like any MCP server.

### Consequences

- Good, because a prompt-injected agent can reach only the tasks of its own request, cannot
  forge a sender, and cannot write any other table, whatever the server's code does.
- Good, because both runners get the same tools and checks from one server.
- Bad, because the scope is coarse: every task of a request can message every other. Finer rules
  (per profile or per role in a DAG) need a new decision.
- Bad, because operators must provision the role and its password (`PRAXIS_COMMS_DB_PASSWORD`,
  `make db-roles`) before the server works; without it the comms tools fail.
- Bad, because on `openai_agents` the `sh` tool runs in the worker container and can read the
  comms database URL from its environment, as it can the sample server's; DSH runs commands in its
  isolated container. The role's grants bound what that URL allows.
- Follow-up: the Phase 4 gateway adds tenants; scoping must then include the tenant, through a new
  ADR that supersedes this one or extends it.

### Confirmation

`tests/integration/test_messages.py` (request scope, refusals stored, ended tasks, cycles, the
fence), `tests/integration/test_comms_mcp.py` (identity from the environment: an argument naming
another sender is ignored; a cross-request send refused through the MCP client),
`tests/integration/test_comms_role.py` (the role's grants) and
`tests/integration/test_messaging_failures.py` (a cross-request send refused on the stack). An
implementation review of any new comms tool checks that it takes identity only from the
environment and writes only through `MessageRepository` as `praxis_comms`.

## Links

- [Phase 2 messaging plan](../plans/2026-11-18-phase-2-events-and-comms/plan.md): D9, D10, D13;
  R10, R11, R23, R25-R27. Role and grants: [notes.md#d6](../plans/2026-11-18-phase-2-events-and-comms/notes.md#d6--messages-wake-rows-and-the-comms-role).
- [As-built overview, Phase 2 messaging](../architecture/overview.md#phase-2-messaging-the-inbox-the-comms-mcp-server-and-waiting-tasks).
- Design §4.4 (`docs/roadmap/design-decisions.md`): `comms_mcp` on a scoped service or client.
- [ADR-0007](0007-fence-harness-attempts-in-one-transaction.md): the fence the attempt identity keys.
- [ADR-0010](0010-wake-agents-through-a-durable-inbox.md): the inbox these tools write to.

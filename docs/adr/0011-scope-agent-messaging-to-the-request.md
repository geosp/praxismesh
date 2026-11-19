---
id: ADR-0011
title: Confine agent messaging to the sender's request, through a separate tool server that takes the sender from the worker
status: proposed
date: 2026-11-19
issue: "#79"
related:
  - docs/plans/2026-11-18-phase-2-events-and-comms/plan.md
  - docs/plans/2026-11-18-phase-2-events-and-comms/notes.md
  - docs/roadmap/design-decisions.md
  - docs/security/threat-model.md
  - docs/adr/0007-fence-harness-attempts-in-one-transaction.md
  - docs/adr/0010-wake-agents-through-a-durable-inbox.md
supersedes: null
superseded_by: null
---

# ADR-0011: Confine agent messaging to the sender's request, through a separate tool server that takes the sender from the worker

## Context and problem statement

Phase 2 gives agents tools to message and ask other tasks (`send_to_agent`, `ask_agent`,
`post_status`, `get_task_context`). Agents act on untrusted input (prompt content, repository
files, tool output; plan §9.5), so the question is how these tools are confined: which tasks an
agent may reach, how its messages are attributed to it, and what the tools may write. The platform
has one tenant until the Phase 4 gateway adds tenant fields, and nothing yet names which tasks may
talk to which. Design §4.4 asks for `comms_mcp` to work "through a scoped service/client".

## Considered options

- A separate MCP server, `comms_mcp`, started by the worker for each attempt on both runners: it
  lets a task reach only tasks of its own `request_id`, takes the sender's task, turn and attempt
  from the environment the worker gives it, and connects as its own role, `praxis_comms`, which
  may write only the message tables.
- The same server and role, but scoped by per-profile allow lists naming which profiles may
  message which.
- The same server and role with no scope check: every message is accepted and audited.
- The tools built into each runner, writing through the worker's own (application-role)
  database connection, with the same request scope.
- The tools built into each runner, each with its own `praxis_comms` connection, with the same
  request scope and identity from the attempt.

## Decision outcome

Chosen option: "A separate MCP server, `comms_mcp`, ...", because the request is the unit the
owner chose for collaboration (plan D9), the worker is the only party that knows which attempt is
running, the tools' own database connection uses a role that PostgreSQL limits to the message
tables, and as an MCP server it is granted per template through the registry and reached by both
runners without changes to either.

Rejected:
- Per-profile allow lists, because they need new registry fields and a policy before anyone knows
  which profiles should talk, while a request already groups the tasks that work together.
- Audit only, because it records an unwanted message after the fact and never rejects it.
- Tools built into each runner on the application role, because that role can write every table,
  so a flaw in a messaging path could reach task, attempt and usage data.
- Tools built into each runner on their own `praxis_comms` connection, which would confine their
  writes just as well (a role belongs to a connection, not a process), because they would be wired
  into both runners and granted outside the registry, while an MCP server is granted per template
  like any other and needs no runner change. Plan D13 gave "two copies" as the reason; the tool
  bodies could be shared (`harness_activity/tools.py` already shares bodies between runners), so
  that reason does not hold, and this ADR replaces it.

The separate process is not a credential boundary: `comms_mcp` runs as a child of the worker, as
the same user in the same container, so code running in it could read the worker's environment.

As built (plan D9, D10, D13; R10, R11, R23, R25-R27):
- Refused and stored as a `rejected` row with its reason, and returned to the model as a tool
  error: a message to a task of another request or to an ended task, a message from an ended
  task, a body over 16,384 characters, a reply to a question that is closed or not addressed to
  the replier, a reply not sent to the asker, and a question that would close a wait cycle.
- `comms_mcp` reads `PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT`, which the worker sets for
  each attempt after the registry entry's literal `env`, so that cannot override them; an entry
  that named them in `secret_env` could, and the loader does not forbid it. No tool argument names
  the sender. The turn and attempt are ADR-0007's fence key: a superseded
  attempt's writes are refused.
- The server connects as `praxis_comms` (created by `infra/db/roles.sh`): `SELECT, INSERT, UPDATE`
  on `task_messages`, `SELECT, INSERT` on `message_wakes`, `SELECT` on `tasks`, `task_attempts`
  and `task_inbox`, and no other table grant of its own. Templates grant the server through
  `registry/mcp/comms.yaml`.

### Consequences

- Good, because the tools' writes are confined by PostgreSQL to the message tables, whatever the
  server's code does.
- Good, because both runners get the same tools and checks from one server.
- Bad, because request scope, sender identity and the fence are enforced by the server's code
  (`MessageRepository`), not by the database: the role may insert or update any message row. They
  hold only while the role's URL stays out of an agent's reach.
- Bad, because on `openai_agents` it does not stay out of reach: `run_command` (with `sh` or
  `python3` allowed by the `local-default` template) runs in the worker container and can read the
  worker's environment, which holds the comms URL and also the
  application role's credentials (threat model R1). There an agent with `sh` can bypass scope,
  identity and the fence, and more. The guarantees above hold on DSH, which runs commands in its
  isolated container, until the Phase 5 sandbox closes R1.
- Bad, because the scope is coarse: every task of a request can message every other. Finer rules
  (per profile, or per role in a DAG) need a new decision.
- Bad, because operators must provision the role and its password (`PRAXIS_COMMS_DB_PASSWORD`,
  `make db-roles`) before the server works; without it the comms tools fail.
- Follow-up: the Phase 4 gateway adds tenants, and scoping must then include the tenant, through a
  new ADR that supersedes or extends this one. Row-level security on the message tables would
  move scope and identity into the database. The threat model needs an entry for the comms server's
  database boundary and the `praxis_comms` role, and the registry loader could refuse
  `PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT` in `secret_env`.

### Confirmation

`tests/integration/test_messages.py` checks the request scope, stored refusals, ended tasks,
cycles and the fence; `tests/integration/test_comms_mcp.py` that an argument naming another
sender is ignored and a cross-request send is refused through the MCP client;
`tests/test_runner_conformance.py` that the harness config gives every MCP server the attempt's
task, turn and attempt, and that both runners start an MCP server with the task ID in its
environment; `tests/integration/test_comms_role.py` that the role
writes messages and reads tasks but cannot write `tasks` or read `checkpoints` (it does not list
the role's full grant set); and `tests/integration/test_messaging_failures.py` a cross-request send
refused on the stack. An implementation review of any new comms tool checks that it takes identity
only from the environment and writes only through `MessageRepository` as `praxis_comms`.

## Links

- [Phase 2 messaging plan](../plans/2026-11-18-phase-2-events-and-comms/plan.md): D9, D10, D13;
  R10, R11, R23, R25-R27. Role and grants: [notes.md#d6](../plans/2026-11-18-phase-2-events-and-comms/notes.md#d6--messages-wake-rows-and-the-comms-role).
- [As-built overview, Phase 2 messaging](../architecture/overview.md#phase-2-messaging-the-inbox-the-comms-mcp-server-and-waiting-tasks).
- [Threat model](../security/threat-model.md), accepted risk R1: no sandbox for commands until Phase 5.
- Design §4.4 (`docs/roadmap/design-decisions.md`): `comms_mcp` on a scoped service or client.
- [ADR-0007](0007-fence-harness-attempts-in-one-transaction.md): the fence the turn and attempt key.
- [ADR-0010](0010-wake-agents-through-a-durable-inbox.md): the inbox these tools write to.

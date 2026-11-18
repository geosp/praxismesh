# Event-transport spike

An isolated experiment for [issue #76](https://github.com/geosp/praxismesh/issues/76), following
the approved plan
[docs/plans/2026-11-17-event-transport-spike](../../docs/plans/2026-11-17-event-transport-spike/plan.md).
It implemented one `EventTransport` interface for Temporal Workflow Streams, a PostgreSQL event
table and NATS JetStream, and ran one shared suite and two workloads against each. The owner
chose the table ([ADR-0009](../../docs/adr/0009-use-a-postgresql-event-table-for-agent-events.md),
[report](../../docs/spikes/event-transport.md)); only it and the in-memory reference remain. The
other implementations are in git history at `1bfac67`. Production
code, migrations, the registry and Compose services are unchanged.

## Layout

| Path | What |
| --- | --- |
| `event_transport/` | the interface, the `AgentEvent` copy and the implementations |
| `tests/` | the shared suite and unit tests |
| `fixtures/` | the recorded DSH turn (JSON lines) |
| `results/` | committed results files |
| `stack.env` | env file for the disposable Compose project `pmspike76` |

## Setup

```bash
cd spikes/event-transport && uv sync --locked      # the spike's own environment
cd ../.. && make up ENV_FILE=spikes/event-transport/stack.env   # disposable stack
```

`stack.env` is `infra/.env.example` with the project name `pmspike76` and its own ports
(Temporal 37233, UI 38080, PostgreSQL 35432, S3 38333), so it runs beside the main stack.
Remove the disposable stack and its data with `make reset ENV_FILE=spikes/event-transport/stack.env`.

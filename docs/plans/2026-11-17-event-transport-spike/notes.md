# Notes · Choose Phase 2's event transport

## Verified

Checked 2026-11-17 against live docs and package indexes.

- **Temporal Workflow Streams** (`temporalio.contrib.workflow_streams`):
  - Present in the pinned `temporalio` 1.36.0 (latest 1.36.1, 2026-11-14). Status: "Public
    Preview" (docs) / "experimental and may change" (README, API reference).
  - Publishes travel as Signals, subscriptions as long-poll Updates, retained items through
    Queries. Activities publish with `WorkflowStreamClient.from_within_activity()`.
  - Installed defaults: `batch_interval` 2 s, `max_batch_size` None, `max_retry_duration` 600 s.
  - "Cost scales with durable batches rather than tokens"; events per batch is not documented.
  - "A retried attempt is a fresh publisher, so its output appears in the stream alongside the
    output from the previous attempt."
  - A truncated offset makes Queries "start at the retained base"; whether the caller is told is
    not documented.
  - `WorkflowStream.continue_as_new(...)` carries the log, `base_offset` and the dedup table.
  - One stream per Workflow, created in `@workflow.init`; ~100 ms round trip; ~1 MB poll cap.
- **NATS JetStream**: nats-server v2.15.3 (2026-11-11); `nats-py` 2.17.0 (2026-11-17,
  Python ≥ 3.7).
  - Limits retention (max age, bytes, messages, per subject); discard old or new.
  - Stream sequences are shared by every subject in a stream.
  - `by_start_sequence` deliver policy; ordered consumers recreate themselves at the next
    expected sequence after a gap in delivery.
  - `Nats-Msg-Id` deduplication within a duplicate window (default 2 min).
  - File storage survives restart; a single-replica stream is lost with its server.
  - Starting before the first retained sequence: behaviour not documented.
  - `nats-py` has no first-class async publish or fast batch publish.
- **This repository**:
  - DSH emits one `token` event per model response (`harness_activity/dsh/gateway.py`), not per
    streamed token; a turn is a few dozen events.
  - No Workflow uses Continue-As-New yet.
  - `AttemptEvents` (`harness_activity/events.py`) numbers events per attempt (`seq`) and stamps
    `attempt_id = task:turn:attempt`. `AgentEvent` is frozen with extra fields forbidden.
  - The production worker builds `DshRunner` with no event sink (`workers/main.py`), so it uses
    `NoOpSink`. `tests/support/dsh_container.py` builds a runner with a given sink.
  - The root project is not installable (`package = false`); `spikes/` is outside root ruff,
    mypy and pytest.
  - `infra/temporal/dynamicconfig.yaml` is empty, so Temporal's default limits apply.

Sources: docs.temporal.io/develop/python/workflows/workflow-streams; the sdk-python
`workflow_streams` README; python.temporal.io API reference; docs.nats.io (JetStream concepts,
streams, consumers, retention and consumer policies, ordered consumer, advanced publishing,
security, Kubernetes); github.com/nats-io/nats.py; PyPI JSON for both packages; GitHub releases
for nats-server.

## D1

```text
class EventTransport(Protocol):
    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None
    def read(self, workflow_id: str, after: int) -> AsyncIterator[tuple[int, AgentEvent] | Expired]
    async def latest(self, workflow_id: str) -> int | None   # highest offset, or None
    # test hooks
    async def expire_below(self, workflow_id: str, offset: int) -> None
    async def roll_over(self, workflow_id: str) -> None

Expired(retained_base: int)
```

- `read(after=N)` yields offsets > N. It yields `Expired` first only when some offset > N is
  below the retained base (R2): `after < retained_base - 1`. `after=0` reads from the start.
- Offsets start at 1, are gap-free per workflow, and survive roll-over (R4).
- `batch_id` is stable for a re-send of the same batch (R3); a new attempt uses new batch IDs.
- `expire_below` uses each option's own retention mechanism: Streams `truncate()`, a JetStream
  purge up to a sequence, a table `DELETE`.
- `roll_over` is Continue-As-New through `WorkflowStream.continue_as_new` for Streams, and a no-op
  for the others (R4 shows N/A for them).
- The spike copies `common/schemas/events.py`'s `AgentEvent`; the copy is checked against the root
  schema's field list in task 1.2.

## D3

- **Recorded turn**: `t01-order-total` driven once through the DSH test support
  (`tests/support/dsh_container.py`, a runner with a recording sink) against the real model, from
  a capture script run in the root environment; the events are written as JSON lines to
  `spikes/event-transport/fixtures/`. Payloads hold SKUs, tool names and token counts only.
- **Synthetic load**: per agent, ~50 `token` events/s with a ~40-byte text delta each, plus a
  `tool_call`/`tool_result` pair every 10 s, for 5 min (~15k events per agent); 3 tailers per
  agent from offset 0; one tailer per agent killed and resumed every 60 s (R1 under load).

## D5

| Option | Mechanisms and parameters, fixed before measuring |
| --- | --- |
| All | publish batches every 200 ms or 64 events, whichever comes first; re-send horizon 600 s; the suite's R3 case uses a horizon of 60 s, the same for all |
| Workflow Streams | `WorkflowStreamClient.from_within_activity()` in a publishing Activity; `batch_interval` 200 ms; a batch-ID set in Workflow state, entries older than the horizon dropped, carried across Continue-As-New; load runs once with roll-over off (growth rate) and once with roll-over at the derived interval (R5, R4 under load) |
| PostgreSQL table | `asyncpg` 0.32.0; one table keyed `(workflow_id, offset)`; a per-workflow counter row; a `(workflow_id, batch_id)` row inserted in the same transaction as the events; `NOTIFY` per batch; readers fall back to a 1 s poll |
| NATS JetStream | a stream per workflow (`events-<workflow_id>`), one message per event, `Nats-Msg-Id` `<batch_id>:<i>`, duplicate window 600 s (60 s in the R3 case), file storage, 1 replica; the cost of one stream per workflow goes into the assessment |

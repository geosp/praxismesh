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
    `attempt_id = task:turn:attempt`.

Sources: docs.temporal.io/develop/python/workflows/workflow-streams; the sdk-python
`workflow_streams` README; python.temporal.io API reference; docs.nats.io (JetStream concepts,
streams, consumers, retention and consumer policies, ordered consumer, advanced publishing,
security, Kubernetes); github.com/nats-io/nats.py; PyPI JSON for both packages; GitHub releases
for nats-server.

## D1

```text
class EventTransport(Protocol):
    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None
    def read(self, workflow_id: str, from_offset: int) -> AsyncIterator[AgentEvent | Expired]
    async def latest(self, workflow_id: str) -> int | None

Expired(retained_base: int)   # yielded once, first, when from_offset < retained_base
```

- Offsets are per workflow, assigned by the transport, gap-free across Continue-As-New (R4).
- `batch_id` is stable for a re-send of the same batch (R3); a new attempt uses new batch IDs.
- Each implementation also exposes `expire_below(workflow_id, offset)` for tests (R2), using the
  option's own retention mechanism where it has one (Streams `truncate()`, JetStream purge by
  sequence, a table `DELETE`).

## D3

- **Recorded turn**: one benchmark task (`t01-order-total`) on the `dsh` profile with a sink
  that writes each `AgentEvent` to JSON lines; committed under
  `spikes/event-transport/fixtures/`. Payloads hold SKUs, tool names and token counts only.
- **Synthetic load**: per agent, ~50 `token` events/s with a ~40-byte text delta each, plus a
  `tool_call`/`tool_result` pair every 10 s, for 5 min (~15k events per agent); 3 tailers per
  agent from offset 0; one tailer per agent killed and resumed every 60 s (R1 under load).

## D5

Parameters set before any measurement, the same across options where they apply:

| Option | Parameters |
| --- | --- |
| All | publish batches every 200 ms or 64 events, whichever comes first |
| Workflow Streams | `batch_interval` 200 ms; no Continue-As-New during the load runs, so R5 measures one run's growth; Continue-As-New only in the R4 test, through `WorkflowStream.continue_as_new` |
| PostgreSQL table | one table, `(workflow_id, offset)` primary key, a per-workflow counter row; `NOTIFY` per batch; readers fall back to a 1 s poll |
| NATS JetStream | one stream `events`, subject `events.<workflow_id>`, file storage, 1 replica, max age 7 days, duplicate window 2 min |

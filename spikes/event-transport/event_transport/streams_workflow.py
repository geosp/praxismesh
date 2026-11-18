"""The Workflow that hosts one workflow's Streams log (plan D5, notes.md#d5; task 2.2).

- `publish_batch` (Update): one per batch. It checks the batch ID against the set
  of IDs seen within the re-send horizon (R3), then appends each event through the
  stream's Workflow-side topic.
- `expire_below` (Update, test hook): truncates the stream (R2).
- `roll_over` (Signal, test hook) and the load policy (Temporal's suggestion or
  every 2,000 batches) continue as new after keeping the last 500 events; the
  batch-ID set and the retained base travel with the stream state (R4).
- `retained_base` (Query): the lowest retained offset, in spike offsets (stream
  offset + 1), which the stream itself does not expose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.contrib.workflow_streams import WorkflowStream, WorkflowStreamState

TOPIC = "events"
ROLL_EVERY_BATCHES = 2000
KEEP_AT_ROLL = 500


@dataclass
class StreamInput:
    horizon_s: float = 600.0
    stream_state: WorkflowStreamState | None = None
    batches: dict[str, float] = field(default_factory=dict)  # batch_id -> seen, epoch seconds
    base: int = 1  # spike offset of the retained base
    batches_this_run: int = 0


@dataclass
class PublishBatch:
    batch_id: str
    events: list[str]  # AgentEvent JSON


@workflow.defn(name="SpikeEventStream")
class EventStreamWorkflow:
    @workflow.init
    def __init__(self, inp: StreamInput) -> None:
        self.stream = WorkflowStream(inp.stream_state)
        self.topic = self.stream.topic(TOPIC)
        self.horizon_s = inp.horizon_s
        self.batches = dict(inp.batches)
        self.base = inp.base
        self.batches_this_run = 0
        self.end = (
            (inp.stream_state.base_offset + len(inp.stream_state.log)) if inp.stream_state else 0
        )
        self.roll_requested = False

    @workflow.run
    async def run(self, inp: StreamInput) -> None:
        await workflow.wait_condition(
            lambda: (
                self.roll_requested
                or self.batches_this_run >= ROLL_EVERY_BATCHES
                or workflow.info().is_continue_as_new_suggested()
            )
        )
        keep_from = max(self.base - 1, self.end - KEEP_AT_ROLL)  # stream offsets
        if keep_from > self.base - 1:
            self.stream.truncate(keep_from)
            self.base = keep_from + 1
        await self.stream.continue_as_new(
            lambda state: [
                StreamInput(
                    horizon_s=self.horizon_s,
                    stream_state=state,
                    batches=self.batches,
                    base=self.base,
                )
            ]
        )

    @workflow.update
    def publish_batch(self, batch: PublishBatch) -> int:
        now = workflow.now().timestamp()
        self.batches = {b: t for b, t in self.batches.items() if now - t < self.horizon_s}
        if batch.batch_id not in self.batches:
            self.batches[batch.batch_id] = now
            for event in batch.events:
                self.topic.publish(event)
            self.end += len(batch.events)
            self.batches_this_run += 1
        return self.end  # the latest spike offset

    @workflow.update
    def expire_below(self, offset: int) -> None:
        if offset - 1 > self.base - 1:
            self.stream.truncate(min(offset - 1, self.end))
            self.base = min(offset, self.end + 1)

    @workflow.signal
    def roll_over(self) -> None:
        self.roll_requested = True

    @workflow.query
    def retained_base(self) -> int:
        return self.base

    @workflow.query
    def latest(self) -> int:
        return self.end


ROLL_TIMEOUT = timedelta(seconds=30)

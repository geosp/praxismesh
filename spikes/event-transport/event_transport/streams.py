"""Temporal Workflow Streams transport (plan D5, notes.md#d5; task 2.2).

Each spike workflow ID is one `SpikeEventStream` Workflow (see streams_workflow.py).
Publishing sends one `publish_batch` Update per batch. Reading does not use
`WorkflowStreamClient.subscribe()`, which hides truncation by restarting at 0
(notes.md#verified); it calls the stream's poll Query (catch-up) and poll Update
(follow) by Workflow ID, so it follows roll-over, maps `TruncatedOffset` to
`Expired` through the `retained_base` Query, and adds 1 to stream offsets.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from collections.abc import AsyncIterator

from temporalio.client import (
    Client,
    WorkflowHandle,
    WorkflowUpdateFailedError,
    WorkflowUpdateRPCTimeoutOrCancelledError,
    WorkflowUpdateStage,
)
from temporalio.common import WorkflowIDConflictPolicy
from temporalio.contrib.workflow_streams import PollInput, PollResult
from temporalio.contrib.workflow_streams._types import _decode_payload
from temporalio.service import RPCError
from temporalio.worker import Worker

from event_transport.models import AgentEvent
from event_transport.streams_workflow import (
    TOPIC,
    EventStreamWorkflow,
    PublishBatch,
    StreamInput,
)
from event_transport.transport import Item, expiry_for

ADDRESS = os.environ.get("SPIKE_TEMPORAL", "127.0.0.1:37233")
COOLDOWN_S = 0.1  # readers poll no faster than every 100 ms when idle (notes.md#d5)
_RETRYABLE = {"StreamDraining"}


class StreamsTransport:
    def __init__(self, client: Client, worker: Worker, queue: str, horizon_s: float) -> None:
        self.client, self.worker, self.queue, self.horizon_s = client, worker, queue, horizon_s
        self._running = asyncio.create_task(worker.run())
        self._started: set[str] = set()

    @classmethod
    async def connect(cls, horizon_s: float, address: str = ADDRESS) -> StreamsTransport:
        client = await Client.connect(address)
        queue = f"spike76-streams-{uuid.uuid4().hex[:8]}"
        worker = Worker(client, task_queue=queue, workflows=[EventStreamWorkflow])
        return cls(client, worker, queue, horizon_s)

    def _wid(self, workflow_id: str) -> str:
        return f"spike76-stream-{workflow_id}"

    async def _handle(self, workflow_id: str) -> WorkflowHandle[EventStreamWorkflow, None]:
        if workflow_id not in self._started:
            await self.client.start_workflow(
                EventStreamWorkflow.run,
                StreamInput(horizon_s=self.horizon_s),
                id=self._wid(workflow_id),
                task_queue=self.queue,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            )
            self._started.add(workflow_id)
        return self.client.get_workflow_handle_for(EventStreamWorkflow.run, self._wid(workflow_id))

    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        handle = await self._handle(workflow_id)
        batch = PublishBatch(batch_id, [e.model_dump_json() for e in events])
        await self._retry(lambda: handle.execute_update(EventStreamWorkflow.publish_batch, batch))

    async def _retry(self, call):  # type: ignore[no-untyped-def]
        """Retry a call that lands while the Workflow is rolling over."""
        for _ in range(200):
            try:
                return await call()
            except WorkflowUpdateFailedError as err:
                if getattr(err.cause, "type", None) not in _RETRYABLE:
                    raise
            except (WorkflowUpdateRPCTimeoutOrCancelledError, RPCError):
                pass
            await asyncio.sleep(COOLDOWN_S)
        raise TimeoutError("the stream Workflow did not accept the call")

    def _decode(self, result: PollResult) -> list[tuple[int, AgentEvent]]:
        conv = self.client.data_converter.payload_converter
        return [
            (
                item.offset + 1,
                AgentEvent.model_validate_json(conv.from_payload(_decode_payload(item.data), str)),
            )
            for item in result.items
        ]

    async def read(
        self, workflow_id: str, after: int, *, follow: bool = False
    ) -> AsyncIterator[Item]:
        handle = await self._handle(workflow_id)
        latest = await self._retry(lambda: handle.query(EventStreamWorkflow.latest))
        if latest:
            base = await self._retry(lambda: handle.query(EventStreamWorkflow.retained_base))
            expired = expiry_for(after, base)
            if expired is not None:
                yield expired
                after = expired.retained_base - 1
        offset = after  # stream offset of the next spike offset (after + 1)
        while True:
            poll = PollInput(topics=[TOPIC], from_offset=offset)
            if not follow:
                result = await self._retry(
                    lambda p=poll: handle.query(
                        "__temporal_workflow_stream_poll", p, result_type=PollResult
                    )
                )
            else:
                result = await self._retry(lambda p=poll: self._poll_update(handle, p))
            for spike_offset, event in self._decode(result):
                yield spike_offset, event
            offset = result.next_offset
            if result.more_ready:
                continue
            if not follow:
                return
            if not result.items:
                await asyncio.sleep(COOLDOWN_S)

    async def _poll_update(self, handle: WorkflowHandle, poll: PollInput) -> PollResult:  # type: ignore[type-arg]
        update = await handle.start_update(
            "__temporal_workflow_stream_poll",
            poll,
            wait_for_stage=WorkflowUpdateStage.ACCEPTED,
            result_type=PollResult,
        )
        return await update.result()

    async def latest(self, workflow_id: str) -> int | None:
        handle = await self._handle(workflow_id)
        end = await self._retry(lambda: handle.query(EventStreamWorkflow.latest))
        return end or None

    async def expire_below(self, workflow_id: str, offset: int) -> None:
        handle = await self._handle(workflow_id)
        await self._retry(lambda: handle.execute_update(EventStreamWorkflow.expire_below, offset))

    async def roll_over(self, workflow_id: str) -> None:
        handle = await self._handle(workflow_id)
        await handle.signal(EventStreamWorkflow.roll_over)

    async def close(self) -> None:
        for wid in self._started:
            with contextlib.suppress(RPCError):
                await self.client.get_workflow_handle(self._wid(wid)).terminate("spike done")
        await self.worker.shutdown()
        await self._running

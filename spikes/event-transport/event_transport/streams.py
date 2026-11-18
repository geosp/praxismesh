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
import os
from collections.abc import AsyncIterator
from datetime import timedelta

from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
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
from event_transport.transport import Item, expiry_for, guarded

ADDRESS = os.environ.get("SPIKE_TEMPORAL", "127.0.0.1:37233")
QUEUE = "spike76-streams"  # fixed, so any instance's worker serves any existing run (F36)
COOLDOWN_S = 0.1  # readers poll no faster than every 100 ms when idle (notes.md#d5)
RUN_TIMEOUT = timedelta(hours=2)  # a run left by a killed suite or probe ends on its own
# Rejections while the Workflow rolls over: retried, and they land on the next run.
_RETRYABLE = {"StreamDraining", "AcceptedUpdateCompletedWorkflow"}
_TRUNCATED = "TruncatedOffset"


def _cause_type(err: WorkflowUpdateFailedError) -> str | None:
    cause = err.cause
    while cause is not None:
        kind = getattr(cause, "type", None)
        if kind:
            return str(kind)
        cause = cause.__cause__
    return None


class StreamsTransport:
    def __init__(self, client: Client, worker: Worker, horizon_s: float) -> None:
        self.client, self.worker, self.horizon_s = client, worker, horizon_s
        self._running = asyncio.create_task(worker.run())
        self._started: set[str] = set()

    @classmethod
    async def connect(cls, horizon_s: float, address: str = ADDRESS) -> StreamsTransport:
        client = await Client.connect(address)
        worker = Worker(client, task_queue=QUEUE, workflows=[EventStreamWorkflow])
        return cls(client, worker, horizon_s)

    def _wid(self, workflow_id: str) -> str:
        return f"spike76-stream-{workflow_id}"

    async def _handle(self, workflow_id: str) -> WorkflowHandle[EventStreamWorkflow, None]:
        if workflow_id not in self._started:
            await self.client.start_workflow(
                EventStreamWorkflow.run,
                StreamInput(horizon_s=self.horizon_s),
                id=self._wid(workflow_id),
                task_queue=QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                execution_timeout=RUN_TIMEOUT,
            )
            self._started.add(workflow_id)
        return self.client.get_workflow_handle_for(EventStreamWorkflow.run, self._wid(workflow_id))

    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        """One `publish_batch` Update per batch. In production the long-running
        Activity that produces the events makes this call from its own process
        (notes.md#d5); the suite makes the same call from the test process."""
        handle = await self._handle(workflow_id)
        batch = PublishBatch(batch_id, [e.model_dump_json() for e in events])
        await self._retry(lambda: handle.execute_update(EventStreamWorkflow.publish_batch, batch))

    async def _retry(self, call):  # type: ignore[no-untyped-def]
        """Retry a call that lands while the Workflow is rolling over."""
        for _ in range(200):
            try:
                return await call()
            except WorkflowUpdateFailedError as err:
                if _cause_type(err) not in _RETRYABLE:
                    raise
            except WorkflowUpdateRPCTimeoutOrCancelledError:
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

    def read(self, workflow_id: str, after: int, *, follow: bool = False) -> AsyncIterator[Item]:
        return guarded(after, self._read(workflow_id, after, follow))

    async def _read(self, workflow_id: str, after: int, follow: bool) -> AsyncIterator[Item]:
        """Every read goes through the stream's poll Update (D5, F33). A non-following
        read stops at the latest offset it saw when it started."""
        handle = await self._handle(workflow_id)
        end = await self._query(handle, EventStreamWorkflow.latest)
        if end:
            expired = expiry_for(
                after, await self._query(handle, EventStreamWorkflow.retained_base)
            )
            if expired is not None:
                yield expired
                after = expired.retained_base - 1
        offset = after  # stream offset of the next spike offset (after + 1)
        while follow or offset < end:
            try:
                result = await self._retry(
                    lambda o=offset: self._poll_update(handle, PollInput([TOPIC], o))
                )
            except WorkflowUpdateFailedError as err:
                if _cause_type(err) != _TRUNCATED:
                    raise
                # Truncated under the reader (F31): resume at the retained base;
                # guarded() reports the jump as Expired.
                offset = await self._query(handle, EventStreamWorkflow.retained_base) - 1
                continue
            for spike_offset, event in self._decode(result):
                yield spike_offset, event
            offset = result.next_offset
            if follow and not result.items and not result.more_ready:
                await asyncio.sleep(COOLDOWN_S)

    async def _query(self, handle: WorkflowHandle, query) -> int:  # type: ignore[no-untyped-def,type-arg]
        for _ in range(200):
            try:
                return int(await handle.query(query))
            except RPCError:  # between runs during a roll-over
                await asyncio.sleep(COOLDOWN_S)
        raise TimeoutError("the stream Workflow did not answer the query")

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
        end = await self._query(handle, EventStreamWorkflow.latest)
        return end or None

    async def expire_below(self, workflow_id: str, offset: int) -> None:
        handle = await self._handle(workflow_id)
        await self._retry(lambda: handle.execute_update(EventStreamWorkflow.expire_below, offset))

    async def roll_over(self, workflow_id: str) -> bool:
        """Signal a roll-over and return once a new run has started (F34)."""
        handle = await self._handle(workflow_id)
        before = (await handle.describe()).run_id
        await handle.signal(EventStreamWorkflow.roll_over)
        for _ in range(300):
            await asyncio.sleep(COOLDOWN_S)
            desc = await handle.describe()
            if desc.run_id != before and desc.status == WorkflowExecutionStatus.RUNNING:
                return True
        return False

    async def close(self) -> None:
        # Runs stay: other instances may still use them (F36); `make reset` on the
        # disposable stack removes them, and RUN_TIMEOUT ends any left behind.
        await self.worker.shutdown()
        await self._running

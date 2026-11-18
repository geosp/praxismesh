"""Event sinks for harness turns (DSH migration plan D8, R16; Phase 2 events plan D2).

Runners emit `AgentEvent`s through an `AttemptEvents`, which hands them to a sink:
`BatchingPublisher` publishes them to the event table; tests use the in-memory sink.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from datetime import UTC, datetime
from typing import Any, Protocol

from common.events import EventTransport, Writer
from common.persistence.fence import FenceRejected
from common.schemas.events import AgentEvent, EventType


class EventSink(Protocol):
    def emit(self, event: AgentEvent) -> None: ...


class NoOpSink:
    def emit(self, event: AgentEvent) -> None:
        return None


class MemorySink:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


class AttemptEvents:
    """Numbers one attempt's events in emission order and stamps its identity."""

    def __init__(self, sink: EventSink, workflow_id: str, task_id: str, turn: int, attempt: int):
        self.sink, self.workflow_id, self.task_id = sink, workflow_id, task_id
        self.attempt_id = f"{task_id}:{turn}:{attempt}"
        self.seq = 0
        self.lock = threading.Lock()

    def emit(self, type: EventType, **payload: Any) -> AgentEvent:
        with self.lock:
            event = AgentEvent(
                seq=self.seq,
                timestamp=datetime.now(UTC),
                workflow_id=self.workflow_id,
                task_id=self.task_id,
                attempt_id=self.attempt_id,
                type=type,
                payload=payload,
            )
            self.seq += 1
            self.sink.emit(event)  # inside the lock: delivery order equals seq (review F8)
        return event


class BatchingPublisher:
    """The event sink of one attempt: it publishes the attempt's events to the event
    table in batches (Phase 2 events plan D2, R7, R8).

    - A batch holds at most `max_batch` events and is cut when that many are
      buffered, `delay_s` after the oldest unpublished event, or at `close()`.
    - One publish runs at a time, in `seq` order. A cut batch is frozen: its ID
      (`<workflow>:<attempt_id>:<n>`) and events never change. A database error
      re-sends it unchanged after each backoff and then at each later trigger, so a
      commit whose reply was lost is deduplicated by its ID; new events wait for
      later batches.
    - A refused publish (`FenceRejected`) stops publishing; `close()` returns it.

    `emit` may be called from any thread; publishing runs on the event loop that
    created the publisher.
    """

    def __init__(
        self,
        transport: EventTransport,
        writer: Writer,
        workflow_id: str,
        attempt_id: str,
        *,
        max_batch: int = 64,
        delay_s: float = 0.2,
        backoff_s: tuple[float, ...] = (0.25, 0.5, 1.0),
    ) -> None:
        self.transport, self.writer, self.workflow_id = transport, writer, workflow_id
        self.attempt_id = attempt_id
        self.max_batch, self.delay_s, self.backoff_s = max_batch, delay_s, backoff_s
        self.loop = asyncio.get_running_loop()
        self.lock = threading.Lock()
        self.buffer: list[AgentEvent] = []
        self.oldest = 0.0  # monotonic time of the oldest buffered event
        self.pending: tuple[str, list[AgentEvent]] | None = None
        self.batches = 0
        self.refused: FenceRejected | None = None
        self.error: Exception | None = None
        self.closing = False
        self.wake = asyncio.Event()
        self.task = self.loop.create_task(self._run())

    def emit(self, event: AgentEvent) -> None:
        with self.lock:
            if self.refused is not None:
                return  # a superseded attempt stores nothing more
            if not self.buffer:
                self.oldest = time.monotonic()
            self.buffer.append(event)
        self.loop.call_soon_threadsafe(self.wake.set)

    @property
    def closed(self) -> bool:
        return self.task.done()

    async def close(self, timeout_s: float = 10.0) -> Exception | None:
        """Publish everything buffered and stop. Shielded from the caller's
        cancellation and bounded by `timeout_s`. Returns the refusal, the last
        database error (or a timeout), or None when every event was stored."""
        if self.task.done():
            return self.refused or self.error
        self.closing = True
        self.wake.set()
        try:
            await asyncio.shield(asyncio.wait_for(asyncio.shield(self.task), timeout_s))
        except TimeoutError as e:
            self.task.cancel()
            return self.refused or self.error or e
        return self.refused or self.error

    def _next_wait(self) -> float | None:
        if self.pending is not None:
            return self.delay_s  # a failed batch: retry at the next trigger
        with self.lock:
            if not self.buffer:
                return None
            return max(0.0, self.oldest + self.delay_s - time.monotonic())

    async def _run(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), self._next_wait())
            self.wake.clear()
            await self._drain()
            if self.refused is not None:
                return
            if self.closing and (self.error is not None or self._empty()):
                return

    def _empty(self) -> bool:
        with self.lock:
            return self.pending is None and not self.buffer

    def _cut(self) -> bool:
        with self.lock:
            due = (
                self.closing
                or len(self.buffer) >= self.max_batch
                or (bool(self.buffer) and time.monotonic() - self.oldest >= self.delay_s)
            )
            if not self.buffer or not due:
                return False
            events, self.buffer = self.buffer[: self.max_batch], self.buffer[self.max_batch :]
            self.oldest = time.monotonic() if self.buffer else 0.0
        self.pending = (f"{self.workflow_id}:{self.attempt_id}:{self.batches}", events)
        self.batches += 1
        return True

    async def _drain(self) -> None:
        while self.pending is not None or self._cut():
            assert self.pending is not None
            batch_id, events = self.pending
            for wait in (*self.backoff_s, None):
                try:
                    await self.transport.publish(self.workflow_id, self.writer, batch_id, events)
                except FenceRejected as e:
                    with self.lock:
                        self.refused, self.buffer = e, []
                    self.pending = None
                    return
                except Exception as e:  # database errors: re-send the same batch
                    self.error = e
                    if wait is None:
                        return  # keep the batch; retry at the next trigger
                    await asyncio.sleep(wait)
                else:
                    self.error, self.pending = None, None
                    break

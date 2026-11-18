"""Event sinks for harness turns (DSH migration plan D8, R16; Phase 2 events plan D2).

Runners emit `AgentEvent`s through an `AttemptEvents`, which hands them to a sink:
`BatchingPublisher` publishes them to the event table; tests use the in-memory sink.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any, Protocol

from common.events import EventTransport, Writer
from common.events.transport import wait_set
from common.persistence.fence import FenceRejected
from common.schemas.events import AgentEvent, EventType

log = logging.getLogger("praxis.events")
CLOSE_TIMEOUT_S = 10.0  # the bound on an attempt's final flush (Phase 2 events plan D2)


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
      re-sends it unchanged after each backoff (once per batch), then once at each
      later trigger, also while closing, so a commit whose reply was lost is
      deduplicated by its ID; new events wait for later batches.
    - A refused publish (`FenceRejected`) stops publishing; `close()` returns it.
    - `close()` runs once: later calls return its result without waiting again.

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
        self.buffer: list[tuple[float, AgentEvent]] = []  # (monotonic emit time, event)
        self.pending: tuple[str, list[AgentEvent]] | None = None
        self.backed_off = False  # the pending batch has used its backoff tries
        self.batches = 0
        self.refused: FenceRejected | None = None
        self.error: Exception | None = None
        self.closing = False
        self.result: Exception | None = None
        self.wake = asyncio.Event()
        self.task = self.loop.create_task(self._run())

    def emit(self, event: AgentEvent) -> None:
        with self.lock:
            if self.refused is not None:
                return  # a superseded attempt stores nothing more
            if self.closing and self.task.done():
                log.warning("event emitted after its attempt closed; not stored",
                            extra={"fields": {"type": event.type, "seq": event.seq}})  # fmt: skip
                return
            self.buffer.append((time.monotonic(), event))
        self.loop.call_soon_threadsafe(self.wake.set)

    @property
    def closed(self) -> bool:
        """True once `close()` has been called, whether or not it has finished."""
        return self.closing

    async def close(self, timeout_s: float | None = None) -> Exception | None:
        """Publish everything buffered and stop. Shielded from the caller's
        cancellation and bounded by `timeout_s`. Returns the refusal, the last
        database error (or a timeout), or None when every event was stored. Only
        the first call waits; later calls return its result."""
        if self.closing:
            return self.result
        self.closing = True
        self.wake.set()
        try:
            # The caller's cancellation reaches the caller only; the flush goes on.
            async with asyncio.timeout(CLOSE_TIMEOUT_S if timeout_s is None else timeout_s):
                await asyncio.shield(self.task)
        except TimeoutError as e:
            self.task.cancel()
            self.result = self.refused or self.error or e
            return self.result
        self.result = self.refused or self.error
        return self.result

    def _next_wait(self) -> float | None:
        if self.pending is not None:
            return self.delay_s  # a failed batch: one more try at the next trigger
        with self.lock:
            if not self.buffer:
                return None
            return max(0.0, self.buffer[0][0] + self.delay_s - time.monotonic())

    async def _run(self) -> None:
        while True:
            await wait_set(self.wake, self._next_wait())
            self.wake.clear()
            await self._drain()
            if self.refused is not None:
                return
            if self.closing and self._empty():
                return  # a failing database keeps it trying until close() times out

    def _empty(self) -> bool:
        with self.lock:
            return self.pending is None and not self.buffer

    def _cut(self) -> bool:
        with self.lock:
            due = (
                self.closing
                or len(self.buffer) >= self.max_batch
                or (bool(self.buffer) and time.monotonic() - self.buffer[0][0] >= self.delay_s)
            )
            if not self.buffer or not due:
                return False
            cut, self.buffer = self.buffer[: self.max_batch], self.buffer[self.max_batch :]
        self.pending = (f"{self.workflow_id}:{self.attempt_id}:{self.batches}", [e for _, e in cut])
        self.backed_off = False
        self.batches += 1
        return True

    async def _drain(self) -> None:
        while self.pending is not None or self._cut():
            assert self.pending is not None
            batch_id, events = self.pending
            waits = (None,) if self.backed_off else (*self.backoff_s, None)
            for wait in waits:
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
                        self.backed_off = True
                        return  # keep the batch; one more try at the next trigger
                    await asyncio.sleep(wait)
                else:
                    self.error, self.pending = None, None
                    break

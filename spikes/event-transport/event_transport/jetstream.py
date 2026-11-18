"""NATS JetStream transport, a correctness probe (plan D2, D5, notes.md#d5; task 2.3).

One stream per spike workflow (`events-<workflow_id>`, subject `events.<workflow_id>`),
so stream sequences are the workflow's gap-free offsets. Each event is one message
with `Nats-Msg-Id` `<batch_id>:<i>`; the duplicate window equals the re-send
horizon (R3). Readers use a pull consumer from a start sequence and detect expiry
by comparing with the stream's first sequence (R2). `nats-py` has no async publish,
so a batch is published one message at a time.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import nats
from nats.errors import TimeoutError as NatsTimeout
from nats.js import api
from nats.js.errors import NotFoundError

from event_transport.models import AgentEvent
from event_transport.transport import Item, expiry_for, guarded

URL = os.environ.get("SPIKE_NATS", "nats://127.0.0.1:34222")
FETCH = 256
WAIT_S = 1.0


class JetStreamTransport:
    def __init__(self, nc: nats.NATS, horizon_s: float) -> None:
        self.nc, self.js, self.horizon_s = nc, nc.jetstream(), horizon_s
        self._streams: set[str] = set()

    @classmethod
    async def connect(cls, horizon_s: float, url: str = URL) -> JetStreamTransport:
        return cls(await nats.connect(url), horizon_s)

    @staticmethod
    def _names(workflow_id: str) -> tuple[str, str]:
        return f"events-{workflow_id}", f"events.{workflow_id}"

    async def _ensure(self, workflow_id: str) -> tuple[str, str]:
        stream, subject = self._names(workflow_id)
        if stream not in self._streams:
            await self.js.add_stream(
                api.StreamConfig(
                    name=stream,
                    subjects=[subject],
                    storage=api.StorageType.FILE,
                    num_replicas=1,
                    duplicate_window=self.horizon_s,
                )
            )
            self._streams.add(stream)
        return stream, subject

    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        _, subject = await self._ensure(workflow_id)
        for i, event in enumerate(events):
            await self.js.publish(
                subject,
                event.model_dump_json().encode(),
                headers={"Nats-Msg-Id": f"{batch_id}:{i}"},
            )

    async def _state(self, workflow_id: str) -> api.StreamState | None:
        stream, _ = self._names(workflow_id)
        try:
            return (await self.js.stream_info(stream)).state
        except NotFoundError:
            return None

    def read(self, workflow_id: str, after: int, *, follow: bool = False) -> AsyncIterator[Item]:
        return guarded(after, self._read(workflow_id, after, follow))

    async def _read(self, workflow_id: str, after: int, follow: bool) -> AsyncIterator[Item]:
        stream, subject = await self._ensure(workflow_id)
        state = await self._state(workflow_id)
        last = state.last_seq if state else 0
        if state and last:
            base = state.first_seq if state.messages else last + 1
            expired = expiry_for(after, base)
            if expired is not None:
                yield expired
                after = expired.retained_base - 1
        if not follow and after >= last:
            return
        sub = await self.js.pull_subscribe(
            subject,
            stream=stream,
            config=api.ConsumerConfig(
                deliver_policy=api.DeliverPolicy.BY_START_SEQUENCE,
                opt_start_seq=after + 1,
                ack_policy=api.AckPolicy.NONE,
                inactive_threshold=60.0,
            ),
        )
        try:
            position = after
            while True:
                try:
                    msgs = await sub.fetch(FETCH, timeout=WAIT_S)
                except NatsTimeout:
                    msgs = []
                for msg in msgs:
                    position = msg.metadata.sequence.stream
                    yield position, AgentEvent.model_validate_json(msg.data)
                if not follow and position >= last:
                    return
                if not follow and not msgs:
                    state = await self._state(workflow_id)  # purged during the read (F40)
                    if state is None or not state.messages or state.last_seq <= position:
                        return
        finally:
            await sub.unsubscribe()

    async def latest(self, workflow_id: str) -> int | None:
        state = await self._state(workflow_id)
        return state.last_seq if state and state.last_seq else None

    async def expire_below(self, workflow_id: str, offset: int) -> None:
        stream, _ = await self._ensure(workflow_id)
        await self.js.purge_stream(stream, seq=offset)

    async def roll_over(self, workflow_id: str) -> bool:
        return False  # not hosted in a Workflow (R4 is n/a)

    async def close(self) -> None:
        # Streams stay: other instances may still use them (F36); `down --volumes`
        # on the NATS project removes them.
        await self.nc.close()

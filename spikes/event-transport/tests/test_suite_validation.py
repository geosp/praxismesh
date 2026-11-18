"""The suite's checks pass on the reference and fail on broken variants (task 1.4)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from event_transport import checks
from event_transport.memory import MemoryTransport
from event_transport.models import AgentEvent
from event_transport.transport import Expired, Item

from tests.test_fixture import recorded_turn

HORIZON_S = 6.0


class DropsEvent(MemoryTransport):
    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        middle = len(events) // 2
        await super().publish(workflow_id, batch_id, events[:middle] + events[middle + 1 :])


class RepeatsEvent(MemoryTransport):
    async def read(
        self, workflow_id: str, after: int, *, follow: bool = False
    ) -> AsyncIterator[Item]:
        first = True
        async for item in super().read(workflow_id, after, follow=follow):
            yield item
            if first and not isinstance(item, Expired):
                first = False
                yield item


class SkipsExpiry(MemoryTransport):
    async def read(
        self, workflow_id: str, after: int, *, follow: bool = False
    ) -> AsyncIterator[Item]:
        async for item in super().read(workflow_id, after, follow=follow):
            if not isinstance(item, Expired):
                yield item


class StoresResentTwice(MemoryTransport):
    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        self._log(workflow_id).batches.clear()
        await super().publish(workflow_id, batch_id, events)


class NeverRolls(MemoryTransport):
    """Claims a Workflow (hosted) but its roll-over does nothing."""


async def run_all(t: MemoryTransport) -> None:
    await checks.check_r1_resume(t)
    await checks.check_r2_expiry(t)
    await checks.check_r2_mid_read(t)
    await checks.check_r3_resend(t, HORIZON_S)
    await checks.check_r4_roll_over(t, hosted=False)
    await checks.check_r7_replay(t, recorded_turn())


async def test_reference_passes_every_check() -> None:
    await run_all(MemoryTransport(HORIZON_S))


@pytest.mark.parametrize(
    ("broken", "check"),
    [
        (DropsEvent, "check_r1_resume"),
        (DropsEvent, "check_r7_replay"),
        (RepeatsEvent, "check_r1_resume"),
        (SkipsExpiry, "check_r2_expiry"),
        (SkipsExpiry, "check_r2_mid_read"),
        (NeverRolls, "check_r4_roll_over"),
        (NeverRolls, "check_r4_truncating_roll_over"),
        (StoresResentTwice, "check_r3_resend"),
    ],
)
async def test_a_broken_transport_fails_its_check(
    broken: type[MemoryTransport], check: str
) -> None:
    t = broken(HORIZON_S)
    fn = getattr(checks, check)
    args: tuple[object, ...] = (t,)
    if check == "check_r3_resend":
        args = (t, HORIZON_S)
    elif check == "check_r4_roll_over":
        args = (t, True)
    elif check == "check_r7_replay":
        args = (t, recorded_turn())
    with pytest.raises(AssertionError):
        await fn(*args)


class ResumesPastBase(MemoryTransport):
    """After a removal during a read, never delivers the first 9 retained events."""

    async def _read(self, workflow_id: str, after: int, follow: bool) -> AsyncIterator[Item]:
        log = self._log(workflow_id)
        async for item in super()._read(workflow_id, after, follow):
            if not isinstance(item, Expired) and 1 < log.base <= item[0] < log.base + 9:
                continue  # a real bug: retained events are lost
            yield item


async def test_a_reader_that_skips_retained_events_fails_r2_mid_read() -> None:
    with pytest.raises(AssertionError):
        await checks.check_r2_mid_read(ResumesPastBase(HORIZON_S))

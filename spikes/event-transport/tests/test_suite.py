"""The shared requirement suite (plan R1-R4, R7; task 1.4).

    SPIKE_TRANSPORTS=memory,table uv run pytest tests/test_suite.py
    SUITE_HORIZON_S=60   # the R3 re-send horizon, the same for every option

Results per requirement and transport go to `results/suite-<transport>.json`
(see conftest.py): pass, fail, or n/a for R4 on options not hosted in a Workflow.
"""

from __future__ import annotations

import pytest
from event_transport import checks
from event_transport.factories import OPTIONS
from event_transport.models import AgentEvent
from event_transport.transport import EventTransport

from tests.test_fixture import recorded_turn


@pytest.mark.requirement("R1")
async def test_r1_resume(transport: EventTransport) -> None:
    await checks.check_r1_resume(transport)


@pytest.mark.requirement("R2")
async def test_r2_expiry(transport: EventTransport) -> None:
    await checks.check_r2_expiry(transport)


@pytest.mark.requirement("R2")
async def test_r2_mid_read(transport: EventTransport) -> None:
    await checks.check_r2_mid_read(transport)


@pytest.mark.requirement("R3")
async def test_r3_resend(transport: EventTransport, horizon_s: float) -> None:
    await checks.check_r3_resend(transport, horizon_s)


@pytest.mark.requirement("R4")
async def test_r4_roll_over(transport: EventTransport, option_name: str) -> None:
    await checks.check_r4_roll_over(transport, OPTIONS[option_name].hosted)


@pytest.mark.requirement("R4")
async def test_r4_truncating_roll_over(transport: EventTransport, option_name: str) -> None:
    if not OPTIONS[option_name].hosted:
        pytest.skip("no Workflow to roll over (R4 is n/a)")
    await checks.check_r4_truncating_roll_over(transport)


@pytest.mark.requirement("R7")
async def test_r7_replay(transport: EventTransport) -> None:
    recorded: list[AgentEvent] = recorded_turn()
    await checks.check_r7_replay(transport, recorded)

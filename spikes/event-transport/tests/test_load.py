"""The load runner keeps its offered rate, names batches per attempt, judges R5, R6 and
R11 correctly, and never leaves a run unbounded (phase 02 impl review F61, F64, F75,
F76)."""

from __future__ import annotations

import asyncio
import dataclasses
import itertools
import os
import time

import load
import pytest
from event_transport.memory import MemoryTransport
from event_transport.models import AgentEvent
from temporalio.testing import ActivityEnvironment


class SlowTransport(MemoryTransport):
    """Each publish takes 100 ms, as a slow transport would."""

    def __init__(self) -> None:
        super().__init__()
        self.batch_ids: list[str] = []

    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        self.batch_ids.append(batch_id)
        await asyncio.sleep(0.1)
        await super().publish(workflow_id, batch_id, events)


async def run_agent(
    transport: MemoryTransport, seconds: float, attempt: int = 1
) -> load.AgentResult:
    env = ActivityEnvironment()
    env.info = dataclasses.replace(env.info, attempt=attempt)
    return await env.run(load.Agents(transport).publish, load.AgentInput("wf-1", seconds))


async def test_a_slow_transport_still_gets_the_offered_rate() -> None:
    """F61: the generator is open-loop, so publish time does not lower the load."""
    t = SlowTransport()
    out = await run_agent(t, 2.0)
    assert out.published >= 0.95 * load.RATE_PER_S * 2.0, out.published


async def test_events_are_stamped_on_their_schedule() -> None:
    """F61: an event's time is when it was due, so a blocked publish shows as latency."""
    t = SlowTransport()
    await run_agent(t, 2.0)
    stamps = [e.payload["t"] for _, e in [i async for i in t.read("wf-1", 0)]]
    gaps = [b - a for a, b in itertools.pairwise(stamps)]
    assert max(gaps) < 3 / load.RATE_PER_S, max(gaps)


async def test_batch_ids_name_the_attempt() -> None:
    """F76: a retried attempt's batches are new batches, not re-sends."""
    t = SlowTransport()
    await run_agent(t, 0.5, attempt=2)
    assert t.batch_ids and all(":2:" in b for b in t.batch_ids), t.batch_ids[:2]


def test_judging_applies_the_thresholds() -> None:
    """F75: R5, R6 and R11 against the plan's bounds; a missing value fails, never raises."""
    ok = load.judge(True, p95=999, complete=True, max_events=5119, max_bytes=5_000_000,
                    max_carried=1_000_000)  # fmt: skip
    assert ok == {"R5": "pass", "R6": "pass", "R11": "pass"}
    assert load.judge(True, 1001, True, 1, 1, 1)["R6"] == "fail"
    assert load.judge(True, 10, False, 1, 1, 1)["R6"] == "fail"  # a tailer fell short
    assert load.judge(True, 10, True, 5120, 1, 1)["R5"] == "fail"
    assert load.judge(True, 10, True, 1, 1, 1_048_576)["R11"] == "fail"
    assert load.judge(True, None, True, None, None, None) == {
        "R5": "fail",
        "R6": "fail",
        "R11": "fail",
    }
    assert load.judge(False, 10, True, None, None, None) == {
        "R5": "n/a",
        "R6": "pass",
        "R11": "n/a",
    }


def test_percentile_picks_the_value_at_the_rank() -> None:
    """F75: the latency percentiles the judging uses."""
    values = [float(v) for v in range(1, 101)]
    assert load.percentile(values, 0.5) == 51.0
    assert load.percentile(values, 0.95) == 96.0
    assert load.percentile(values, 0.99) == 100.0
    assert load.percentile([], 0.95) is None


class FailingTransport(MemoryTransport):
    async def publish(self, workflow_id: str, batch_id: str, events: list[AgentEvent]) -> None:
        raise RuntimeError("the transport is down")


@pytest.mark.skipif(not os.environ.get("SPIKE_STACK"), reason="needs the disposable stack")
async def test_a_failing_transport_ends_the_run_and_leaves_no_agent_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """F64: one attempt per agent, a Workflow timeout, and cleanup on the way out."""
    from temporalio.client import Client

    async def failing(horizon_s: float) -> FailingTransport:
        return FailingTransport()

    monkeypatch.setitem(
        load.OPTIONS, "memory", dataclasses.replace(load.OPTIONS["memory"], build=failing)
    )
    monkeypatch.setattr(load, "RESULTS", tmp_path)
    started = time.monotonic()
    code = await asyncio.wait_for(load.main(["memory", "--seconds", "5", "--label", "fail"]), 60)
    assert code != 0 and time.monotonic() - started < 60
    client = await Client.connect(load.ADDRESS)
    running = [
        w async for w in client.list_workflows(
            "WorkflowType = 'SpikeLoadAgent' AND ExecutionStatus = 'Running'"
        )
    ]  # fmt: skip
    assert running == [], [w.id for w in running]

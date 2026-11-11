"""Replay test for HelloWorkflow (plan §8): the current Workflow code must replay
the history recorded from the local stack without a non-determinism error.
No server needed. Re-record with: RECORD_HELLO_HISTORY=1 make smoke"""

from __future__ import annotations

from pathlib import Path

from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

from tests.support.hello import HelloWorkflow

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hello_history.json"


async def test_hello_replay() -> None:
    history = WorkflowHistory.from_json("phase0-hello", FIXTURE.read_text())
    result = await Replayer(workflows=[HelloWorkflow]).replay_workflow(history)
    assert result.replay_failure is None

"""The history payload guard finds a payload over 64 KiB wherever it sits in an
event (Phase 3A persistence plan phase 01 task 3.3; R18, D9)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from temporalio.api.common.v1 import Header, Memo, Payload, Payloads
from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import (
    ActivityTaskCompletedEventAttributes,
    History,
    HistoryEvent,
    WorkflowExecutionStartedEventAttributes,
)
from temporalio.client import Client

from tests.support import history_guard
from tests.support.history_guard import LIMIT_BYTES, LargePayload, guard_failure, large_payloads


def payload(size: int) -> Payload:
    return Payload(metadata={"encoding": b"json/plain"}, data=b"x" * size)


def history(*events: HistoryEvent) -> History:
    return History(events=list(events))


def test_a_seeded_65_kib_payload_fails() -> None:
    started = HistoryEvent(
        event_id=1,
        event_type=EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED,
        workflow_execution_started_event_attributes=WorkflowExecutionStartedEventAttributes(
            input=Payloads(payloads=[payload(100), payload(65 * 1024)])
        ),
    )
    (found,) = large_payloads("wf", history(started))
    assert (found.workflow_id, found.event_id) == ("wf", 1)
    assert found.event_type == "workflow_execution_started_event_attributes"
    assert found.size > LIMIT_BYTES


def test_payloads_in_maps_and_results_are_checked() -> None:
    started = HistoryEvent(
        event_id=1,
        workflow_execution_started_event_attributes=WorkflowExecutionStartedEventAttributes(
            memo=Memo(fields={"big": payload(70_000)}),
            header=Header(fields={"small": payload(10)}),
        ),
    )
    completed = HistoryEvent(
        event_id=5,
        activity_task_completed_event_attributes=ActivityTaskCompletedEventAttributes(
            result=Payloads(payloads=[payload(66_000)])
        ),
    )
    assert [p.event_id for p in large_payloads("wf", history(started, completed))] == [1, 5]


def test_payloads_up_to_the_limit_pass() -> None:
    event = HistoryEvent(
        event_id=1,
        activity_task_completed_event_attributes=ActivityTaskCompletedEventAttributes(
            result=Payloads(payloads=[payload(60 * 1024)])
        ),
    )
    assert large_payloads("wf", history(event)) == []


async def test_the_guard_fails_when_temporal_cannot_be_reached() -> None:
    """Review F84: an unreachable Temporal is a failure, not a silent pass."""

    async def unreachable() -> Client:
        raise RuntimeError("connection refused")

    failure = await guard_failure(datetime.now(UTC), connect=unreachable, settle=0)
    assert failure is not None and "connection refused" in failure


async def test_the_guard_reports_each_large_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failing path of the session guard (review F84)."""

    async def found(client: Client, since: datetime) -> list[LargePayload]:
        return [LargePayload("wf-1", 5, "activity_task_completed", LIMIT_BYTES + 1)]

    async def connect() -> Client:
        return cast(Client, object())

    monkeypatch.setattr(history_guard, "check_since", found)
    failure = await guard_failure(datetime.now(UTC), connect=connect, settle=0)
    assert failure is not None and "wf-1 event 5" in failure


async def test_the_guard_passes_with_no_large_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def found(client: Client, since: datetime) -> list[LargePayload]:
        return []

    async def connect() -> Client:
        return cast(Client, object())

    monkeypatch.setattr(history_guard, "check_since", found)
    assert await guard_failure(datetime.now(UTC), connect=connect, settle=0) is None

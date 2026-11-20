"""The history payload guard finds a payload over 64 KiB wherever it sits in an
event (Phase 3A persistence plan phase 01 task 3.3; R18, D9)."""

from __future__ import annotations

from temporalio.api.common.v1 import Header, Memo, Payload, Payloads
from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import (
    ActivityTaskCompletedEventAttributes,
    History,
    HistoryEvent,
    WorkflowExecutionStartedEventAttributes,
)

from tests.support.history_guard import LIMIT_BYTES, large_payloads


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

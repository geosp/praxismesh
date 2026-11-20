"""Claim Check guard: no payload in a Workflow history may exceed 64 KiB (Phase 3A
persistence plan R18, D9). Large values travel as `BlobRef`s, so a bigger payload
means something large slipped into Temporal history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from google.protobuf.message import Message
from temporalio.api.common.v1 import Payload
from temporalio.api.history.v1 import History
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

LIMIT_BYTES = 64 * 1024


@dataclass(frozen=True)
class LargePayload:
    workflow_id: str
    event_id: int
    event_type: str
    size: int


def _payloads(message: Message) -> list[Payload]:
    """Every `Payload` inside `message`, at any depth (inputs, results, memos,
    headers, failure details)."""
    if isinstance(message, Payload):
        return [message]
    found: list[Payload] = []
    for field, value in message.ListFields():
        if field.message_type is None:
            continue
        if field.message_type.GetOptions().map_entry:
            entry_value = field.message_type.fields_by_name["value"]
            if entry_value.message_type is not None:
                for item in value.values():
                    found.extend(_payloads(item))
        elif field.is_repeated:
            for item in value:
                found.extend(_payloads(item))
        else:
            found.extend(_payloads(value))
    return found


def large_payloads(
    workflow_id: str, history: History, limit: int = LIMIT_BYTES
) -> list[LargePayload]:
    """The payloads of `history` larger than `limit` bytes (data plus metadata)."""
    out = []
    for event in history.events:
        for payload in _payloads(event):
            size = payload.ByteSize()
            if size > limit:
                out.append(
                    LargePayload(
                        workflow_id, event.event_id, event.WhichOneof("attributes") or "?", size
                    )
                )
    return out


async def runs_since(client: Client, since: datetime) -> list[tuple[str, str]]:
    """(Workflow ID, run ID) of every run started at or after `since`."""
    query = f"StartTime >= '{since.isoformat()}'"
    return [(e.id, e.run_id) async for e in client.list_workflows(query)]


async def check_since(client: Client, since: datetime) -> list[LargePayload]:
    """Check every Workflow run started at or after `since`. A run deleted since
    (some tests delete closed runs) is skipped."""
    found: list[LargePayload] = []
    for workflow_id, run_id in await runs_since(client, since):
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        try:
            history = await handle.fetch_history()
        except RPCError as e:
            if e.status == RPCStatusCode.NOT_FOUND:
                continue
            raise
        found.extend(large_payloads(workflow_id, History(events=history.events)))
    return found

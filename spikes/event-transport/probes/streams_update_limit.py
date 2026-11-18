"""Growth of the roll-over-off Streams load (`measure.sh`'s `--no-roll` run), read from
the hosting runs' histories after it stalled at Temporal's per-run Update limit.

    PYTHONPATH=. uv run python probes/streams_update_limit.py > results/streams-growth-norollover.json
"""

import asyncio
import json

from temporalio.client import Client


async def main() -> None:
    client = await Client.connect("127.0.0.1:37233")
    out = []
    query = "WorkflowId STARTS_WITH 'spike76-stream-load-' AND ExecutionStatus = 'Running'"
    async for ex in client.list_workflows(query):
        handle = client.get_workflow_handle(ex.id, run_id=ex.run_id)
        events = size = 0
        updates: dict[str, int] = {}
        first = last = None
        async for e in handle.fetch_history_events():
            events += 1
            size += e.ByteSize()
            t = e.event_time.ToDatetime()
            first, last = first or t, t
            if e.HasField("workflow_execution_update_accepted_event_attributes"):
                attrs = e.workflow_execution_update_accepted_event_attributes
                name = attrs.accepted_request.input.name
                updates[name] = updates.get(name, 0) + 1
        minutes = max((last - first).total_seconds() / 60, 1e-9) if first and last else 0
        out.append(
            {
                "workflow": ex.id,
                "minutes_to_last_event": round(minutes, 2),
                "events": events,
                "bytes": size,
                "updates_accepted": updates,
                "events_per_min": round(events / minutes) if minutes else None,
                "mb_per_min": round(size / minutes / 1e6, 2) if minutes else None,
            }
        )
    print(json.dumps(out, indent=2))


asyncio.run(main())

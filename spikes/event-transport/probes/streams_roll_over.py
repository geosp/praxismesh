import asyncio
import uuid

from event_transport.checks import collect, make_events, offsets
from event_transport.streams import StreamsTransport


async def main():
    t = await StreamsTransport.connect(60)
    try:
        wf = f"probe-can-{uuid.uuid4().hex[:8]}"
        await t.publish(wf, "b0", make_events(wf, 600))
        h = t.client.get_workflow_handle(t._wid(wf))
        before = (await h.describe()).run_id
        await t.roll_over(wf)
        await asyncio.sleep(2)
        await t.publish(wf, "b1", make_events(wf, 5, start=600))
        after = (await h.describe()).run_id
        items = await collect(t, wf, 0)
        print(
            "run changed:",
            before != after,
            "| first item:",
            items[0],
            "| offsets",
            offsets(items)[:2],
            "...",
            offsets(items)[-1],
        )
    finally:
        await t.close()


asyncio.run(main())

"""What does a JetStream consumer get when it starts below the first retained sequence?"""

import asyncio
import uuid

import nats
from nats.js import api

STREAM = f"probe-expiry-{uuid.uuid4().hex[:8]}"
SUBJECT = STREAM.replace("-", ".")


async def main():
    nc = await nats.connect("nats://127.0.0.1:34222")
    js = nc.jetstream()
    await js.add_stream(
        api.StreamConfig(name=STREAM, subjects=[SUBJECT], storage=api.StorageType.FILE)
    )
    try:
        for i in range(20):
            await js.publish(SUBJECT, str(i).encode())
        await js.purge_stream(STREAM, seq=15)
        st = (await js.stream_info(STREAM)).state
        print(
            f"after purge: first_seq={st.first_seq} last_seq={st.last_seq} messages={st.messages}"
        )
        sub = await js.pull_subscribe(
            SUBJECT,
            stream=STREAM,
            config=api.ConsumerConfig(
                deliver_policy=api.DeliverPolicy.BY_START_SEQUENCE,
                opt_start_seq=5,
                ack_policy=api.AckPolicy.NONE,
            ),
        )
        msgs = await sub.fetch(100, timeout=2)
        seqs = [m.metadata.sequence.stream for m in msgs]
        print(
            f"consumer from opt_start_seq=5: first delivered seq={seqs[0]}, "
            f"count={len(seqs)}, no error or gap marker raised"
        )
        await sub.unsubscribe()
    finally:
        await js.delete_stream(STREAM)
        await nc.close()


asyncio.run(main())

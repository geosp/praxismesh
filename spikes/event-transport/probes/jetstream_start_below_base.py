"""What does a JetStream consumer get when it starts below the first retained sequence?"""

import asyncio

import nats
from nats.js import api


async def main():
    nc = await nats.connect("nats://127.0.0.1:34222")
    js = nc.jetstream()
    await js.add_stream(
        api.StreamConfig(
            name="probe-expiry", subjects=["probe.expiry"], storage=api.StorageType.FILE
        )
    )
    try:
        for i in range(20):
            await js.publish("probe.expiry", str(i).encode())
        await js.purge_stream("probe-expiry", seq=15)
        st = (await js.stream_info("probe-expiry")).state
        print(
            f"after purge: first_seq={st.first_seq} last_seq={st.last_seq} messages={st.messages}"
        )
        sub = await js.pull_subscribe(
            "probe.expiry",
            stream="probe-expiry",
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
        await js.delete_stream("probe-expiry")
        await nc.close()


asyncio.run(main())

# Probes

Small scripts that answer questions the docs leave open. Run from `spikes/event-transport`
with the disposable stack and the NATS project up:

    PYTHONPATH=. uv run python probes/<script>.py

| Probe | Question | Observed (2026-11-18, nats-server 2.15.3, temporalio 1.36.0) |
| --- | --- | --- |
| `jetstream_start_below_base.py` | What does a JetStream consumer get when it starts below the stream's first retained sequence? | After purging below 15, a consumer from `opt_start_seq=5` silently delivers from 15 (6 messages), with no error or gap marker. A reader must compare with `first_seq` itself to report expiry (R2). |
| `streams_roll_over.py` | Does `roll_over` really continue as new, and do offsets continue across it? | The run ID changes; 600 events are kept as the last 500 (base 101), so a read from 0 yields `Expired(101)`, then offsets 101-605 with no gap. |

From the pinned `temporalio` 1.36.0 source (design review round 2): `WorkflowStreamClient.subscribe()`
catches the poll Update's `TruncatedOffset` and silently restarts at offset 0, so it cannot report
expiry either. Both options meet R2 in the spike only because the reader checks the retained base
before reading (plan D1).

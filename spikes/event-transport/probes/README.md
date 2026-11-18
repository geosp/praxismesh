# Probes

Small scripts that answered questions the docs leave open. They exercised the Workflow Streams
and NATS JetStream transports, which were removed after the decision (ADR-0009); the scripts are
in git history at `1bfac67` (run from `spikes/event-transport` with `PYTHONPATH=.`).

| Probe | Question | Observed (2026-11-18, nats-server 2.15.3, temporalio 1.36.0) |
| --- | --- | --- |
| `jetstream_start_below_base.py` | What does a JetStream consumer get when it starts below the stream's first retained sequence? | After purging below 15, a consumer from `opt_start_seq=5` silently delivers from 15 (6 messages), with no error or gap marker. A reader must compare with `first_seq` itself to report expiry (R2). |
| `streams_roll_over.py` | Does `roll_over` really continue as new, and do offsets continue across it? | The run ID changes; 600 events are kept as the last 500 (base 101), so a read from 0 yields `Expired(101)`, then offsets 101-605 with no gap. |
| `streams_update_limit.py` | How fast does a Streams hosting run grow with roll-over off? | Each run hit Temporal's 2,000-Updates-per-run limit after ~1.85 min (~500 publish, ~1,500 poll Updates with 3 tailers), at ~8,500 events and ~10.2 MB (`results/streams-growth-norollover.provenance.json`; the raw `streams-growth-norollover.json` also lists 12 leftover runs). |

From the pinned `temporalio` 1.36.0 source (design review round 2): `WorkflowStreamClient.subscribe()`
catches the poll Update's `TruncatedOffset` and silently restarts at offset 0, so it cannot report
expiry either. The spike meets R2 with two checks: the reader compares its offset with the
retained base before reading (`expiry_for`, plan D1), and `transport.guarded()` reports an offset
that jumps during a read.

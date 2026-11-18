# Event-transport spike: results and recommendation

- Plan: [docs/plans/2026-11-17-event-transport-spike](../plans/2026-11-17-event-transport-spike/plan.md) (issue #76).
- Code: `spikes/event-transport/`; measurements at commit `c1fda62` (clean tree), results in
  `spikes/event-transport/results/`.
- Versions: `temporalio` 1.36.0 (Workflow Streams, Public Preview), Temporal server from
  `infra/docker-compose.yml`, PostgreSQL (ParadeDB, ADR-0002) via `asyncpg` 0.32.0, nats-server
  2.15.3 and `nats-py` 2.17.0.
- Date: 2026-11-18.

## Decision

D2 (following design §4.4): Streams wins if it passes R1-R7 and R11; otherwise the table; NATS
only if both fail.

Workflow Streams and the PostgreSQL table both passed every must-pass requirement in all 3 runs,
so D2 selects Streams. NATS passed the correctness suite (its load runs were not needed).

**Owner decision (2026-11-18): the PostgreSQL table.** The measurements below favour it on
everything D2 did not weigh: cost under load, limits, API maturity, code size, fencing and latency
(see [Owner attention](#owner-attention)). This departs deliberately from §4.4's preference and is
recorded in ADR-0009 (proposed) and the decision log. The Streams and NATS implementations were
then deleted from the spike (D6); they remain in git history at `1bfac67`.

## Requirements per option

| Requirement | Workflow Streams | PostgreSQL table | NATS JetStream (probe) |
| --- | --- | --- | --- |
| R1 Readers resume after their offset | pass (3/3) | pass (3/3) | pass |
| R2 An expired offset is reported | pass (3/3) | pass (3/3) | pass |
| R3 A re-sent batch is stored once | pass (3/3) | pass (3/3) | pass |
| R4 Offsets survive roll-over | pass (3/3) | n/a | n/a |
| R5 History stays bounded | pass (3/3): largest run 3,531 events, 4.50 MB (bound 5,120 / 5 MB) | n/a | not measured |
| R6 p95 publish-to-display ≤ 1 s | pass (3/3): 199-200 ms | pass (3/3): 187-188 ms | not measured |
| R7 The recorded turn replays exactly | pass (3/3) | pass (3/3) | pass |
| R8 Results are reproducible | every pass/fail matches across 3 runs | same | single suite run (phase 01) |
| R9 Production stays unchanged | holds (diff outside `spikes/` and `docs/` is empty) | | |
| R10 Stale attempts assessed | see [Fencing](#fencing-r10) | | |
| R11 Carried state < 50% of payload limit | pass (3/3): 298 KB (bound 1 MB) | n/a | n/a |

Sources: `results/run{1,2,3}/suite-*.json`, `results/load-{streams,table}-run{1,2,3}.json`,
`results/suite-nats.json` (phase 01, commit `69c95c4`).

## Measurements

Synthetic load: 4 agents, ~50 token events/s each plus a tool pair every 10 s, 5 min, 3 tailers
per agent (one stopped and resumed every 60 s); 54,900-58,100 events per run.

| Metric (median of 3 runs) | Workflow Streams | PostgreSQL table |
| --- | --- | --- |
| Latency p50 / p95 / p99 | 113 / 199 / 326 ms | 92 / 187 / 189 ms |
| Tailers complete, expiries seen | all complete, none | all complete, none |
| Hosting runs per agent in 5 min | 8 (a roll-over every ~40 s) | n/a |
| Largest run | ~3,520 events, 4.5 MB, ~825 Updates | n/a |
| Carried state per roll-over | 298 KB (the last 500 events) | n/a |
| Temporal container CPU (median / max, run 1) | 32.6% / 204% | 1.6% / 3.1% |
| PostgreSQL container CPU (median / max, run 1) | 13.1% / 21.1% (Temporal's persistence) | 3.2% / 9.1% |

The 200 ms publish batch accounts for most of the latency of both options.

### Streams growth without roll-over (informational)

With roll-over off, every hosting run stalled after **~1.85 min** at Temporal's limit of
**2,000 Updates per run**: ~500 publish and ~1,500 poll Updates (3 tailers), ~8,500 events and
~10.2 MB of history (~4,600 events and ~5.5 MB per minute). Source:
`results/streams-growth-norollover.json` (`probes/streams_update_limit.py`). Every tailer adds
one poll Update per batch, so a run holds at most 2,000 / (1 + tailers) batches: at this load,
roll-over every ~100 s with 3 tailers and every ~36 s with 10. In the judged runs Temporal's
Continue-As-New suggestion arrived at ~770 Updates, before D5's 2,000-batch trigger.

## Findings that apply whichever option wins

- **Neither third-party option reports expiry itself.** Streams' `subscribe()` silently restarts
  at offset 0 on a truncated offset (pinned source); a JetStream consumer starting below the
  first retained sequence silently delivers from it (`probes/jetstream_start_below_base.py`).
  The spike meets R2 for every option with one reader rule (`transport.guarded()`): an offset that
  jumps is reported as `Expired`, a repeat raises. Phase 2 needs that rule.
- **Token text has no place yet.** `AgentEvent` payloads must hold no model text
  (`common/schemas/events.py`), but streamed token deltas are model text. Phase 2 must decide
  where token text lives (a blob per turn, or an exception for token events).
- **A removal through the end of the log** yields no expiry until a later event arrives
  (impl review F55), the same for every option.

## Operating cost (task 2.1)

| Heading | Workflow Streams | PostgreSQL table | NATS JetStream |
| --- | --- | --- | --- |
| New components | none (Temporal) | none (the application database) | a NATS server; 3 replicas in production (Helm chart StatefulSet) |
| API maturity | Public Preview / experimental; the spike imports a private decoder | stable | stable |
| Backups | events live in Temporal history; kept per namespace retention | in the application database's backups (Phase 3A) | its own volume; incremental stream backups only planned (2.16) |
| Authentication and scoping | any Temporal client can query or update any Workflow: scoping must be in the gateway | the app role; scoping by workflow and tenant in queries | NATS accounts and per-subject permissions |
| Upgrades | the preview API may change between SDK releases | none new | server lines (two maintained at a time) |
| Kubernetes path | Temporal's (already planned) | the application database's | a new StatefulSet |
| Load on shared services | Temporal CPU ~20x the table's; Temporal's database 4x | small | its own |
| Extra code beyond D5 | the hosting Workflow (115 lines), a custom publish Update with batch-ID dedup, a `retained_base` Query, Update-only reads mapping `TruncatedOffset`, a cancellation fix in the retry loop: 314 lines in all | counter row, batch table, `LISTEN/NOTIFY` reader: 183 lines | a stream per workflow, a pull consumer, purge-aware reads: 131 lines plus a Compose file |
| Limits that bind | 2,000 Updates per run (poll Updates count); 50 MB / 51,200 events per run; 2 MB per payload | table growth and `DELETE` churn (partitioning by time later) | streams per workflow; consumers expire after 60 s idle |

Sources: `docs/plans/2026-11-17-event-transport-spike/notes.md#verified` and #d5 (docs read
2026-11-17), the results files above, and the spike code.

## Fencing (R10)

ADR-0007 asks every new attempt write path to take the fence or justify why not.

- **PostgreSQL table:** fenceable as ADR-0007 does it. Event inserts are in the same database as
  `task_attempts`; the publish transaction can take the per-task advisory lock and check that no
  newer attempt exists.
- **Workflow Streams:** not in one transaction with the attempt rows (Temporal history vs the
  application database). The hosting Workflow can refuse batches from an attempt older than the
  newest it has seen, which orders them but does not consult the fence. Justification needed:
  events are for observation, and readers use `attempt_id` and `reset` events.
- **NATS JetStream:** like Streams; no transaction with the attempt rows.

## Owner attention

D2 selects Workflow Streams. Before accepting the ADR, weigh what that costs against the table,
which also passed everything:

- **Cost grows with observers.** Every tailer adds history and Updates to the run, so a busy agent
  with 10 watchers would roll over every ~36 s; Temporal used ~20x the table's CPU at 3 tailers.
- **A preview API** with a private import, and 314 lines of workaround code (dedup, expiry,
  cancellation), against 183 lines for the table.
- **Weaker fencing** than ADR-0007 gives the table.
- **For Streams:** the plan's §4.4 preference, no new storage, and Temporal-native reads that
  follow roll-over.

The owner chose the table; ADR-0009 (proposed) records it with these numbers.

# Event-transport spike: results and recommendation

- Plan: [docs/plans/2026-11-17-event-transport-spike](../plans/2026-11-17-event-transport-spike/plan.md) (issue #76).
- Code: `spikes/event-transport/`. Comparison runs at commit `c1fda62` (clean tree; Streams and the
  table); open-loop table runs at `5854ca2` (clean tree, a stack reset before each run). Results in
  `spikes/event-transport/results/`.
- Versions: ParadeDB 0.26.6 (PostgreSQL 16) via `asyncpg` 0.32.0; Temporal server 1.32.2 with
  `temporalio` 1.36.0 (Workflow Streams, Public Preview); nats-server 2.15.3 and `nats-py` 2.17.0.
- Date: 2026-11-18. Figures are median (range) over 3 runs unless stated.

## Decision

D2 (following design §4.4): Streams wins if it passes R1-R7 and R11; otherwise the table; NATS
only if both fail.

Workflow Streams and the PostgreSQL table both passed every must-pass requirement in all 3 runs,
so D2 selects Streams. NATS passed the correctness suite (its load runs were not needed).

**Owner decision (2026-11-18): the PostgreSQL table.** The measurements below favour it on
everything D2 did not weigh: cost under load, limits, API maturity, code size and fencing (see
[Weighing the outcome](#weighing-the-outcome)). This departs deliberately from §4.4's preference
and is recorded in ADR-0009 (proposed) and the decision log. The Streams and NATS implementations
were then deleted from the spike (D6); they remain in git history at `1bfac67`.

## Requirements per option

| Requirement | Workflow Streams | PostgreSQL table | NATS JetStream (probe) |
| --- | --- | --- | --- |
| R1 Readers resume after their offset | pass (3/3) | pass (3/3; open-loop 3/3) | pass |
| R2 An expired offset is reported | pass (3/3) | pass (3/3; 3/3) | pass |
| R3 A re-sent batch is stored once | pass (3/3) | pass (3/3; 3/3) | pass |
| R4 Offsets survive roll-over | pass (3/3) | n/a | n/a |
| R5 History stays bounded | pass (3/3): per load, the most events in a run 3,519 (3,519-3,531) and the most bytes 4.50 MB (decimal; bounds 5,120 events and 5 MiB) | n/a | not measured |
| R6 p95 publish-to-display ≤ 1 s | pass (3/3): 199 (199-200) ms | pass (3/3): 187 (187-188) ms; open-loop 204 (204-204) ms | not measured |
| R7 The recorded turn replays exactly | pass (3/3) | pass (3/3; 3/3) | pass |
| R8 Results are reproducible | every pass/fail matches across 3 runs | same, in both sets | single suite run at `69c95c4`, before the cancel check (`check_r1_cancel`) existed |
| R9 Production stays unchanged | holds (the diff outside `spikes/` and `docs/` is empty) | | |
| R10 Stale attempts assessed | see [Fencing](#fencing-r10) | | |
| R11 Carried state < 50% of payload limit | pass (3/3): 298 KB at 5 min, still growing (see [R11](#r11-carried-state)) | n/a | n/a |

Sources: `results/run{1,2,3}/suite-*.json`, `results/load-{streams,table}-run{1,2,3}.json` (at
`c1fda62`); `results/open{1,2,3}/suite-table.json`, `results/load-table-open{1,2,3}.json` (at
`5854ca2`); `results/suite-nats.json` (at `69c95c4`).

## Measurements

Synthetic load: 4 agents, 50 token events/s each plus a tool pair every 10 s, 5 min, 3 tailers per
agent (one stopped and resumed every 60 s).

| Metric | Workflow Streams (`c1fda62`) | Table (`c1fda62`) | Table, open-loop (`5854ca2`) |
| --- | --- | --- | --- |
| Events published (open-loop offered load: 60,232; the closed-loop rate depended on publish time) | 54,897 (54,889-54,956) | 58,002 (57,811-58,059) | 60,232 (all runs) |
| Publish time p50 | 13.4 (13.1-13.7) ms | 4.3 (4.3-4.4) ms | 4.3 (4.2-4.3) ms |
| Publish time p95 | 23.8 (18.4-26.9) ms | 5.5 (5.4-6.1) ms | 5.7 (5.7-5.8) ms |
| Latency p50 | 113 (113-114) ms | 92 (92-104) ms | 110 (109-110) ms |
| Latency p95 | 199 (199-200) ms | 187 (187-188) ms | 204 (204-204) ms |
| Latency p99 | 326 (326-372) ms | 189 (188-190) ms | 214 (213-214) ms |
| Latency max | 1,225 (1,218-1,227) ms | 222 (218-227) ms | 224 (223-227) ms |
| Tailers complete, expiries seen | all complete, none | all complete, none | all complete, none |
| Hosting runs per agent in 5 min | 8 (a roll-over every ~40 s) | n/a | n/a |
| Completed hosting runs (84; each chain's last, partial run left out) | 3,232-3,531 events, 4.44-4.50 MB, 757-827 Updates, 191-207 batches | n/a | n/a |
| Temporal CPU, median of run medians (range) | 32.4% (32.1-32.6%) | 1.4% (1.4-1.6%) | 1.3% (1.2-1.8%) |
| Temporal CPU, peak (range over runs) | 185% (39-204%) | 3% (3-15%) | 13% (13-21%) |
| PostgreSQL CPU, median (range) | 12.8% (12.1-13.1%), Temporal's persistence | 4.0% (3.2-7.1%) | 3.3% (3.2-3.3%) |

Caveats about the `c1fda62` comparison:
- **Closed-loop load (impl review F61).** The original generator waited for each publish, so
  Streams' slower publishes gave it ~5% less load than the table, and time blocked in a publish was
  not counted as latency. The bias likely favours Streams; Streams' R6 at equal offered load was not
  measured, so D2's selection of Streams rests on these closed-loop runs. The open-loop runner
  (`5854ca2`) produces events on a fixed schedule and stamps each when due; the table keeps every
  requirement at the full offered load. Its p95 is higher (204 ms); the cause was not isolated
  (blocked time now counts, and the runner's 10 ms flush poll adds delay). No latency comparison
  between the options at equal load was made.
- **No reset between runs (F62).** Earlier Streams hosting runs stayed Running during later table
  runs, and table rows accumulated; the table's database CPU drifted from 3.2% to 7.1% across runs.
  The open-loop runs reset the stack before each run, and their figures are steady.
- **Ratios.** Temporal CPU was ~20-23x the table's (32.1-32.6% against 1.4-1.6%); PostgreSQL CPU
  was 3.2x (1.7-4.1x).
- **History bytes** are the sum of each fetched event's encoded size, close to but not the same as
  Temporal's own history-size accounting. The agents' own `SpikeLoadAgent` runs (one Activity
  each) were not measured.

The 200 ms publish batch accounts for most of the latency of every option.

### Streams growth and roll-over (informational)

With roll-over off (`load.py streams --no-roll`), every hosting run stalled after ~1.85 min at
Temporal's limit of **2,000 Updates per run**: ~500 publish and ~1,500 poll Updates (3 tailers),
~8,500 events and ~10.2 MB of history, ~4,600 events and ~5.5 MB per minute. That run never wrote
its own results file: it was stopped, and its hosting runs' histories were read by a probe
(`results/streams-growth-norollover.provenance.json`, which keeps the 4 growth runs and names the
probe's commit and command; the raw `streams-growth-norollover.json` also lists 12 runs left over
from the judged loads, which are not growth data). Per-tailer growth was not measured directly; it
follows from the Update counts: each tailer adds one poll Update per batch.

What that means for roll-over, as measured: with 3 tailers each batch costs 4 Updates, so the cap
arrives at ~500 batches and D5's 2,000-batch trigger can never fire first. In the judged runs the
84 completed hosting runs rolled over after 191-207 batches (~40 s), at 4.44-4.50 MB and 757-827
Updates, when Temporal suggested Continue-As-New, apparently on history size. How Streams behaves at other event
sizes or tailer counts was not measured. The risk: more tailers add bytes and Updates per batch, so
roll-over comes sooner; small batches may reach the 2,000-Update cap before the size suggestion,
and a run then stalls as the roll-over-off run did, unless Temporal also suggests Continue-As-New
on Update count.

### R11 carried state

The carried state is the stream log kept at roll-over (the last 500 events) plus the batch-ID set
for the 600 s re-send horizon. In the 5-minute runs it grew ~8 KB per roll-over (248 KB to 298 KB),
because the batch-ID set had not reached its full horizon. Extrapolated to 600 s it would be
~360 KB, still under R11's 1 MB bound; that steady state was not measured.

## Findings that apply whichever option wins

- **Neither third-party option reports expiry itself.** Streams' `subscribe()` silently restarts
  at offset 0 on a truncated offset (pinned source); a JetStream consumer starting below the first
  retained sequence silently delivers from it (probe, in git history at `1bfac67`). The spike meets
  R2 for every option with two checks: before reading, the reader compares its offset with the
  transport's retained base (`expiry_for`); during a read, `transport.guarded()` reports an offset
  that jumps as `Expired` and raises on a repeat. Phase 2 needs both.
- **Token text has no place yet.** `AgentEvent` payloads must hold no model text
  (`common/schemas/events.py`), but streamed token deltas are model text. Phase 2 must decide where
  token text lives (a blob per turn, or an exception for token events).
- **A removal through the end of the log during a read** yields no expiry until a later event
  arrives (impl review F55), the same for every option; a read that starts afterwards reports it
  through the retained-base check.
- **Batch IDs must name the attempt.** A retried publisher that reuses batch IDs has its new events
  dropped as re-sends; the runner now uses `<workflow>:<attempt>:<n>`.

## Operating cost (task 2.1)

| Heading | Workflow Streams | PostgreSQL table | NATS JetStream |
| --- | --- | --- | --- |
| New components | none (Temporal) | none (the application database) | a NATS server; the documented Kubernetes deployment is a 3-replica StatefulSet (Helm chart) |
| API maturity | Public Preview / experimental; the spike imports a private decoder | stable | stable |
| Backups | events live in Temporal history, kept for the namespace's retention (`TEMPORAL_RETENTION`) | in the application database's backups (Phase 3A) | its own volume |
| Authentication and scoping | any Temporal client can query or update any Workflow: scoping must be in the gateway | the app role; queries scope by workflow (no tenant column yet; tenant scoping is for Phase 2 to add) | NATS accounts and per-subject permissions |
| Upgrades | the preview API may change between SDK releases | none new | NATS server releases |
| Kubernetes path | Temporal's (already planned) | the application database's | a new StatefulSet |
| Load on shared services | Temporal CPU ~20-23x the table's; Temporal's database 3.2x (1.7-4.1x) | small | its own |
| Spike code (whole files, at `1bfac67`) | 314 lines: the hosting Workflow (115), a custom publish Update with batch-ID dedup, a `retained_base` Query, Update-only reads mapping `TruncatedOffset`, a cancellation fix | 183 lines: counter row, batch table, `LISTEN/NOTIFY` reader | 131 lines plus a Compose file: a stream per workflow, a pull consumer, purge-aware reads |
| Limits that bind | 2,000 Updates per run (poll Updates count); 50 MB / 51,200 events per run; 2 MB per payload; the spike's 2 h execution timeout covers the whole Continue-As-New chain | table growth and `DELETE` churn (partitioning by time later); one connection per follower; one global `NOTIFY` channel wakes every follower | streams per workflow; consumers expire after 60 s idle |

Sources: `docs/plans/2026-11-17-event-transport-spike/notes.md#verified` and #d5 (docs read
2026-11-17), the results files above, and the spike code.

## Fencing (R10)

ADR-0007 asks every new attempt write path to take the fence or justify why not.

- **PostgreSQL table:** fenceable as ADR-0007 does it. Event inserts are in the same database as
  `task_attempts`; the publish transaction can take the per-task advisory lock and check that no
  newer attempt exists. Phase 2 sets the lock order against the counter row and measures the cost
  (not measured here).
- **Workflow Streams:** not in one transaction with the attempt rows (Temporal history against the
  application database). The hosting Workflow could be changed to refuse batches from an attempt
  older than the newest it has seen (the spike's Workflow deduplicates by batch ID only), which
  would order them but not consult the fence. Justification needed:
  events are for observation, and readers use `attempt_id` and `reset` events.
- **NATS JetStream:** like Streams; no transaction with the attempt rows.

## Weighing the outcome

D2 selected Workflow Streams; the table also passed everything. What the owner weighed:

- **Cost grows with observers under Streams.** Every tailer adds history and Updates to the run;
  Temporal used ~20-23x the table's CPU at 3 tailers, and roll-over came every ~40 s.
- **A preview API** with a private import, and 314 lines of spike code (dedup, expiry,
  cancellation), against 183 lines for the table.
- **Weaker fencing** than ADR-0007 gives the table.
- **For Streams:** the plan's §4.4 preference, no new storage, and Temporal-native reads that
  follow roll-over.

The owner chose the table; ADR-0009 (proposed) records it with these numbers.

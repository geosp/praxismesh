<!-- Verbatim subagent report (impl-review phase 02 round 1, scope, 5371368..4d6c4ca, frozen at 4d6c4ca; resumed once after a usage-limit stop); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Event-transport spike, phase 02, impl review round 1: scope lens

Diff: `5371368d..4d6c4ca`. Measurements read from the committed results (taken at `c1fda62`); the Streams code was read at `1bfac67`.

## Major

### M1. The report and notes stretch Streams' roll-over behaviour past the load that was measured, and treat the 2,000-Update cap as if it were the roll-over interval
- **Location:** `docs/spikes/event-transport.md`, "Streams growth without roll-over" ("a run holds at most 2,000 / (1 + tailers) batches: at this load, roll-over every ~100 s with 3 tailers and every ~36 s with 10"). The same claim is in Owner attention ("10 watchers would roll over every ~36 s") and in `notes.md` (Checked in phase 02, F47).
- **IDs:** R5, R8 (task 2.2: "every number in the report traces to a committed results file"), D5.
- **Scope mismatch:** D5's roll-over trigger "every 2,000 batches" (`streams_workflow.py@1bfac67`, `ROLL_EVERY_BATCHES = 2000`, `batches_this_run`) can never fire before the per-run cap of 2,000 Updates. With 3 tailers each batch costs 4 Updates, so the cap arrives at 500 batches. Bounded history therefore depends only on `is_continue_as_new_suggested()`. In the judged runs that suggestion came from history size: every run closed at about 4.45-4.50 MB and about 775-827 Updates, after about 194-207 batches (`results/load-streams-run*.json`, `history.runs`). That holds for one event size and one tailer count only.
- **Failure scenario:**
  - 3 tailers: measured roll-over was every ~40 s (the report's own Measurements table), not ~100 s. The ~100 s figure is the time to the stall point, not the roll-over interval.
  - 10 tailers: each poll result also lands in history, so bytes per batch rise about 11/4. The size suggestion would then come after roughly 75 batches (~15 s), not ~36 s.
  - Small batches (an agent at 5 events/s gives 1 event per 200 ms batch): 2,000 Updates of a few hundred bytes stay well under the 4 MB size suggestion. The run reaches the cap and stalls the way the roll-over-off run did ("every hosting run stalled after ~1.85 min"), and R5 and R6 fail. Unless the server also suggests Continue-As-New on Update count, which nothing in the spike verifies.
  - Neither the ~36 s nor the ~100 s figure traces to a results file.
- **Impact:** the D2 outcome does not change (the owner chose the table), but the record that ADR-0009 and the decision log cite misstates how Streams behaves outside the measured load.
- **Test that would expose it:** at `1bfac67`, `load.py streams --tailers 10`, plus a run with a low-rate agent (about 1 event per batch). Compare roll-over spacing and the per-run Update count with the 2,000 cap.

## Nits

- `results/load-streams-run*.json` `max_carried_bytes` and the report's "298 KB (the last 500 events)" (R11): carried state was measured before the batch-ID set reached steady state, and the report misdescribes what it holds.
  - The 5-minute load is shorter than the 600 s horizon over which the carried batch-ID set grows, and carried state was still growing ~8 KB per roll-over at the end (248,476 → 297,764 B).
  - Extrapolated to 600 s (~2,700 entries × ~42 B) it reaches ~356 KB, still under 1 MiB, so the result holds. But the batch-ID set (~50 KB at the end) is part of the 298 KB, so "the last 500 events" is not all it holds.
- `load.py:97-123` (R6, D3): the load is closed-loop.
  - Publishing is awaited inside the generator loop, so a slower transport receives less load: Streams 54,889-54,956 events against table 57,811-58,059, against the ~60,000 D3 implies.
  - Events that would have been generated during a roll-over stall are never created (coordinated omission), so Streams' tail latency (max ~1.2 s) is understated.
  - R6 still passes with a wide margin, and the bias only strengthens the table choice.
- `docs/spikes/event-transport.md` Measurements (R8: "measurements are reported as median and range"): container CPU is reported for run 1 only, and most rows give a median without a range. The per-run medians are steady (Temporal 32.1-32.6% against 1.4-1.6%), but table DB CPU varies 3.2-7.1% and Temporal max varies 39-204%.
- `results/streams-growth-norollover.json` (task 1.2 verify: "each results file names its commit and command"):
  - The file has no commit or command field.
  - `probes/streams_update_limit.py@1bfac67` selects every Running `spike76-stream-load-*` run, so 12 of its 16 entries are leftover last runs from the judged loads (`minutes_to_last_event` 0.01-0.02, `mb_per_min` up to 20.93), not growth data. The report uses the right 4 entries.
- `measure.sh@c1fda62` and plan "Rollout & rollback" ("After each run, `make reset`"): there is no reset between runs.
  - Streams hosting runs from earlier loads stay Running (2 h `RUN_TIMEOUT`) through later table loads.
  - Table rows build up across runs: table run 3 starts on about 116k rows from runs 1-2 plus the suite.
  - Results are consistent across runs, so the impact looks small.
- `measure.sh@c1fda62` last line (R8): the `--no-roll` load cannot finish by itself once runs hit the Update cap, since no growth `load-*.json` was written and the data came from a separate probe. So the committed command does not reproduce the informational result. I could not verify whether it hangs or fails.
- `streams.py@1bfac67` `RUN_TIMEOUT` (`execution_timeout`) and `notes.md` ("the report lists them with the others"): a Workflow execution timeout covers the whole Continue-As-New chain, so a Streams log would end 2 h after its first run, not "per hosting run". The report's Limits row lists neither this timeout nor the fixed task queue.
- `load.py:84-89,117` (pair: Activity retry with per-attempt batch IDs): batch IDs are `f"{wf}-{out.batches}"` and restart at 0 if the publishing Activity is retried (30 s heartbeat timeout; Streams' `_retry` can block for 20 s or more). A retried attempt's new events would be dropped as re-sends within the 600 s horizon. This did not happen here (published equals the sum of `latest` in every run), but a Phase 2 port needs the attempt in the batch ID.
- `table.py` `CHANNEL` and `_read` (ADR-0009 consequences, report "Load on shared services: small"):
  - There is one global `NOTIFY` channel, filtered client-side, so every following reader wakes for every workflow's batch: cost grows with batches × all tailers.
  - Each reader holds a pool connection, and the pool maximum is 20, so 17 or more tailers in one process would block publishers on `acquire`.
  - Both were measured only at 12 tailers. The ADR records the connection cost but not the broadcast.
- `load.py:264-277` (R5): only Streams hosting runs are judged. The publishing `SpikeLoadAgent` Workflow runs (present for every option) are never measured, though R5 says "no Workflow run". They are trivially small (one Activity), so this is acceptable.
- `notes.md` D5 row and `tests/conftest.py` `horizon_s` (R3): the suite tests dedup with a 60 s horizon, not the 600 s re-send horizon. This is documented and design-reviewed, and it is the same for every option.
- `load.py@4d6c4ca` (D6 cleanup): the `option.hosted` branches for R5 and R11 and the NATS container name in `wanted` are now dead code. The Streams measurement can only be reproduced at `c1fda62`, which the report states.

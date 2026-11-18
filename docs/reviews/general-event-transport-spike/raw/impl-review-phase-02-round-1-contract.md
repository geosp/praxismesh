<!-- Verbatim subagent report (impl-review phase 02 round 1, contract, 5371368..4d6c4ca, frozen at 4d6c4ca); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Contract review: event-transport spike, phase 02 (5371368..4d6c4ca)

Lens: contract. Delivered: R5, R6, R8, R10, R11; Decisions D2-D6; tasks 1.1-3.1.

**Verdict: Changes requested.** There are 5 Majors and 11 Nits. None of them changes the D2 outcome or the owner's choice. Every Major is about the evidence (traceability, reproducibility, fairness); none is about the code that remains.

## Promise map

| Promise | Enforced at | Evidence / test |
| --- | --- | --- |
| R5 every hosting run < 5,120 events / 5 MB | load.py@c1fda62 `stream_runs` + `judged["R5"]` (load.py:270-275 at 4d6c4ca) | results/load-streams-run{1,2,3}.json: 96 runs, max 3,531 events / 4,495,354 B, all "pass". No unit test of the judging logic. |
| R11 carried state < 1 MB at each Continue-As-New | load.py@c1fda62 `carried_input_bytes` + `judged["R11"]` | Same files: max 297,765 B. Not observable at steady state (F5). |
| R6 p95 <= 1 s in each of 3 runs | load.py:162 (latency per shown event), :276 (p95 and `complete`) | Streams 198.9/199.6/199.x ms, table 187.8/186.8/187.1 ms; all tailers complete, no errors. |
| R8 same pass/fail in 3 runs; median and range | measure.sh@c1fda62; results files name commit and command | Suite and load pass/fail match across 3 runs for table and Streams. Median-and-range is not met (F1); the growth file is not traceable (F2). |
| R10 fencing statement per option | docs/spikes/event-transport.md "Fencing (R10)" | Present for all three options. |
| D2 rule | report "Decision" | Applied correctly (Streams selected), then overridden by the owner. |
| D2 override recorded | plan.md Decision log; decision-log.md row 2026-11-18; ADR-0009 "Decision outcome"; report "Decision" | Consistent across all four. One stale paragraph remains (N3). |
| D5 parameters | load.py:47-54 (200 ms / 64-event batches, 50/s, one Activity per agent) | Same constants for both options. Load generation is closed-loop (F3). |
| D6 delete the losers | 4d6c4ca removes streams*.py, jetstream.py, nats.compose.yml, probes, and nats-py from pyproject/uv.lock | Done. |
| Plan Rollout: reset after each run; Risks: one option at a time | measure.sh@c1fda62 | Not done between runs (F4). |
| Task 1.1: growth per minute per agent and per tailer | none in load.py | Missing (F2). |

## Majors

**F1 · Major · R8, task 2.2 · docs/spikes/event-transport.md, Measurements table and Operating-cost "Load on shared services"**
- **Problem:** R8 says "measurements are reported as median and range". The Measurements table gives medians only. The container-CPU rows are labelled "(median / max, run 1)", so they come from one run while the table heading says "median of 3 runs". The resulting "Temporal's database 4x" is the most favourable of the 3 runs.
- **Scenario:** recompute from the committed files. DB-container median CPU is Streams 13.06 / 12.79 / 12.11 % against table 3.18 / 3.95 / 7.10 %. That gives ratios of 4.1x, 3.2x and 1.7x: a median of 3.2x and a range of 1.7-4.1x, not "4x". The Temporal-CPU ratios are 20.6x, 22.8x and 22.7x, so "~20x" holds, but its range is missing.
- **Evidence:** report lines "Temporal container CPU (median / max, run 1)" and "Temporal's database 4x"; the `containers` arrays in results/load-*-run{1,2,3}.json.
- **Test that exposes it:** a script that recomputes every report figure from the results files as median [min-max] across the 3 runs and diffs it against the report.

**F2 · Major · R8, task 1.1, task 1.2 Verify · results/streams-growth-norollover.json; probes/streams_update_limit.py (added in 36ebee0, deleted in 4d6c4ca)**
- **The growth file is not traceable.** Task 1.2's Verify is "each results file names its commit and command". This file is a bare JSON list with no commit, command or dirty flag. The probe that wrote it was added in 36ebee0, after the measurement commit c1fda62 that the report cites, so the growth figures ("~1.85 min", "~8,500 events, ~10.2 MB", "~4,600 events and ~5.5 MB per minute") cannot be reproduced from c1fda62.
- **The growth run's own results are missing.** measure.sh@c1fda62 ends with `uv run python load.py streams --no-roll --label growth`, but no `load-streams-growth.json` was committed. The report does not say whether that run completed, failed or hung.
- **The file mixes in other runs.** It holds 12 extra entries from the judged runs' final, still-running hosting runs (load-fb809c98, -3c994f04, -5e40dd37), for example `minutes_to_last_event 0.02, mb_per_min 20.93`. They are present because the probe's query is `ExecutionStatus = 'Running'` on prefix `spike76-stream-load-`. Anyone reading the file without the report would take 20.9 MB/min as a growth rate.
- **Task 1.1's metric was never built.** Task 1.1 asks the load runner for "growth per minute per agent and per tailer". load.py never computes it. The per-tailer figure was inferred afterwards from poll-Update counts.
- **Test that exposes it:** check every file under results/ for `commit` and `command` keys; rerun measure.sh at c1fda62 and look for the growth output.

**F3 · Major · D5, D3, the plan's core fairness risk · load.py:97-128**
- **Problem:** the publisher is closed-loop. It `await`s `transport.publish` inline and then sleeps 1/50 s. Events are created (and stamped with `payload["t"]`, line 104) only after the previous publish returns.
- **Scenario:** Streams' publish p50/p95 is 13.7/26.9 ms against the table's 4.3/5.5 ms. So in the same 300 s Streams received about 5% less load: 54,889-54,956 events against 57,811-58,059, about 45.7 against 48.3 events/s per agent. Time spent blocked in publish is never counted as latency (coordinated omission).
- **Effect:** Streams' p95 (199 ms) and its CPU are measured at a lower offered load than the table's. The report states "4 agents, ~50 token events/s each" for both and does not disclose this. The direction favours the losing option, so the decision does not flip. But "p95 187 against 199 ms" in ADR-0009 and the decision log understates the gap, and the comparison is not at equal load.
- **Evidence:** the `published` and `publish_ms` fields in the six load files.
- **Test that exposes it:** an open-loop generator on a fixed schedule that stamps `t` at the scheduled time. Assert that published counts differ by less than 1% between options.

**F4 · Major · D4, plan Rollout ("After each run, `make reset`"), Risks ("one option at a time") · measure.sh@c1fda62**
- **Problem:** measure.sh interleaves table and Streams on the same Temporal and PostgreSQL stack, with no reset between runs (suite, table load, Streams load, then repeat).
- **Evidence:** the growth file shows each judged run's final Streams hosting run still `Running` afterwards. Table runs 2 and 3 therefore ran on a stack holding prior Streams histories and open Workflows.
- **Effect:** the table's DB-container median CPU climbs 3.18 → 3.95 → 7.10 % across runs. This is the same drift that makes F1's "4x" fragile. The run-1 comparison happens to be the cleanest, because table run 1 preceded Streams run 1.
- **Test that exposes it:** add `make reset` between runs in measure.sh and compare the per-run medians.

**F5 · Major (observability) · R11 · load.py@c1fda62 carried-state measurement; report "Carried state per roll-over 298 KB"**
- **Problem:** the 5-minute load is shorter than the 600 s re-send horizon. The batch-ID set carried across Continue-As-New therefore never reaches steady state.
- **Evidence:** carried state grows every roll-over in every run, 248 → 256 → 264 → 272 → 280 → 290 → 298 KB (about 8 KB per ~194 batches).
- **Effect:** 298 KB is not the maximum R11 asks about ("when a run continues as new"). Extrapolating to a full horizon (about 3,000 batch IDs) gives roughly 370 KB. That is still under 1 MB, so the pass very likely holds, but the setup does not observe it and the report presents 298 KB as the figure.
- **Setup that would observe it:** a load run of at least 600 s plus one roll-over interval, or a carried-state measurement after the horizon has filled.

## Nits

- **N1** · report R-table "NATS R1 pass" · NATS's suite result (results/suite-nats.json @69c95c4) predates `check_r1_cancel` (added in 5ae0731), the check that caught the Streams cancellation bug. Commit 5ae0731's message says it "passes for all four", but no committed result shows it for NATS. Nit because NATS is a probe under D2.
- **N2** · report Operating-cost NATS and Streams cells · "3 replicas (Helm chart StatefulSet)", "incremental stream backups only planned (2.16)", "two maintained at a time" and Streams "kept per namespace retention" are not in notes.md#verified, the cited source. Task 2.1 asks for "with sources" and task 2.2 for "every number traces". Nit: low decision weight.
- **N3** · report "Owner attention" · it still opens "D2 selects Workflow Streams. Before accepting the ADR, weigh..." as if the ADR were for Streams, and only the last line says the owner chose the table. Pre-decision text left in a post-decision document.
- **N4** · report R5 row and Measurements · "4.50 MB (bound 5 MB)" mixes units. 4,495,354 B is 4.50 MB decimal (4.29 MiB), while load.py:53 sets the bound as 0.1 × 50 MiB = 5,242,880 B. The verdict is unaffected.
- **N5** · R5 observability · load.py@c1fda62 sums the `ByteSize()` of fetched history events. That is close to, but not identical with, the server's own history-size accounting, which enforces the limit. The universal "no Workflow run" also covers the `SpikeLoadAgent` runs, which were never measured (they are trivially small). Nit.
- **N6** · load.py:260-279 at 4d6c4ca · `runs = {}`, so `max_events`, `max_bytes` and `max_carried` are None. For any `hosted` option, `None < ...` would raise TypeError. No hosted option remains, so it is dead code. But ADR-0009's Confirmation points Phase 2 at this runner.
- **N7** · load.py:229 · the `pmspike76-nats-nats-1` container name survives the NATS deletion. Harmless.
- **N8** · report "Extra code beyond D5" · "314 / 183 / 131 lines" are whole-file line counts at 1bfac67 (streams.py 199 + streams_workflow.py 115; table.py 183; jetstream.py 131), including docstrings and the measurement-only no-roll toggle. They are not "extra beyond D5". The method is the same for all options, so it is fair, but the label is wrong.
- **N9** · probes/README.md at 4d6c4ca · the `streams_update_limit.py` row is appended after the prose paragraph, detached from the table header, so it does not render as part of the table. The README also lists the probe, but the probe is not in the tree.
- **N10** · decision-log.md 2026-11-18 row · it gives "verified versions" for Temporal client and NATS but not for the winner's server side (PostgreSQL/ParadeDB version; the Temporal server is only "from infra/docker-compose.yml"). D6 asks for the verified versions.
- **N11** · load.py · the R5/R6/R11 judging and `percentile()` have no unit test. A wrong threshold or a wrong `complete` check would pass silently. The phase had no requirement to add one.

## Checks that passed

- Every pass/fail in the 6 suite files and 6 load files matches across runs. All judged files carry commit c1fda62, `dirty: false` and their command.
- The report's latency figures (113/199/326 and 92/187/189 ms medians; 199-200 and 187-188 ms p95 ranges), event counts (54,900-58,100), runs per agent (8), largest run (~3,520 events, ~825 Updates), carried state (298 KB) and Temporal-CPU ~20x trace to the results files.
- The growth figures match the e47794c1 entries in the growth file. The derived "2,000 / (1 + tailers)" arithmetic is correct.
- The D2 override is recorded consistently in plan.md's Decision log, decision-log.md, ADR-0009 (status proposed, listed in docs/adr/README.md) and the report.
- R10: all three options have a fencing statement with a mechanism or a justification.
- D6: the Streams and NATS code, their probes, nats.compose.yml and nats-py (pyproject and uv.lock) are deleted. The remaining code references only the memory and table options. The diff touches only `spikes/` and `docs/` (R9).

<!-- Verbatim subagent report (impl-review phase 02 round 2, targeted contract, 4d6c4ca..02018c5, frozen at 02018c5); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Impl review, event-transport spike phase 02, round 2 (contract lens)

Diff `4d6c4ca..02018c5`, files read at `02018c5`.

**Verdict: changes requested.** Three Major findings, all in documents. Two are new numbers or claims the round-1 fixes introduced. One reopens F59 in ADR-0009. The code fixes (F61, F64, F71, F75, F76, F78) are in place and have tests. Most report figures trace to committed results.

## What I checked

- **Report against results.** I recomputed every figure in docs/spikes/event-transport.md from the committed results files at 02018c5:
  - `results/load-{streams,table}-run{1,2,3}.json` (commit c1fda62, dirty=false)
  - `results/load-table-open{1,2,3}.json` and `results/open{1,2,3}/suite-table.json` (commit 5854ca2, dirty=false)
  - `results/streams-growth-norollover{,.provenance}.json`

  These figures all match: R5 (3,519 (3,519-3,531) events, 4.50 MB), R6 for Streams, the table and the open-loop table, events published, latency p50/p95/p99/max, Temporal and PostgreSQL CPU medians and peaks with ranges, the ratios (20-23x and 3.2x (1.7-4.1x)), the R11 carried state (248 to 298 KB, ~8 KB per roll-over), the growth figures and the versions (uv.lock; infra/docker-compose.yml:14,51).
- **Code since 5854ca2.** It is unchanged, so the open-loop results come from the code under review.
- **R9.** `git diff --stat 5371368..02018c5 -- . ':!spikes' ':!docs'` is empty, so R9 holds.
- **Decision log consistency.** The plan's Decision log line, the report's Decision section, ADR-0009 and docs/roadmap/decision-log.md tell the same story: D2 selected Streams, and the owner chose the table.

## Findings

### M1 · Major · the roll-over ranges added by the F65 fix do not match the results

- **Location:**
  - docs/spikes/event-transport.md:94-95 ("every hosting run rolled over after ~194-207 batches (~40 s), at ~4.45-4.50 MB and ~775-827 Updates")
  - docs/spikes/event-transport.md:60 ("Largest run | 3,519 events, 4.50 MB, ~775-827 Updates")
  - notes.md, the same sentence in the F47 bullet
- **Requirement:** R8; task 2.2 ("Verify: every number in the report traces to a committed results file"); reopens nothing; new with the F65 fix.
- **Evidence:** I took every completed hosting run in `load-streams-run{1,2,3}.json` `history.runs`, leaving out each chain's last, partial run (84 runs). They span:
  - publish_batch 191-207
  - total Updates 757-827
  - bytes 4,442,795-4,495,354

  In every load run, at least four runs stopped at 191 batches and 757-764 Updates. The runs with the most events in each load had 824-827 Updates, not "~775-827".
- **Failure scenario:** A Phase 2 reader sizes roll-over from the report's lower bound of 194 batches and 775 Updates. The measured minimum is 191 and 757. The "every hosting run" claim is false, and the largest run's Update range is wrong. The real impact is small, but this is exactly the trace that task 2.2 requires.
- **Test that exposes it:** a check that recomputes min and max of `publish_batch`, total Updates and bytes over `history.runs[*][:-1]` in the three files and compares them with the report's ranges. It gives 191 / 757 / 4.44 MB.

### M2 · Major · ADR-0009 still cites run-1 CPU figures as "median" (reopens F59)

- **Location:** docs/adr/0009-use-a-postgresql-event-table-for-agent-events.md:42, "Temporal used ~20x less CPU (1.6% median against 33% under the spike's load)".
- **Requirement:** reopens F59 (R8: "measurements are reported as median and range"); D6.
- **Evidence:**
  - The table's 1.6% is run 1's Temporal median (1.58 in load-table-run1.json). Its 3-run medians are 1.58, 1.41 and 1.43, so the median is 1.4%.
  - Streams' 33% is run 1's median (32.635 in load-streams-run1.json). Its 3-run median is 32.4% (32.1-32.6%).
  - The report, as fixed, says "32.4% (32.1-32.6%)" and "1.4% (1.4-1.6%)" (event-transport.md:61).
  - F59 was raised because "container CPU is from run 1 only", and its fix touched only the report.
- **Failure scenario:** The decision record that Phase 2 builds on states single-run figures under a 3-run label, and they disagree with the spike report it links to.
- **Test that exposes it:** compare the ADR's CPU figures with the report's line 61. Or recompute medians of the per-run `containers` medians for `pmspike76-temporal-1` across run1-3.

### M3 · Major · ADR-0009 says the open-loop rerun "confirms" the table's figures, but the rerun's figures differ

- **Location:** docs/adr/0009-use-a-postgresql-event-table-for-agent-events.md:48-50, "p95 latency of 187 ms against 199 ms. ... an open-loop rerun of the table confirms its figures at the full offered load (spike report)."
- **Requirement:** F61's fix (new mismatch); R6, R8.
- **Evidence:**
  - load-table-open{1,2,3}.json: `latency_ms.p95` is 204.0, 204.4 and 203.6; `p50` is 109.6, 109.8 and 109.4.
  - The closed-loop table had p95 187 (187-188) and p50 92 (92-104).
  - The report itself says "Its p95 is higher (204 ms)" (event-transport.md:70).
  - Streams was never rerun open-loop.
- **Failure scenario:**
  - At full offered load, the table's p95 (204 ms) is above Streams' closed-loop 199 ms.
  - The ADR still lists "187 against 199" as a reason the owner weighed, and calls it confirmed.
  - The rerun confirms only that the table passes R6 at the full load. The latency advantage is not established at equal load.
  - A Phase 2 reviewer reading only the ADR would treat a latency advantage as measured, but none was measured.
- **Test that exposes it:** compare the ADR's latency sentence with `latency_ms` in load-table-open*.json.

## Nits

- **event-transport.md:53 (F59):** the publish-time row gives medians without ranges, and the open-loop cell is empty. The committed files have it: p50 4.24-4.26 ms, p95 5.66-5.80 ms. F59 claimed "median (range) ... for every figure".
- **event-transport.md:60:** "3,519 events, 4.50 MB" combines the maximum event count and the maximum byte count, which come from different runs. For example, in run 1 the 3,531-event run has 4.45 MB. It also has no range. The label "Largest run" suggests a single run.
- **event-transport.md:70:** "Its p95 is higher (204 ms) because blocked time now counts" is an unmeasured cause. The table's publish p95 is ~5.7 ms, which cannot explain a +18 ms p50 shift (92 to 110 ms). The 10 ms flush poll or scheduling differences are equally possible.
- **event-transport.md:16-17, 66-68 (D2, R6):** "The bias favours Streams" is an inference. Streams' R6 pass, and so D2's selection, rests only on closed-loop runs; Streams had a 1,225 ms max latency, which open-loop stamping would now count. The report discloses the closed-loop bias, but Streams' R6 at equal offered load was never measured. The owner's override makes this moot for the outcome.
- **tests/test_load.py (F75 partial):** `percentile()` still has no unit test. F75 named both `judge()` and `percentile()`; only `judge()` got a test.
- **tests/test_suite.py:110 (F78 partial):** the suite results are still written with `write_text` in place, not atomically. The resolution says "results are written atomically", but only load.py:392-394 changed.
- **tests/test_load.py:89 (F64):** the orphaned-agent test is skipped unless `SPIKE_STACK` is set, so CI never runs it. On the old code it would hit `wait_for`'s 60 s timeout rather than list orphans, so the resolution's "found 8 orphaned agents" is not reproducible from committed artifacts.
- **measure.sh:12-15 (F62, F80, plan Rollout):**
  - The stack is reset before each run, not after, so the last run's data is left in place. The plan says "After each run, `make reset`".
  - No results file records that a reset happened.
  - Task 3.1's reset and the removal of the NATS Compose project have no committed evidence.
- **results/streams-growth-norollover.provenance.json (F60):** the file is written by hand. It says the commit is 36ebee0, which is the commit that also added the probe's output, so the probe ran from an uncommitted tree. The raw file still names no commit.
- **load.py:13-16:** the docstring still says it measures Streams hosting runs and "NATS containers". F71 removed the NATS container name.
- **ADR-0009:71:** "17 or more followers in one process would block publishers" assumes 4 concurrent publishers sharing the pool of 20 (table.py:61). This is not measured or stated.
- **probes/README.md:11:** the row says "Each run hit ..." and cites `streams-growth-norollover.json`, which also holds 12 runs that are not growth data. It does not point to the provenance file.

## Earlier findings

These fixes are in place and I am not raising them again:

- **Fixed and verified:**
  - **F60:** the provenance file is present, apart from the Nit above.
  - **F61, code:** the open-loop producer is at load.py:101-153. test_a_slow_transport_still_gets_the_offered_rate and test_events_are_stamped_on_their_schedule would both fail on the old closed-loop runner, which waits on each 100 ms publish and stamps events at creation.
  - **F62:** measure.sh resets before each run.
  - **F63:** the report covers the carried state at event-transport.md:104-107.
  - **F64, code:** RetryPolicy(maximum_attempts=1), execution_timeout and terminate in `finally`.
  - **F66, F67, F68, F69, F72, F73, F74, F81, F82.**
  - **F71:** `judge()` treats a missing value as a fail, and the test covers the None cases.
  - **F76:** batch IDs `<wf>:<attempt>:<n>`; test_batch_ids_name_the_attempt fails on the old `<wf>-<n>`.
- **Partly fixed:** F75 and F78, see the Nits.
- **Reopened:** F59, in ADR-0009 (M2).
- **Accepted and not re-raised:** F70, F77, F79's second part and F80's second part.

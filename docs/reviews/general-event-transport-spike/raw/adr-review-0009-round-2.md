<!-- Verbatim subagent report (adr-review-0009-round-2, branch docs/76-close-event-transport-spike at 6a9f073); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

## Review of ADR-0009 (round 2), branch docs/76-close-event-transport-spike at 6a9f073

I found no Blocker or Major problems, so the ADR can be accepted. There are eight Nits, listed at the end. The review was read-only.

### What I checked

**Figures, against the results files**
- **Temporal CPU.** I recomputed the medians from `containers` in `spikes/event-transport/results/load-{streams,table}-run{1,2,3}.json`.
  - Streams: 32.64, 32.08 and 32.41.
  - Table: 1.58, 1.41 and 1.43.
  - Open-loop table: 1.84, 1.24 and 1.27.
  - So "1.4% against 32.4%" and "~20-23x" are right.
- **p95 latency** (`latency_ms.p95`): 199 ms for Streams, 187 ms for the table, and 204 ms open-loop. All three are right.
- **Load gap.** The `published` counts are 54,897 against 58,002, so "~5% less load" for Streams is right.
- **Line counts.**
  - `event_transport/table.py` is 183 lines.
  - At commit 1bfac67, `streams.py` is 199 lines and `streams_workflow.py` is 115, which adds up to 314.
- **NATS.** `results/suite-nats.json` ran at `69c95c4`, before the cancel check, as the ADR says.

**Mechanisms, against the code**
- The counter row is locked with `FOR UPDATE` (`table.py:76-79`).
- The batch row is written in the same transaction (`table.py:89-94`).
- There is one global `NOTIFY` channel (`table.py:29,104`).
- The reader clears its wake-up before each fetch (`table.py:145`) and polls every 1 s as a fallback (`table.py:31,154-155`).
- The retained-base check is at `table.py:137-142`.
- The offset-jump check and the repeat check are in `transport.py:35-52`.
- The pool allows 20 connections (`table.py:61`), and a follower holds one connection while it follows (`table.py:127`).
- Publishers and tailers share one transport in one process (`load.py:258,262,287`). The ADR's "beyond 16 / at 20" arithmetic is therefore right, and the ADR labels it as derived.
- Batch IDs have the form `<workflow>:<attempt>:<n>` (`load.py:141`).

**Round 1**
- Both Majors from round 1 are resolved.
  - §4.3, §4.4, `PROJECT_PLAN.md:106` and `PROJECT_PLAN.md:222`, and `phase-2.md:9` are all updated.
  - The ADR now has a commitments list and a must-still-decide list.
- The round-1 Nits are addressed.

**ADR quality**
- It records one decision.
- It considers three options and says why Streams and NATS lost.
- It admits plainly that D2 selected Streams and that the owner departed from it.
- Its downsides are real: table growth and `DELETE` churn, one connection per follower, and the global channel.
- It has follow-ups, and its Confirmation is pinned to `bfa210b`.

**Consistency**
- The ADR agrees with ADR-0007's follow-up ("Phase 2 events … must take the fence"), the decision-log row of 2026-11-18, the spike report's Decision and Weighing sections, and the updated §4.3, §4.4, PROJECT_PLAN.md and phase-2.md.
- I found no plan text that still prescribes Workflow Streams as the transport. Some stale wording remains; it is listed in the Nits.

### Nits

1. **Status is proposed, but the text says accepted.** ADR, Consequences: "…were updated to match when this ADR was accepted". The front matter says `status: proposed`, as do the `docs/adr/README.md` row, `decision-log.md:9` "(ADR-0009, proposed)" and the spike report's "ADR-0009 (proposed)". Meanwhile `design-decisions.md:32` already states the decision without "proposed". The acceptance commit must flip all of these together.
2. **NATS did run the recorded turn.** ADR, Context: "NATS ran the suite only". R7 (the recorded DSH turn) is part of the suite (`tests/test_suite.py:59-61`), and `results/suite-nats.json` shows `"R7": "pass"`. NATS ran the recorded turn but not the synthetic load.
3. **The 600 s horizon was not what the suite tested.** ADR, "What Phase 2 commits to": "Dedup holds within a re-send horizon (600 s in the spike)". 600 s is only the load runner's setting (`load.py:258`). R3 was verified at `SUITE_HORIZON_S=60` (the commands in `results/run*/suite-*.json`; default in `tests/conftest.py:53`).
4. **The Confirmation leaves out a test for a committed mechanism.** ADR, Confirmation, ports `tests/test_suite.py` and `load.py` only. The ADR commits to "clear their wake-up before each fetch", and that is covered by `tests/test_table_notify.py:39` (`test_a_notify_during_a_fetch_is_not_lost`), which the Confirmation does not name.
5. **The behaviour of a refused publish is not stated.** ADR, "What Phase 2 must still decide", lists the fence's lock order and cost. It does not say what a fenced-out publish does: raise `FenceRejected` and then `Superseded` as in ADR-0007, or drop silently. ADR-0007 implies the former, but the event path should say so.
6. **§4.4's second bullet is stale.** `design-decisions.md:33`: "**Streams are for progress and observation** … avoid one Temporal history event per token". Events no longer enter Temporal history, so the "Streams" naming and the history rationale are stale.
7. **The core plan still lists Streams to verify.** `PROJECT_PLAN.md:75` still has "Temporal Workflow Streams" among the live APIs to verify before implementing. That item is now moot.
8. **The decision log states a derived figure as measured.** `decision-log.md:9`: "one poll Update per observer per batch". The spike report says this was derived from Update counts and not measured per observer. The ADR itself was already corrected on this point.

Verdict: pass

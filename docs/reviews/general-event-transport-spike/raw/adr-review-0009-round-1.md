<!-- Verbatim subagent report (adr-review-0009-round-1, branch docs/76-close-event-transport-spike at bfa210b); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Review of ADR-0009 (/home/geo/develop/praxismesh/docs/adr/0009-use-a-postgresql-event-table-for-agent-events.md) at HEAD bfa210b. I only read files and ran no commands that change anything.

## Accuracy check: every figure is correct
I checked each claim against the results files, the code and the spike report.
- **Temporal CPU.** Medians of the per-run medians are 32.64, 32.08 and 32.41 for Streams (`results/load-streams-run{1,2,3}.json`, `containers`) and 1.58, 1.41 and 1.43 for the table (`results/load-table-run{1,2,3}.json`). That gives 32.4% against 1.4%, and the ratio range of ~20-23x is right.
- **Latency.** p95 is 199 ms for Streams and 187 ms for the table (`latency_ms.p95`). The open-loop p95 is 204 ms (`results/load-table-open{1,2,3}.json`).
- **Load gap.** 54,897 events against 58,002 (`published`) is about 5% less load for Streams.
- **Line counts.**
  - `table.py` is 183 lines.
  - At commit 1bfac67, `streams.py` is 199 lines and `streams_workflow.py` is 115, which adds up to 314.
  - The private import is at 1bfac67 `streams.py:28` (`_types._decode_payload`).
- **Update limit.** The cap of 2,000 Updates per run is in notes.md:128-129.
- **Table mechanisms.**
  - The counter row is locked with `FOR UPDATE` (`table.py:76-79`).
  - The batch row is written in the same transaction (`table.py:89-94`).
  - There is one `pg_notify` per batch on one global channel (`table.py:29,104`).
  - The reader clears its wake-up before each fetch (`table.py:145`) and falls back to a 1 s poll (`table.py:31,154-155`).
- **Reader rule.** An offset jump is reported as expiry and a repeated offset raises (`transport.py:47-50`).
- **Connection pool.** The pool allows 20 connections (`table.py:61`), and a follower holds one for as long as it follows (`table.py:127`). Publishers and tailers share one transport in one process (`load.py` `main`).
- **NATS.** Its suite run is at `69c95c4`, before the cancel check, which matches `results/suite-nats.json`.
- **Honesty of the departure.** The ADR says openly that D2 selected Streams and that the owner departed from it. This matches the spike report (lines 16-23) and the decision-log row of 2026-11-18.

## Findings

**Major 1: the departure from §4.4 is not reconciled anywhere, and the ADR does not list that work.**
- Where: Consequences, "Bad, because it departs from the §4.4 preference; the decision log records why."
- Evidence:
  - `docs/roadmap/design-decisions.md:32` still says "Prefer Temporal Python Workflow Streams…".
  - `PROJECT_PLAN.md:106` still draws "Workflow Streams -> gateway SSE / agentctl / UI".
  - `PROJECT_PLAN.md:222` still has a risk row that treats Streams as the default and the offset transport as the fallback.
  - `docs/roadmap/phases/phase-2.md:9` still reads "Verify and adopt Temporal Python Workflow Streams if suitable… Implement event state rollover across Continue-As-New". It does not say what rollover means when the events live in a table.
  - `phase-2.md:7` tells Phase 2 to read §4.4 first, so the implementer gets the opposite preference.
- Why it matters: `design-decisions.md:183` requires that when a decision changes an approved requirement, the master plan is updated as well. The decision log alone does not meet that rule.
- Fix: add a follow-up that names these four places, to be updated when the ADR is accepted. Say what phase-2 item 9's rollover and §4.3's "stream offset/state" carried across Continue-As-New mean now. This could be the publisher's own state only.

**Major 2: a Phase 2 implementer reading only this ADR would miss obligations the spike says Phase 2 must meet.**
- Where: Decision outcome, "How it is used (from the spike)", and the follow-up about token text.
- Evidence:
  - **Batch IDs must name the attempt** (spike report lines 127-128). A retried publisher that reuses batch IDs has its new events silently dropped as re-sends. The ADR's "a batch-ID row … so a re-sent batch is stored once" does not mention this, so an implementer could introduce silent event loss.
  - **Deduplication only lasts the re-send horizon of 600 s** (`table.py:80-88`). The ADR states "stored once" with no limit.
  - **Both expiry checks are needed.** The spike says "Phase 2 needs both" (report lines 118-120): the retained-base check before a read (`expiry_for`, `table.py:137-142`) and the jump check during a read. The ADR names only the jump check.
  - **The fence's lock order against the counter row, and its cost, are open.** The report says "Phase 2 sets the lock order against the counter row and measures the cost (not measured here)" (lines 151-154). The ADR presents the fence as a benefit, but leaves out the possible deadlock and the unmeasured cost. Every publish, about 5 per second per agent, would take the per-task lock.
  - **No tenant scoping.** The spike has no tenant column (report line 137), and `docs/roadmap/schemas.md:28` requires tenant and repository access checks.
  - **Keying is undecided.** The spike's table offset is separate from `AgentEvent.seq`, which counts per attempt. The table is keyed by workflow while the fence is keyed by task. Phase-2 item 10 asks for "monotonic `seq`".
- Fix: list these as commitments or as open decisions for Phase 2.

**Nits**
- Considered options and Decision outcome: the chosen-option label "A PostgreSQL event table, behind an event-transport interface" does not match the listed option "A PostgreSQL event table with a per-workflow counter and `LISTEN/NOTIFY`".
- Context: "against one test suite and one load" overstates NATS, which ran only the suite (plan D2), and there were two workloads, the recorded turn and the synthetic load (plan D3).
- Decision outcome: "every observer adds one poll Update per batch" is stated as measured, but the report says "Per-tailer growth was not measured directly; it follows from the Update counts" (report lines 94-95).
- Decision outcome: the ADR never says why NATS lost (a new 3-replica StatefulSet, and no fence in the same transaction; report lines 134 and 160). "The interface keeps that switch contained" also skips the fencing justification that ADR-0007 would then require.
- Consequences: the arithmetic of "beyond 16 followers … at 20 they all wait" is correct from the code (`table.py:61,127`) but was never measured. It should be labelled as derived.
- Confirmation: it relies on spike files that "can be deleted at any time" (plan line 212). Pin the commit (bfa210b) or move the suite into Phase 2. Also note that the suite does not exercise the fence or attempt-named batch IDs, so those rest only on the review checklist.

Verdict: changes-requested

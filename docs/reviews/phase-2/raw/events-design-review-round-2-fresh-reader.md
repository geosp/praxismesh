<!-- Verbatim subagent report (events plan design-review round 2, fresh reader, at 910be44); reviewers: fresh-subagent (design-reader); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Report on /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/plan.md (206 lines, all read)

## From the Summary
This change makes agents observable. Each harness attempt, on either runner, sends its events through a batching publisher into a PostgreSQL event table. Each publish is fenced, so an attempt that has been superseded stores nothing. Publishes go out one at a time, retry with the same batch ID, and are flushed before the attempt records its finish. Offsets have no gaps within a workflow, and a new `agentctl tail` command follows a task live, resumes after an offset, and reports pruned events. The main risk is that taking the per-task fence lock on every batch makes publishing slow. If p95 goes above 250 ms, the batching design goes back to review.

## From the whole plan
Today events go to a no-op sink and only the DSH runner emits them. The plan adds three tables (`event_logs`, `agent_events`, `event_batches`) and ports the spike's event-transport library into `common/events/`. Each attempt gets one `BatchingPublisher`, owned by `run_harness_turn`. It sends fenced batches of up to 64 events one at a time, deduplicates re-sends by batch ID, and flushes before the finish is written, so a superseded attempt cannot store events or a finish. Both runners emit `reset` and `status` events, and `openai_agents` gains tool and token events (counts only, never model text). Operators get `./agentctl tail` (follow via LISTEN/NOTIFY plus a 1 s poll, resume with `--after`) and manual `events prune`. The purpose is the first half of roadmap Phase 2, and it settles the four questions the spike left open (lock order and cost, keying, tenants, token text).

## How the existing system works, per this plan
A task is one `TaskWorkflow`. It runs turns through the `run_harness_turn` Activity, and each turn runs as Temporal attempts recorded in `task_attempts`. An attempt restores the newest checkpoint. A runner (DSH by default, or `openai_agents`) does the work and calls `before_model_call` before each model request, which already stops a superseded attempt. ADR-0007's fence (a per-task advisory lock plus a check that no newer turn or attempt exists) guards attempt writes. `AttemptEvents` numbers an attempt's events by `seq` from 0, but its sink is a no-op, only DSH emits events, and nothing stores or shows them. An existing `orchestrator.cli` exists, and the project is not a package.

## Summary vs plan
- Major, Summary / R-citations: the Summary says flushing comes "before its finish is written (R7, R8, D2)". The requirement that actually stops the finish when the flush is refused is R5, and R7 is about batching. The Summary cites R5 only for the fence, so the "refused flush raises Superseded and blocks the finish/outcome/artifact" behaviour is only implied.
- Nit, Summary: it gives one risk and leaves out the second (database CPU more than double the spike's run returns to design review).
- Nit, Summary: it doesn't say pruning is manual-only (D4) or that `openai_agents` gains tool/token events while both runners gain reset/status (D3). "On either runner" is all it says.
- Nit, Summary: it doesn't mention that a final flush that fails on database errors makes the attempt fail retryably (Assumptions). This is the one case besides supersession where events are lost.

## Sections I couldn't paraphrase (Blockers)
- No findings. Every section could be paraphrased.

## Unexplained project-specific terms
- Major, D1 / What changes: "retention class" (`task`). What it is, what other classes exist, and what reads it are never explained.
- Major, Risks / Summary: "Phase 01 task 2.3". The tasks are not in this plan (Phases table only shows "0/12"), and "2.3" numbering inside phase 01 is unexplained.
- Nit, Why / Links: ADR-0009 is only summarised in one line in Links. Fine for the gist.
- Nit, R5: "artifact" and "outcome" as things an attempt writes at finish are never introduced. Only "checkpoint" is defined.
- Nit, D2: "runs shielded" (presumably cancellation-shielded) is not explained.
- Nit, What changes: "demo", "as-built overview" and `schemas.md` are named but not described.
- Nit, Impact: `retention.py` and `workers/` appear only in Impact.
- Nit, D5: what `orchestrator.cli` does today, and the `tasks` row status values (`running`), are not explained.
- Nit, events: the event types (`reset`, `status`, `tool`, `token`) are never listed in one place with their payload fields.
- Nit, Terms: "Phase 3A", "Phase 4", "Phase 8" are used as owners. Acceptable, but unexplained.

## Places where parts don't connect
- Major, R8 vs Assumptions (bullet 2): R8 says every event is stored unless the attempt was superseded or its worker was killed. The Assumptions say a final flush that still fails after re-sends makes the attempt fail retryably, which is a third exception that R8 leaves out.
- Major, R7 (first Given) vs D3/R9: "640 events emitted at once ... stored in 10 batches" ignores the Activity's own `reset` and `status` events. With those added, the attempt has 642 events, which needs 11 batches. Say whether the 640 includes them.
- Major, Assumptions (bullet 3) vs D1: "D1 deletes old rows on publish" is a mechanism D1 never states. D1 only says `event_batches` holds batch IDs "seen in the last 600 s". The cleanup rule exists only in an assumption.
- Major, What changes / D2: `fence.py` is "shared by every fenced write", but the plan never says whether existing fenced writers (checkpoints, outcomes) are refactored onto it. The lock order (task lock, then `event_logs` row) only matters if they all use it.
- Nit, Terms: `before_model_call` is defined but never used anywhere in the plan.
- Nit, D4: `--older-than 7d` needs an event timestamp, but no column or timestamp is mentioned. It is also unclear what the retained base becomes if every event is pruned.
- Nit, D5: it is unclear how `--no-follow` interacts with "once the tasks row is no longer running it reads once more and stops".
- Nit, Why vs front matter: "two design-review rounds found no Major issue in this part" sits next to `design_review: changes-requested, rounds: 1`. The two rounds apparently refer to the messaging plan, but that reads as a contradiction.
- Nit, Summary / Links: the messaging half's path is named `phase-2-events-and-comms`, which reads as if it covers events too.

## Readability
- Nit, Assumptions bullet 2: about 45 words, and it holds two rules (shared DB, so the finish would fail too; then fail retryably).
- Nit, D1: "which is how a re-sent batch is recognised (D2 bounds re-sends well below that)". I had to reread this to see that "that" means 600 s.
- Nit, Summary: the "Offsets are gap-free per workflow; `agentctl tail` follows ..." sentence is about 40 words and packs four facts.
- Nit, D3: "DSH already emits both, with counts only. Token events carry counts (owner decision...)" says the same fact twice. It is stated a third time in Why and a fourth in R6.
- Nit, R7: one requirement with several rules (max 64 per publish; three start triggers).
- Nit, R1: two rules (stored once on re-send; offsets gap-free).
- Nit, R9: two rules (reset comes first; offsets follow `seq` within an attempt).
- Nit, R8: two rules (flush on normal end; final `status` on failure or cancellation).
- Nit, Terms "Reader rule": three rules in one definition (below base gives Expired; jump during read gives Expired; repeat is an error).

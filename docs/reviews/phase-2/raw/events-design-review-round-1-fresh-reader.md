<!-- Verbatim subagent report (events plan design-review round 1, fresh reader, at aa6580f); reviewers: fresh-subagent (design-reader); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

Report on /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-agent-events/plan.md (read in full, 197 lines; no other files opened)

## Pass 1

### From the Summary
Every harness attempt, on either runner, sends its events through one batching publisher into a PostgreSQL event table, so agents become observable. Each event gets a gap-free offset per workflow, and a new `agentctl tail` command follows a task live, resumes from an offset and reports pruned ranges. Every publish goes through ADR-0007's fence, so an outdated (superseded) attempt can't store events and is ended. The main risk is that taking the fence's per-task lock on every batch slows publishing; task 2.3 measures this against a limit.

## Pass 2

### From the whole plan
This is the event half of roadmap Phase 2. The messaging half lives in its own plan. Migration 0005 adds three tables. The event-transport spike's code moves into `common/events/`. `run_harness_turn` creates one `AttemptEvents` per attempt over a `BatchingPublisher` and passes it to the runner. The publisher flushes at 64 events, 200 ms after the oldest unpublished event, or when the attempt ends. Each flush is fenced: task lock, then a check for a newer turn or attempt, then a lock on the workflow's `event_logs` row. If the fence refuses a flush, the attempt raises `Superseded` at its next model call or final flush. Both runners emit `reset` and `status` events, `openai_agents` gains tool and token events, and token events carry counts only. `./agentctl` adds `tail` and a manual `events prune`. The reason: events currently go nowhere, and the spike plus ADR-0009 already chose the table.

### How the existing system works, per this plan
A task is a Temporal `TaskWorkflow`. It runs turns as the Activity `run_harness_turn`, and Temporal may run a turn as several attempts. Each attempt restores the newest checkpoint. There are two runners: `DshRunner` (the default) and `openai_agents`. Only DSH emits events today. DSH builds its own `AttemptEvents`, which numbers events by a per-attempt `seq` and hands them to a no-op sink in `harness_activity/events.py`, so nothing is stored or shown. ADR-0007 already fences every attempt write path under a per-task advisory lock. There is already an `orchestrator.cli`.

### Summary vs plan
- Major, Summary: "a stated limit" is never stated in the Summary. The rest of the plan gives two different numbers: under 20 ms per lock (Assumptions) and 250 ms p95 (Risks). The Summary also leaves out what happens if the limit is exceeded: the plan goes back to design review to change R7.
- Major, Summary: it leaves out R9 (each attempt opens with a `reset` event) and R8 (an ending attempt flushes its events). R9 is how a `tail` reader can tell a retried attempt's events apart, and R8 is a correctness guarantee.
- Nit, Summary: it never mentions `agentctl events prune` (D4), though "reports pruned events" depends on something doing the pruning.
- Nit, Summary: "on either runner" reads as if both runners gain the same events. In fact `openai_agents` gains tool and token events, and DSH only gains `reset`/`status` (D3).
- Nit, Summary: the diagram's "LISTEN + 1 s poll" appears nowhere else in the plan (see item 6).

### Sections I couldn't paraphrase (Blockers)
- No Blockers. Every section could be paraphrased, though some only roughly (see items 6 and 7).

### Terms used but not explained
- Major, Why: "keying" ("left this phase the fence's lock order and cost, keying and token text"). It is unclear what is being keyed. I guess it is offsets per workflow vs per task (D1), but the plan doesn't say.
- Major, D1/D2: `event_logs`, `agent_events`, `event_batches`. Their roles are never stated. From context, `event_logs` is a per-workflow row, maybe holding the next offset and the retained base, and `event_batches` dedups batch IDs for R1. The plan states neither.
- Major, D1: "the spike's re-send horizon (600 s)". It is not explained what is re-sent or why 600 s.
- Nit, Terms/D2: `Expired` appears only inside the reader-rule definition and in R3. It has no entry of its own and its argument (the retained base) is not described.
- Nit, D3: "run hooks" (of `openai_agents`).
- Nit, What changes: "as-built overview".
- Nit, D4: "the demo".
- Nit, D5: `infra/.env` and what it provides (presumably database credentials).
- Nit, Non-goals/Assumptions: Phase 3A, Phase 4 and Phase 8 are named as owners but never described beyond one word each.
- Nit, Links/Terms: ADR-0007 and ADR-0009 are summarized only in one-line link notes. That is enough at a basic level.

### Places where the parts don't connect
- Major, Summary/Assumptions/Risks: "task 2.3" is the only measurement mechanism, but the plan contains no tasks. The Phases table lists phase "01" with 0/11 tasks, so the "2.3" numbering doesn't match anything in this document.
- Major, Assumptions vs Risks: "under 20 ms" per lock vs "250 ms p95". It is unclear whether both measure the same thing (lock wait? whole publish latency?) and why one is assumed and the other is the threshold. It is also unclear why exceeding it means changing R7 (bigger batches? longer intervals?).
- Major, Summary diagram: "LISTEN + 1 s poll" is a mechanism with no decision behind it. No D-section says that `tail --follow` uses LISTEN/NOTIFY, who sends NOTIFY, or why there is a 1 s poll fallback.
- Major, D1 vs Terms/D5: Terms defines a task as one `TaskWorkflow`, and the workflow ID as that workflow's ID. Yet D1 rejects "per-task offsets" in favor of per-workflow ones, and D5 has `tail` "resolve the task's workflow ID". So a task must have its own ID that differs from the workflow ID, but this is never said. Without that, the D1 alternative it rejects looks identical to the chosen one.
- Major, D3 vs R6: "DSH already emits both [tool and token events]". The plan doesn't say whether DSH's existing token events contain model text that must be removed to meet R6. As written, there is no step that makes DSH comply with R6.
- Major, R1/D1: the plan never shows how a retried batch is stored only once. The batch ID format and a 600 s batch-row deletion appear, but the dedup check is never stated. I suspect it is in notes.md#d1.
- Major, R4/D2: "checks for a newer turn or attempt" depends on ADR-0007 recording turns and attempts somewhere. The plan doesn't say where, or how a publishing attempt knows its own identity (`attempt_id`). Readable only if you already know ADR-0007.
- Nit, D2: "the same order as every fenced write" asserts a lock order (task lock, then `event_logs` row) without saying why that order matters (presumably deadlock avoidance).
- Nit, R9: it is undefined what `reset` names as "the checkpoint it restored from" when no checkpoint exists yet (first attempt of a first turn).
- Nit, D3: the `status` event's payload and the full list of event types are never given.
- Nit, D4: the format of `--older-than D` is not given. For `--older-than`, it is not said how the retained base is chosen.
- Nit, Assumptions: "A finished workflow keeps its last batch rows until Phase 3A". This is a consequence of D1 deleting only on publish, so it is a known leak with no stated bound.
- Nit, front matter: `design_review: rounds: 0`, but Why cites two review rounds. Correct, since those were for the parent plan, but it is easy to misread.
- Nit, Decision log: the section is empty and has no "none" marker.
- Nit, D1/D2: they end with "Details: notes.md#…". The decisions mostly stand alone, but the dedup and re-send-horizon rationale seems to live only there (see above).

### Readability
- Nit, Why: "...chose the table (ADR-0009) and left this phase the fence's lock order and cost, keying and token text." I had to reread this: "left this phase" means "left open for this phase", and the list is ambiguous.
- Nit, Terms "Reader rule": one sentence holding three rules (Expired below the base, Expired on a jump, fail on a repeat). "An offset jumps during a read" needed a reread, since offsets are supposed to be gap-free (it presumably means a prune during a read).
- Nit, Summary: the sentence "Every publish takes ADR-0007's fence, so a superseded attempt stores nothing, and a refused publish ends the attempt `Superseded` at its next model call or when it finishes (R4, R5)" is about 40 words and packs two rules into one.
- Nit, D2: "A publish takes the task lock, checks for a newer turn or attempt, then locks the workflow's `event_logs` row: the same order as every fenced write." This is dense and needed a reread.
- Nit, R1: holds two rules (stored once; gap-free offsets).
- Nit, R5: holds two triggers ("next model call or when it finishes"). This is acceptable as one rule, but the scenario tests only the finish trigger.
- Nit, R7: holds three flush triggers. "When it ends" duplicates R8.
- Nit, repetition: the R5 behavior is stated three times (Summary, R5, D2), and "token counts only / owner decision 2026-11-18" twice (Why, D3). Fine for a summary, but D2 and R5 say the same thing in different words.
- Nit, naming: the messaging plan's path is `phase-2-events-and-comms` while this events plan is `phase-2-agent-events`, so the "events" name points at the wrong plan.

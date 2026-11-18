<!-- Verbatim subagent report (messaging plan design-review round 3, zoom out, at 88ea037); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

I found 3 Majors and 6 Nits; nothing is a Blocker. The plan fixes the real cause. Today `TaskWorkflow` ends when its turns finish and every submit creates a new request (orchestrator/workflow.py:97-157, orchestrator/submit.py:45). The plan adds a durable inbox, a wait state and `--join`, which is what the roadmap Accept line needs. New logic goes where similar logic already lives: `MessageRepository` next to the fenced repositories, `comms_mcp/` next to `sample_mcp/`, the dispatcher in the orchestrator worker, and the wait uses the existing `wait_set` helper.

**Major 1 — A failed or cancelled `claim_inbox` ends the Workflow without `complete_task`** (plan.md › D7, D17; notes.md › D7 "Endings")
- **The gap:** notes.md handles only one cancellation: "`CancelledError` caught in the wait -> `failed` "cancelled", after `complete_task`". Nothing says what happens when `claim_inbox` itself fails.
- **Retries run out quickly:** short Activities use `SHORT_RETRY = RetryPolicy(maximum_attempts=5, ...)` (orchestrator/workflow.py:38-39). With the default backoff that is about 15 s of database downtime.
- **Cancellation takes the same path:** a cancel that lands while the claim runs reaches the Workflow as an `ActivityError`, not a `CancelledError`.
- **Either way, nothing closes the task.** The `ActivityError` escapes `run`, so `complete_task` and `end_task` never run. The `tasks` row stays `running`. Questions to the task stay open until their deadlines, R25 keeps accepting sends to it, and R30's `undelivered` marking never happens. That breaks R24 and R30.
- **Why this is worse than today:** the code already accepts a run ending without `complete_task`, but only around the one-time `record_task` (workflow.py:82-83). The claim runs on every wake of every waiting task, so a short database restart fails every waiting task at once.
- **Fix:** make the claim retry until the wall-time deadline (it is idempotent). Then send any `ActivityError` from the claim, including a cancellation, to `complete_task(failed)`. Add "database unavailable while tasks wait" to Risks.

**Major 2 — One Signal per message leaves history unbounded during a turn, and R33 does not cover it** (plan.md › D6, D11, R33; notes.md › D6)
- **What the plan does:** every send writes its own wake row, and the dispatcher sends one `inbox` Signal per row.
- **Why it escapes the bound:** each Signal is a history event, plus a workflow task when the run is idle. D11 checks history length "Before sleeping" only. Signals that arrive during a long turn are never checked, and a turn can last up to `turn_timeout * 6` (workflow.py:127).
- **Example:** several tasks messaging one coordinator can push a run past 2,000 events.
- **The Signal adds nothing per message:** notes.md › D7 says "the flag only ends a sleep early", because the claim reads everything pending.
- **Fix (smaller than the current design):** keep at most one wake row per recipient (`UNIQUE (recipient_workflow)` with `ON CONFLICT DO NOTHING`). Signals then scale with sleeps, not with messages.

**Major 3 — R19 lets a task finish while its answer sits unread, and the answer is then thrown away** (plan.md › Terms "Open question", R19, D8, R30)
- **Answered counts as closed:** an open question is "a question not answered, expired or cancelled". So once B replies while A's turn is still running, A's `finish_task("done")` is accepted. At the end, `end_task` marks the reply `undelivered` (R30). A asked, got an answer, and finished without ever seeing it. With a fast replier (the fake model, or small local models) this is the common case, not an edge case.
- **Same-step calls:** an `ask_agent` and a `finish_task` in the same model step can also pass the check. Multi-call steps do happen; the DSH runner already handles "finish_task came with another call" (harness_activity/dsh/runner.py:600). `finish_task_body` simply records the finish (harness_activity/tools.py:207-214).
- **Fix:** have the check refuse while the task has open questions or unread replies to its own questions. The same query, under the request lock, also closes the same-step race.

**Nits**
- plan.md › D12: the patch does not do what its rationale says, and replay doesn't need it. Phase 1 histories never return `waiting` and the non-waiting path issues no new commands, so `patched("phase2-wait")` is not needed for replay. A v1 task the drain misses is refused by v2 workers (harness_activity/activity.py:226-237) until `schedule_to_close` (workflow.py:127), so the patch does not save it either.
- notes.md › D7 "Restore": the woken turn's input "lists its rows … instead of CONTINUE_MESSAGE". On a rerun that restores a checkpoint from the same turn (activity.py:490-513), the session already holds those rows, so the model would see them twice. Say: render the rows only when the newest checkpoint is from an earlier turn.
- plan.md › D14: "the Activity passes `max_ask_wait` to `comms_mcp`", but `TurnInput` has no such field and forbids unknown fields (common/schemas/task.py:61-70). Task 1.1 doesn't say whether `TurnInput` gains it or the Activity resolves the profile itself.
- notes.md › D6 cycle walk: it starts "from the recipient" and refuses on "reaching the asker". A task asking itself is never refused and waits until its own deadline. Refuse self-asks explicitly.
- phases/02 › task 2.1: `init.sh` is mounted as a single file (infra/docker-compose.yml:26), and the `db` service env (docker-compose.yml:14-22) has no `PRAXIS_COMMS_DB_PASSWORD`. A fresh volume can't run `roles.sh` unless both are added. `make db-roles` is in notes.md but in no task, and Rollout doesn't say how to run it.
- notes.md › D6 grants: `INSERT` on `message_wakes` is not enough if `id` is a `serial`; that also needs `USAGE` on its sequence (an identity column would not).
- plan.md › D13: the `praxis_comms` scoping holds only for DSH. On `openai_agents`, `sh` runs in the worker container with the worker's UID (tools.py:136-151; `cli_tools: [python3, wc, git, sh]` in registry/templates/local-default.yaml), so it can read `/proc/*/environ`, including the comms DB URL. That would bypass R10 and R26. The same exposure already exists for `PRAXIS_SAMPLE_DB_URL`; state it as a known limit.

**Rollout & rollback:** apart from the `roles.sh` gap above, the section is adequate.
- **Deploy order:** roles, migrate, orchestrator, harness workers, CLI is correct for strict schemas, as long as submissions stay stopped in between.
- **Migration:** 0006 only adds tables and needs no backfill.
- **Rollback:** reverting the worker image also reverts the strict registry files, and draining tasks started on the new code is needed and stated.

Paths:
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/plan.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/notes.md
- /home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/phases/02-inbox-and-comms.md
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/tools.py
- /home/geo/develop/praxismesh/harness_activity/dsh/runner.py
- /home/geo/develop/praxismesh/common/schemas/task.py
- /home/geo/develop/praxismesh/infra/docker-compose.yml
- /home/geo/develop/praxismesh/registry/templates/local-default.yaml

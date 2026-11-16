<!-- Verbatim subagent report (design-review round 4, zoom out, targeted follow-up on the phase 02 decision changes); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. The run stopped once on a usage limit and was resumed. -->

Design review of the "Run production agents on DSH" plan, as frozen at 98835319

Scope: I read plan.md, the three phase files, notes.md, reviews.md and ADR-0001 to ADR-0006. I checked these against the code in orchestrator/workflow.py, orchestrator/activities.py, workers/main.py, infra/docker-compose.yml, registry/, tests/benchmarks/run.py, tests/support/{workers,dsh}.py, harness_activity/dsh/barrier.py, the 0004 migration and common/persistence/retention.py.

Phases 01 and 02 are already built and impl-reviewed. I judged the plan as written, focusing on what is still open: the targeted design review the decision log asks for, phase 03, and Rollout & rollback.

1. Root cause
The plan fixes the cause. "Why" says the five ADR-0005 conditions were proven only in isolation. Each condition maps to requirements, and each requirement maps to a phase task. No findings.

2. Simplicity
No findings beyond Nit N1 below. D8 (the event sink built before Phase 2) is justified by ADR-0005's sequencing decision. The D3 alternatives are argued properly.

3. Placement
No findings. New code sits in harness_activity/dsh/, next to the existing runner. The ledger reconciliation sits in the orchestrator's complete_task, where the task's usage is already finalised. usage_ledger joins the existing retention-class table list (common/persistence/retention.py:30).

4 and 5. Failure modes and rollout: findings

M1 · Major · plan.md › Rollout & rollback; phases/03-acceptance.md › 2.2
The drain bound is wrong, and the rollback never says to keep the DSH pair running.
- The plan says: "the drain is bounded by the profile's `max_wall_time`".
- The workflow checks the deadline only before it starts a turn (orchestrator/workflow.py:90 and :105-107).
- A turn started just before the deadline can then run until `schedule_to_close_timeout=resolved.turn_timeout * 6` (workflow.py:126). For local-dsh that is PT10M x 6 = 60 min (registry/templates/local-dsh.yaml:15).
- So the real bound is min(profile max_wall_time, max_wall_time_cap) + 6 x turn_timeout: about 90 min today, not 30.
- The section also never says the `dsh` Compose profile (dsh-a and worker-dsh-a, infra/docker-compose.yml:185-215) must stay up for that whole window.
- An operator who follows the plan and stops the pair after 30 minutes strands the final turns. Those tasks cannot fall back, since "`openai_agents` cannot resume a DSH checkpoint".
- Fix: state the real bound and "keep the DSH pair up until no task resolved to local-dsh is open" in Rollout & rollback and in the task 2.2 runbook. Task 2.2's Verify should also check that an in-flight DSH task finishes after the revert, not only that a new task runs on openai_agents.

M2 · Major · plan.md › Rollout & rollback; phases/03-acceptance.md › Goal ("two-field rollback") and 2.1/2.2
The rollback is more than two field edits.
- The registry is loaded once, at process start (workers/main.py:132; orchestrator activities hold `self.registry`, orchestrator/activities.py:37). It is resolved once per task (workflow.py:74, `resolve_capabilities`).
- Reverting `default.yaml` therefore also needs:
  - `make registry-lock`, because the profile is locked;
  - rebuilding the shared `praxismesh-worker:dev` image, since the registry ships in it;
  - restarting the orchestrator and any CLI or submit host.
- The plan names none of these steps, and nothing says new submissions keep going to DSH until the orchestrator restarts.
- The same steps apply in reverse for the switch in task 2.1.

M3 · Major · plan.md › Rollout & rollback
Undoing the code (as opposed to the profile) is ambiguous, and the plan contradicts the migration.
- The plan says: "Code rollback below D7 is not supported." The migration docstring says the opposite: "Additive only, so the previous code keeps working against this schema" (common/persistence/migrations/versions/0004_dsh_usage_and_sessions.py:3), then "Code rolled back below this migration is not supported" (line 11).
- Phases 01 and 02 changed the production openai_agents path, including the session-store seam and the D10 advisory-lock fence. That is the one change every current task depends on.
- The plan never says how to undo a regression there. Options it could choose between: revert the code while keeping the 0004 schema (does pre-plan code tolerate NULL `tokens_in` rows written by DSH?), or roll forward only.
- It also never says what happens to in-flight Temporal workflows when TaskWorkflow is reverted. The workflow gained `cancellation_type=WAIT_CANCELLATION_COMPLETED` and `usage_known` handling at workflow.py:128-130 and :143-153.
- Fix: say which of these is supported.

M4 · Major · plan.md › Rollout & rollback and Risks; phases/03-acceptance.md › 2.1
Switching `default` cuts its capacity, and the plan never mentions it.
- Today `default` is served by two local-default workers, worker-a and worker-b (infra/docker-compose.yml:168, :217), each with `concurrency_per_pod: 1`.
- The plan adds one DSH pair (dsh-a/worker-dsh-a with the volume `dsh-attempts-a`), and D3 pins `concurrency_per_pod: 1`.
- After task 2.1, `default` has one slot at about 1.9x the wall time: roughly a quarter of today's throughput.
- Queued turns also eat into `schedule_to_close` (turn_timeout x 6), so under load turns can time out before they run.
- Under Risks, "Cost and latency … measured in R19" does not cover this. The benchmark runs tasks one at a time in-process (tests/benchmarks/run.py:171-173), so it cannot show it.
- Adding pairs is not a scale flag: each pair needs its own service and volume names.
- Fix: state the number of DSH pairs required before the switch, in Rollout and in task 2.1.

M5 · Major · phases/03-acceptance.md › 1.1
The benchmark task underestimates what DSH needs, and its Verify step cannot catch the gap.
- The task says "`running_workers` already takes a template".
- A local-dsh worker needs DSH_CONTROL and a live paired DSH container sharing the attempt volume and the GID (workers/main.py:92-93; infra/docker-compose.yml:196, :204-206). `running_workers` (tests/support/workers.py:19-30) starts in-process workers with neither.
- The only harness that does this is tests/support/dsh.py, which is pytest-only (it calls `pytest.skip`) and rewrites the launcher's UID and GID for the test process.
- tests/benchmarks/run.py also hard-codes `"profile": "default"` (line 58) and `TEMPLATE = "local-default"` (line 47). TEMPLATE drives environment(), the system prompt it reads, and the output file name `{date}-{TEMPLATE}`.
- Without changes there, a DSH run is mislabelled as local-default, or overwrites the same-day default result that task 1.2 needs.
- The Verify step, "a benchmark dry run selects each profile", would pass without any of this working.
- Fix: name the DSH container lifecycle and the result naming in the task, and make Verify start a real local-dsh turn.

N1 · Nit · phases/03-acceptance.md › 1.1
"set `local-dsh`'s `turn_timeout` and `max_wall_time_cap` as in `local-default`" is already true: PT10M and PT1H in both templates (registry/templates/local-dsh.yaml:15,19 and local-default.yaml:15,19). Either drop it, or say whether the ~1.9x wall time calls for different values.

N2 · Nit · plan.md › Requirements › R18 versus Decisions › D11
- R18 says each TaskResult "matches `docs/spikes/dsh-phase02-r2-evidence.json`".
- D11 says R18 adds retried attempts' steps to the spike's counts, and reviews.md F65 says the tests "apply only recorded differences".
- Fix: put the exception in R18 itself, so the requirement and its tests agree.

N3 · Nit · plan.md › Requirements › R8, R6
Open items leave holes in R8 and R6, but the phase is marked impl-reviewed with no deviation recorded.
- F103: a `unresolved usage` denial starts no exit timer, so the runtime runs to the deadline.
- F111: `poll` and the in-run `stop` have no timeout, so a stalled launcher skips the 5 s margin.
- F106: a stale attempt's `_charge` writes usage columns without the fence.
- R8 ("Every DSH process must exit within 5 s") and R6 are stated as absolute.
- Fix: fix these, or record them as known deviations in the decision log before phase 03 relies on R8.

N4 · Nit · notes.md › D6 step 2
- The flush check re-reads every session file in full on each barrier (`session_contains`, harness_activity/dsh/barrier.py:35-41).
- Together with a full workspace capture on every model request after the first, cost per turn grows with turn length times session and workspace size.
- The benchmark's small workspaces will not show this. It deserves a line under Risks for repository-sized workspaces.

N5 · Nit · plan.md › Requirements › R17; reviews.md F99
- A worker that refuses to serve exits with code 3, and Compose restarts it (`restart: unless-stopped`, infra/docker-compose.yml:214).
- With a persistent digest mismatch the worker loops forever, and turns wait until `schedule_to_close`. The worker shutdown wiring has no automated test (F99).
- The plan's R17 and Rollout should say how an operator notices this, for example a log line or a health signal.

Everything else checks out
- The migration is metadata-only on PostgreSQL 16: a nullable change and a constant-default column.
- D10's per-task advisory lock is sound: `hashtext` collisions only serialise unrelated tasks.
- The profile is resolved once per task, so running tasks really do stay on DSH after a revert.
- Retries are bounded by `schedule_to_close`, and re-running a step is guarded by the fence.

Files referenced
- <repo>/docs/plans/2026-11-15-dsh-production-harness/plan.md
- <repo>/docs/plans/2026-11-15-dsh-production-harness/phases/03-acceptance.md
- <repo>/docs/plans/2026-11-15-dsh-production-harness/notes.md
- <repo>/orchestrator/workflow.py
- <repo>/orchestrator/activities.py
- <repo>/workers/main.py
- <repo>/infra/docker-compose.yml
- <repo>/tests/benchmarks/run.py
- <repo>/tests/support/workers.py
- <repo>/tests/support/dsh.py
- <repo>/common/persistence/migrations/versions/0004_dsh_usage_and_sessions.py
- <repo>/harness_activity/dsh/barrier.py
- <repo>/registry/templates/local-dsh.yaml
- <repo>/registry/templates/local-default.yaml

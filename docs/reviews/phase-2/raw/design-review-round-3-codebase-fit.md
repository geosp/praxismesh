<!-- Verbatim subagent report (messaging plan design-review round 3, codebase fit, at 88ea037); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

## Review: Phase 2 messaging plan (docs/plans/2026-11-18-phase-2-events-and-comms), plan at 88ea037, code at main 2f4b012

Most claims about the code check out: `fence.py`, `TASK_LOCK`/`NO_NEWER_ATTEMPT`, `wait_set` in `common/events/transport.py`, `MCP_CALL_TIMEOUT_S = 120`, the 150 s bridge timeout, `sample_mcp`'s idempotency key, `agent_messages` from migration 0003, `CONTINUE_MESSAGE` restore and finish short-circuit, `stop_at_tool_names`, `request_id` minted in `prepare_task`, `--request` as a JSON file, the replay fixture, and `make registry-lock`. No Decision contradicts an ADR in force (0002, 0003, 0005-0009). The plan uses the two-key advisory lock form for the request lock, and PostgreSQL keeps the one-key and two-key lock spaces separate, so D10 does not collide with ADR-0007's task lock.

### Major

**M1. Continue-As-New only runs before a sleep, so a task that keeps getting woken never continues** (plan.md Decisions › D11; notes.md#d7 "Wait loop"; phases/02 task 4.3; R33)
- D11 says: "Before sleeping, the Workflow continues as new when Temporal suggests it or its run's history passes 1,000 events". The notes' loop is "claim; a count above zero runs the woken turn now; otherwise sleep".
- If messages land during every turn, each claim returns a count above zero, the Workflow never sleeps, and it never reaches the Continue-As-New check. History then grows by about 15-20 events per woken turn (claim and turn Activities plus Workflow tasks), with nothing stopping it except `max_wakes`.
- The default `max_wakes` of 50 stays under about 1,000 events. The test profile in phase 03 task 1.5 (`max_wakes` 200), or any cap above about 100, can break R33's rule ("No run of a waiting task exceeds 2,000 history events").
- R33's test can still pass if its sender spaces out the wakes, so the test would hide this.
- Fix: check for Continue-As-New after every `waiting` outcome, before the claim, not only before a sleep.

**M2. `max_ask_wait` has no way to reach the Activity** (Decisions › D14; phases/02 task 3.2)
- D14 says "`resolve_capabilities` puts them in the resolved task; the Activity passes `max_ask_wait` to `comms_mcp`", and task 3.2 adds `PRAXIS_MAX_ASK_WAIT` to `build_config`.
- `run_harness_turn` receives only `TurnInput` (common/schemas/task.py:61-70: task, turn, template, version, hash, remaining tokens and wall time, request_id). It never sees `ResolvedTask`, and `build_config(registry, loaded, task_id)` (harness_activity/config.py:39) has no profile.
- Something has to carry the value: a new `TurnInput` field (all schemas are `extra="forbid"`, common/schemas/base.py:19, so this is an interface change between orchestrator and harness workers), or a lookup by task profile in the Activity. No task names either one, and Impact does not list a `TurnInput` change.

**M3. Fresh-volume and operator wiring for `praxis_comms` is incomplete** (phases/02 task 2.1; notes.md#d6 "Role"; Rollout & rollback)
- Task 2.1 adds `PRAXIS_COMMS_DB_PASSWORD` only to `.env.example`, `check-prereqs.sh` and "the harness workers' Compose env". But `init.sh` runs inside the `db` container, which gets only `POSTGRES_*`, `TEMPORAL_DB_PASSWORD` and `APP_DB_PASSWORD` (infra/docker-compose.yml:15-22).
- Only `init.sh` is mounted into that container (`./db/init.sh:/docker-entrypoint-initdb.d/20_praxismesh.sh`, docker-compose.yml:26), so a separate `roles.sh` called by `init.sh` would not be present.
- The notes tell operators to run `make db-roles`, but there is no such target in the Makefile (Makefile:34 `.PHONY` list) and no task adds one.
- Result: CI's fresh stack and the clean-worktree `verify-phase` run would fail to create the role, unless task 2.1 also adds the `db` service env entry, the mount and the Make target.

### Nits
- phases/02 task 2.2: it says every `MessageRepository` method is "each in D10's lock order and fenced". That contradicts notes.md#d6 ("`end_task` takes only the request lock (it is not an attempt write)"), and `claim` runs in the orchestrator with no attempt to fence. Say which methods are fenced.
- notes.md#d7 `read_claimed`: the attempt marks rows `read`. That is a new attempt write path, and ADR-0007's follow-up asks that it "take the fence or justify why it need not". The plan does neither.
- phases/02 task 3.3: the "ask-then-wait prompt text" can't go into `registry/prompts/local-default.md`, which both v1 templates use. The template hash covers the prompt (registry/registry.lock header), so `registry.lock --check` would report "changed under an existing version". v2 needs a new prompt file.
- notes.md#d6 grants: `praxis_comms` gets `INSERT` on `message_wakes` but no sequence `USAGE`. If `id` is serial, like 0003's `sa.Integer, autoincrement=True` (0003_phase1_tables.py:129), comms inserts fail. Use `sa.Identity()` (as `order_id` does, :111) or grant the sequence.
- D10/D17: the comms writes check the recipient's status but not the sender's. A stale attempt of a task that `end_task` has already closed passes the fence (no newer attempt exists) and can open a new question after R24 closed everything.
- notes.md#d7 "Endings": only "`CancelledError` caught in the wait" is covered. A cancel that arrives during `claim_inbox` (an `ActivityError`) needs the same `complete_task`/`end_task` path, or R24 fails for that case.
- R22/D14: the plan doesn't say which budget pays for a `continue` turn that follows a woken turn (`max_turns` or `max_wakes`).
- phases/03 task 1.5: the test profile's `max_wakes` 200 needs a template with `max_wakes_cap` ≥ 200, because the effective value is the minimum of the two (like `max_turns`, orchestrator/activities.py:84). Task 3.3 sets no cap value.
- R28: "No message body enters Temporal history" is too broad. A model can quote a message in the `finish_task` summary, which goes into `TurnOutcome`/`TaskResult`. Limit the rule to claims and Signals.

### Relevant files
- /home/geo/develop/praxismesh/orchestrator/workflow.py
- /home/geo/develop/praxismesh/common/schemas/task.py
- /home/geo/develop/praxismesh/harness_activity/config.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/infra/docker-compose.yml
- /home/geo/develop/praxismesh/infra/db/init.sh
- /home/geo/develop/praxismesh/Makefile
- /home/geo/develop/praxismesh/registry/registry.lock
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0003_phase1_tables.py
- /home/geo/develop/praxismesh/docs/adr/0007-fence-harness-attempts-in-one-transaction.md

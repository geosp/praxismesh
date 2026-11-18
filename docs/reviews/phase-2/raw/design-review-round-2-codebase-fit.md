<!-- Verbatim subagent report (design-review round 2, codebase fit, at 4c992ea); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

## Design review: Phase 2 plan (`docs/plans/2026-11-18-phase-2-events-and-comms`, plan files at 4c992ea)

Most of the plan's claims about the code check out. These all hold:
- the DshRunner sink (`harness_activity/dsh/runner.py:238`, `:360`), and `workers/main.py:97` passing no sink;
- `MCP_CALL_TIMEOUT_S = 120` and the bridge's 150 s timeout;
- `_TASK_LOCK` / `_NO_NEWER_ATTEMPT` (`common/persistence/repositories.py:380-384`);
- `record_task` refusing a new run ID (`repositories.py:79-86`);
- restore picking the newest checkpoint across turns (`repositories.py:453`, `activity.py:435-451`);
- `request_id` minted on every submit (`submit.py:45`);
- the fake model stepping by tool-call count;
- the replay fixture, and the spike's `transport.py` / `memory.py` / `table.py` with `Expired`, `expiry_for` and `guarded`.

No Decision contradicts an ADR in force. The plan settles ADR-0009's open items (tenant scoping: one tenant, by request; keying: D1; token text: D3; lock order: D2/D10), and D2 and D10 name their fence as ADR-0007 requires. The findings below are gaps between the plan and the code, or contradictions inside the plan.

### Major

**M1. The `praxis_comms` role never exists on an existing database, so migration 0006 fails.**
- Where: phase 02 task 1.1; notes.md#d6 ("`infra/db/init.sh` creates `praxis_comms`"); Rollout & rollback ("migrate").
- Evidence: `infra/db/init.sh:3-6` says the script runs "once ... on a fresh `pgdata` volume. It never runs again on an existing volume, so a failed init or a changed password needs `make reset`."
- Consequences:
  - On any existing dev or deployed volume, 0006's `GRANT ... TO praxis_comms` errors, and so does the task's own check ("upgrade and downgrade on a copy of the dev database").
  - `init.sh:29-31` revokes `CONNECT` from `PUBLIC` and grants it only to `praxismesh`. So 0006 (or init.sh) must also grant `CONNECT` on `praxismesh`, and `USAGE` on schema `public`, to the new role. The plan doesn't mention either.
  - The app role cannot `CREATE ROLE`, and no existing migration creates roles or grants (none of 0001-0004 does).
- Fix: the plan needs an upgrade path for existing volumes, such as a one-off superuser step in the runbook or rollout, or a guarded `DO` block run by an operator, plus the `CONNECT`/`USAGE` grants.

**M2. `claim_inbox` returning "the claimed rows" puts message bodies in Temporal history, which breaks R28.**
- Where: phase 02 task 3.3 ("returns the claimed rows and the next deadline"); D7 ("the woken turn's input lists the claimed rows"); notes.md#d7 (rows include "body").
- R28 says "Events and message bodies never enter Temporal history." An Activity's return value is recorded in history, and bodies can be up to 16 KB each (D6).
- Fix: `claim_inbox` should return only counts, IDs and the next deadline. `run_harness_turn` should then read the rows by `(task, claimed_turn)`, which also makes R13's "same messages again on rerun" work naturally. The plan needs to say this.

**M3. R19's refusal has no mechanism, and on `openai_agents` a refused `finish_task` still ends the run.**
- Where: D8; phase 02 task 3.1.
- No database access: `finish_task` is a synchronous built-in (`harness_activity/tools.py:207-214`, `:271-277`). `build_tools(workspace, cli_tools, state, runner)` has no engine or repository, so it cannot check for open questions or name them. The plan doesn't say how the check reaches the database: an injected callable, the Activity's engine, or something run through DSH's `_invoke` thread (`dsh/executor.py:39-49`).
- `openai_agents` ends the run anyway: `runner.py:250` sets `tool_use_behavior={"stop_at_tool_names": [FINISH_TOOL]}`, so the SDK stops on any `finish_task` call, including a refused one. The runner then returns `continue` ("stopped without finish_task", `runner.py:274-275`). The model never sees the refusal in that run, and each refusal uses up one `max_turns` turn. A model that keeps calling `done` can end the task `failed` ("turn budget exhausted") with questions still open.
- DSH behaves differently: `executor.py:162-163` marks the run finished only if `state.finish` was set.
- Fix: D8 and the conformance tests in task 3.1 need to settle what both runners do on a refused `finish_task`.

**M4. R11 and R27 contradict each other.**
- R11: "Every refused send or ask is stored as a `rejected` row with its reason."
- R27: "A send, ask or reply from a superseded attempt is refused ... nothing is stored."
- A fence refusal is a refused send, so the two cannot both pass as written. R11 needs to exclude fence refusals, or R27 needs to allow a rejected row.

**M5. The new profile and template fields have no path to the code that uses them, and task 2.2 comes before the schema change.**
- Where: D7, D8, D14; phase 02 tasks 2.2 and 3.1.
- `ResolvedTask` (`common/schemas/task.py:136-149`) and `resolve_capabilities` (`orchestrator/activities.py:71-90`) carry only `max_turns`, `max_tokens` and `max_wall_time`. No task extends them with `idle_timeout`, `max_wakes` (capped by `max_wakes_cap`) or `max_ask_wait`, yet the Workflow needs the first two.
- The new fields must have defaults. Otherwise the Phase 1 fixture's recorded `ResolvedTask` payload no longer decodes, and R29 fails: `Strict` forbids unknown fields but requires declared ones (`base.py:14-18`).
- `comms_mcp` must cap `wait` at `max_ask_wait`, but it only gets `PRAXIS_*` env and reads of `tasks`/`task_attempts`. It has no registry, so it has no way to learn the cap.
- Task 2.2 adds `max_wakes_cap` to the template YAMLs, but only task 3.1 touches schemas, and only profile fields. `WorkerTemplate` is `extra="forbid"` (`capability.py:40-70`), so the registry fails to load at 2.2, and its own check (`tests/test_registry.py`) fails.

**M6. Cancelling a waiting task skips `complete_task`, so R24 fails in its main case.**
- Where: D7 / notes.md#d7 "Endings"; R24; phase 02 task 3.4.
- The notes list only these endings: idle timeout, wall time and `max_wakes`.
- Today cancellation reaches `complete_task` only because it surfaces as `ActivityError` around `run_harness_turn` (`workflow.py:107-152`). A cancel that arrives while the Workflow waits on a Signal or timer raises `asyncio.CancelledError`, which nothing catches. `complete_task`, and therefore `cancel_for`, never runs, and A is never woken (R24: "B is cancelled ... A runs a turn saying B ended").
- Fix: the wait loop must catch cancellation and still run `complete_task` (and `cancel_for`), and task 3.4's tests should cover a cancel during the wait.

### Nits
- D15 and phase 02 task 2.2: "the Activity's tool-call hook" does not exist. Tool events come from `dsh/executor.py:171-177` and `openai_agents`' `_Hooks.on_tool_end` (`runner.py:196`). `post_status` must be handled in both, including parsing stage and progress from the tool result.
- Phase 02 task 2.3: `prepare_task(data, registry, blobs, *, base_dir)` (`submit.py:29-31`) has no database access, and `TaskRepository` has no lookup by `request_id`. The "refuses one with no existing task" check needs both.
- D6: the dispatcher `LISTEN`s, but nothing in D6 or notes.md#d6 says who `NOTIFY`s on a `message_wakes` insert, or on which channel. Only `agent_events` has a `NOTIFY`.
- Terms › Reader rule: it leaves out ADR-0009's "fails on a repeated offset". `guarded` does that check, so the rule as written drops a committed check.
- Phase 02 task 3.2: `activity.py:508-516` stores a finish report only for `done`/`needs_input`. The plan should also store `waiting` there, or a lost-after-finish `waiting` attempt reruns the model.
- D11: Continue-As-New counts only woken turns. Late Signals that lead to empty claim cycles add history the count misses. Checking `workflow.info().get_current_history_length()` would bound R28 directly.
- Phase 02 task 2.2: `PRAXIS_ATTEMPT` must be Temporal's `info.attempt`, the fence key (`activity.py:244`, `:398`), not `real_attempt`. The plan should say which.
- Phase 02 task 1.1 / infra: the new password and URL variables also belong in `infra/check-prereqs.sh:23-25` (its list of known variables) and in compose's harness-worker env, as `PRAXIS_SAMPLE_DB_URL` is (`docker-compose.yml:149`).
- R25 / notes.md#d7: `complete_task` runs `tasks.complete` and `cancel_for` with no stated order or shared transaction. An ask between them could be accepted for an ending recipient and wait until its deadline.

### Relevant files
- `/home/geo/develop/praxismesh/docs/plans/2026-11-18-phase-2-events-and-comms/plan.md`, `notes.md`, `phases/01-event-table-and-tail.md`, `phases/02-inbox-and-comms.md`, `phases/03-acceptance.md`
- `/home/geo/develop/praxismesh/infra/db/init.sh`
- `/home/geo/develop/praxismesh/harness_activity/tools.py`, `harness_activity/runner.py`, `harness_activity/activity.py`, `harness_activity/dsh/executor.py`
- `/home/geo/develop/praxismesh/orchestrator/workflow.py`, `orchestrator/activities.py`, `orchestrator/submit.py`
- `/home/geo/develop/praxismesh/common/schemas/task.py`, `common/schemas/capability.py`, `common/persistence/repositories.py`

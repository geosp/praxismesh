<!-- Provenance: verbatim copy of .verify/report-as-built.md, written by a fresh verifier subagent (verify-phase gate mode, brief "As-built claims") for Phase 2 messaging (phases 02 and 03) at code_sha = docs_sha 417c441c0f3c65ec637f873113a41d72aeda1e0e. Copied with cp; not edited. -->

# As-built documentation check: Phase 2 messaging

- Checkout: `verify-phase2-messaging` at `417c441c0f3c65ec637f873113a41d72aeda1e0e` (`git rev-parse HEAD`; `git status --short` shows only `.verify/`).
- Probes (read only): `docker compose -p pmphase2 --env-file infra/.env -f infra/docker-compose.yml exec -T -u postgres db psql -d praxismesh -X -c ...` (written as `PSQL` below), plus `docker compose ... config`. Running services: `db running, s3 running, temporal running, temporal-ui running`. Workers are stopped. No tests were run and no workers were started. The `praxismesh` project was not touched.
- Documents: `docs/architecture/overview.md` lines 241-296; `docs/operations/runbook.md` lines 182-211; `docs/roadmap/schemas.md` lines 53-68; `docs/demos/phase-2.md`. Observed run values in the demo were out of scope.

## Summary

- 4 claims contradicted: 1 Major, 3 Nit.
- 2 imprecise or ambiguous claims (Nit).
- Runtime-only claims were blocked because the workers are stopped and tests were out of scope. These are listed as unverifiable.
- Everything else was confirmed against the code, and against the database or Compose config where a probe could show it.

## Contradicted or imprecise claims

| # | Severity | Location | Claim | Evidence |
|---|---|---|---|---|
| C1 | **Major** | overview.md:254 (Waiting Workflow row); runbook.md:198-201 | "with none it sleeps until an `inbox` Signal, its earliest open question's deadline, its idle timeout (only with no open question) or its wall-time deadline, then claims again." The runbook gives the same list and says only that the task "runs a woken turn when its inbox has rows". | When the idle timeout fires, the task does not claim again. It ends the task as `succeeded` without a final claim. `orchestrator/workflow.py:373-380`: `except TimeoutError: ... if deadline is None: return "succeeded", None  # idle timeout (R20)`. Only a Signal or a question deadline leads to another claim (workflow.py:381). The wall-time deadline leads to one final claim that decides the ending (workflow.py:377-378, 383-403). None of the checked documents says that an idle waiting task ends as succeeded after `idle_timeout` (default 10 min), or that rows still pending at that moment then become `undelivered` through `end_task`. |
| C2 | Nit | overview.md:250 (Comms role row) | "`praxis_comms` gets `SELECT, INSERT, UPDATE` on `task_messages`, `SELECT, INSERT` on `message_wakes`, and `SELECT` on `tasks`, `task_attempts` and `task_inbox`, and nothing else." | The table grants match exactly. `PSQL "select table_name, string_agg(privilege_type...) from information_schema.role_table_grants where grantee='praxis_comms'"` returned: `message_wakes INSERT,SELECT; task_attempts SELECT; task_inbox SELECT; task_messages INSERT,SELECT,UPDATE; tasks SELECT` (5 rows). However, "nothing else" is not literally true. The role also holds `CONNECT` on `praxismesh` and `USAGE` on `public` (`roles.sh:21,26`; probe `c=t u=t cr=f`). Through PUBLIC it can also read ParadeDB catalog objects: `has_table_privilege` lists `paradedb._typmod_cache`, `paradedb._typmod_cache_id_seq`, `paradedb.index_layer_info` and `pdb.index_layer_info`, with `relacl {postgres=arwdDxt/postgres,=r/postgres}` and USAGE on schemas `paradedb` and `pdb` = t. These are harmless, but the absolute wording overstates. |
| C3 | Nit | runbook.md:207 | "Then `make db-roles`, `make migrate`, and `make workers-up` (the orchestrator worker accepts `waiting` first)." | `make workers-up` (Makefile:129-131) starts `orchestrator worker-a worker-b dsh-a worker-dsh-a dsh-b worker-dsh-b` in a single `docker compose up`. The template workers have no `depends_on` for `orchestrator`. The config probe returned `worker-a ['db','s3','temporal']` and `worker-dsh-a ['db','dsh-a','s3','temporal']`. Nothing makes the orchestrator start first, which plan.md:350 requires ("Deploy the orchestrator worker first"). Because the runbook says to drain all tasks first, the practical impact is small. |
| C4 | Nit | overview.md:254 | "Every ending runs `complete_task`, retried without limit and run again after a cancel." | `resolve_capabilities` and `record_task` (workflow.py:211-224) run outside the `try` block. A failure there, or a cancel during them, ends the Workflow without `complete_task`. `COMPLETE_RETRY` is `maximum_attempts=0` but keeps `non_retryable_error_types=NON_RETRYABLE` (workflow.py:50), so "without limit" does not apply to those error types. "Run again after a cancel" happens at most once (`for _ in range(2)`, workflow.py:432). The claim is true for every ending after the task is recorded. |
| C5 | Nit | schemas.md:56 | "The body is inline text of at most 16 KB" | The code and the database enforce 16,384 **characters**: `CHECK (length(body) <= 16384)` (probe `\d task_messages`), `MAX_BODY = 16_384` with `len(body)` (messages.py:29,380), and `Field(max_length=16_384)` (common/schemas/messages.py:36). The overview's deviations and known limits say this correctly, but schemas.md does not. |
| C6 | Nit (ambiguous) | overview.md:252 | "`ask_agent` (deadline 1 s up to the profile's `max_ask_wait`, default 300 s)" | The 300 s default belongs to the deadline: `DEFAULT_WAIT_S = 300` (comms_mcp/server.py:28,104). It is not the default for `max_ask_wait`, which is 10 min: `max_ask_wait: timedelta = timedelta(minutes=10)` (common/schemas/capability.py:105, task.py:79,169), and the server falls back to `"600"` (server.py:105). A reader can take "default 300 s" as the default for `max_ask_wait`. A deadline above the cap is clamped, not refused (`min(wait, max_wait)`, messages.py:172). |

## Unverifiable claims (blocked: runtime only, workers stopped, tests not run)

| # | Severity | Location | Claim | Why |
|---|---|---|---|---|
| U1 | Nit | overview.md:269 | "An attempt lost after a send reruns the same step; the identical send stores nothing" | The idempotency half is confirmed by code: the key is the task, turn, tool and arguments, with no attempt (messages.py:97-101; server.py:60-61), and `_by_key` returns the stored row (messages.py:116-118, 438-452). The idempotency key is also UNIQUE in the database (`task_messages_idempotency_key_key`). The claim that the step reruns after a SIGKILL depends on checkpoints at run time. The cited `tests/integration/test_messaging_failures.py::test_a_send_before_a_killed_worker_is_delivered_once` exists but was not run. |
| U2 | Nit | overview.md:256 | "for a closed or missing Workflow the row is dropped (logged)" | The code drops the row on `RPCStatusCode.NOT_FOUND` (dispatcher.py:110-114). Whether Temporal answers NOT_FOUND when a closed Workflow is signalled cannot be observed without a running dispatcher. |
| U3 | Nit | runbook.md:194 | "Without the password the role is skipped and comms tools fail." | The skip is confirmed (roles.sh:12-15). The failure follows from the code: the worker URL `praxis_comms:${PRAXIS_COMMS_DB_PASSWORD:-}@db` (compose:153) points at a role that does not exist, and `engine()` connects on first use. It was not observed at run time. |
| U4 | Nit | runbook.md:209 | "the old code cannot replay their histories" | This is consistent with the code: v2 histories contain `claim_inbox` activities and timers that `_run_v1` never schedules (workflow.py:94-96, 342-374). Replay with the old workers was not run. |

## Confirmed claims

### overview.md, Components

1. **Migration 0006 creates `task_messages`, `task_inbox` and `message_wakes`.** Confirmed in `common/persistence/migrations/versions/0006_task_messages.py:60-104`. Probe `select version_num from alembic_version` returned `0006`.
2. **`task_messages` has one row per message, question or reply, with status, `claimed_turn` and `notice_turn`, a body of at most 16,384 characters and a unique idempotency key.** `\d task_messages` shows:
   - `kind_check` = send/ask/reply;
   - `status_check` with the 8 statuses;
   - columns `claimed_turn integer` and `notice_turn integer`;
   - `task_messages_body_check CHECK (length(body) <= 16384)`;
   - `UNIQUE CONSTRAINT ... (idempotency_key)`.
3. **`task_inbox` holds per-task `sleeping`.** `\d task_inbox`: `task_id text PK`, `sleeping boolean not null default false`.
4. **`message_wakes` allows at most one pending wake per recipient Workflow.** `\d message_wakes`: `message_wakes_recipient_workflow_key UNIQUE CONSTRAINT`.
5. **Comms role grants are given through `infra/db/roles.sh` and `make db-roles`.** Makefile:105-106 runs `exec -T -u postgres db bash /usr/local/bin/praxismesh-roles`. Compose mounts `./db/roles.sh:/usr/local/bin/praxismesh-roles` (compose:29, and the `config db` probe shows `target: /usr/local/bin/praxismesh-roles`). For the grants themselves, see C2.
6. **"`init.sh` runs `roles.sh` on a fresh volume when `PRAXIS_COMMS_DB_PASSWORD` is set."** init.sh is mounted as `/docker-entrypoint-initdb.d/20_praxismesh.sh` (compose:28) and calls `bash /usr/local/bin/praxismesh-roles` (init.sh:42). roles.sh exits early without the password (roles.sh:12-15). The `db` service receives `PRAXIS_COMMS_DB_PASSWORD` (compose:22; `config db` shows it set).
7. **The role exists.** Probe: `praxis_comms | rolcanlogin t | rolsuper f | rolcreaterole f | rolcreatedb f`. It is a member of no role (`pg_auth_members` returned 0 rows).
8. **Repository (`MessageRepository`): `send`, `ask`, `read_claimed` and `blocking_finish` are attempt writes, using the task lock and fence, then a per-request advisory lock.** Each calls `_enter` (messages.py:115, 156, 188, 211). `_enter` takes `TASK_LOCK`, checks `NO_NEWER_ATTEMPT`, then `_REQUEST_LOCK` = `pg_advisory_xact_lock(2, hashtext(:r))` (messages.py:32, 357-365).
9. **`claim` and `end_task` take only the request lock.** messages.py:238, 296.
10. **Messages go only to running tasks of the sender's request.** `_refusal` refuses when the sender is not running, the recipient is in another request, or the recipient has ended (messages.py:377-393).
11. **A refusal is stored as a `rejected` row with its reason.** `_reject` (messages.py:484-501). Probe: every `rejected` row has a reason (`no_reason=0` of 80).
12. **An identical repeat stores nothing.** `_by_key` (messages.py:116-118, 157-159).
13. **A reply must answer an open question addressed to the replier and go to its asker.** `_question_for_reply` (messages.py:395-416).
14. **A send to a sleeping recipient adds a wake row and `NOTIFY message_wakes`.** `_wake_if_sleeping` (messages.py:503-515), called from `send` (140) and `ask` (180).
15. **Comms MCP server tools.** The four tools are defined in comms_mcp/server.py:75-144, and `registry/mcp/comms.yaml` lists `tools_allowed: [send_to_agent, ask_agent, post_status, get_task_context]`.
    - `deadline_seconds < 1` is refused (server.py:101-102).
    - `post_status` takes a stage Literal and progress 0-100 (server.py:33, 122-127).
    - `get_task_context` returns the request's tasks and the caller's undelivered messages (messages.py:331-353).
16. **The server runs as a stdio subprocess per attempt, started by the worker, and takes its identity from environment variables.**
    - comms.yaml `transport: stdio`, `args: ["-m","comms_mcp"]`.
    - `build_config` per attempt sets `PRAXIS_TASK_ID`, `PRAXIS_TURN`, `PRAXIS_ATTEMPT` and `PRAXIS_MAX_ASK_WAIT` (harness_activity/config.py:62-71; activity.py:486-493).
    - No tool takes a sender; `me()` reads only the environment (server.py:49-57).
17. **Refusals return MCP errors.** `ToolError` (server.py:64-66, 89, 102, 112, 124).
18. **Comms is granted by `local-dsh` v2 and `local-default` v2.** Both templates have `version: 2` and `mcp_servers: [sample-shop, comms]`, and `secret_refs` includes `PRAXIS_COMMS_DB_URL`.
19. **Dispatcher.** `workers/main.py:197-199` starts `Dispatcher(...).run()` only for the `orchestrator` role.
    - It LISTENs on `message_wakes` (dispatcher.py:32, 62).
    - It polls every 1 s (`POLL_S = 1.0`, `wait_set(woken, self.poll_s)`).
    - Each row gets its own transaction: delete, then Signal `inbox` with `rpc_timeout=5 s`. A failed Signal triggers a rollback (dispatcher.py:36, 83-102, 107-117).
    - The connection is retried until cancelled (dispatcher.py:43-51; `CancelledError` is not caught by `except Exception`).
20. **Waiting Workflow.**
    - The patch is `WAIT_PATCH = "phase2-wait"` (workflow.py:49, 94).
    - It claims after a `waiting` turn, and with rows runs a woken turn at once (workflow.py:235-240, 289-291, 363-364).
    - It sleeps until a Signal, the earliest deadline, the idle timeout (only when there is no open question) or wall time (workflow.py:365-374).
    - Woken turns count against `max_wakes` and other turns against `max_turns` (workflow.py:241-246, 259-262).
    - At wall time, the last claim gives `succeeded` with no open question and `failed` "wall-time budget exhausted" with one (workflow.py:383-403).
    - It continues as new when suggested or after more than 1,000 events, using `TaskStart.carried` (workflow.py:52, 331-336).
    - `complete_task` retries without a limit (workflow.py:50, 432-448). See C1 and C4 for the exceptions.
21. **Harness.**
    - A woken turn's input is `render_inbox` of the rows `read_claimed` returns, read for a new turn only (activity.py:523-526, 622-629, 738-763).
    - `finish_task` is refused while there is an open question or an unread reply (`finish_task_body`, tools.py:209-222, with the query in messages.py:207-229). Both runners use it through `TurnState(finish_check=...)`: runner.py:269 and dsh/executor.py:64, sharing `build_tools`.
    - The finish is checked again after the run, and a blocked finish becomes `continue` (activity.py:581-598).
    - A `waiting` turn keeps its outputs (activity.py:680; workflow.py:289-290).
    - `post_status` results become `status` events with `source="agent"` (events.py:26-44; runner.py:234-235; dsh/executor.py:150-151).
    - The documented path `dsh/executor.py` is `harness_activity/dsh/executor.py`.
22. **CLI `--join REQ`.** cli.py:305 and 81-82. A request with no task is refused: `request {joined} has no task to join` (cli.py:89-90). The request ID is reused in submit.py:45.

### overview.md, Data flow (each line)

1. **tool call → comms_mcp → `praxis_comms` → `task_messages` (+ wakes, NOTIFY).** Confirmed by server.py:42-45, compose:153 (`praxis_comms` URL) and messages.py:503-515.
2. **dispatcher LISTEN / 1 s poll → delete row, Signal `inbox` → TaskWorkflow wakes.** Confirmed by dispatcher.py:77-117 and workflow.py:85-88, 374.
3. **claim_inbox → rows assigned to the next turn → run_harness_turn reads them.** Claim for `run.turn + 1` (workflow.py:344), then `run.turn += 1` (258). `read_claimed` filters on `claimed_turn = turn` (messages.py:189-196).
4. **Any ending → complete_task → end_task: questions cancelled, unread rows undelivered, askers woken.** Confirmed by activities.py:146-152 and messages.py:291-329.

### overview.md, Failure and recovery

- **Recipient attempt lost after its claim.** A rerun reads the same rows, because `read_claimed` selects by `claimed_turn` whatever the status (messages.py:189-196). Rows are claimed only while `status='pending'`, so a later turn does not get them (messages.py:246-253).
- **Dispatcher down.** Timers live in the Workflow (workflow.py:374). A crash before commit keeps the row, because each row has its own transaction (dispatcher.py:84-102).
- **Database down.** `claim_inbox` uses `maximum_attempts=0` with `schedule_to_close_timeout=remaining` (workflow.py:342-350). `complete_task` retries without limit (see C4).
- **Cancel.** `asyncio.CancelledError` is caught, then `_complete` runs (workflow.py:292-294). `end_task` cancels asks to the task and wakes the askers. The askers are told through `notice_turn` (messages.py:254-261, 311-329; activity.py:743-749).

### overview.md, Tests

All 14 cited test files and `infra/demo/phase-2-messaging.sh` exist (`test -f` ok for each).
- `test_task_workflow_waiting.py:101` uses `WorkflowEnvironment.start_time_skipping`.
- The acceptance tests use `local-dsh` and DSH containers.
- The named cases exist: `test_an_unanswered_question_times_out`, `test_a_cross_request_message_is_refused`, `test_a_cancelled_recipient_tells_the_waiting_asker`, `test_a_send_before_a_killed_worker_is_delivered_once`, `test_done_with_an_open_question_is_refused_and_the_task_waits`, `test_an_unread_message_to_an_ended_task_is_listed_as_undelivered`, `test_a_task_woken_100_times_keeps_every_run_bounded` and `test_50_messages_during_one_turn_bring_at_most_one_signal`.

### overview.md, Deviations

- **D11 and D16.** Both are recorded in the plan's decision log (plan.md:386-387). `carried` is a field on `TaskStart` (task.py:60-63). `${input:` is in `tests/support/fake_model/__init__.py`.
- **F97, F99, F118 and F136.** All four are in reviews.md:132, 134, 153 and 178, with the stated resolutions. The code matches: activity.py:581-598, and dispatcher.py:77-102 commits each row in its own transaction.

### overview.md, Known limits

- **Body limit in characters.** Confirmed; see C5.
- **Terminate skips `complete_task`.** No Workflow code runs on terminate.
- **Several wakes per sleep.** The dispatcher deletes a row while `sleeping` stays true until the next claim, so a later send inserts a new row (messages.py:506-513).
- **Replayed refusal.** `_by_key` returns the rejected row (messages.py:450-451).
- **Rows marked `read` stay `read`.** `end_task` undelivers only `pending` and `claimed` rows (messages.py:322-324).
- **`sh` on openai_agents.** The worker container's environment has `PRAXIS_COMMS_DB_URL` (compose config: `worker-dsh-a`/`orchestrator` env keys include it; same `*worker-env` anchor for `worker-a`). The command itself gets a scrubbed environment (`command_env`, tools.py:118-124), so it could reach the URL only through the worker process environment (for example `/proc`). This was not exercised. DSH runs commands in container `dsh-a`, whose environment is only `DSH_SHARED_GID, DSH_WORKER_UID` with `network_mode none`. The limit is also understated: the worker environment holds `APP_DB_PASSWORD` and the S3 keys as well.

### runbook.md

- **Setup.** `.env.example:56-57` defines `PRAXIS_COMMS_DB_PASSWORD` and `PRAXIS_COMMS_DB_URL`. The `db` service reads the password, so a container recreated by `make up` sees it. `make db-roles` can be rerun: it creates the role if missing, then `ALTER ROLE`, and the grants are idempotent (roles.sh:17-33). `make migrate` runs `alembic upgrade head`, which is now 0006.
- **The role may write only the message tables.** The role can write only `task_messages` (INSERT, UPDATE) and `message_wakes` (INSERT); see the grant probe under C2.
- **Waiting defaults.** `idle_timeout` defaults to 10 min and `max_wakes` to 50, capped at `min(profile.max_wakes, t.max_wakes_cap)` (capability.py:104-106; activities.py:94). `max_wakes_cap` defaults to 100. The idle-timeout ending is described incompletely; see C1.
- **Deploying.** Workers refuse other template versions (activity.py:237). The registry has only v2 templates. For the deploy order, see C3.

### schemas.md

- **`MessageEnvelope` mirrors the row.** common/schemas/messages.py:24-40 has every column except `retention_class`.
- **Statuses and kinds.** These match the database CHECK constraints.
- **`correlation_id`, `deadline` and `reply_to`.** An ask sets `correlation_id = message_id` and a deadline (messages.py:176-179). Probe: 0 asks are missing either field, apart from 24 rejected asks, which store neither.
- **`claimed_turn` and `notice_turn`.** Confirmed in messages.py:246-261.
- **Idempotency key = sender, turn, tool, arguments.** Confirmed in messages.py:97-101.
- **`InboxClaim` holds message IDs and the next deadline, never a body; `ClaimInboxInput` is task, turn, now.** Confirmed in messages.py (schemas) :43-60 and activities.py:112-120.
- **`waiting` is accepted** in `finish_task` (tools.py:211, 281), `TurnOutcome` (task.py:84) and `AttemptOutcome` (task.py:119-129). The `task_attempts` table has no outcome CHECK constraint; the probe shows only `retention_class` checks.
- **New limits.** The profile and template fields, the `ResolvedTask` defaults and `TurnInput.max_ask_wait` are in capability.py:63, 104-106 and task.py:79, 168-170.
- **`join_request`.** Defined at task.py:48 with pattern `^req-...`.
- **`TaskState` carries counters, usage, deadline and outputs.** Confirmed in task.py:173-190; it also carries `resolved` and `summary`.

### demos/phase-2.md (claims about the code and the script)

- **The script.** It runs as `sh infra/demo/phase-2-messaging.sh [OUT_DIR]` and uses `python3`, `uv` and `timeout` (script lines 27-28, 73). Every submission carries a `[script:demo-*]` marker (lines 52, 60, 84, 87, 93), and the markers are defined in `tests/support/fake_model/scripts.json`.
- **The script stops at once if a task ends instead of waiting.** `asleep()` (lines 43-47).
- **The probe.** Subcommands `sleeping`, `messages`, `history`, `batches` and `cancel` exist (messaging_probe.py:86-100), and the script runs it with `PYTHONPATH=.` (script line 28).
- **Commits.** `5b68eb6` is "Run the demo probe with the repository root on the import path". `90ad371` is "Make the demo's silent task instructions plain; stop if a task ends early". `a0faad5` exists, and `4b14066` is an ancestor of HEAD.
- **`tail --after N`.** cli.py:314.
- **`default` profile.** It is `harness: dsh` with `allowed_templates: [local-dsh]`.
- **Cleanup via `complete_task`.** The probe cancels the Workflow, and a cancel runs `_complete` (workflow.py:292-294).
- **Downgrade command.** `common/persistence/alembic.ini` exists and 0006 has a `downgrade()` (0006:107-114).

## Other observations (not documentation claims)

- **Open rows left in the shared database.** It holds 126 `pending` and 15 `claimed` rows addressed to tasks whose status is `running`. There are 59 open asks from `running` tasks, and 4 `pending` sends whose recipient has no `tasks` row.
- **Likely source.** These most likely come from integration tests that write through the repository or the role directly, without a Workflow. They do not contradict a documented claim.
- **Why it matters.** A `send` to a recipient with no `tasks` row would be refused by `_refusal`, so those 4 rows were not written through `MessageRepository.send`.

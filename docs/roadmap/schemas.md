# PraxisMesh plan: schemas and persistence model (§5)

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## 5. Versioned schemas and persistence model

Define Pydantic schemas in `common/schemas.py` (or organized modules re-exported there). Include a `schema_version` and migration strategy. Preserve the original model fields below.

- **`AgentProfile`**: `name`, `tier`, `repo?`, `new_repo_policy` (`never|ask|auto`; default `ask`), `harness` (`claude_sdk|claude_cli|openai_agents|dsh`), `model_override?`, `allowed_templates[]?`, `max_turns`, timeouts, approval policy, global budget limits. **No MCP/skills fields.**
- **`WorkerTemplate`**: `name`, `version`, `tier`, `image`, `harness`, `model`, `base_url`, `api_style` (`anthropic|openai`), `allowed_model_overrides[]`, CPU/memory/GPU resource spec, `mcp_servers[]`, `skills_bundle`, `cli_tools[]`, derived `capabilities[]`, `concurrency_per_pod`, `context_window?` (tokens; required for `dsh`), min/max backlog/cooldown scaling, `secret_refs[]`, `repo_capable`, `cost_weight`.
- **`McpServer`**: `name`, transport (`stdio|sidecar|service`), command/image/url, env/secret refs, capability tags, health check.
- **`TriageResult`**: complexity (`trivial|moderate|hard`), delivery (`inline|artifact|repo`), `repo?`, `needs_plan`, rationale, signals (context size/tools/risk), estimated budget/capability needs.
- **`PlanSchema`**: `plan_id`, `revision`, `goal`, `repo?`, tasks with `id`, title, instructions, `depends_on[]`, tier, `required_skills[]`, `required_tools[]`, acceptance criteria, `risk` (`low|med|high`), optional budget. Validate DAG cycles, references, limits and stable task IDs; retry bad plans at most N times.
- **`TaskResult`**: `task_id`, status (`succeeded|failed|needs_input`), summary, `artifacts[]` (immutable `BlobRef`, branch/commit paths), questions, `tier_used`, turns, tokens, attempt ID, verification metadata. Keep in-Temporal result small.
- **`AgentEvent`**: `seq`, timestamp, workflow/task IDs, **attempt ID**, type (`status|token|tool_call|tool_result|plan|approval_request|result|error|reset`), small payload, optional `blob_ref`. Durability/retention metadata.
- **`BlobRef`**: backend-independent opaque ID, object key/version, checksum, content type, bytes, optional tenant/repo and retention information; never expose underlying credentials.
- **`MessageEnvelope`**: message ID, sender, recipient, correlation ID, reply-to ID, TTL/deadline, status, authorization context, payload ref, idempotency key.
- **`Conversation`/`Response`/`Request`**: conversation ID, response ID, request ID/idempotency key, parent/previous response ID, workflow ID/run IDs, requester policy, status, delivery, timestamps.
- **`ExecutionAttempt`/`BudgetLedger`**: task/turn attempt, failure category, tier/template, predicted/actual tier, token/time/cost counts, quality retry/escalation/replan counts.
- **`GitHubDelivery`**: repo, integration branch, task branch SHAs, PR number/node ID, current head SHA, CI status checked against SHA, approval status, stable operation keys.
- **`WorkflowTemplate`/`WorkflowRun`**: immutable template ID/version, ordered stage DAG, stage role/capability policy, allowed skill/template refs, artifact input/output contracts, evidence/approval rules, total budget, run ID and immutable resolved template version.
- **`StageExecution`/`ReviewEvidence`**: stage ID and attempt, assigned role/identity, required input ref/revision, Git SHA/artifact checksum, isolated session ID, reviewer skill/policy version, verdict (`pass|fail|blocked|needs_input`), tests/checks, evidence refs, approval provenance, invalidation status and idempotency key.
- **`RepositoryProvisioning`**: authorized owner/org, desired repo name/visibility, requester and approval, provider operation ID, verified created repo identity, resulting permissions/protection status, idempotency/reconciliation state.
- **`RepoEvent`/`ScheduleConfig`/`Approval`/`AuditEvent`**: unique webhook delivery ID/event type/repo, normalized payload ref, dispatch status, versioned schedule rules, approval decision provenance and append-only audit entries.

### PostgreSQL application persistence

Create migrations (e.g., Alembic) for conversations/responses, plans/revisions, task executions/attempts, agent inbox/outbox, event index, budgets, blob metadata, GitHub deliveries, webhook inbox/outbox, repo schedules, approvals, versioned workflow templates/runs, stage execution/review evidence, repository provisioning, and audit. Migrations land with the phase that first needs them: baseline in Phase 0, checkpoint/attempt tables in Phase 1, inbox/event tables in Phase 2, the bulk in Phase 3A, delivery tables in Phase 5, and workflow-template/stage tables in Phase 6B. Use tenant/repository access checks and indexes for primary query patterns. External I/O occurs only through Activities/services. Do not use database records as hidden mutable Workflow replay state.

As built for the DSH migration (migration 0004, plan D1, D7, D9): attempt token
counts are nullable, with `usage_known` false when usage could not be observed
(stored as NULL, never 0); `usage_ledger` records each model request before
dispatch and its settled usage; checkpoints may carry a session blob
(`session_ref`, `session_digest`). `TurnOutcome`, `TaskResult` and
`ExecutionAttempt` carry `usage_known` (default true).

As built for the Phase 2 events plan (migration 0005, plan D1-D3): `AgentEvent`s
are stored in `agent_events` at a gap-free `offset` per workflow (the task's
workflow ID), with `event_logs` holding each workflow's next offset and retained
base and `event_batches` the batch IDs (`<workflow>:<attempt_id>:<n>`) seen in the
last 600 s, so a re-sent batch is stored once. All three carry retention class
`task`. `seq` stays per attempt. Event types and payloads (counts, names, IDs and
statuses only; never model or tool text):

| Type | Payload | Emitted by |
| --- | --- | --- |
| `reset` | `restored_from` (checkpoint ID, or null for a fresh start or a failure before the lookup) | the Activity, first event of every attempt that records itself (an attempt refused by the fence at start, or past its attempt limit, stores no events) |
| `token` | `input_tokens`, `output_tokens` (DSH adds `request_id`) | both runners, one per model response |
| `tool_call` | `tool`, `call` | both runners |
| `tool_result` | `tool`, `call`, `status` (`refused` for a tool the template does not grant; its name is capped at 64 characters) | both runners |
| `status` | `status` (the runner's result, not the recorded outcome), `error` on failure | the Activity, last event of every attempt except a superseded one or one whose worker was killed |

As built for the Phase 2 messaging plan (migration 0006, plan D6, D7, D13): messages
between tasks of one request are rows of `task_messages`, mirrored by `MessageEnvelope`
(`common/schemas/messages.py`). The body is inline text of at most 16,384 characters (`length(body)`,
not bytes), not a blob reference; the authorization context is the request (`request_id`). A question has a
`correlation_id` and a `deadline`; a reply names it in `reply_to`. Statuses: `pending`,
`claimed` (assigned to a turn, `claimed_turn`), `read`, `answered`, `expired`,
`cancelled` (the asker is told through `notice_turn`), `undelivered` and `rejected` (a
refusal, with its `reason`). The idempotency key is the sender, turn, tool and
arguments. `task_inbox` records whether a task is sleeping; `message_wakes` holds at
most one pending wake per recipient. `claim_inbox` returns an `InboxClaim`: message
IDs and the next deadline, never a body. `finish_task`, `TurnOutcome` and attempt outcomes
accept `waiting`. Profiles gain `idle_timeout`, `max_ask_wait` and `max_wakes`; templates
gain `max_wakes_cap`; `ResolvedTask` carries all three (defaulted, so earlier payloads
decode) and `TurnInput` carries `max_ask_wait`. `TaskRequest.join_request` puts a task
in an existing request. A waiting `TaskWorkflow` continues as new with `TaskStart.carried`
set to its `TaskState` (counters, usage, the wall-time deadline, the latest outputs).

As built for the Phase 3A persistence plan, phase 01 (migration 0007; plan
`docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle`, D2, D3, D7):
- **Retention classes** are §4.13's `ephemeral` (1 day after the write),
  `checkpoint` (7 days), `transcript` (30 days) and `artifact` (90 days), each
  counted from the task's `tasks.ended_at`, and `audit` (kept). `RetentionClass`
  keeps the Phase 1-2 value `task` so recorded payloads decode; it ranks as
  `transcript` and nothing writes it. Each table's class is the plan's
  notes.md#d3 table (`common/persistence/retention.py`, `TABLE_CLASS`); every
  check still allows `task`.
- **`blob_refs`**, the reference index: one row per holder and blob key
  (`holder_table`, `holder_key` as the holder row's primary key in text,
  `holder_column`), with `task_id`, `request_id` (null for an upload), class,
  `created_at`, `removed_at` and `removed_by`. Every row that stores a `BlobRef`
  (`tasks`, `checkpoints`, `agent_events`) writes its index rows in its own
  transaction; every upload made for a task is held by the task (`upload`, task
  ID, ''). Removed references stay, marked. Expiry is computed, never stored.
- **`audit_log`**: `actor` (`cli:<OS user>`), `action`, `subject`,
  `operation_id`, `details` (counts and IDs, never content), class `audit`; a
  trigger refuses `UPDATE` and `DELETE`.
- **New columns:** `tasks.ended_at` (set by `end_task`); `blob_objects.removed_at`,
  `removed_by`, `last_put_at` (each `put`) and `bucket_deleted_at`.
- **Outbox pattern (§4.13):** where a database write and a second service cannot
  commit together, commit a row with the write and let one drainer act on it,
  idempotently, deleting the row only after the other service accepts. The
  Phase 2 wake rows (`message_wakes`, drained by the dispatcher into `inbox`
  Signals, ADR-0010) are the one instance so far; no general outbox table
  exists until a second service needs one (Phase 5's GitHub delivery).

### `BlobStore` contract

Provide a narrow async Python interface with `put`, `get/stream`, `delete`, `stat`, optional presigned/access-controlled URL operation, and typed error handling. The default adapter targets **SeaweedFS via S3-compatible API**. Ceph RGW uses the S3 adapter with configuration changes; GCS uses a dedicated adapter when enabled. Verify backend semantics for multipart uploads, versioning, conditional writes, signed URLs and integrity instead of assuming perfect interchangeability.

# PraxisMesh plan: schemas and persistence model (§5)

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## 5. Versioned schemas and persistence model

Define Pydantic schemas in `common/schemas.py` (or organized modules re-exported there). Include a `schema_version` and migration strategy. Preserve the original model fields below.

- **`AgentProfile`**: `name`, `tier`, `repo?`, `new_repo_policy` (`never|ask|auto`; default `ask`), `harness` (`claude_sdk|claude_cli|openai_agents`), `model_override?`, `allowed_templates[]?`, `max_turns`, timeouts, approval policy, global budget limits. **No MCP/skills fields.**
- **`WorkerTemplate`**: `name`, `version`, `tier`, `image`, `harness`, `model`, `base_url`, `api_style` (`anthropic|openai`), `allowed_model_overrides[]`, CPU/memory/GPU resource spec, `mcp_servers[]`, `skills_bundle`, `cli_tools[]`, derived `capabilities[]`, `concurrency_per_pod`, min/max backlog/cooldown scaling, `secret_refs[]`, `repo_capable`, `cost_weight`.
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

### `BlobStore` contract

Provide a narrow async Python interface with `put`, `get/stream`, `delete`, `stat`, optional presigned/access-controlled URL operation, and typed error handling. The default adapter targets **SeaweedFS via S3-compatible API**. Ceph RGW uses the S3 adapter with configuration changes; GCS uses a dedicated adapter when enabled. Verify backend semantics for multipart uploads, versioning, conditional writes, signed URLs and integrity instead of assuming perfect interchangeability.

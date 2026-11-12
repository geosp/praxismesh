---
title: Phase 1 harness-in-Activity, single agent
type: rfc
tier: light
status: draft
phase: 1
issue: "#44"
openspec_change: openspec/changes/phase-1-single-agent
plan_sections: [Phase 1, "§2", "§4.1", "§4.2", "§4.10", "§4.13", "§5", "§6", "§8"]
size: L
hardware: x86_64 workstation with Docker (no GPU); vLLM on the DGX Spark pair for real-model runs; CI uses a scripted fake model endpoint
pre0_inputs: [harness decision (go, openai_agents default), model per tier (spark: qwen3.8-flash-next)]
date: 2026-11-11
authors: [owner, coding agent]
revision: 2 (addresses the design review of e437d0f, docs/reviews/phase-1/design-review.md)
---

# RFC: Phase 1 harness-in-Activity, single agent

## Background

Phase 0 built the local stack: Temporal, ParadeDB, SeaweedFS, and an external vLLM endpoint. Phase 1 adds the first product code. One agent, on the local model, does useful work as a durable Temporal task and survives the loss of its worker mid-task. Tracking issue: #44.

Plan references:
- [PROJECT_PLAN.md](../../PROJECT_PLAN.md) and its document map;
- [the Phase 1 file](../plan/phases/phase-1.md), the [design decisions](../plan/design-decisions.md) §4.1, §4.2, §4.10 and §4.13, and the [schemas](../plan/schemas.md) §5.

The Pre-0 spike, [docs/spikes/harness-vllm.md](../spikes/harness-vllm.md), ran both harnesses against the local model. Its 10 tasks seed the benchmark suite.

Owner decisions (decision log, 2026-11-11):
- Both harness runners sit behind one `HarnessRunner` interface, with **`openai_agents` as the default** while the Claude Agent SDK's licensing with local models is open (plan §2).
- The benchmark regression limit is **at most 1 task lost out of 10**.
- Under Compose, "pod loss" means **stopping one worker container while a second one takes over**.

APIs checked on 2026-11-11 by reading the installed packages (plan §2: verify live APIs):

| Package | Version | What this design relies on |
|---|---|---|
| `openai-agents` | 0.24.0 (MIT) | `Runner.run(..., max_turns, session=, run_config=, hooks=)` <br> `RunConfig(tracing_disabled, tool_not_found_behavior)`; the defaults are `False` and `"raise_error"` <br> `set_tracing_disabled()` <br> `RunHooks.on_llm_start/on_llm_end/on_tool_start/on_tool_end` <br> the `Session` protocol and `extensions.memory.SQLAlchemySession` <br> `MCPServerStdio` with `tool_filter` |
| `claude-agent-sdk` | 0.2.180 (MIT; bundles the Claude Code CLI) | `ClaudeAgentOptions` fields: <br> `tools`, `allowed_tools`, `disallowed_tools` <br> `permission_mode` (including `"dontAsk"`) <br> `mcp_servers`, `strict_mcp_config`, `setting_sources`, `plugins`, `skills` <br> `resume`, `session_store`, `effort`, `cwd`, `env`, `cli_path`, `hooks` <br> the `SessionStore` protocol and `SessionKey(project_key, session_id, subpath)` <br> **`env` is merged over the parent process environment** |
| `temporalio` | 1.36.0 (MIT) | `start_workflow(id_reuse_policy, id_conflict_policy)`; **the default reuse policy is `ALLOW_DUPLICATE`** <br> heartbeat details, which the next attempt reads from `activity.info().heartbeat_details` <br> `WorkflowEnvironment` (time-skipping) and `Replayer` <br> `contrib.opentelemetry.TracingInterceptor` <br> `contrib.pydantic` |
| `opentelemetry-sdk`, `-exporter-otlp` | 1.45.2 (Apache-2.0) | Spans and OTLP export. Checked on PyPI only, not installed yet; PR 1 verifies the API in use |

### Terms

| Term | Meaning |
|---|---|
| **Template** (`WorkerTemplate`) | The unit of capability: model, endpoint, MCP servers, skills, tools and limits. Workers poll one template's queue, `tpl.{template}`. |
| **Profile** (`AgentProfile`) | Who the agent is, and the task-level limits. It grants no capabilities. |
| **Inner turn** | One model call inside a harness invocation. This is the SDK's `max_turns`, capped per Activity by the template's `inner_max_turns`. |
| **Harness turn** | One `run_harness_turn` Activity, which is one bounded harness invocation. Capped per task by the effective `max_turns`. |
| **Attempt** | One execution of a harness turn. Temporal retries after infrastructure failures create further attempts. They never count as harness turns. |
| **Checkpoint** | A committed `checkpoints` row recording a session position and a workspace snapshot `BlobRef`. It counts as **acknowledged** once its row is committed. |
| **Budget** | Per-task limits on harness turns, tokens and wall time: the smaller of the profile's value and the template's cap. |
| **`stack` job** | The CI job that runs the Compose stack and the integration tests (Phase 0). |

## Plan

### Components and repository layout (plan §6)

```mermaid
flowchart LR
  cli[praxis CLI] -->|start TaskWorkflow| t[(Temporal)]
  subgraph orch [orchestrator worker: queue orchestration]
    wf[TaskWorkflow]
    acts[resolve_capabilities<br/>record_task / finish_task]
  end
  subgraph w1 [worker container A: queue tpl.local-default]
    h1[run_harness_turn<br/>HarnessRunner]
  end
  subgraph w2 [worker container B: same queue]
    h2[run_harness_turn]
  end
  t <--> wf
  wf -->|Activities| acts
  wf -->|harness turns| h1 & h2
  h1 & h2 --> db[(praxismesh DB)]
  h1 & h2 --> s3[(SeaweedFS)]
  h1 & h2 --> vllm[vLLM on the Sparks<br/>or the fake model in CI]
  h1 & h2 --> mcp[sample MCP server<br/>stdio, one per invocation]
```

| Path | Contents |
|---|---|
| `common/schemas/` | Pydantic models with `schema_version`: <br> `AgentProfile`, `WorkerTemplate`, `McpServer` <br> `TaskRequest`, `TaskResult`, `TurnInput`, `TurnOutcome` <br> `BlobRef`, `ExecutionAttempt` <br> These are the §5 fields that Phase 1 needs. |
| `common/blob_store/` | The `BlobStore` protocol, typed errors, an in-memory fake, the S3 adapter and the contract suite |
| `common/persistence/` | Migration `0003`, `retention.py` and repositories. Reuses `settings.app_database_url`. |
| `common/observability/` | JSON logging with context IDs, OpenTelemetry setup and Prometheus metrics |
| `registry/` | `profiles/*.yaml`, `templates/*.yaml`, `mcp/*.yaml`, `skills/<bundle>/`, `registry.lock`, and the loaders |
| `orchestrator/` | `TaskWorkflow`, its Activities, and the CLI (`python -m orchestrator.cli`, because `[tool.uv] package = false` allows no script entry points) |
| `harness_activity/` | `run_harness_turn`, `HarnessRunner`, `OpenAIAgentsRunner`, `ClaudeSdkRunner`, the session stores, workspace snapshots and `run_command` |
| `sample_mcp/` | The sample MCP server (stdio) |
| `comms_mcp/` | A stub; messaging arrives in Phase 2 |
| `workers/` | The generic worker entry point and `Dockerfile` |
| `tests/support/fake_model/` | The deterministic fake model endpoint, used by CI and the recovery check (below) |
| `tests/benchmarks/agent_tasks/` | The benchmark suite. Results go to `docs/benchmarks/`. |

### Capability model (§4.10, §5)

**`WorkerTemplate`**
- `name`, `version`, `harness`
- `model`, `base_url_env` (the name of the `infra/.env` variable that holds the base URL, for example `VLLM_BASE_URL`), `api_style` (`openai` or `anthropic`), `allowed_model_overrides[]`, `effort` (for the Claude runner; Pre-0.1 showed that the model rejects `high`)
- `mcp_servers[]` (names in the catalog), `skills_bundle`, `cli_tools[]`
- `inner_max_turns`, `turn_timeout`, `heartbeat_timeout`
- caps: `max_turns_cap`, `max_tokens_cap`, `max_wall_time_cap`
- `secret_refs[]` (names of `infra/.env` variables that the worker may pass to named MCP servers)
- `concurrency_per_pod`, and the resource and scaling fields of §5, which are stored but unused until Phase 7

Derived `capabilities[]` (MCP tool names, skills, tools) are recorded with each task for audit. Nothing in Phase 1 schedules by them.

**`AgentProfile`**
- `name`, `tier`, `harness`, `model_override?`
- `allowed_templates[]` (the first entry is the default), `max_turns`, `max_tokens`, `max_wall_time`
- **No MCP or skills fields.** Unknown fields are forbidden.

**`McpServer`**
- `name`, `transport` (Phase 1 runs `stdio` only)
- `command`, `args`, `env` (literal, non-secret), `secret_env` (variable names taken from the template's `secret_refs`), `tools_allowed[]`

**`TaskRequest`**
- `task_id?`, `profile`, `template?` (must be in `allowed_templates`), `instructions`, `input_files[]` (paths to upload), `outputs[]` (workspace paths to return as artifacts)
- Unknown fields are forbidden.
- A request that names skills, MCP servers or tools is rejected. The CLI checks this, and `resolve_capabilities` checks it again.

**Choosing the harness and the template.** The template's `harness` is authoritative. A profile whose `harness` differs from the chosen template's is rejected with `CapabilityError`.

**Versions.** `registry/registry.lock` maps each template `name@version` to the sha256 of its file, and CI checks it. A file changed without a version bump fails to load, with a message that names the template. Each task records `template@version` and its hash in `TurnInput`. A worker whose loaded hash differs rejects the turn with a non-retryable `CapabilityError`. This stops a rolling change from mixing versions within one task.

### `BlobStore` contract (§4.13, §5)

- **Operations:** `async put(data | stream, *, content_type, retention) -> BlobRef`, `get(ref) -> bytes`, `stream(ref) -> AsyncIterator[bytes]`, `stat(ref) -> BlobRef`, `delete(ref)`.
- **Keys** are content-addressed (`sha256/<hex>`). A `put` of existing content returns the same `BlobRef`. If the new call names a stronger retention class, the stronger class wins (`ephemeral` < `task` < `audit`).
- **`BlobRef`:** `id`, `key`, `checksum`, `content_type`, `bytes`, `retention_class` and `created_at`. It never carries credentials.
- **Typed errors:** `BlobNotFound`, `BlobCorrupt` (the checksum does not match on read), `BlobUnauthorized`, and `BlobUnavailable` (retryable).
- **S3 adapter:** boto3 runs in a thread, with the same path-style client configuration as `tests/support/stack.py`. One bucket comes from configuration (a new key in `infra/.env`). Every `put` records a row in `blob_objects`.
- **Contract suite:** one suite runs against the fake in unit tests and against SeaweedFS in the `stack` job.

### Retention classes (§4.13)

Every blob and every stored row carries a `retention_class` from its first write: `ephemeral`, `task` or `audit`. `common/persistence/retention.py` holds the default lifetimes. Deletion and garbage collection arrive in Phase 3A.

| What | Class |
|---|---|
| Workspace snapshots | `task` (one class, so no mixed dedup) |
| Input files and instructions | `task` |
| Output artifacts, attempts, idempotency records, `TaskResult` | `audit` |

### Application database: migration `0003` (§5)

| Table | Unique / upsert key | Notes |
|---|---|---|
| `tasks` | `task_id` | `workflow_id`, `profile`, `template`, `template_version`, `template_hash`, `instructions_ref`, `status`, `result_ref`, timestamps, `retention_class` |
| `task_attempts` | (`task_id`, `turn`, `attempt`) | Inserted when an attempt **starts**, updated when it ends: `worker_identity`, `outcome`, `failure_category`, `tokens_in`, `tokens_out`, `tool_calls` |
| `checkpoints` | (`task_id`, `turn`, `attempt`, `seq`) | `session_id`, `session_position`, `workspace_ref` |
| `idempotency_keys` | `key` | `task_id`, `tool`, `result` (small JSON) |
| `blob_objects` | `key` | `checksum`, `bytes`, `content_type`, `retention_class` |
| `sample_orders` | `order_id` | Written only by the sample MCP server. `idempotency_key` is unique. |
| `agent_sessions`, `agent_messages` | as defined by `SQLAlchemySession` | Created by the migration with the SDK's layout, never with `create_tables=True` |
| `claude_session_entries` | (`project_key`, `session_id`, `subpath`, `seq`) | The Claude `SessionStore` adapter |

Every table has `retention_class NOT NULL`. On the three session-store tables and `sample_orders` it also has `DEFAULT 'task'`, so rows that an SDK inserts without naming the column still get a class.

`TaskWorkflow` never reads these tables as hidden replay state. All database access happens in Activities.

### `TaskWorkflow` (orchestration queue)

```mermaid
sequenceDiagram
  participant C as praxis CLI
  participant W as TaskWorkflow
  participant A as orchestrator Activities
  participant H as run_harness_turn (tpl queue)
  C->>C: validate request, mint task_id, upload inputs and instructions as blobs
  C->>W: start(task_id, profile, template, refs) with REJECT_DUPLICATE
  W->>A: resolve_capabilities -> template@version+hash, effective budget
  W->>A: record_task
  loop until done, needs_input, failed, or budget exhausted
    W->>H: TurnInput(task_id, turn n, template hash, latest checkpoint, remaining budget)
    H-->>W: TurnOutcome(status, checkpoint, usage incl. lost attempts, summary)
    W->>W: account turns, tokens, wall time
  end
  W->>A: finish_task -> TaskResult (outputs as BlobRefs)
  W-->>C: TaskResult
```

**Starting a task**
- **Task ID:** the CLI mints `task_id` (`task-` plus a UUIDv4) unless the request gives one. The Workflow ID is the `task_id`.
- **One task, one run:** the Workflow starts with `id_reuse_policy=REJECT_DUPLICATE` and `id_conflict_policy=FAIL`. A second start with the same ID is rejected, whether the first run is still running or has finished. That keeps idempotency keys from one run from leaking into another.
- **Instructions and input files** are uploaded as `task` blobs before the start. Workflow inputs carry only IDs and `BlobRef`s.

**Each harness turn**
- **Placement:** an Activity on `tpl.{template}`.
- **Timeouts:** `start_to_close = turn_timeout`, the template's `heartbeat_timeout`, and `schedule_to_close = 6 × turn_timeout`. The last one bounds a turn's retries. A queue that has no worker at all waits until `schedule_to_close`; this is accepted for Phase 1 (§4.3 scales from zero later).
- **Retries** cover infrastructure failures only, up to 5 attempts with backoff. These errors are non-retryable: `CapabilityError`, `BudgetExceeded`, `InvalidTaskInput` and `HarnessProtocolError` (for example a `ModelBehaviorError` from the SDK).

**Outcomes and budgets**
- A turn returns `done`, `continue` (its inner-turn limit was reached and work remains) or `needs_input`.
- `needs_input` ends the task with status `needs_input`. That status is terminal in Phase 1; answering questions arrives in Phase 2.
- **Usage** in a `TurnOutcome` includes the tokens and tool calls of earlier lost attempts of the same turn, read from their last heartbeat details. Budgets therefore count work done by a worker that was later lost.
- **Wall time** is checked between turns. A single turn can overrun it by at most its own `schedule_to_close`.
- **Exhausted budget:** the task ends `failed` with the reason, and the last checkpoint is kept.

**Tests:** replay tests against committed histories, using the same pattern as `tests/test_hello_replay.py`, and time-skipping tests with mocked Activities: retry, timeout, budget exhaustion, `needs_input`, and a non-retryable error (§8).

### `run_harness_turn` (§4.1)

1. **Start.** Upsert the `task_attempts` row as started. Reject the turn if the template hash in `TurnInput` differs from the one this worker loaded.
2. **Restore.** Find the newest checkpoint for the task by reading `checkpoints`, preferring the highest attempt and then the highest `seq`. Unpack its workspace snapshot into a fresh directory under the worker's scratch volume; turn 1 starts from the task's input files. Restore the session, then truncate it to the checkpoint's `session_position` (see Sessions).
3. **Configure, from the template only.**
   - **For both runners:**
     - the model client from `base_url_env`;
     - the MCP servers, spawned as stdio subprocesses with `tool_filter` set to `tools_allowed`, and an environment of their literal `env` plus `PRAXIS_TASK_ID` plus only their declared `secret_env`;
     - the skills bundle, copied read-only to `.skills/` and listed in the instructions;
     - the built-in tools `read_file`, `write_file` and `list_files`, plus `run_command` if `cli_tools` is non-empty.
   - **The OpenAI runner also:**
     - runs with `RunConfig(tracing_disabled=True, tool_not_found_behavior="return_error_to_model")`;
     - has the worker call `set_tracing_disabled(True)` at startup, so nothing is ever sent to the SDK's default trace backend.
   - **The Claude runner also** (see the Claude runner section).
4. **Run** for at most `inner_max_turns` inner turns.
   - **Heartbeat** every `heartbeat_timeout / 3`. The details are the latest checkpoint ID, the inner turn, and tool-call and token counts so far.
   - **Checkpoint** when an inner turn has changed the workspace or added session items. The hook point is the **next `on_llm_start`**: by then the SDK has saved the previous turn's items to the session. A final checkpoint is also taken after `Runner.run` returns. A checkpoint does three things:
     1. packs the workspace deterministically: sorted entries, `mtime`, `uid` and `gid` set to 0, gzip `mtime=0`, `.skills/` excluded;
     2. `put`s it off the event loop;
     3. inserts the `checkpoints` row with the session's current item count.
5. **Finish.**
   - **Outputs:** upload the request's `outputs[]` as `audit` blobs on `done`.
   - **Attempt row:** update it with the outcome and the counts.
   - **Return** a `TurnOutcome` with a summary of at most 2 KB.

**Sessions**
- **`openai_agents`:** an `SQLAlchemySession` on the `praxismesh` database (asyncpg), keyed by `task_id`.
  - **When the SDK writes:** it saves a turn's items once the turn's tool calls have finished, not item by item.
  - **Position:** `session_position` is the number of session items at the checkpoint. On restore, items beyond it are removed with `pop_item`. A test covers this ordering: a checkpoint's item count matches its workspace.
- **`claude_sdk`:** a `SessionStore` adapter on `claude_session_entries`, with `SessionKey.project_key = task_id`. Using the task ID, not the working directory, means a restore into a new directory on another worker finds the session.
  - **Position:** `session_position` is the entry count. On restore, the adapter deletes entries beyond it, then the runner starts with `resume=<session_id>`.
  - **To verify in PR 3:** whether the CLI resumes from the store alone on another worker. If it can't, the plan's fallback applies (§7.1 risk table): restart the turn from the checkpoint's workspace with a transcript summary, recorded as a deviation.

**Overlapping attempts.** An attempt that outlives its heartbeat timeout can run alongside its replacement. Checkpoints are keyed by attempt and restore prefers the highest attempt. A late write from an older attempt therefore never replaces the newer one's position. The older attempt's Activity result is discarded by Temporal.

### The Claude runner (optional extra)

Configuration:

| Option | Value |
|---|---|
| `tools` | the base set the template allows (`Read`, `Write`, `Edit`, `Glob`, `Grep`, plus `Bash` only if `cli_tools` is set) |
| `allowed_tools` | the exact names: those base tools, plus `mcp__<server>__<tool>` for each allowed MCP tool |
| `permission_mode` | `"dontAsk"`, so anything not allowed is refused instead of prompting |
| `strict_mcp_config` | `True` |
| `setting_sources` | `[]` |
| `plugins` | one local plugin directory, generated from the skills bundle, so the bundle's skills load without user or project settings |
| `effort` | from the template |
| `session_store` and `resume` | as in Sessions |

**Environment.** The SDK merges `env` over the worker's own environment, so the runner sets `cli_path` to a wrapper, `harness_activity/claude/clean-env-claude`. The wrapper runs `env -i` with an explicit list:
- `PATH`;
- `HOME`, set to a per-attempt scratch directory;
- `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` and the `ANTHROPIC_DEFAULT_*_MODEL` variables from the template;
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`;
- `CLAUDE_CODE_EFFORT_LEVEL`.

Neither the CLI nor its `Bash` tool sees the worker's credentials.

**Counting.** The SDK's `PostToolUse` hook and its result messages provide the tool-call and token counts, the equivalent of `RunHooks`.

**Test** (`test_claude_runner_isolation`): the workspace contains `.claude/settings.json`, `.claude/skills/rogue/` and an `.mcp.json`, and the worker environment carries a canary credential. The test runs the CLI against the fake model's Anthropic endpoint and checks the request the CLI sent:
- the tool list holds only the allowed names;
- no rogue skill appears;
- a `Bash` call to `env` does not show the canary.

The test runs in the `stack` job, which installs the `claude` extra. Installing it in CI is not publishing.

### Side effects and idempotency (§4.2)

- **The sample MCP server computes the key.** It is the sha256 of `PRAXIS_TASK_ID`, the tool name and the canonical JSON of the arguments. The key excludes the model's tool-call ID, because that ID changes when a model repeats a call after a crash.
- **One transaction.** `record_order` inserts into `sample_orders` and `idempotency_keys` in a single transaction. A repeat returns the recorded result.
- **Credentials.** The server reaches the database through `PRAXIS_SAMPLE_DB_URL`, a `secret_env` entry that the template's `secret_refs` allow. It is passed only to this server's subprocess.
- **Intended consequence for the sample:** two identical `record_order` calls in one task are one order. The skill says to record each order once. A real tool that needs repeats would add a caller-supplied sequence number to its arguments.

### The sample skill and MCP server

- **`sample_mcp` (stdio).**
  - Read-only tools: `lookup_price(sku)`, `lookup_stock(sku)`, `get_discount(code)` and `get_setting(key)`. The last two cover the spike tasks that need them.
  - Side-effecting and idempotent: `record_order(sku, qty)`.
- **The `order-desk` skill bundle** (`registry/skills/order-desk/`): its `SKILL.md` says how to write `order-summary.md` (format, rounding) and to record each order once.
- **Template `local-default@1`:**

  | Setting | Value |
  |---|---|
  | `harness` | `openai_agents` |
  | `model` | `spark` |
  | `base_url_env` | `VLLM_BASE_URL` |
  | MCP server | `sample-shop` |
  | Skills | `order-desk` |
  | `cli_tools` | `python3`, `wc`, `git`, `sh` |
  | `inner_max_turns` | 8 |
  | `turn_timeout` | 10 min |
  | `heartbeat_timeout` | 30 s |
  | `max_turns_cap` | 10 |
  | `max_tokens_cap` | 2 M |
  | `max_wall_time_cap` | 1 h |

- **Profile `default`:** `max_turns` 6. `allowed_templates` is `[local-default]`.

### Command tool and containment (Phase 1 level)

`run_command` runs only in the task workspace, inside the worker container.
- **Environment:** minimal (`PATH`, `HOME` set to the workspace, `LANG`). No credentials or template secrets reach it.
- **Limits:** a timeout and capped output.
- **Allow-list:** offered only when `cli_tools` is non-empty, and the command's first word must be listed.

This is **not** a sandbox for untrusted code. Egress is not restricted, and a pipe can call any binary in the image. The sandbox is the Phase 5 ADR (§2), and the threat model records this as an accepted Phase 1 risk.

### Deterministic fake model (`tests/support/fake_model/`)

A small HTTP server that serves the OpenAI chat-completions and Anthropic Messages endpoints, reached through `base_url_env` like the real one. CI uses it instead of a real model: deterministic stubs, §8.

- **Replies come from the conversation, not from its own state.** A script maps "the number of tool results in the request's message history" to the next reply (a tool call or a final answer). Any worker that resends the same history therefore gets the same next step.
- **Proving the conversation survived.** The recovery check sends worker B the history recorded by worker A. A fresh session would restart at step 0, and the test would fail.
- **A pause point.** A script step can be marked `pause`: the server holds that response until the test releases it through `POST /control/release`, and `GET /control/state` shows which steps were served.
- **Request log.** The server records the requests it receives, for the Claude isolation test.

### Recovery check (`make recovery-check`, run in the `stack` job)

1. Start the `workers` profile with the fake model. Submit a scripted task: write a file, call `record_order`, then keep working until the pause step.
2. Wait until `checkpoints` shows a row after the `record_order` step and the fake model reports it is paused. Find the worker that holds the attempt from `task_attempts.worker_identity`, then stop that worker's container.
3. Release the pause. The held response goes to a dead connection.
4. After `heartbeat_timeout`, check that:
   - the other worker resumed the same `task_id` and Workflow ID;
   - the restored workspace contains the file;
   - the fake model received the full prior history;
   - `sample_orders` has one row;
   - the task completes.
5. Restart the stopped worker and clean up.

`test_side_effect_not_repeated_after_crash` runs the same check with the pause placed between `record_order` and the next checkpoint.

### Workers and Compose

- **`workers/Dockerfile`:** a Python 3.11 image with the project installed through uv. The Claude extra and its CLI are installed **only when the image is built** with `INSTALL_CLAUDE_HARNESS=1`, on the installer's machine. No image is published (§2).
- **Compose profile `workers`:**
  - `orchestrator` polls `orchestration`;
  - `worker-a` and `worker-b` poll `tpl.local-default`;
  - each worker has its own scratch volume, plus the database, S3 and model settings from `infra/.env`.
- **New `infra/.env` keys:** `S3_BUCKET`, `PRAXIS_SAMPLE_DB_URL` and `OTEL_EXPORTER_OTLP_ENDPOINT`. They are added to `infra/.env.example` and to `check-prereqs.sh`'s list of known keys.
- **New targets:** `make workers-up`, `workers-down`, `task PROMPT=…`, `task-status ID=…` (status, turns, attempts and the latest checkpoint), `recovery-check` and `benchmark`.

### Observability baseline

- **Logs:** JSON lines with `request_id`, `task_id`, `workflow_id`, `turn`, `attempt` and `worker`, set from Workflow and Activity info through `contextvars`. Conversation IDs arrive with conversations in Phase 2.
- **Traces:** OpenTelemetry with Temporal's `TracingInterceptor` on the client and the workers. The runners' hooks add child spans for model and tool calls. Export uses OTLP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise nothing is exported. The SDK's own tracing is off (Configure). Tests use an in-memory exporter and check:
  - the parent-child chain from submission to tool calls;
  - that no `openai-agents` trace processor is registered.
- **Metrics:** `prometheus-client` serves `/metrics` on each worker: Activity duration, heartbeat lag, tokens, tool calls and errors, and checkpoint size and time.
- **Compose profile `observability`:** Prometheus and Jaeger, pinned by digest.

### Agent benchmark suite (§8)

- **Tasks:** the 10 spike tasks move to `tests/benchmarks/agent_tasks/`, adapted to `sample_mcp` with their checks unchanged in substance.
- **Running:** `make benchmark` runs each task once through `TaskWorkflow`. Results go to `docs/benchmarks/<date>-<template>.md`: pass/fail per task, harness and inner turns, tokens, wall time, and the model, template version and hash, harness version and prompt hash.
- **Baseline:** the first run on the Sparks with `local-default@1`.
- **When it runs:** after any change to a model, template, harness version or system prompt, and at every phase closure. A run that passes 2 or more fewer tasks than the baseline blocks phase closure.
- **Not in PR CI:** it needs the real model (§8). It runs on request, and the phase evidence links its latest result.

### Threat model, first version

`docs/security/threat-model.md` covers:
- **Assets:** workspace contents, sessions, the database, object storage, model access, template secrets.
- **Trust boundaries:** CLI to Temporal; Workflow to worker; worker to model, MCP and commands; worker to the database and S3; the third-party trace backend (closed).
- **Actors:** a hostile prompt, hostile file content, a compromised worker, an over-privileged profile.
- **Controls, each mapped to a test:**
  - template-only capabilities;
  - the extra-forbidding profile and request schemas;
  - the template hash check;
  - the MCP tool filter with errors returned to the model;
  - the command allow-list and its credential-free environment;
  - the Claude runner's clean environment and `dontAsk` mode;
  - idempotency keys;
  - no secrets in Temporal history;
  - SDK tracing off.
- **Accepted Phase 1 risks:**
  - no egress control;
  - no sandbox for untrusted code;
  - identical side-effect calls collapse into one.

### Dependencies

New runtime dependencies, with their expected licenses. PR 1 confirms them through CI's license job.

| Package | License |
|---|---|
| `openai-agents` | MIT |
| `pydantic` | MIT |
| `pyyaml` | MIT; becomes a runtime dependency |
| `mcp` | MIT |
| `opentelemetry-sdk` | Apache-2.0 |
| `opentelemetry-exporter-otlp` | Apache-2.0 |
| `prometheus-client` | Apache-2.0 |

`claude-agent-sdk` (MIT; it bundles the Claude Code CLI under Anthropic's terms) is the optional extra `praxismesh[claude]`. The mypy `files` list gains the new packages.

### Implementation PRs

1. **Foundations:**
   - schemas, loaders, `registry.lock` and the negative capability tests;
   - `BlobStore` and its contract suite;
   - migration `0003` and the retention classes;
   - observability, with SDK tracing off;
   - the CLI skeleton;
   - the new `.env` keys.
2. **Harness:**
   - `HarnessRunner` and both runners;
   - the built-in tools and `run_command`;
   - `sample_mcp` and the skill;
   - the fake model;
   - `run_harness_turn` and `TaskWorkflow`, with replay and time-skipping tests;
   - the `workers` profile;
   - a scripted end-to-end test;
   - `test_claude_runner_isolation`.
3. **Durability:**
   - checkpoints and restore;
   - both session stores, and the Claude cross-worker verification;
   - idempotency;
   - `make recovery-check` and the effect-then-crash test.
4. **Evidence:**
   - the benchmark suite and its baseline;
   - the threat model;
   - the `observability` profile;
   - the demo;
   - the as-built section.

## Traceability

| Plan requirement (phase-1.md) | OpenSpec capability | Acceptance test |
|---|---|---|
| Versioned profiles, templates, MCP catalog, loaders, generic worker | `agents/capability-model` | `test_loaders`, `test_registry_lock`, `test_profile_rejects_capability_fields`, `test_request_rejects_capability_fields` |
| Minimal `BlobStore`, S3 adapter, contract tests | `storage/blob-store` | `test_blob_contract` (fake and SeaweedFS) |
| Phase 1 migrations, retention from the first write | `persistence/app-database` | `test_migration_0003`, `test_every_row_and_blob_has_retention` |
| Baseline observability | `observability/baseline` | `test_trace_parentage`, `test_no_sdk_trace_export`, `test_log_context_ids`, `test_metrics_endpoint` |
| Agent benchmark suite | `quality/agent-benchmarks` | `make benchmark`, with the baseline recorded |
| Threat model | `security/threat-model` | the controls-to-tests table |
| `run_harness_turn` | `execution/harness-turn` | `test_harness_turn_scripted`, `test_prohibited_tool_returns_error`, `test_claude_runner_isolation`, `test_heartbeat_details` |
| Durable session, workspace snapshots, recovery on another worker | `execution/durability` | `make recovery-check`, `test_checkpoint_matches_session_position` |
| `TaskWorkflow` | `execution/task-workflow` | `test_task_workflow_*` (time-skipping), `test_task_workflow_replay`, `test_duplicate_task_id_rejected` |
| Sample skill and MCP tool, negative capability test | `agents/capability-model` | `test_forbidden_skill_or_tool_rejected` |
| No duplicated side effects | `execution/durability` | `test_side_effect_not_repeated_after_crash` |

## Alternatives

- **`temporalio.contrib.openai_agents`.** It runs the agent loop in the Workflow, with each model call as an Activity, so per-step durability comes built in. Rejected:
  - the Claude runner is a CLI subprocess and cannot run inside a Workflow, and one `HarnessRunner` interface needs both runners to run the same way;
  - plan §4.1 puts one bounded harness run in an Activity.

  It is the first option to revisit if mid-turn checkpoints prove fragile.
- **Checkpoint only at the end of a turn.** A lost worker would lose up to `inner_max_turns` of edits, which fails the acceptance criterion.
- **Sessions only as blobs.** This would need its own consistency logic, where the SDK stores already provide it.
- **The SDK's sandbox agent for skills.** Its session model differs from the Claude runner's. A read-only bundle plus a plugin works for both.
- **An in-process `ScriptedModel` for the recovery check.** It restarts at step 0 on the replacement worker, so it cannot show that the conversation continued. The fake HTTP endpoint can.
- **Claude as the default harness.** Rejected by the owner while licensing is open.

## Risks

| Risk | Handling | §7.1 trigger and action |
|---|---|---|
| The Claude session does not restore on another worker | Verified in PR 3; `openai_agents`, the default, does not depend on it | If it fails, apply the restart-from-checkpoint fallback and record the deviation |
| Mid-turn checkpoint consistency | A crash between the blob `put` and the row insert leaves a harmless orphan blob. A crash after the insert is covered, because restore reads `checkpoints` itself. A crash between an effect and the next checkpoint is covered by idempotency keys. | If recovery tests are flaky, revisit `contrib.openai_agents` |
| The local model's reliability over many turns | Measured by the benchmark | Below 7 of 10 on the baseline: tune the template (prompt, turn limits, effort), then re-run before Phase 2 |
| Token use: the Claude runner used about 14× the input tokens in the spike | Not the default; tokens are recorded | — |
| Shell access without a sandbox | Accepted for Phase 1; Phase 5 closes it | — |
| Workspace size | Snapshots are whole tarballs | A checkpoint over 50 MB or 2 s on the sample tasks: switch to incremental snapshots |

## Testing and demo

**Automated, in PR CI** (hosted runners, with the fake model):
- **Unit tests:**
  - schemas and loaders, the lock file, negative capability;
  - `BlobStore` against the fake;
  - idempotency, session truncation;
  - logs and traces, and SDK tracing off.
- **Workflow tests:** `TaskWorkflow` replay and time-skipping tests.
- **`stack` job:**
  - the `BlobStore` contract against SeaweedFS;
  - migration `0003`;
  - a scripted end-to-end task through the worker containers;
  - `test_prohibited_tool_returns_error`;
  - `test_claude_runner_isolation`;
  - `make recovery-check`;
  - the effect-then-crash test.

**Real model, on request** (linked from the evidence): the end-to-end sample task and `make benchmark`, both against the Sparks. Phase 1 cannot close on stubbed results alone (§8).

**Demo** (`docs/demos/phase-1.md`). Entry point: `make workers-up`, then `make task`.
1. **Sample task:** it uses the `order-desk` skill and the `sample-shop` MCP tool, and produces `order-summary.md` plus a validated `TaskResult`. Show the file, the `TaskResult` and the task in the Temporal UI.
2. **Worker loss:** during a second task, wait for an acknowledged checkpoint (in `make task-status`), then stop the worker that holds the attempt. The other worker resumes and finishes. Show:
   - the same `task_id` and Workflow ID;
   - the edits kept;
   - the conversation continuing.
3. **Side effects and rejection:**
   - show that `record_order` ran once: `sample_orders` has one row per order;
   - submit a request that names a skill or an MCP server, and show it rejected.
4. **Tracing:** show one trace in Jaeger, from submission to result.
5. **Clean up** with `make workers-down` and `make reset`.

## Future work

- Live messaging, streaming, `comms_mcp`, conversation IDs, and answering `needs_input`: Phase 2.
- Ceph and GCS adapters, presigned access, retention enforcement and garbage collection, Claim Check: Phase 3A.
- Worker affinity queues: only if measurements call for them.
- A sandbox for untrusted code, egress control, and published images: Phase 5 and the licensing decision.
- The PraxisMesh documentation skill: before Phase 3A.

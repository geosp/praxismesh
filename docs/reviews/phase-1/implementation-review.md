---
review: implementation
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: [docs/adr/0001-keep-default-openspec-schema.md, docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 593acd4a467a10763a117b6577ef90b3cd8c05ab
docs_sha: n/a
diff_base: 13eb944
session: fresh
date: 2026-11-12
verdict: FAIL
reviewers:
  - { lens: contract, status: completed }
  - { lens: failure and retry, status: completed }
  - { lens: scope and composition, status: completed }
---

# Implementation review: Phase 1 harness-in-Activity, single agent

Gate mode, light tier. A fresh coordinator session ran this review and then `verify-phase` (`docs/reviews/phase-1/verification.md`) against the same `code_sha`; independence between the two is knowingly waived (§7.0). The session did not write, implement or discuss the work, and read no implementation transcripts.

The code is the merge of PR #49 on `main`, the last of the four Phase 1 implementation PRs (#46, #47, #48, #49). Tracking issue: #44. `git status --porcelain` was empty at review time.

## Inputs

Revision: `git diff 13eb944 593acd4a467a10763a117b6577ef90b3cd8c05ab` (13eb944 is the merged design, PR #45).

Contract files given to each reviewer:

- `openspec/changes/phase-1-single-agent/proposal.md`, `design.md`, `tasks.md`
- `openspec/changes/phase-1-single-agent/specs/{agents/capability-model, execution/durability, execution/harness-turn, execution/task-workflow, observability/baseline, persistence/app-database, quality/agent-benchmarks, security/threat-model, storage/blob-store}/spec.md`
- `docs/rfcs/phase-1-single-agent.md`
- `docs/adr/0001-keep-default-openspec-schema.md`, `docs/adr/0002-paradedb-as-postgresql-server.md`
- `docs/plan/phases/phase-1.md`
- `docs/plan/decision-log.md` (rows dated 2026-11-11 and 2026-11-12)

Guidance files: `AGENTS.md`, `PROJECT_PLAN.md` (§2 and §8).

Nothing else was provided. The three reviewers (`impl-reviewer` agent) ran in parallel. The first launch of all three was cut off by an API usage limit before any report; the contract reviewer was resumed and the other two were relaunched with the same brief. All three then completed.

**Severity scope (owner instruction for this gate).** A finding is a Blocker or Major only if it would make Phase 1 fail an acceptance criterion or demo item, contradict a §2 hard constraint, mis-state verified SDK or API behavior, leave a requirement without a test that could fail, or make an as-built or demo claim false. Developer-tooling edge cases are Nits at most. The decision-log rows of 2026-11-11 and 2026-11-12 are accepted as given (Claude runner deferred, `finish_task` ends turns, recovery tests kill processes, the demo uses `docker kill`). The coordinator applied this rule when merging; where it changed a reviewer's severity, the Resolution column says so.

## Findings

Reviewers: C = contract, F = failure and retry, S = scope and composition.

### Major

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| F1 | Major | C, F, S | `orchestrator/workflow.py:45-50, 120-128`; `harness_activity/activity.py:176-180, 194-199` | Task R.1 is ticked but only the `TimeoutError` path is handled. `heartbeated_tokens` reads `last_heartbeat_details`, which only Temporal's `TimeoutError` carries. When a turn is lost 5 times and attempt 6 raises `AttemptsExhausted` (the normal terminal path), or a `HarnessInputError`/`CapabilityError` ends the turn, the Workflow adds 0 tokens and `attempts += 1`: the `TaskResult` under-reports about 5 attempts and all their heartbeated tokens. Contract: tasks.md R.1; task-workflow spec ("usage SHALL include the tokens ... of earlier attempts ... that were lost"). `test_failed_turn_counts_heartbeated_tokens` (`tests/test_task_workflow.py:221`) only unit-tests the helper on a hand-built `TimeoutError`. | Fix: time-skipping test whose mocked turn heartbeats, times out, then raises `ApplicationError(type="AttemptsExhausted")`; assert `TaskResult` tokens and attempts. Then carry `Progress` (with the real attempt count) in the error's `details` and read it in the Workflow. | open |
| F2 | Major | C, F, S | `harness_activity/activity.py:179, 190-201, 213, 305-308`; `orchestrator/activities.py:211-231`; `common/persistence/repositories.py:132-135` | Task R.2 is ticked but attempt rows stay `outcome='started'` forever after: `schedule_to_close` expiry (no Activity code runs; `complete_task` never closes rows), a `CapabilityError` from `build_config`, and `HarnessInputError("task ... is not recorded")` from `_fresh_start` (outside the `except` clauses). `AttemptsExhausted` closes attempt 5 as `attempts_exhausted` rather than its real category. No test mentions `close_unfinished` or these categories. (F rated this Nit; C and S Major; kept Major: a ticked requirement with no test that could fail.) | Fix: `run_harness_turn` tests for attempt 6, a missing `base_url_env` and a missing task row, plus a Workflow-level `schedule_to_close` case, each asserting no `started` row remains and the category; then close rows on those paths (for example in `complete_task`). | open |
| F3 | Major | C, S | `common/observability/metrics.py:7-15` | `ACTIVITY_SECONDS`, `HEARTBEAT_LAG_SECONDS` and `TOOL_ERRORS` are defined but never recorded anywhere; tool calls are counted only as `tool="any"`. The spec scenario "its `/metrics` endpoint reports a non-zero Activity count and token count" cannot hold for the Activity count (verification observed no Activity or heartbeat samples on a worker after a task). `test_metrics_endpoint` (`tests/test_observability.py:35`) increments `TOKENS` by hand. Contract: observability spec ("Activity duration, heartbeat lag, tokens, tool calls and errors"); phase-1.md baseline observability task. | Fix: run a scripted task with `METRICS_PORT` set, scrape `/metrics`, assert Activity count, heartbeat lag and token count; then record the three metrics. | open |
| F4 | Major | C, S | `harness_activity/tools.py:119-121`; `harness_activity/runner.py:128-134` | A `run_command` refusal (a disallowed first word) appends to `state.refused`, which nothing reads; no log line is written. The only refusal log (`on_llm_end`) fires for unknown tool names. Removing that log line also leaves every test green (verification mutation). Contract: capability-model spec ("the refusal is logged with the task and attempt IDs"); threat model C4 ("and is logged"). (S rated this Nit; kept Major: requirement without a test, and a threat-model control claim that is false for `run_command`.) | Fix: capture logs inside `log_context(task_id=..., attempt=...)` and assert one JSON refusal line for an unknown tool and for a refused command; then log `run_command` refusals. | open |
| F5 | Major | C | `registry/mcp/sample-shop.yaml`; `harness_activity/runner.py:179` | `sample-shop.tools_allowed` lists all five tools the server has, so `create_static_tool_filter` filters nothing in any test. A regression that drops `tool_filter` would expose unlisted MCP tools and every test would pass. Contract: capability-model scenario "a model calls an MCP tool that is not in `tools_allowed` -> refused"; threat model C4 cites this. | Fix: a conformance case with a generated catalog entry whose `tools_allowed` omits `record_order`; assert it is absent from the request's tool list and that a call to it returns an error. | open |
| F6 | Major | C, S | `tests/benchmarks/run.py:84-105`; `docs/benchmarks/2026-11-12-local-default.{md,json}` | The benchmark records no inner turns: the variable named `inner` is `sum(tool_calls)`, reported as tool calls, and `TurnOutcome.inner_turns` is not aggregated anywhere. Contract: agent-benchmarks spec ("record, per task, pass/fail, harness and inner turns, tokens and wall time"). No test covers the record's columns. | Fix: a unit test on the row/markdown builder asserting an inner-turns column; then persist `inner_turns` (for example on `task_attempts`) and report it. | open |
| F7 | Major | C, S | `tests/test_task_workflow.py`; `orchestrator/workflow.py:93-96, 120-128` | No time-skipping test covers a heartbeat or `schedule_to_close` timeout or the wall-time budget, although the task-workflow spec makes the wall-time budget a SHALL and the RFC's test list names "retry, timeout, budget exhaustion". The `"wall-time budget exhausted"` branch and the Workflow's timeout handling never run in a test. (S rated this Nit; kept Major: requirement without a test that could fail.) | Fix: time-skipping tests for a turn timeout and for wall-time exhaustion, asserting the `TaskResult` status and reason. | open |
| F8 | Major | C | `harness_activity/activity.py:181-187`; `orchestrator/cli.py`; `orchestrator/activities.py` | Logs do not carry `request_id` outside the CLI: the harness `log_context` sets no `request_id` (the Workflow knows it but `TurnInput` lacks it), orchestrator Activities set no `log_context`, and the orchestrator emitted no JSON log lines during verification. The RFC says logs are "JSON lines with `request_id`, `task_id`, `workflow_id`, `turn`, `attempt` and `worker`"; phase-1.md asks for logs "carrying request, ... workflow, task and attempt IDs". `test_log_context_ids` tests only the formatter. (C and S rated this Nit, citing the spec's "where known"; raised to Major because the RFC's unqualified claim is false as built and the verification observed it.) | Fix: a test that runs a scripted task and asserts worker and orchestrator JSON lines carry `request_id` and the task IDs; then pass `request_id` through `TurnInput` and set `log_context` in orchestrator Activities. Or contest by narrowing the RFC wording to the spec's "where known". | open |
| F9 | Major | C | `docs/security/threat-model.md` C6, C7; `harness_activity/tools.py:54`; `harness_activity/config.py:48-55` | The threat-model spec requires each control to name a test. C6 ("File tools cannot leave the workspace") cites tests that never exercise a `../` or absolute path for `read_file`/`write_file`; C7 ("MCP servers get only their literal `env`, `PRAXIS_TASK_ID` and the secrets the template grants") cites a registry load test, not the runtime env built in `config.py`. Verification mutations (disabling `inside()`; adding `**os.environ` to the MCP env) left all 141 unit tests green. | Fix: tests for path escape on both file tools and for the exact MCP subprocess env; update the threat-model table to name them. | open |

### Nit

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| N1 | Nit | C, F, S | `common/persistence/repositories.py:133` | Lost attempts are recorded as `lost_or_timed_out`; the RFC says `worker_lost` or `timeout`. | Fix wording in code or RFC. | open |
| N2 | Nit | C, F, S | `harness_activity/activity.py:86, 171` | Heartbeat details carry an extra `refusals` field; the harness-turn spec limits them to checkpoint ID, inner turn, tool-call and token counts. | Fix spec or details. | open |
| N3 | Nit | C, F, S | `activity.py:356`; `tools.py:100, 325` | The 2 KB summary cap counts characters, not bytes; `finish_task` `questions` is unbounded and flows into Workflow history (§2 bounded histories). | Fix: byte cap and a bound on questions. | open |
| N4 | Nit | C, S | `activity.py:170-177` | Refusal counting relies on the heartbeat sent before `TemplateVersionUnavailable` reaching the next attempt; tested only in `ActivityEnvironment`. No test of `MAX_REAL_ATTEMPTS`/`AttemptsExhausted`. (F read the SDK and found it waits for the last heartbeat, `temporalio/worker/_activity.py:533-535`.) | Fix: a real-server test. | open |
| N5 | Nit | C, S | `tests/integration/test_recovery.py` | No kill test asserts the `TaskResult` tokens include the killed attempt's heartbeated usage through real Temporal (heartbeat throttling); the "at least 70,000 tokens" scenario is checked only at Activity level. | Fix: assert tokens in a recovery test. | open |
| N6 | Nit | C | `common/blob_store/s3.py:223` | `get` reads the body outside `_call`, so a dropped connection mid-read raises raw botocore/urllib3 errors instead of `BlobUnavailable`. | Fix. | open |
| N7 | Nit | C | BlobStore contract tests | No `BlobUnauthorized`/`BlobUnavailable` case through the adapter; `test_idempotent_put` checks neither one stored object nor full `BlobRef` equality. | Fix. | open |
| N8 | Nit | C | `s3.py:200-218` | A put that upgrades retention calls `copy_object`, changing `LastModified`, so later puts of the same bytes return a different `created_at` (spec: same `BlobRef`). | Fix or narrow spec. | open |
| N9 | Nit | C | tracing test | `test_task_trace_reaches_model_and_tool_calls` asserts parentage only for model/tool spans and `run_harness_turn`, not every Activity span. | Fix. | open |
| N10 | Nit | C | `tests/test_observability.py:30` | `test_no_sdk_trace_export` calls `disable_sdk_tracing()` itself; removing the call from `workers/main.py:105` leaves tests green. `RunConfig(tracing_disabled=True)` still holds the control today. | Fix: test the worker startup path. | open |
| N11 | Nit | C | `docs/security/threat-model.md` C12, C13 | C13 says "reviewed, not tested" and C12 names a mechanism, though the spec says each control names a test. | Fix table or spec. | open |
| N12 | Nit | C, S | `tests/benchmarks/run.py:46, 78-83, 146-186` | No test of the regression verdict; pass/fail ignores task status (a `failed` task with correct files passes); `--only` compares a subset with the 10-task baseline; a same-day rerun overwrites the baseline's results file. | Fix. | open |
| N13 | Nit | C, S | `harness_activity/runner.py:87-90, 143-145` | The J12 "finish next to a failed call" heuristic misses a `run_command` result with a non-zero exit, and misfires on a `read_file` whose content starts with "error" or "refused". | Fix. | open |
| N14 | Nit | C | tools | Nothing checks that `run_command` is absent when `cli_tools` is empty. | Fix. | open |
| N15 | Nit | C | replay fixture | The one committed history is "done in one turn"; no multi-turn or failure history. | Fix. | open |
| N16 | Nit | C, S | `orchestrator/submit.py:42, 252` | Input files are keyed by basename; two with the same name collide and one is dropped silently. | Fix. | open |
| N17 | Nit | C | `harness_activity/config.py` | `model_override` is validated against `allowed_model_overrides` but never applied (the RFC does not require applying it). | Contest or fix. | open |
| N18 | Nit | C | repository layout | No `comms_mcp/` stub, though the proposal and RFC layout list one; phase-1.md says Phase 1 "may" use a stub. | Fix layout text. | open |
| N19 | Nit | C, F | `s3.py:35, 43-44`; `activity.py:194-196` | `NoSuchBucket` maps to `BlobNotFound` and then to the non-retryable `HarnessInputError`; `BlobUnauthorized` is retried as an infrastructure fault. | Fix classification. | open |
| N20 | Nit | F, S | `activity.py:300-302` | The post-run checkpoint and output upload have no `newer_attempt_exists` check: a superseded attempt whose in-flight call is `finish_task` can still write. Restore ordering keeps it harmless; Temporal cancellation probably wins in practice. Threat model C9 says "A superseded attempt writes nothing". | Fix: fence before the final checkpoint; test with the pause on `finish_task`. | open |
| N21 | Nit | F | `orchestrator/workflow.py:38, 77, 153` | `record_task`/`complete_task` stop after 5 tries (about 15 s); a 20 s database outage at the end leaves the `tasks` row `running` with no result, and the `task_id` cannot be reused. (F rated Major; downgraded: the spec's "SHALL be retried" is met, the bound is unspecified, and no acceptance criterion is affected.) | Fix: longer retry for these idempotent Activities. | open |
| N22 | Nit | F | `workflow.py:95-127` | Cancelling a `TaskWorkflow` leaves the `tasks` row `running` and the attempt `started` (not in the contract; the CLI has no cancel). | Document or fix. | open |
| N23 | Nit | F | Workflow reset | A Temporal reset collides with the earlier run's `tasks` row, checkpoints and attempt numbers. | Document resets as unsupported. | open |
| N24 | Nit | F | `activity.py` | If a worker dies after `_finish` of a `continue` turn but before Temporal records completion, the retry runs a whole extra invocation (bounded by budgets). | Note. | open |
| N25 | Nit | F | `repositories.py:285-306`; `s3.py:91-102` | `RecordingBlobStore.put` writes S3 before the `blob_objects` row (a death between leaves an untracked object); concurrent first puts with different classes can leave S3 metadata and the row disagreeing. | Note for Phase 3A GC. | open |
| N26 | Nit | F, S | `common/schemas/task.py:69`; `workflow.py:108` | `TurnInput.remaining_wall_time` is set but never read (the RFC accepts a last-turn overrun). | Remove or use. | open |
| N27 | Nit | F | `activity.py:222-228` | Truncation logs a warning and continues when the session is shorter than the checkpoint position. | Note. | open |
| N28 | Nit | F | `orchestrator/cli.py:59-75` | A retried submit whose first start succeeded raises an uncaught `WorkflowAlreadyStartedError`. | Fix. | open |
| N29 | Nit | F | `tests/benchmarks/run.py:71, 93, 150-200` | Results are written only at the end; `handle.result()` has no timeout; `engine.dispose()` is not in `finally`. | Fix. | open |
| N30 | Nit | S | `runner.py:198` | `inner_max_turns` applies per attempt, so one turn can run up to 5 x 8 inner turns across resumed attempts; not stated. | Document. | open |
| N31 | Nit | S | `runner.py:138, 146` | Tool spans are keyed by tool name; two parallel calls to the same tool overwrite a span that is never ended. | Fix. | open |

## Requirements confirmed by the reviewers

Each has enforcing code and a test that would fail without it: template-only capabilities and request/profile rejection by field name; harness mismatch; the registry lock and the worker hash refusal; restore order, fresh start, truncation, checkpoint position and seq 0; recovery on another worker after workspace edits and in a later turn; idempotent `record_order` after a crash; self-fencing before model calls; duplicate task IDs rejected in Temporal (`REJECT_DUPLICATE`) and in `tasks`; retries are not turns; capability errors are final; turn and token budgets; the inner-turn limit returns `continue`; `finish_task`, `needs_input`, J11 and J12; retention NOT NULL and the stronger class wins; the scripted end-to-end task; and the trace chain to model and tool calls. Replay determinism is covered (`tests/test_task_workflow.py:214-218`). The diff has no Signals, Updates or Continue-As-New.

## Reviewer status

| Lens | Status |
|---|---|
| Contract | completed (resumed once after an API usage limit) |
| Failure and retry | completed (relaunched once after an API usage limit) |
| Scope and composition | completed (relaunched once after an API usage limit) |

## Verdict

**FAIL.** Rule 5 of `docs/reviews/README.md`: every Major must be fixed or contested with evidence before a PASS, and F1-F9 are open. No Blocker was raised, and every reviewer ran.

## Open items

- F1-F9 (Major) go back to the implementer. Any re-check runs in a new session (rule 6).
- 31 Nits (N1-N31) do not block.

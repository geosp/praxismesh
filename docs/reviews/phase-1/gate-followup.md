---
review: implementation
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: [docs/adr/0001-keep-default-openspec-schema.md, docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: cbd48750a936f38cfe94e0178ddc92335e82c650
docs_sha: n/a
diff_base: 593acd4a467a10763a117b6577ef90b3cd8c05ab
session: fresh (targeted follow-up, docs/reviews/README.md rule 6)
date: 2026-11-12
verdict: FAIL
reviewers:
  - { lens: contract, status: completed }
  - { lens: failure and retry, status: completed }
  - { lens: scope and composition, status: completed }
---

# Phase 1 gate: targeted follow-up of the fixes in PR #51

A targeted follow-up under rule 6 of [README.md](../README.md). The session did not write, implement or discuss the work, and read no session transcripts. It was given the correction list up front, as rule 6 allows for a labelled follow-up:

- [implementation-review.md](implementation-review.md): FAIL, Majors F1-F9;
- [verification.md](verification.md): fail, Majors V1-V6;
- the claimed resolutions in [gate-findings-response.md](gate-findings-response.md);
- the fix diff `593acd4..cbd4875` (PR #51). Tracking issue: #44.

The owner's decisions in the [decision log](../../plan/decision-log.md) are taken as given. This includes the 2026-11-12 row that makes `run_command`'s first-word-only check accepted risk R1 until Phase 5.

**Scope:**
1. Is each of F1-F9 and V1-V6 resolved? A finding counts as resolved when the fix exists and its named test fails with the fix removed (checked by mutation).
2. Are there new Blockers or Majors, looking only at what changed in `593acd4..cbd4875`?
3. Severity follows the owner's rule. A finding is a Blocker or Major only if it:
   - fails a Phase 1 acceptance criterion or demo item;
   - contradicts plan §2;
   - mis-states verified SDK or API behavior;
   - leaves a requirement without a test that could fail;
   - or makes an as-built, demo or threat-model claim false.

   Everything else is a Nit. The 45 Nits of the gate run are carried to Phase 2 and are not raised again.

## Inputs

**Revision:** `git diff 593acd4 cbd4875`, reviewed in a disposable worktree at `cbd4875`. `git status --porcelain` was empty before each run, and every mutation was restored afterwards.

**Each of the three `impl-reviewer` agents received:**
- the header brief from `review-implementation`, with this follow-up's scope added;
- the contract:
  - `openspec/changes/phase-1-single-agent/` (`proposal.md`, `design.md`, `tasks.md`, every `specs/**/spec.md`)
  - `docs/rfcs/phase-1-single-agent.md`
  - ADR 0001 and ADR 0002
  - `docs/plan/phases/phase-1.md`
  - `docs/plan/decision-log.md` (rows dated 2026-11-11 and 2026-11-12)
  - `docs/security/threat-model.md`
- the guidance files: `AGENTS.md`, and `PROJECT_PLAN.md` (§2, §8);
- the correction list above.

**Execution** (the `verify-phase` part, only for the items that need it):
- Compose project `pmfollowup` on ports 15432, 17233, 18080 and 18333.
- The stack of project `praxismesh` was left running and untouched.

## Checks run

| Check | Command | Result |
|---|---|---|
| Unit tests | `uv run pytest` | 151 passed |
| Integration tests | `make smoke` | 81 passed, 4 skipped (model endpoint not set for this run) |
| Recovery | `make recovery-check` | 5 passed |
| Mutations | 30 single-point mutations and one added assertion, listed below. Each ran its named test, or the whole unit and integration suite (`-m 'integration or not integration'`, without recovery; 232 tests) where the point was to show that nothing fails. Every file was restored with `git checkout` | see below |
| C7 subprocess environment | `MCPServerStdio` (openai-agents 0.24.0, mcp 2.3.0) started `sh -c env` with `env={PATH, LANG, PRAXIS_TASK_ID}` and a canary variable in the worker's environment | the child had `HOME`, `LOGNAME`, `SHELL`, `USER` (and `TERM` when set) as well. The canary did not reach it. Source: `mcp/client/stdio.py:129`, `env=get_default_environment() \| (server.env or {})` |
| V3 demo | `make workers-up`, `make demo-worker-loss`, `make task-status` | Workers built from `cbd4875` and pointed at the real model endpoint, whose URL was passed only through the environment. Task `task-0d8f8be3-…`:
- latest checkpoint at the kill: `…:1:1:1`;
- `pmfollowup-worker-a-1` killed;
- turn 1 attempt 1 `lost`, attempt 2 `done` on the other container;
- four orders, each recorded once;
- task `succeeded`, Workflow `COMPLETED`.

`make task-status` shows the attempts, `checkpoints: 8`, the latest checkpoint (`…:1:2:5`, session position 46) and the orders. All of this matches `docs/demos/phase-1.md` step 2: **pass** |

### Mutations

"Red" means the named test failed with the fix removed, so the test pins the fix. "Green" means every test still passed, so nothing pins the fix.

| Item | Mutation | Test run | Result |
|---|---|---|---|
| F1 | `workflow.py`: `attempts += lost_attempts` changed to `attempts += 1` | `test_attempts_exhausted_counts_usage_and_attempts` | red |
| F1 | `workflow.py`: drop `or getattr(cause, "details", None)` | `test_failed_turn_usage_from_either_error`, `test_attempts_exhausted_counts_usage_and_attempts` | red |
| F1 | `activity.py`: error details changed to `{}` | `test_attempts_exhausted_closes_rows_and_reports_usage` | red |
| F1 | `activity.py`: `"attempts"` in the details changed to `1` | the same | red |
| F1 (timeout path) | add `assert result.attempts > 1` to `test_turn_timeout_fails_the_turn`, with no change to the code | that test | **red**: `AssertionError: 1`, so the gap is confirmed |
| F2 | `activity.py`: `close_unfinished` aimed at another task | `test_attempts_exhausted_closes_rows_and_reports_usage`, `test_missing_model_url_closes_the_row` | red |
| F2 | `activity.py`: outcome is always `failed` | `test_attempts_exhausted_closes_rows_and_reports_usage` | red |
| F2 | `activities.py`: delete `close_unfinished` in `complete_task` | `test_complete_task_closes_rows_left_open` | red |
| F3/V1 | delete the `HEARTBEAT_LAG_SECONDS` observation | `test_activity_metrics_are_recorded` | red |
| F3/V1 | delete the `ACTIVITY_SECONDS` observation | the same | red |
| F3/V1 | delete the `TOOL_ERRORS` increment in `on_tool_end` | `test_tool_errors_are_counted` | red |
| F3/V1 | delete the `TOOL_CALLS` increment | the same | red |
| F3/V1 | delete both `TOKENS` increments | whole suite | **green** (232 passed) |
| F4 | delete `log.warning("refused command", …)` | `test_refusals_are_logged_with_ids` | red |
| F5 | delete `tool_filter=…` | `test_mcp_tools_allowed_filter` | red |
| F6 | drop the inner-turns cell from the markdown row | `tests/test_benchmark_report.py` | red |
| F6 | `workflow.py`: delete `inner_turns += outcome.inner_turns` | whole suite | **green** (232 passed) |
| F6 | `activities.py`: delete `inner_turns=payload.inner_turns` | whole suite | **green** (232 passed) |
| F7 | delete the wall-time budget check | `test_wall_time_budget_exhausted` | red |
| F7 | `break` changed to `continue` after a failed turn | `test_turn_timeout_fails_the_turn` | red |
| F8/V2 | `activity.py`: delete `request_id=turn.request_id` from `log_context` | `test_log_lines_carry_request_and_task_ids` | red |
| F8/V2 | delete `logging.setLogRecordFactory(...)` | the same | red |
| F8/V2 | `workflow.py`: delete `request_id=start.request_id` | whole suite | **green** (232 passed) |
| F9/V5 | `tools.py` `inside()`: delete the outside-the-workspace check | `test_file_tools_stay_in_the_workspace` | red |
| F9/V5 | `list_files`: `inside(workspace, path)` changed to `workspace / path` | whole suite | **green** (232 passed) |
| F9/V6 | `config.py`: prepend `**os.environ` to the MCP env | `test_mcp_server_env_is_exactly_what_is_granted` | red |
| F9/V6 | `runner.py:184`: `"env": s.env` changed to `{**os.environ, **s.env}` | whole suite | **green** (232 passed). The first attempt raised `NameError` (`os` is not imported there) and was discarded |
| V4 | `tools.py`: `if first not in cli_tools` changed to `if False` | `test_prohibited_tool_returns_error` | red |
| V4 | delete `timeout=COMMAND_TIMEOUT_S` | whole suite | **green** (232 passed) |
| V4 | `done.stdout[-OUTPUT_CAP:]` changed to `done.stdout` | whole suite | **green** (232 passed) |
| V4 | `cwd=workspace` changed to `cwd="/"` | whole suite | **green** (232 passed) |

## Status of the correction list

| Item | Status | Basis |
|---|---|---|
| F1 | **Partly resolved** | Fixed and pinned for `AttemptsExhausted`, `HarnessInputError` and `CapabilityError` (4 mutations red). A turn that ends at `schedule_to_close` still reports 1 attempt: see M1 |
| F2 | Resolved | `close_unfinished` on every final failure and in `complete_task`; 3 mutations red. Category on the timeout path: Nit N2 |
| F3 / V1 | **Partly resolved** | Activity duration, heartbeat lag, tool calls and tool errors are recorded and pinned (4 mutations red). The token count in the spec scenario, and the checkpoint metrics, have no test that can fail: see M2 |
| F4 | Resolved | 1 mutation red |
| F5 | Resolved | 1 mutation red |
| F6 | **Partly resolved** | The column is pinned. The value on the success path, which produced every baseline row, is not: 2 mutations green. See M3 |
| F7 | Resolved | 2 mutations red |
| F8 / V2 | **Partly resolved** | The harness, the record factory and `resolve_capabilities` are pinned (2 mutations red). The Workflow's hand-off of `request_id` is not (M4), and the overview claims JSON logs from the CLI, which writes none (M5) |
| F9 / V5 | Resolved for the file tools as tested (C6). `list_files` is named in C6 but untested: Nit N9 |
| F9 / V6 | **Not resolved** | The `build_config` env is pinned (1 mutation red). The rewritten C7 claim ("exactly … and nothing else from the worker") is false at the subprocess, and the runner's hand-off is unpinned: see M6 |
| V3 | Resolved | `infra/demo/worker-loss.sh` (`make demo-worker-loss`) and `make task-status` are committed and ran as the demo record describes (see Checks). The script asserts nothing: Nit N11 |
| V4 | **Partly resolved** | The false confinement claim is corrected, consistent with decision-log R1, and the first-word test is pinned (1 mutation red). The rest of V4 is not addressed: C5 still claims a workspace cwd, a 60 s timeout and capped output, and removing each still leaves every test green. See M7 |

## Findings

New or remaining Blockers and Majors, from the changed code and text only. The Reviewer column uses C (contract), F (failure and retry), S (scope and composition) and Co (coordinator, by execution).

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| M1 | Major | C, F, S | `orchestrator/workflow.py:46-59`; `harness_activity/activity.py:79-88` | When `schedule_to_close` (6 × `turn_timeout`) ends a turn, the cause is a `TimeoutError`. `failed_turn_usage` then reads `last_heartbeat_details`, but `Progress` has no `attempts` field, so `d.get("attempts", 1)` gives 1. `TaskResult.attempts` therefore under-counts. Contract: tasks.md R.1 ("tokens **and attempts**"). `test_turn_timeout_fails_the_turn` runs this path but checks only status and reason. Adding `assert result.attempts > 1` makes it fail with `attempts == 1`. The path is rare in production (template-version refusals, or attempts that run to `start_to_close`) | Fix: heartbeat the real attempt (a `Progress` field), and assert the attempt count in the timeout test | open |
| M2 | Major | C | `tests/integration/test_harness_activity.py::test_activity_metrics_are_recorded`; `activity.py` `TOKENS`, `CHECKPOINT_*` | The observability spec scenario requires "a non-zero Activity count **and token count**", and F3's action asked for both. With both `TOKENS` increments deleted, all 232 tests pass. The checkpoint size and time metrics, part of the same SHALL, are also unpinned | Fix: assert `praxis_tokens_total` and `praxis_checkpoint_*_count` in that test | open |
| M3 | Major | C, S | `orchestrator/workflow.py:141`; `orchestrator/activities.py:89` | Agent-benchmarks spec: "record, per task, … harness and inner turns". With either line deleted, all 232 tests pass, and every successful benchmark row would record 0 or null inner turns. Only the failure path and the markdown column are tested | Fix: a Workflow test with two turns that return `inner_turns` 3 and 4, asserting 7 in the `TaskResult` and in `CompleteTaskInput` | open |
| M4 | Major | C, S | `orchestrator/workflow.py:118`; `common/schemas/task.py` (`request_id: str = ""`) | With `request_id=start.request_id` deleted, worker log lines carry `"request_id": ""`, which is exactly what V2 observed, and all 232 tests still pass. The log test builds `TurnInput` by hand | Fix: the mocked `run_harness_turn` in `tests/test_task_workflow.py` asserts `turn.request_id`, or make the field required | open |
| M5 | Major | C | `docs/architecture/overview.md` Observability row (rewritten in this diff); `orchestrator/cli.py` | The overview says "JSON logs with request, task, workflow, … IDs, from the CLI, the orchestrator and the harness". `orchestrator/cli.py` never calls `configure_logging` and makes no logger call: its `log_context` wraps code that logs nothing. So the as-built claim is false, and the observability spec's "Workers and the CLI SHALL log JSON lines" has neither code nor a test for the CLI | Fix: configure JSON logging in the CLI and test one line with `request_id` and `task_id`. Or narrow the overview (and, by a decision-log row, the spec) to the workers | open |
| M6 | Major | C, S, Co | `docs/security/threat-model.md` C7 (rewritten in this diff); `harness_activity/runner.py:184` | C7 now says an MCP server "gets exactly `PATH`, `LANG`, its literal `env`, `PRAXIS_TASK_ID` and the secrets its template grants, and nothing else from the worker". In mcp 2.3.0, `stdio_client` starts the server with `get_default_environment() \| server.env` (`mcp/client/stdio.py:129`), which adds `HOME`, `LOGNAME`, `SHELL`, `TERM` and `USER` from the worker. Observed directly (see Checks). So the claim is false and mis-states the SDK's behavior. None of these are secrets. Separately, changing `runner.py:184` to `{**os.environ, **s.env}` hands the worker's whole environment, S3 keys included, to the server, all 232 tests still pass: the test checks only `build_config`'s dict | Fix: correct C7 to name the SDK's inherited variables, and test the env the server process actually gets (a stdio fixture server that reports `os.environ` keys, with a canary) | open |
| M7 | Major | S (C rated Nit) | `docs/security/threat-model.md` C5; `harness_activity/tools.py:139-148` | V4 reported that removing the timeout, removing the output cap, or setting `cwd="/"` left the tests green. The fix rewrote C5, which still claims "in the workspace, … a 60 s timeout and capped output", but added no test for these. Re-run: each of the three mutations still leaves all 232 tests passing. The threat-model spec requires every control to map to a test that checks it | Fix: tests for `pwd`, a timeout (with a patched `COMMAND_TIMEOUT_S`) and output past `OUTPUT_CAP`, named in C5 | open |

### Nits (new, in the changed code or text)

| ID | Reviewer | Location | Note |
|---|---|---|---|
| N1 | C, F, S | `activity.py:205-210`; `repositories.py` `close_unfinished` | This closes every `started` row of the turn, including a newer attempt's. A superseded attempt that hits a `NonRetryableError` after the next attempt has started marks that attempt `failed`. The newer attempt's `finish` then does nothing, which goes against C9 ("writes nothing") in a narrow race. The race existed before for `BadRequest`, and the fix widens it to every final error. Suggested fix: `AND attempt <= :a` |
| N2 | C, F, S | `orchestrator/activities.py:93` | Rows left open at `schedule_to_close` are closed as `failed`/`task_completed`, not with their real category (R.2; RFC: `lost` with `worker_lost`/`timeout`) |
| N3 | F | response, F2 | "A missing task row … goes through the same handler" is imprecise. The foreign key raises `IntegrityError`, which is retryable, so five retries end in `AttemptsExhausted` with category `lost_or_timed_out` |
| N4 | S | `activity.py:207` | `input_unreadable` and `model_rejected` are both recorded as `HarnessInputError`, so a corrupt snapshot can no longer be told apart from a model rejection |
| N5 | C | `activity.py:205` | If `close_unfinished` itself fails (database down), a final failure becomes a retryable one |
| N6 | F | `tests/fixtures/task_workflow_history.json` | The replay fixture is replaced, not added to. Replay no longer checks the new code against a history recorded by the old code, and the `except ActivityError` branch is not replayed. By reasoning the change is deterministic: the command sequence is unchanged |
| N7 | C, S | `runner.py:137` | `TOOL_ERRORS` is labelled with the name the model gave a refused tool. That label set has no bound under prompt injection, and that branch is untested |
| N8 | C, S | `activity.py:140-145, 217-220` | `ACTIVITY_SECONDS` covers only `run_harness_turn`: not the template-refusal path, and not the orchestrator's Activities. "Heartbeat lag" measures the heartbeat interval |
| N9 | C, S | C6; `tools.py` `list_files` | C6 names `list_files`, but the test does not exercise it. Changing `inside(...)` to `workspace / path` there leaves all tests green  |
| N10 | C, F | `orchestrator/activities.py:61, 96` | The log IDs of `record_task` and `complete_task` are untested; only `resolve_capabilities` is |
| N11 | F, S | `infra/demo/worker-loss.sh` | The script asserts nothing: it exits 0 even without a lost attempt or with duplicate orders. Its "no checkpoint after 120 s" message understates the real wait, because each poll also runs `uv run` |
| N12 | C | metrics tests | The tests read `prometheus_client.REGISTRY` directly, not `/metrics` as the spec scenario says (equivalent today) |
| N13 | C | `orchestrator/cli.py` `status`; `AttemptRepository.list`, `CheckpointRepository.count`, `TaskRepository.sample_orders` | Untested; the demo and `make task-status` use them |
| N14 | C | `test_mcp_tools_allowed_filter` | The refusal log for a filtered MCP tool is not asserted |
| N15 | C, F | F1 and F2 tests | The Workflow and Activity sides are tested separately. The Activity-side tests are integration tests (`make smoke`, CI's stack job), not part of `uv run pytest` |

## Verdict

**FAIL.** Rule 5: every Major must be fixed or contested before a PASS, and seven are open (M1-M7). All three reviewers completed. No Blockers.

Every acceptance suite passed at `cbd4875` (unit, integration, recovery). The open Majors are about requirements and claims that no test pins, and about two documentation claims that are false (M5, M6). They are not about acceptance behavior that fails.

## Open items

- M1-M7, for the implementer. A re-check runs in a new session (rule 6).
- N1-N15: Nits. They are not blocking and can be carried with the gate run's Nits to Phase 2.

# Phase 1 gate: response to findings

Response to the [implementation review](implementation-review.md) (FAIL) and the [verification](verification.md) (fail) of `593acd4`. Those reports are unchanged. The fixes are on branch `fix/44-phase-1-gate-fixes` (issue #44), for a targeted follow-up under `docs/reviews/README.md` rule 6. Every acceptance suite and demo item passed in the gate run. The findings were promises without a test that could fail, and claims that were not true.

## Majors

| ID | Resolution | Test (fails without the fix) |
|---|---|---|
| F1 | A turn that fails for good (`AttemptsExhausted`, `HarnessInputError`, `CapabilityError` or another `NonRetryableError`) raises a non-retryable `ApplicationError` whose details carry the turn's cumulative usage, inner turns and real attempts. The Workflow reads them (`failed_turn_usage`), as it reads a timeout's last heartbeat. | `tests/test_task_workflow.py::test_attempts_exhausted_counts_usage_and_attempts`, `::test_failed_turn_usage_from_either_error`; `tests/integration/test_harness_activity.py::test_attempts_exhausted_closes_rows_and_reports_usage` |
| F2 | The same path closes the turn's open attempt rows. Attempts exhausted gives `lost` with category `lost_or_timed_out`; other errors give `failed` with the error's type. `complete_task` closes any rows still open, with category `task_completed`, for example after `schedule_to_close`, when no Activity code runs. A task row missing under an attempt cannot happen (foreign key); its path goes through the same handler. | `test_attempts_exhausted_closes_rows_and_reports_usage`, `test_missing_model_url_closes_the_row`, `test_complete_task_closes_rows_left_open` |
| F3 / V1 | Activity duration (`praxis_activity_seconds`, by outcome), heartbeat lag (`praxis_heartbeat_lag_seconds`), tool calls and tool errors per tool (`praxis_tool_calls_total`, `praxis_tool_errors_total`) are recorded. | `test_harness_activity.py::test_activity_metrics_are_recorded`; `tests/test_runner_conformance.py::test_tool_errors_are_counted` |
| F4 | A refused `run_command` is logged (`refused command`, with the program), like a refused tool call. | `test_runner_conformance.py::test_refusals_are_logged_with_ids` (both refusals, with task and attempt IDs) |
| F5 | — (the filter was right; it was never exercised) | `test_runner_conformance.py::test_mcp_tools_allowed_filter`: a catalog entry without `record_order` neither offers it nor lets it be called |
| F6 | `TaskResult` (and `CompleteTaskInput`) carries `inner_turns`, summed by the Workflow; the benchmark records it in its own column and names the tool-call count as such. The baseline is re-recorded: 10 of 10, with one task in 2 harness turns. | `tests/test_benchmark_report.py` |
| F7 | — | `test_task_workflow.py::test_wall_time_budget_exhausted`, `::test_turn_timeout_fails_the_turn` |
| F8 / V2 | `TurnInput` carries `request_id`, which the harness puts in its log context; the orchestrator Activities write JSON lines with request, task and workflow IDs. Log records now take the IDs when created, not when formatted, so a handler that formats later keeps them. | `test_harness_activity.py::test_log_lines_carry_request_and_task_ids` |
| F9 / V5 / V6 | File tools return their errors as text (the SDK replaced exceptions with a generic message the model could not act on). C6 and C7 have tests that fail when the control is removed (both checked by mutation). | `test_runner_conformance.py::test_file_tools_stay_in_the_workspace` (`..`, absolute path, symlink, write outside), `::test_mcp_server_env_is_exactly_what_is_granted` |
| V3 | The demo's worker-loss steps are committed as `infra/demo/worker-loss.sh` (`make demo-worker-loss`); `make task-status` shows the attempts, the checkpoint count, the latest checkpoint and the orders. Run on the DGX Spark endpoint after the fixes: attempt 1 `lost`, attempt 2 `done` on the other container, four orders each once. | the script itself; recorded in `docs/demos/phase-1.md` |
| V4 | Threat-model control C5 is corrected: `run_command` checks only the first word, then runs the whole string with `sh -c`, so with `sh` allowed any command runs, including reads outside the workspace. It stays an accepted risk (R1) until the Phase 5 sandbox (decision log 2026-11-12); the RFC, the capability-model spec and the as-built section say the same. | `test_prohibited_tool_returns_error` (first word), `test_command_env_has_no_credentials` |

## Nits

The 45 Nits (31 + 14) are not individually resolved in this round. Those touched by the fixes above are covered by their tests. The rest are carried into the Phase 2 planning, to be triaged with its design.

## Evidence after the fixes

| Suite | Result |
|---|---|
| Unit (`uv run pytest`) | 151 passed |
| Integration (`make smoke`) | 81 passed, 4 skipped (no model endpoint set) |
| Recovery (`make recovery-check`) | 5 passed |
| Worker loss on the DGX Spark endpoint (`make demo-worker-loss`) | recovered on the other container; orders once each |
| Benchmark on the DGX Spark endpoint (`make benchmark ARGS=--baseline`) | 10 of 10 |

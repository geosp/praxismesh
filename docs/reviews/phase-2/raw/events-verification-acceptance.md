<!-- Verbatim verifier report (Phase 2 events, phase 01 gate verification, acceptance and demo, at 629e8db); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-acceptance.md per docs/reviews/README.md rule 1. -->

# Phase 2 events, phase 01: acceptance verification

- Checkout: `/tmp/claude-1000/-home-geo-develop-praxismesh/599639d3-a59f-4a32-945c-fd5372c3c537/scratchpad/verify-phase2-events`, `git rev-parse HEAD` = `629e8db17fa03f13d12421e12aa0d1ba62e99540`, working tree clean apart from the untracked `.verify/`.
- Stack: Compose project `pmverify2` only (DB 55432, Temporal 57233/58080, S3 58333, `VLLM_BASE_URL=http://spark-01:8000`). No `praxismesh-*` container or volume was stopped, exec'd into or changed; after all runs `docker ps` still shows `praxismesh-worker-dsh-b-1 Up 26 minutes (healthy)` etc.
- Date: 2026-11-18. All logs are under `.verify/` in the checkout.
- Shell note (not a project finding): the calling shell had `VIRTUAL_ENV` and `PATH` pointing at the owner's checkout `.venv`; I unset `VIRTUAL_ENV` and removed that path entry (`.verify/env.sh`) so `uv` used this checkout's own environment.

**Verdict: FAIL.** One finding blocks: the integration suite is red at the frozen commit (`tests/test_runner_conformance.py::test_tool_and_token_events[dsh]` fails reproducibly). Everything else passed with quoted output: the repository checks, the unit suite, the phase's named tests, the migration round trip, the short load benchmark, the deploy checks and the full demo, including the worker-kill recovery.

## Findings

| ID | Severity | Finding |
|---|---|---|
| V1 | Major (blocks) | `uv run --env-file infra/.env pytest -m integration` exits 1: `FAILED tests/test_runner_conformance.py::test_tool_and_token_events[dsh]` / `1 failed, 209 passed, 308 deselected in 400.50s`. It fails again when run alone (`1 failed, 1 deselected in 4.11s`). The test (added in phase commit 5c31ca7, a caller that task 2.2 updates) asserts `set(e.payload) == {"input_tokens", "output_tokens"}` for every `token` event (tests/test_runner_conformance.py:589). The DSH gateway also emits `request_id` (harness_activity/dsh/gateway.py:319-324, unchanged since DSH phase 02). Live DSH tails show `{"input_tokens": 1490, "output_tokens": 82, "request_id": "req-0001"}`. `docs/roadmap/schemas.md` line 48 documents ``| `token` | `input_tokens`, `output_tokens` (DSH adds `request_id`) |``, and R6 allows IDs, so the code matches the documented contract and the test assertion is wrong for the `dsh` parameter. CI never runs this parameter: it is integration-marked and lives in `tests/`, while CI's stack job runs only `tests/integration` (`make smoke`), so it went unnoticed. |
| V2 | Minor | The committed load results (`docs/benchmarks/2026-11-18-event-load.json`) name commit `cda93d9` (`dirty: False`, command `python -m tests.benchmarks.event_load --seconds 180 --runs 3`). Later commits changed the publisher under test: `git diff --stat cda93d9 HEAD -- harness_activity/events.py` shows `59 insertions(+), 34 deletions(-)` (4463f52, c7c59a0). The committed numbers therefore do not describe the frozen commit. My shortened run at 629e8db passes with similar numbers (below), so this is a provenance gap and the result itself looks the same. |
| V3 | Minor | The two CPU readings sit at the noise floor, so the CPU-ratio gate barely discriminates. My run measured fenced `db_cpu_median_pct: 2.5` and unfenced `8.12` (the unfenced run used more CPU); the committed run measured 3.4-3.63 fenced and 3.48 unfenced. The gate passes, but at this load it cannot detect a doubling reliably. Observation only. |
| V4 | Minor | Shared image tags across Compose projects. `make workers-up` in this second checkout rebuilt the fixed tags `praxismesh-worker:dev` (f054dd6443c1 -> 363d716e405a) and `praxismesh-dsh:dev` (01ea04dd2d52 -> 836f5933b91f). The owner's stack uses the same tags; its running containers were unaffected (still on image f054dd6443c1), but its next `make workers-up` or restart picks up images built from this checkout. README "Several checkouts" requires a separate project name and ports, but does not mention the image tags. |
| V5 | Trivial (docs) | README "Checks" omits `uv run .github/scripts/check_dsh_licences.py` (AGENTS.md lists it). README status ("Phase 2 is next and has not started") and the AGENTS.md status line are stale for this branch. |
| V6 | Trivial (docs) | `infra/demo/phase-2-events.sh` needs host `python3`, GNU `grep -P` and `timeout`. Neither the script header nor the demo record names them; they were present here. |

No step the run needed was missing from the documentation (apart from the shell-environment note above, which is specific to this machine).

## 1. Prerequisites (documented steps only)

| # | Step (source) | Command | Observed | Result |
|---|---|---|---|---|
| P1 | README Set up | `uv python install 3.11`; `uv sync --locked` | `Python 3.11 is already installed`; packages installed, exit 0 | pass |
| P2 | Makefile | `make check` | exit 0 | pass |
| P3 | README / runbook | `make up` | `stack is up; run 'make status' for addresses and health`, exit 0 (`.verify/make-up.log`) | pass |
| P4 | README | `make status` | `addresses: Temporal 127.0.0.1:57233, UI http://127.0.0.1:58080, S3 http://127.0.0.1:58333, DB 127.0.0.1:55432` / `model endpoint: http://spark-01:8000 answers /v1/models` / `all services healthy` | pass |
| P5 | Runbook Deploy 1 | `make migrate` | `Running upgrade 0004 -> 0005, Phase 2 events plan D1: the agent event log (ADR-0009).` exit 0 | pass |
| P6 | Runbook Deploy 2 | `make workers-up` | all of `pmverify2-orchestrator-1`, `worker-a-1`, `worker-b-1`, `dsh-a-1`, `dsh-b-1`, `worker-dsh-a-1`, `worker-dsh-b-1` `Healthy`, exit 0 (`.verify/workers-up.log`); see V4 | pass |
| P7 | Runbook Deploy 3 | `make task PROFILE=default PROMPT="Order 3 units of SKU-1 and write order-summary.md." OUTPUT=order-summary.md` | expected template `local-dsh`; observed `"status": "succeeded"`, `"template": "local-dsh"`, `"attempts": 1`, exit 0 (task-a9cefcf1-...) | pass |
| P8 | Runbook Deploy 3 | same with `PROFILE=openai` | expected `local-default`; observed `"status": "succeeded"`, `"template": "local-default"`, exit 0 (task-8d59a15d-...) | pass |
| P9 | Runbook Agent events (both runners publish) | `./agentctl tail <id> --no-follow` for P7 and P8 | both exit 0, each 22 lines from `1 ... reset {"restored_from": null}` to `22 ... status {"status": "done"}`. openai token events: `{"input_tokens": 1435, "output_tokens": 73}`; DSH: `{"input_tokens": 1446, "output_tokens": 52, "request_id": "req-0001"}` | pass |

## 2. Acceptance tests

### Repository checks (AGENTS.md "Checks"), `.verify/checks.log`

| Command | Exit | Summary |
|---|---|---|
| `uv sync --locked` | 0 | `Checked 86 packages` |
| `uv run ruff check .` | 0 | `All checks passed!` |
| `uv run ruff format --check .` | 0 | `425 files already formatted` |
| `uv run mypy` | 0 | `Success: no issues found in 134 source files` |
| `uv run pytest` (unit) | 0 | `308 passed, 210 deselected in 37.54s` |
| `uv run .agents/sync_agents.py --check` | 0 | `ok: 3 generated agent file(s) up to date` |
| `uv run .github/scripts/check_plans.py` | 0 | `Validated 7 implementation plan(s); 0 error(s)` |
| `uv run .github/scripts/check_dsh_licences.py` | 0 | `licence notices present for 7 pinned DSH distributions` |
| gitleaks / actionlint | - | blocked: neither is installed on this host (`which: no gitleaks`, `which: no actionlint`); README marks gitleaks "if installed". CI covers both. |

### Phase-named unit tests

`uv run pytest tests/test_event_publisher.py tests/test_event_transport.py tests/test_cli.py -v`: exit 0, `22 passed in 3.63s` (`.verify/unit-named.log`). These cover every R7/R8 scenario and task 2.1 case: `test_640_events_at_once_are_ten_batches`, `test_a_few_events_wait_for_the_delay_then_go_in_one_batch`, `test_close_flushes_the_last_event`, `test_a_lost_reply_is_resent_and_stored_once`, `test_a_frozen_batch_survives_failed_tries_while_more_events_arrive`, `test_a_slow_publish_keeps_batches_in_order`, `test_close_completes_when_its_caller_is_cancelled`, `test_batch_ids_name_the_attempt`. Task 3.1 is covered by `test_tail_resumes_after_an_offset`, `test_tail_reports_pruned_events_first` and `test_tail_follows_until_the_workflow_closes_then_reads_to_the_end`. All PASSED.

### Integration suite

`uv run --env-file infra/.env pytest -m integration -v` (env loaded as the Makefile's `UV` does): **exit 1**, `1 failed, 209 passed, 308 deselected in 400.50s (0:06:40)`, 0 skipped (`.verify/integration.log`). The only failure is `tests/test_runner_conformance.py::test_tool_and_token_events[dsh]` (V1). A rerun of that test alone also fails (`.verify/conformance-rerun.log`). `test_recovery.py` (all 5) and the model-endpoint tests passed against the real endpoint.

Phase-named integration files (from the same run):

- `tests/integration/test_event_table.py`: 22 passed, 0 failed. Includes `test_a_notify_during_a_fetch_is_not_lost PASSED`, `test_a_superseded_attempt_publishes_nothing PASSED`, `test_publish_and_fenced_checkpoint_never_deadlock PASSED` and `test_two_attempts_publishing_get_gap_free_offsets PASSED`.
- `tests/integration/test_harness_activity.py`: 28 passed, 0 failed. Includes `test_an_attempt_opens_with_reset_and_ends_with_status`, `test_a_retried_attempt_resets_from_its_checkpoint`, `test_a_refused_final_flush_makes_no_finish_write`, `test_a_refused_flush_on_the_finish_shortcut_makes_no_finish_write`, `test_a_runner_failure_stores_its_events_and_keeps_its_error` and `test_a_cancelled_attempt_stores_its_events`, all PASSED.
- `tests/integration/test_dsh_activity.py`: 18 passed, 0 failed (`test_dsh_turn_through_the_activity PASSED`).
- Retention (task 1.1): `test_persistence_phase1.py::test_every_phase1_table_requires_retention PASSED` (it asserts `set(APP_TABLES) <= tables`; `APP_TABLES` is in `common/persistence/retention.py:21`).

### Task 1.1 migration round trip (`.verify/migration-roundtrip.log`)

I ran this on the disposable `pmverify2` database rather than a copy. `alembic downgrade -1` gave `Running downgrade 0005 -> 0004`, exit 0, and `current` = `0004`; the event tables were absent (the psql query returned no rows). `alembic upgrade head` gave `Running upgrade 0004 -> 0005`, exit 0, and `current` = `0005 (head)`; the tables `event_logs`, `agent_events` and `event_batches` were present again. Pass.

### Load benchmark (task 2.3)

`uv run --env-file infra/.env python -m tests.benchmarks.event_load --seconds 60 --runs 1 --out .verify/event-load-short.json`: exit 0, wall `2m6.352s`.

```
run 1: fenced=True  {"events_published": 11756, "publishes": 1172, "publish_p95_s": 0.0097, "display_p95_s": 0.2083, "tailers_complete": true, "db_cpu_median_pct": 2.5}
run 2: fenced=False {"events_published": 11748, "publishes": 1172, "publish_p95_s": 0.0096, "display_p95_s": 0.2084, "tailers_complete": true, "db_cpu_median_pct": 8.12}
{"verdict": {"display_p95": true, "publish_p95": true, "tailers_complete": true, "db_cpu_ratio": true}, "pass": true}
```

The output file records `commit 629e8db17fa0..., dirty False, command python -m tests.benchmarks.event_load --seconds 60 --runs 1 --out .verify/event-load-short.json`.

Committed full results: commit `cda93d947d21...` (an ancestor of HEAD), `dirty: False`, command `python -m tests.benchmarks.event_load --seconds 180 --runs 3`, 3 fenced runs plus 1 unfenced. Fenced publish p95 was about 0.0102 s and display p95 about 0.2089 s; fenced DB CPU was 3.6 / 3.63 / 3.4 against 3.48 unfenced; `pass: True`. The shortened run agrees on both thresholds (publish p95 under 250 ms, display p95 at most 1 s), with large margins. See V2 (commit provenance) and V3 (CPU signal).

## 3. Demo (`sh infra/demo/phase-2-events.sh .verify/demo`)

Exit 0 (`.verify/demo-run.log`, files in `.verify/demo/`). Task `task-a70928e4-430c-429c-8d15-f04b6e54505f`.

| Step | Command or action | Expected (record) | Observed | Result |
|---|---|---|---|---|
| Submit | `./agentctl task submit --profile default ...` (script) | "a DSH task" | `task: task-a70928e4-430c-429c-8d15-f04b6e54505f`; its attempts' `worker_identity` is `.../local-dsh` | pass |
| Tail live | `./agentctl tail <id>` in the background | "one line per event: offset, attempt, type, payload" | `1 task-a70928e4-...:1:1 reset {"restored_from": null}`, `2 ... token {"input_tokens": 1490, "output_tokens": 82, "request_id": "req-0001"}`, `3 ... tool_call {"call": 1, "tool": "read_file"}`; the tail was stopped before the task ended and had already written 21 lines, so it was live. `tail-1.err` is empty. | pass |
| Kill the worker mid-turn (failure / recovery) | after the second checkpoint, `docker kill` the holder's container | "the turn is retried on the other worker" | `latest checkpoint: task-a70928e4-...:1:1:1`; `killed pmverify2-worker-dsh-b-1 (abrupt stop)` (hostname `7eb20bfd4d8c`). Attempts: `{'turn': 1, 'attempt': 1, 'worker_identity': '7eb20bfd4d8c@1/local-dsh', 'outcome': 'lost', 'failure_category': 'lost_or_timed_out'}`, then `{'turn': 1, 'attempt': 2, 'worker_identity': '4441e0c614e6@1/local-dsh', 'outcome': 'done'}` (4441e0c614e6 = `pmverify2-worker-dsh-a-1`). The recovery is visible: a lost attempt and a retry elsewhere, not silent success. | pass |
| Retried attempt opens with reset (R9) | attempt 2's lines in the tails | "its first event is a `reset` naming the restored checkpoint" | `22 task-a70928e4-...:1:2 reset {"restored_from": "task-a70928e4-...:1:1:1"}`. Per-attempt run counts in offset order: `21 x attempt 1`, then `20 x attempt 2` (contiguous, no interleaving). | pass |
| Stop and resume (R2) | stop the first tail 15 s after the kill; `./agentctl tail <id> --after 21` | "resumes at 22; together the two tails show every offset once" | `first tail stopped after offset 21`; the second tail starts with `22 ... reset` and ends with `41 ... status {"status": "done"}`, stopping by itself when the Workflow closed (inside `timeout 900`; exit 0 under `set -e`). Script: `offsets across both tails: 1..41, each once`. | pass |
| Task outcome | `./agentctl task status <id>` | "the task completes despite the lost worker" | `task status: succeeded`; workflow `COMPLETED` | pass |
| No model text (R6) | payload keys in both tails | "counts, names, IDs and statuses only" | keys `['call', 'input_tokens', 'output_tokens', 'request_id', 'restored_from', 'status', 'tool']`; types `{'reset': 2, 'token': 6, 'tool_call': 16, 'tool_result': 16, 'status': 1}`, 41 events (identical to the record's counts) | pass |
| Prune and expiry (R3) | `./agentctl events prune --task <id> --below 10`; `./agentctl tail <id> --after 3 --no-follow` | "the retained base is 10; the tail reports the expiry first, then 10 onwards" | `{"task_id": "task-a70928e4-...", "retained_base": 10}`; then `expired: events before 10 were pruned`, `10 ... tool_call {"call": 4, "tool": "lookup_price"}`, `11 ...`; 33 lines (1 expiry + offsets 10..41) | pass |
| Cleanup | `docker start` the killed container | "the killed worker serves again" | `restarted pmverify2-worker-dsh-b-1`; `docker ps`: `pmverify2-worker-dsh-b-1 Up 12 seconds (healthy)` | pass |

The demo reproduced the record step for step from this checkout, whose `infra/.env` comes from `infra/.env.example` (task 4.1's Verify).

## 4. State left behind

All `pmverify2` services are still running and healthy: `db`, `temporal`, `temporal-ui`, `s3`, the orchestrator, `worker-a`, `worker-b`, both DSH pairs. The database is at migration `0005 (head)`. No source, test or doc file was modified.

## Not in scope here

Task 4.2 (the as-built overview) is unchecked in the phase file and is left to the verifier's separate as-built check.

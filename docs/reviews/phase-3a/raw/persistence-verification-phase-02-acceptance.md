<!-- Verbatim verifier report (Phase 3A persistence plan, phase 02 gate verification, acceptance and operator commands, at 4dde76d); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-acceptance.md per docs/reviews/README.md rule 1. -->

# Acceptance verification: Phase 3A persistence plan, phase 02 (GC and delete-by-request)

- Checkout: `/tmp/claude-1000/-home-geo-develop-praxismesh/5562944e-be36-4ae6-b40e-bb1b87da77f8/scratchpad/verify-phase3a-02`, `git rev-parse HEAD` = `4dde76d70a3a7e378dddb1a7714f0a9ddc76362a`. The worktree was clean apart from `.verify/`.
- Stack: Compose project `pmverify3a` (DB 55432, Temporal 57233, UI 58080, S3 58333), `VLLM_BASE_URL=http://spark-01:8000`, `VLLM_MODEL=spark`. I did not touch any `praxismesh-*` container or volume. The only containers I exec'd into were `pmverify3a-db-1` (read-only `psql` queries, plus one advisory-lock hold for the lock check).
- Logs: every log named below is under `<checkout>/.verify/`.

**Verdict: PASS with findings.** Every acceptance item passed, with output quoted below. There are no blocking findings. Four findings are minor (F1–F4, at the end). gitleaks and actionlint are blocked because they are not installed.

## 1. Prerequisites (documented steps only)

| # | Step (source) | Observed |
|---|---|---|
| 0 | `diff infra/.env.example infra/.env` | Only `COMPOSE_PROJECT_NAME=pmverify3a`, `DB_PORT=55432`, `TEMPORAL_PORT=57233`, `TEMPORAL_UI_PORT=58080`, `S3_PORT=58333`, `VLLM_BASE_URL=http://spark-01:8000` and the two `*_DB_URL` ports `55432` differ. These are the README "Several checkouts" / "Model endpoint" edits. |
| 0b | The calling shell had `VIRTUAL_ENV=/home/geo/develop/praxismesh/.venv` and that `.venv/bin` on `PATH` | Removed per the brief (`.verify/env.sh`). This is not a documentation gap. |
| 1 | `uv python install 3.11` (README Set up) | `Python 3.11 is already installed` |
| 2 | `uv sync --locked` (README, AGENTS.md) | EXIT=0 (`01-uv-sync.log`) |
| 3 | `make up` | `stack is up; run 'make status' for addresses and health`, EXIT=0 (`02-make-up.log`) |
| 4 | `make status` | `addresses: Temporal 127.0.0.1:57233, UI http://127.0.0.1:58080, S3 http://127.0.0.1:58333, DB 127.0.0.1:55432` / `model endpoint: http://spark-01:8000 answers /v1/models` / `all services healthy`, EXIT=0 |
| 5 | `make migrate` | `Running upgrade  -> 0001` ... `Running upgrade 0006 -> 0007, Phase 3A persistence plan, phase 01: ...`, EXIT=0 (`04-make-migrate.log`) |
| 6 | Integration suite and `make smoke` with no workers running | Confirmed: no `pmverify3a` worker containers existed. |
| 7 | `make workers-up` (README "Running an agent task"), only for step 2e | All 7 worker containers `Healthy`, EXIT=0 (`11-workers-up.log`) |
| 8 | `make workers-down` at the end | EXIT=0. `db`, `temporal`, `temporal-ui` and `s3` are left running (`28-workers-down.log`). |

The run needed no undocumented step, except for the link check (F2).

## 2a. AGENTS.md "Checks"

| Command | Result |
|---|---|
| `uv sync --locked` | EXIT=0 |
| `uv run ruff check .` | `All checks passed!` EXIT=0 |
| `uv run ruff format --check .` | `535 files already formatted` EXIT=0 |
| `uv run mypy` | `Success: no issues found in 180 source files` EXIT=0 |
| `uv run pytest` (unit) | `376 passed, 337 deselected in 59.46s` EXIT=0 (`06-unit.log`) |
| `uv run .agents/sync_agents.py --check` | `ok: 3 generated agent file(s) up to date` EXIT=0 |
| `uv run .github/scripts/check_plans.py` | `Validated 8 implementation plan(s); 0 error(s)` EXIT=0 |
| `uv run .github/scripts/check_dsh_licences.py` | `licence notices present for 7 pinned DSH distributions` EXIT=0 |
| gitleaks | **BLOCKED**: `which: no gitleaks` (not installed) |
| actionlint | **BLOCKED**: `which: no actionlint` (not installed) |
| Offline link check (CI `links` job args), run with the local image `lycheeverse/lychee:latest` (0.24.2) under `--network none`, plus `--exclude-path '\.verify'` | `542 Total ... 453 OK 🚫 0 Errors 👻 89 Excluded` EXIT=0 (`07-lychee.log`). Canary `[broken](./does-not-exist.md)`: `1 Error`, EXIT=2, as CI expects. CI pins lychee-action v2.9.0, which may bundle a different lychee version from the 0.24.2 used here. |

## 2b. Suites

- **Full integration suite**: `uv run --env-file infra/.env pytest -m integration -rs -v`, workers stopped. Result: `337 passed, 376 deselected in 885.33s (0:14:45)`, EXIT=0, no skips (the model tests ran against spark-01) (`08-integration.log`).
- **`make smoke`**: `307 passed in 780.45s (0:13:00)`, EXIT=0 (`10-smoke.log`).
- **Targeted unit tests**: `uv run pytest tests/test_cli.py tests/test_lifecycle_rules.py -v` gave `11 passed`, including `test_gc_dry_run_reaches_gc_and_prints_its_plan`, `test_request_delete_passes_force_and_dry_run`, `test_every_expiring_table_has_a_gc_rule` and `test_rules_take_their_class_from_table_class` (`09-unit-targeted.log`).

## 2c. Tasks and their "Verify:" lines

All results below are from `08-integration.log` and show PASSED.

| Task | Verify line | Implementing tests | Result |
|---|---|---|---|
| 1.1 BlobExpired | integration tests through the store and the CLI | `test_blob_expired.py::test_get_stream_and_stat_raise_expired_with_the_date`, `::test_task_output_reports_an_artifact_gc_removed` | PASSED. On the real stack (`20-read-check.log`): `BlobExpired: blob sha256/bd6038... expired: removed on 2026-11-21 12:28 UTC`, the format the runbook gives. |
| 1.2 removal engine | shared blob; crash after each step | `test_removal_engine.py::test_a_shared_blob_survives_while_another_task_holds_it`, `::test_a_crash_inside_the_batch_leaves_nothing`, `::test_a_crash_before_the_bucket_step_is_finished_by_the_next_run`, `::test_a_crash_after_the_bucket_delete_is_finished_by_the_next_run`, `::test_a_dry_run_changes_nothing_and_reports_the_same_counts`, `::test_the_engine_never_records_a_key_that_is_not_a_content_key` | PASSED |
| 1.3 revive | resubmit after delete; put between mark and bucket delete; bucket delete before put; old orphan again | `test_revive.py::test_a_file_resubmitted_after_a_delete_is_live_again`, `::test_a_put_between_the_mark_and_the_bucket_delete_keeps_the_object`, `::test_a_put_after_the_bucket_delete_uploads_the_bytes_again`, `::test_an_old_orphan_uploaded_again_restarts_its_window`, `::test_a_file_resubmitted_after_a_request_delete_survives_the_next_gc`; `test_removal_engine.py::test_a_put_between_the_batch_and_the_bucket_step_keeps_the_object` | PASSED. Also reproduced on the real stack (2e, R22). |
| 1.4 prune through engine | tail reports expired after GC; prune and tombstone atomic; mypy | `test_event_prune.py::test_a_gc_prune_reads_as_expired_not_as_a_gap`, `::test_a_prune_and_its_tombstone_commit_together`, `::test_a_long_log_is_pruned_in_batches_of_at_most_500`, `::test_prune_marks_the_pruned_events_references`, `::test_an_attached_blob_is_marked_and_removed_with_its_event`; `test_gc.py::test_every_row_rule_and_the_event_prune_expire_with_their_task` (asserts `lines == ["expired: events before 6 were pruned"]` after `gc`); mypy | PASSED. mypy: `Success`. |
| 1.5 run lock | two concurrent runs across several batches | `test_gc.py::test_a_second_gc_or_a_delete_fails_at_once_while_gc_runs`, `::test_gc_fails_at_once_while_another_run_holds_the_lock`; `test_event_prune.py::test_a_second_run_fails_at_once_while_the_first_holds_the_lock` | PASSED. On the real stack (`26-lock.log`): `error: another gc, request delete, events prune or backup is running; try again when it ends`, EXIT=2. |
| 2.1 gc | times set in rows: 8/6 days, stale late upload, running, audit, undelivered wake, orphans 25 h/1 h, row-less closed/queued, event_batches | `test_gc.py::test_gc_removes_what_expired_and_keeps_the_rest` (8 d, 6 d, late upload, running, audit), `::test_wake_and_batch_rows_expire_with_their_task` (wake, event_batches), `::test_orphans_wait_for_the_safety_window` (25 h/1 h), `::test_rowless_uploads_go_only_when_the_workflow_is_not_running` (closed/queued, 30 h), `::test_gc_refuses_while_a_reference_is_unindexed`, `::test_every_batch_has_a_tombstone_and_the_counts_add_up`, `::test_a_dry_run_reports_the_same_plan_and_changes_nothing`, `::test_an_object_that_is_not_a_content_key_is_reported_not_removed`, `::test_an_orphan_uploaded_after_the_listing_is_kept_and_not_counted`, `::test_bytes_back_under_a_removed_row_are_removed_again` | PASSED |
| 3.1 session ownership | session IDs of a finished task on each runner | openai_agents: `test_task_e2e.py::test_scripted_task_end_to_end` (`sessions == {name: {task_id} ...}`); DSH: `test_dsh_outcomes.py::test_outcome_case[*]` (12 cases; DSH writes no `agent_sessions` rows, checkpoints keyed by the task ID) | PASSED (the assumption holds; no pause needed) |
| 3.2 request delete | two-task request; running one; terminated with/without --force; shared blob; joiner mid-delete; --force while Activity runs; task output of redacted task | `test_request_delete.py::test_a_finished_request_is_removed_redacted_and_recorded`, `::test_a_request_with_a_running_task_is_refused`, `::test_force_deletes_only_a_closed_workflow`, `::test_a_blob_shared_with_another_request_survives`, `::test_a_task_joining_mid_delete_is_untouched`, `::test_a_late_attempt_of_a_deleted_task_writes_nothing`, `::test_task_output_of_a_redacted_task_reports_no_output`, plus 15 further tests in that file (fencing, locks, batches of 500, failure_reason redaction, unindexed refusal, rerun task list, force reason) | PASSED (22/22). Refusal and --force were also exercised against real Temporal (2e). |
| 3.3 kill tests | each committed batch has its tombstone; counts sum once; dangling check finds nothing | `test_removal_kills.py::test_a_killed_delete_finishes_when_run_again[inside]`, `[after]`, `::test_a_killed_gc_finishes_when_run_again[inside]`, `[after]` | PASSED. See F3 on how the "kill" is simulated. |
| 4.1 docs | link check passes | lychee offline run (2a) | PASSED (local image; see F2) |

## 2d. Requirements and scenarios

| Req | Scenario | Evidence |
|---|---|---|
| R3 | Identical bytes in two tasks; one request deleted; the blob still reads for the other | `test_request_delete.py::test_a_blob_shared_with_another_request_survives`, `test_removal_engine.py::test_a_shared_blob_survives_...` PASSED. On the real stack, tasks A and B shared `sha256/035894c3...`. After deleting A's request: `TB shared input via RecordingBlobStore: b'sku,qty\nSKU-1,3\n'`. |
| R6 | Ended 8 d ago plus a stale late upload; checkpoints, refs, late upload and freed blobs removed | `test_gc.py::test_gc_removes_what_expired_and_keeps_the_rest` PASSED |
| R7 | Running or ended 6 d ago: unchanged | same test PASSED |
| R7 | Submitted, Workflow waited 30 h: inputs kept | `test_gc.py::test_rowless_uploads_go_only_when_the_workflow_is_not_running` PASSED (FakeTemporal, see F1). On the real stack, `gc` asked Temporal nothing (no row-less upload was older than 24 h). |
| R7 | `audit` of any age kept | `test_gc_removes_what_expired_and_keeps_the_rest` (`audit_log` count, a 400-day `audit` blob, task row kept) PASSED |
| R8 | Orphan 25 h removed; 1 h kept | `test_gc.py::test_orphans_wait_for_the_safety_window` PASSED |
| R9 | Artifact removed by GC; `task output` says expired with the date, not "not found" | `test_blob_expired.py::test_task_output_reports_an_artifact_gc_removed` PASSED. On the real stack (SeaweedFS) the store read gives `expired: removed on 2026-11-21 12:28 UTC`. |
| R10 | Finished two-task request deleted: artifacts, checkpoints and inputs unreadable | `test_request_delete.py::test_a_finished_request_is_removed_redacted_and_recorded` PASSED. Real stack (one-task request A): `live refs TA \| 0`, `checkpoints TA \| 0`, instructions `BlobNotFound` in the bucket and `BlobExpired` through the store, `task output` gives `has no output 'order-summary.md' (outputs: none)`. |
| R11 | Content holds the marker; IDs, statuses and usage remain | Same test plus `::test_content_that_only_looks_redacted_is_redacted` and `::test_a_failed_tasks_failure_reason_is_redacted` PASSED. Real stack: `"summary": "[deleted 2026-11-21]"`, `"artifacts": []`, `"status": "succeeded"`, `"tokens_in": 16268`, attempts kept. |
| R12 | One running task: fails naming it, nothing changes | `test_request_delete.py::test_a_request_with_a_running_task_is_refused` PASSED. Real stack: `error: request req-d4bf... has tasks that have not ended: task-0fcd6d3e-.... Wait for them, or, if their Workflows are closed, use --force`, EXIT=2. |
| R13 | Tombstones name the request; counts sum; no content | `test_a_finished_request_is_removed_redacted_and_recorded`, `test_gc.py::test_every_batch_has_a_tombstone_and_the_counts_add_up` PASSED. Real stack (`27-tombstones.log`): 8 rows `request.delete \| request:req-bd4c...`, summed `35\|26\|9\|8`, which equals the report (`rows 35, references 26, blobs 9, batches 8`). Details hold only counts, reasons and task IDs. |
| R13 | gc killed after its first batch: that tombstone is present | `test_removal_kills.py::test_a_killed_gc_finishes_when_run_again[after]` (`tombstones >= 1`), `test_event_prune.py::test_a_prune_and_its_tombstone_commit_together` PASSED |
| R15 | Delete killed after some blobs removed; rerun completes, no dangling, nothing counted twice | `test_removal_kills.py::test_a_killed_delete_finishes_when_run_again[after]`, `test_request_delete.py::test_a_rerun_finishes_the_killed_deletes_own_task_list` PASSED |
| R21 | Terminated Workflow, `--force`: proceeds | `test_force_deletes_only_a_closed_workflow` PASSED (FakeTemporal). Real Temporal: after terminating TC (`before: running` / `after: closed`), `request delete --force` gives `'forced': {'task-0fcd...': 'closed'}`, EXIT=0, and `task status` shows `TERMINATED failed 2026-11-21 12:29:23... ['started', 'deleted']`. |
| R21 | Still-running Workflow, `--force`: refuses | Same test PASSED. Real Temporal: `error: ... has tasks whose Workflow is still running: task-0fcd.... --force applies only to closed Workflows`, EXIT=2. |
| R22 | Deleted request; same file submitted again; the new task reads it and the next gc keeps it | `test_revive.py::test_a_file_resubmitted_after_a_request_delete_survives_the_next_gc` PASSED. Real stack: task D resubmitted A's instructions and input. `blob_objects` for `sha256/bd6038...` shows `removed_at` NULL and `last_put_at 12:30:28`. Its refs `upload\|task-ea8b...\|t`, `tasks\|task-ea8b...\|t` are live and A's stay marked. `./agentctl gc` then reported `batches 0`, the blob was still live, and `task output` of D printed the summary. |
| R22 | A gc marked a blob; a put commits before the bucket delete: object kept | `test_revive.py::test_a_put_between_the_mark_and_the_bucket_delete_keeps_the_object`, `test_removal_engine.py::test_a_put_between_the_batch_and_the_bucket_step_keeps_the_object` PASSED |
| R24 | A task joining mid-delete is unchanged | `test_request_delete.py::test_a_task_joining_mid_delete_is_untouched` PASSED |
| R25 | `--force` delete while the Activity runs; later insert and publish refused; upload leaves no live ref | `test_request_delete.py::test_a_late_attempt_of_a_deleted_task_writes_nothing`, `::test_an_attempt_of_a_later_turn_is_fenced_too`, `::test_a_deleted_task_with_no_upload_left_still_revives_nothing`, `::test_a_deleted_tasks_conversation_and_tool_writes_are_refused`, `::test_a_put_during_the_delete_already_revives_nothing` PASSED. On the real stack I terminated the Workflow first (Temporal cancels the Activity), so this is not a true "Activity still running" case. 45 s later, task C still had `checkpoints 0`, `live refs 0`, `events 0`. |

Decisions D4, D5, D6, D10, D11 and D12 are covered by the same tests: lock and dry-run; 24 h window and Temporal check; batch order and bucket step; revive; prune through the engine; fixed task list, fencing and redaction. On the real stack, the dry-run counts equalled the real-run counts exactly (`batches 8, rows 35, references 26, blobs 9`, same `by_reason`), and a DB snapshot taken before and after the dry run was identical (`17-snap-after-dry.log`).

## 2e. Operator commands on the pmverify3a stack (real Temporal, SeaweedFS and model)

Logs: `12`–`27-*.log`. The workers were up. The tasks ran on the configured model (`template local-dsh`, `"status": "succeeded"`).

1. **Task A** with an input file: `./agentctl task submit --wait --instructions "Read orders.csv ... write order-summary.md ..." --input .verify/in/orders.csv --output order-summary.md`. Output: `{"task_id": "task-94a453ac-...", "request_id": "req-bd4c2a81-..."}`, then `"status": "succeeded"`. Before the delete, `task output` printed `# Order summary ... Total: 37.50`. Task B (`task-1106c13f-...`, `req-ddd1eb27-...`) used the same input file and also succeeded.
2. **`./agentctl gc --dry-run`** gave `"dry_run": true, "batches": 0, "rows": 0, "references": 0, "blobs": 0, "by_reason": {}, "unrecognised": [], "finished_from_earlier_runs": 0`. That is correct: nothing on a fresh stack has expired. It matches the runbook ("what has expired, by reason").
3. **`./agentctl request delete req-bd4c... --dry-run`** gave `"dry_run": true, "batches": 8, "rows": 35, "references": 26, "blobs": 9`, with reasons `checkpoints deleted` (6/12/0), `sample_orders deleted`, `events deleted` (26), `results redacted`, `idempotency_keys redacted`, `references deleted` (0/14/9) and `complete`. The DB snapshot was unchanged afterwards. Matches "changes nothing".
4. **`./agentctl events prune --task task-1106... --below 5 --dry-run`** on the live task B gave `{"retained_base": 1, "dry_run": true, ..., "events": 4, "references": 0, "blobs": 0}`. Afterwards `tail` still started at offset 1, so the dry run changed nothing.
5. **`./agentctl request delete req-bd4c...`** gave `"dry_run": false`, with the same counts as the dry run. EXIT=0.
6. **`./agentctl task output task-94a4... order-summary.md`** gave `error: task task-94a453ac-... has no output 'order-summary.md' (outputs: none)`, EXIT=2. Matches the runbook ("After a delete, `task output` reports the task has no outputs").
   - `task status` shows `"summary": "[deleted 2026-11-21]"`, `"artifacts": []`, usage kept, and a `deleted` attempt row (`worker_identity "cli:request-delete"`). Matches the runbook (redaction, "each task gets a `deleted` attempt row").
   - `./agentctl tail task-94a4... --no-follow` gave `expired: events before 27 were pruned`. Matches the runbook's expired line.
7. **`./agentctl events prune --task task-94a4... --below 10 --dry-run`** and **`--below 30 --dry-run`** both gave `{"retained_base": 27, "dry_run": true, ..., "events": 0, "references": 0, "blobs": 0}`. Correct: the delete had pruned the log to its end.
8. **`./agentctl gc`** gave `"dry_run": false, "batches": 0, ... "finished_from_earlier_runs": 0`, EXIT=0. It completed. I ran it again after the R22 resubmission: `batches 0`, and the revived blob stayed live.
9. Additional runbook claims I checked:
   - The lock message (step 1.5 above).
   - A refused delete without `--force`, and with `--force` on a running Workflow.
   - `--force` on a terminated Workflow: the plan, the report and the first tombstone each list `"forced": {"task-0fcd...": "closed"}`. Tombstone details: `{"reason": "request delete", "tasks": [...], "forced": {...: "closed"}, "resumed": false, ...}`.
   - The tombstone count reconciles with the marks. 9 blobs were marked: 6 still carry `removed_by=delete:54a8...`, and 3 (instructions `bd60...`, artifact `9c80...`, workspace `ea1b...`) were later revived by task D's identical uploads, as D10 intends. The shared input `035894...` and `2e735a...` were never marked.

## 3. Demo

Not applicable to this phase: the plan's demo belongs to phase 03.

## 4. End state

`make workers-down` EXIT=0. `pmverify3a-db-1`, `-temporal-1`, `-temporal-ui-1` and `-s3-1` are still up and healthy. No source, test or doc file was changed (`git status --short` shows only `?? .verify/`).

## Findings

- **F1 (minor, test coverage):**
  - The phase 02 integration tests for gc, delete, revive and the kill tests run on a scratch PostgreSQL database with `MemoryBlobStore` and `FakeTemporal`, not on SeaweedFS or a Temporal server.
  - The production Temporal adapter `orchestrator/cli.py::workflow_status` (describe → `running`/`closed`/`missing`, NOT_FOUND → `missing`) is not called by any test (`grep -rn workflow_status tests` gives no match). R21 and D5 therefore depend on untested glue.
  - I exercised it by hand on real Temporal: `running` and `closed` both behaved correctly. The `missing` branch and D5's row-less-upload path against a real server remain unexercised.
- **F2 (minor, docs/tooling):**
  - Task 4.1's "Verify: the link check passes" has no documented local command. AGENTS.md "Checks" and README "Checks" only say CI does it, and lychee is not installed on this host.
  - I ran the CI arguments with a locally present `lycheeverse/lychee:latest` image (0.24.2). CI pins lychee-action v2.9.0, so the lychee versions may differ.
- **F3 (minor, test fidelity):** The "kill" tests in `tests/integration/test_removal_kills.py` simulate the kill by raising an exception inside `RemovalEngine._batch` or `finish` (monkeypatched). No process is killed. This is a reasonable model of the transactional boundaries, but it is not a process kill.
- **F4 (observation):**
  - On the real stack, `gc` removed nothing, because nothing had expired. The positive removal paths of R6 and R8 are shown only by the time-shifted scratch-database tests.
  - The R25 real-stack check terminated the Workflow first, so the case of an Activity still running is shown only by `test_a_late_attempt_of_a_deleted_task_writes_nothing`.

Blocked: gitleaks and actionlint (not installed).

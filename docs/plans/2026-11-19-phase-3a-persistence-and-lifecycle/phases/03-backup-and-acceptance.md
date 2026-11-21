---
phase: 3
title: Backup, restore, reconciliation and acceptance
status: in-progress
branch: feat/92-phase-3a-backup-restore
base: 9920f3601335040d8aae069097c950c50a0572c3
delivers: [R16, R17, R23]
design_review: { status: passed, rounds: 3, last: 2026-11-20 }
impl_review: { status: changes-requested, rounds: 1, last: 2026-11-21 }
approved: 2026-11-20
---

# Phase 03 · Backup, restore, reconciliation and acceptance

## Goal

A stack can be backed up, restored into a clean stack and checked, as §4.13's drill asks; the
plan's acceptance suite and demo pass, and the as-built documentation describes them.

## Tasks

### 1. Reconciliation

- [x] 1.1 `agentctl reconcile [--reindex]`: prints the phase 01 checks (dangling references, orphaned blobs with age, unindexed references) and tasks left unended whose Workflow Temporal reports closed; read-only without `--reindex`; exit status 1 when anything is listed (R17). Verify: integration tests that seed each case.

### 2. Backup and restore

- [x] 2.1 `agentctl backup` and `make backup`, holding the D4 lock (phase 02's helper) and stopping the workers during the dumps, in the order of notes.md#d8; `backups/` git-ignored (D8). Verify: a backup of a stack with finished tasks has the three dumps, every object and a manifest, and the workers run again afterwards; a `gc` started during it fails on the lock.
- [x] 2.2 `infra/db/databases.sh` (the database statements moved out of `init.sh`, mounted in Compose), `infra/restore.sh` and `make restore BACKUP=...`, as notes.md#d8: refuses a stack with tasks, a Workflow in the app namespace (through Temporal's API), or objects, then drops and recreates the three databases with their grants, reruns `roles.sh`, loads, starts Temporal and prints reconcile's report without failing on it (R16, R23, D8). Verify: restore into a stack with a task, or a Workflow and no task, changes nothing; restore after `make reset` succeeds and `comms_mcp` connects; after a restore killed mid-load, `make reset` and a second restore succeed; a fresh `make up` still initialises through `init.sh`.
- [x] 2.3 The drill as `make drill`, opt-in and outside `make smoke`, on a stack started with `make up`: back up, `make reset`, `make up`, restore into the same project, then `task status`, `task output` and `comms_mcp` work, and reconcile lists one dangling reference after a deliberately removed object (R16, R17; notes.md#d8). Verify: `make drill` passes as its own step in the CI `stack` job, after the smoke tests, within its 45-minute budget.

### 3. Acceptance and demo

- [x] 3.1 Run the acceptance suite: every scenario of R1-R25, mapped to its test in the phase file's verification evidence. Verify: unit and integration runs pass from a clean worktree whose `infra/.env` comes from `infra/.env.example`.
- [x] 3.2 Demo script `infra/demo/phase-3a-lifecycle.sh` and record `docs/demos/phase-3a-lifecycle.md`: a request with an artifact, a dry-run GC, a GC with its tombstone and the artifact's expired read, a delete of a second request with its tombstone and redacted output, a resubmit that revives the input, a backup, `make reset`, a restore and its reconcile report. Verify: the script runs end to end on the fake model.
- [x] 3.3 As-built overview section, runbook ("Backup and restore"), `schemas.md` and decision log. Verify: `check_plans.py` and the link check pass.

## Verification evidence

The plan's acceptance suite (task 3.1): each requirement's scenarios and the tests that show
them. Unless a path is given, `tests/integration/`; `[…]` marks a parametrised test.

| Req | Scenario | Tests |
| --- | --- | --- |
| R1 | Two inputs are held by their task when the submit's uploads commit | `test_upload_refs.py::test_submit_uploads_are_held_by_their_task_before_record_task`, `test_index_writers.py::test_record_task_indexes_instructions_and_inputs` |
| R1 | A refused fenced checkpoint leaves no index row | `test_index_writers.py::test_refused_fenced_checkpoint_leaves_no_index_row`, `::test_a_failed_index_write_rolls_back_its_holder_row` |
| R2 | Migrating 0006 data: nothing unindexed, every ended task has `ended_at` | `test_migration_0007.py::test_migration_0007_backfills_remaps_and_round_trips` |
| R3 | Identical bytes in two tasks; one request deleted; the blob still reads for the other | `test_request_delete.py::test_a_blob_shared_with_another_request_survives` |
| R4 | A new checkpoint and its index rows carry `checkpoint` | `test_index_writers.py::test_checkpoint_inserts_index_their_blobs`, `test_task_e2e.py::test_scripted_task_end_to_end`, `tests/test_retention.py::test_task_is_never_written` |
| R4 | An event inserted without a class carries `transcript` | `test_migration_0007.py::test_new_defaults_and_checks` |
| R5 | A history with `retention_class: task` replays | `tests/test_task_workflow.py::test_task_workflow_replay`, `tests/test_retention.py::test_old_payloads_still_decode` |
| R6 | Ended 8 days ago with a stale late upload: checkpoints, references, the upload and freed blobs removed | `test_gc.py::test_gc_removes_what_expired_and_keeps_the_rest` |
| R7 | A running task, or one ended 6 days ago: unchanged; an `audit` row of any age kept | `test_gc.py::test_gc_removes_what_expired_and_keeps_the_rest` |
| R7 | A Workflow waiting 30 hours for a worker keeps its inputs | `test_gc.py::test_rowless_uploads_go_only_when_the_workflow_is_not_running`, `test_workflow_status.py::test_running_closed_and_missing` (real Temporal) |
| R8 | An orphan last uploaded 25 hours ago goes; 1 hour ago stays | `test_gc.py::test_orphans_wait_for_the_safety_window` |
| R9 | An artifact GC removed reads as expired with the date | `test_blob_expired.py::test_task_output_reports_an_artifact_gc_removed`; the demo, step 2 |
| R10 | A two-task request deleted: no artifact, checkpoint or input reads | `test_request_delete.py::test_a_finished_request_is_removed_redacted_and_recorded`; the demo, step 3 |
| R11 | Content holds the marker; IDs, statuses and usage remain | `test_request_delete.py::test_a_finished_request_is_removed_redacted_and_recorded`, `::test_content_that_only_looks_redacted_is_redacted`, `::test_a_failed_tasks_failure_reason_is_redacted` |
| R12 | A request with a running task is refused, naming it | `test_request_delete.py::test_a_request_with_a_running_task_is_refused` |
| R13 | A delete's tombstones name the request and their counts sum, with no content | `test_request_delete.py::test_a_finished_request_is_removed_redacted_and_recorded`, `test_gc.py::test_every_batch_has_a_tombstone_and_the_counts_add_up` |
| R13 | A gc killed after its first batch leaves that batch's tombstone | `test_removal_kills.py::test_a_killed_gc_finishes_when_run_again[after]`, `::test_a_delete_whose_process_is_killed_finishes_when_run_again` (SIGKILL) |
| R14 | The app role's `UPDATE` and `DELETE` on `audit_log` are refused | `test_audit_log.py::test_app_role_cannot_change_audit_rows[…]` |
| R15 | A delete killed after some blobs were removed completes when run again, nothing dangling or counted twice | `test_removal_kills.py::test_a_killed_delete_finishes_when_run_again[after]`, `::test_a_delete_whose_process_is_killed_finishes_when_run_again` (SIGKILL, SeaweedFS), `test_request_delete.py::test_a_rerun_finishes_the_killed_deletes_own_task_list` |
| R16 | Backed up, reset, restored: `task status`, `task output` and the comms role work | `make drill`, step 5; `test_backup.py::test_a_backup_has_three_dumps_every_object_and_a_manifest`; the demo, step 5 |
| R17 | A restored backup missing one blob lists it as dangling | `make drill`, step 6; `test_reconcile.py::test_a_missing_blob_is_listed_as_dangling` |
| R17 | An orphan is listed with its age | `test_reconcile.py::test_an_orphan_is_listed_with_its_age` |
| R17 | A task left `running` whose Workflow is closed is listed as never ended | `test_reconcile.py::test_a_task_whose_workflow_closed_is_listed_as_never_ended` |
| R18 | No history payload of the suite exceeds 64 KiB, with 20 questions of 500 characters | `test_history_payloads.py::test_twenty_long_questions_stay_under_the_limit` and the session guard over every integration run (`tests/support/history_guard.py`) |
| R19 | A `task` row moves to its table's class; an `audit` artifact becomes `artifact` | `test_migration_0007.py::test_migration_0007_backfills_remaps_and_round_trips`, `tests/test_retention.py::test_every_app_table_has_its_d3_class` |
| R20 | `end_task` sets `ended_at` for each terminal status | `test_index_writers.py::test_end_task_sets_ended_at_and_indexes_artifacts[…]` |
| R21 | `--force` proceeds for a closed Workflow and refuses a running one | `test_request_delete.py::test_force_deletes_only_a_closed_workflow`, `test_workflow_status.py::test_running_closed_and_missing` (real Temporal) |
| R22 | A deleted request's file submitted again is read, and the next gc keeps it | `test_revive.py::test_a_file_resubmitted_after_a_request_delete_survives_the_next_gc`; the demo, step 4 |
| R22 | A put committed between a gc's mark and its bucket delete keeps the object | `test_revive.py::test_a_put_between_the_mark_and_the_bucket_delete_keeps_the_object`, `test_removal_engine.py::test_a_put_between_the_batch_and_the_bucket_step_keeps_the_object` |
| R23 | A stack with one task, or one Workflow and no task row, is refused and unchanged | `test_restore_refusals.py::test_a_task_row_is_refused`, `::test_a_workflow_without_a_task_row_is_refused`, `::test_a_bucket_object_is_refused`; `make drill`, step 3 |
| R24 | A task that joins mid-delete is unchanged | `test_request_delete.py::test_a_task_joining_mid_delete_is_untouched` |
| R25 | A `--force` delete while the Activity runs: the later insert and publish are refused, the upload leaves no live reference | `test_request_delete.py::test_a_late_attempt_of_a_deleted_task_writes_nothing`, `::test_an_attempt_of_a_later_turn_is_fenced_too`, `::test_a_deleted_tasks_conversation_and_tool_writes_are_refused`, `test_upload_refs.py::test_a_deleted_tasks_late_upload_of_new_bytes_leaves_no_live_reference` |

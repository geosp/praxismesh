<!-- Verbatim verifier report (Phase 3A persistence plan, phase 01 gate verification, acceptance and demo, at bbfe1ce); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-acceptance.md per docs/reviews/README.md rule 1. -->

# Acceptance verification: Phase 3A persistence plan, phase 01 (index, classes, audit log, payload guard)

- Checkout: /tmp/claude-1000/-home-geo-develop-praxismesh/5562944e-be36-4ae6-b40e-bb1b87da77f8/scratchpad/verify-phase3a-01
- Commit: `bbfe1ceb5cdc5e36138a4d9fbdbc10d117259844` (`git rev-parse HEAD`), clean tree except the untracked `.verify/`
- Date: 2026-11-20. Compose project: `pmverify3a`. Logs are in `<checkout>/.verify/`.
- Shell: every command ran after `. .verify/env.sh`, which unsets `VIRTUAL_ENV` and removes `/home/geo/develop/praxismesh/.venv/bin` from `PATH` (the calling shell had both), then `cd`s into the checkout.
- Owner stack: I did not touch any `praxismesh-*` container or volume. Afterwards they still showed their original uptimes ("Up 33 hours", "Up 5 days", "Up 2 hours").

**Verdict: PASS for phase 01's deliverables, with 2 findings outside the phase (F1 is documentation, F2 is a flaky test).** Every task's Verify line and every delivered requirement (R1, R2, R4, R5, R14, R18, R19, R20) is backed by an observed pass, quoted below. The full integration run, done in the order the brief gives (workers up), exited 1 with 5 failures. None of them is in phase 01 code. 4 come from the documented workers being up (F1), and all 4 pass with the workers stopped. 1 is a flaky test that passed when rerun (F2).

## 1. Prerequisites (steps run, in order)

| # | Step | Source | Observed |
|---|---|---|---|
| 0 | `diff infra/.env.example infra/.env` | brief | Only these differ: `COMPOSE_PROJECT_NAME=pmverify3a`, `DB_PORT=55432`, `TEMPORAL_PORT=57233`, `TEMPORAL_UI_PORT=58080`, `S3_PORT=58333`, `VLLM_BASE_URL=http://spark-01:8000`, and both DB URLs on `127.0.0.1:55432` |
| 1 | `uv python install 3.11; uv sync --locked` | README Set up | exit 0 (`01-sync.log`) |
| 2 | `make up` | README Local stack | exit 0, `stack is up; run 'make status' for addresses and health` (`02-up.log`) |
| 3 | `make status` | README | exit 0: `addresses: Temporal 127.0.0.1:57233, UI http://127.0.0.1:58080, S3 http://127.0.0.1:58333, DB 127.0.0.1:55432` / `model endpoint: http://spark-01:8000 answers /v1/models` / `all services healthy` (`03-status.log`) |
| 4 | `make migrate` | README | exit 0, ran 0001 -> ... -> `Running upgrade 0006 -> 0007, Phase 3A persistence plan, phase 01: ...` (`04-migrate.log`) |
| 5 | `make workers-up` | README Running an agent task | exit 0; every worker container `Healthy` (`05-workers-up.log`) |
| 6 | `make workers-down`, before rerunning the messaging tests | README | exit 0. The docs do not say this is needed for the integration suite: **finding F1** |
| 7 | `make workers-up` at the end | README | exit 0; `make status`: `all services healthy`. All 11 `pmverify3a-*` services are up (`16-workers-up-again.log`) |

The stack is left running as the brief asks.

## 2a. AGENTS.md "Checks" (`06-checks.log`)

| Command | Expected | Observed |
|---|---|---|
| `uv sync --locked` | exit 0 | `Checked 86 packages`, exit=0 |
| `uv run ruff check .` | pass | `All checks passed!` exit=0 |
| `uv run ruff format --check .` | pass | `510 files already formatted` exit=0 |
| `uv run mypy` | pass | `Success: no issues found in 169 source files` exit=0 |
| `uv run pytest` | pass | see 2b |
| `uv run .agents/sync_agents.py --check` | pass | `ok: 3 generated agent file(s) up to date` exit=0 |
| `uv run .github/scripts/check_plans.py` | pass | `Validated 8 implementation plan(s); 0 error(s)` exit=0 |
| `uv run .github/scripts/check_dsh_licences.py` | pass | `licence notices present for 7 pinned DSH distributions` exit=0 |
| gitleaks | (if installed) | **BLOCKED**: `which: no gitleaks` |
| actionlint | CI only | **BLOCKED**: `which: no actionlint` |
| Offline link check (task 4.1 Verify; CI `links` job) | pass | `lycheeverse/lychee:latest` was already on the host (0.24.2; CI pins lychee-action v2.9.0, so the versions may differ). I ran it with CI's args, plus `--exclude-path '\.verify'`, under `--network none` with the checkout mounted read-only: `532 Total ... 444 OK 🚫 0 Errors 👻 88 Excluded`, exit=0 (`10-lychee.log`) |

## 2b. Test suites

| Run | Exit | Summary line |
|---|---|---|
| `uv run pytest` (unit) | 0 | `372 passed, 279 deselected in 59.55s` (`07-pytest-unit.log`) |
| `uv run --env-file infra/.env pytest -m integration -rs -v` (workers up, as in step 5) | **1** | `5 failed, 274 passed, 372 deselected in 862.52s (0:14:22)` (`08-pytest-integration.log`); 0 skipped. The history-payload session guard reported nothing: `grep -c "history payload"` = 0 |
| Rerun of the 5 failures, workers still up | 1 | `4 failed, 1 passed`: `test_refusals_are_logged_with_ids[dsh] PASSED`; the 4 messaging tests failed again (`11-rerun-workers-up.log`) |
| Rerun of the 4 messaging failures after `make workers-down` | 0 | `4 passed in 5.81s` (`13-rerun-workers-down.log`) |
| `make smoke` (workers down) | 0 | `249 passed in 738.52s (0:12:18)`, with no history guard failure (`14-smoke-workers-down.log`) |

The failures in the full run:
- `tests/integration/test_comms_mcp.py::test_a_send_wakes_a_sleeping_recipient_as_the_comms_role` (`assert 0 == 1`, wake row count)
- `tests/integration/test_dispatcher.py::test_a_wake_waits_for_a_stopped_dispatcher_and_is_then_delivered` (`assert 0 == 1`)
- `tests/integration/test_dispatcher.py::test_a_wake_for_a_closed_workflow_is_deleted_and_logged` (`assert (0 >= 1)`)
- `tests/integration/test_dispatcher.py::test_a_wake_sent_while_its_row_is_signalled_is_kept` (`assert 0 == 1`)
- `tests/test_runner_conformance.py::test_refusals_are_logged_with_ids[dsh]` (`KeyError: 'refused tool call'`)

The cause of the first 4 is visible in `docker logs pmverify3a-orchestrator-1`. The container's dispatcher drained the tests' wake rows, for example `"logger": "praxis.dispatcher", "msg": "wake for a closed workflow dropped", "workflow_id": "inbox-closed-40fc8afc"` and `... "inbox-race-fa7ba58b"`. See F1 and F2.

## 2c. Each task's Verify line

| Task | Verify line | What I did / which tests | Result |
|---|---|---|---|
| 1.1 Migration 0007 | scratch DB to 0006, seed every kind in notes.md#refs (with an `audit` artifact), to 0007, down, up | **Done by hand**, with my own seed, separate from the test's (below), plus `tests/integration/test_migration_0007.py::test_migration_0007_backfills_remaps_and_round_trips` and `::test_new_defaults_and_checks` | PASS (both tests PASSED in both integration runs) |
| 1.2 audit_log trigger | integration test as the app role | `tests/integration/test_audit_log.py::test_app_role_cannot_change_audit_rows[UPDATE ...]`, `[DELETE ...]`, plus a manual probe as `praxismesh` (below) | PASS |
| 1.3 RetentionClass, lifetimes, APP_TABLES vs d3 | unit tests, with a repeat `put` over `task` metadata | `tests/test_retention.py`: `test_every_app_table_has_its_d3_class`, `test_migration_0007_uses_the_same_classes`, `test_reference_query_matches_the_migration`, `test_reference_classes_match_d3_blob_table`, `test_order_and_lifetimes`, `test_stronger_never_returns_task[x6]`, `test_old_payloads_still_decode`, `test_repeat_put_over_task_metadata`, `test_task_is_never_written` | PASS (`09-unit-targeted.log`: `36 passed`) |
| 1.4 reference checks, expiry, reindex | seed each case, including a bucket object with no row; reindex twice changes nothing | `tests/integration/test_refs.py::test_unindexed_then_reindex_twice` (asserts `first == Reindexed(references=2, blobs=3)` and `second == Reindexed(references=0, blobs=0)`, with a bucket-only object `key("bucket only")` -> `ephemeral`), `::test_dangling_references`, `::test_orphans_with_their_age`, `::test_expiry`, `::test_rowless_uploads_wait_for_the_window`. I also ran `refs.unindexed` on my migrated scratch DB (below) | PASS |
| 2.1 index_refs writers; complete removed | per-writer tests; a refused fenced checkpoint leaves no index row | `tests/integration/test_index_writers.py::test_record_task_indexes_instructions_and_inputs`, `::test_checkpoint_inserts_index_their_blobs`, `::test_refused_fenced_checkpoint_leaves_no_index_row`, `::test_event_publish_indexes_attachments`, `::test_conflict_keeps_the_stronger_class_and_a_delete_mark`, `::test_a_failed_index_write_rolls_back_its_holder_row`. `grep -rn "def complete\b\|\.complete("` over common/orchestrator/harness_activity found nothing | PASS |
| 2.2 put(task_id), upload refs before record_task | integration test; mypy | `tests/integration/test_upload_refs.py::test_submit_uploads_are_held_by_their_task_before_record_task` (asserts `TaskRepository.get(...) is None`, then 3 `upload` rows: instructions + 2 inputs), `::test_repeat_put_clears_a_removal_and_keeps_the_stronger_class`, `::test_a_deleted_tasks_late_upload_of_the_same_bytes_revives_nothing`, `::test_a_deleted_tasks_late_upload_of_new_bytes_leaves_no_live_reference`; mypy `Success: no issues found in 169 source files` | PASS |
| 2.3 end_task indexes artifacts, sets ended_at | test for each terminal status | `tests/integration/test_index_writers.py::test_end_task_sets_ended_at_and_indexes_artifacts[succeeded]`, `[failed]`, `[needs_input]`, `::test_a_retried_end_task_keeps_a_redaction` | PASS |
| 2.4 writers use the new classes | fake-model task reads each class back from rows and `blob_refs` | `tests/integration/test_task_e2e.py::test_scripted_task_end_to_end` (asserts the row classes per table and the index set `upload/transcript`, `upload/checkpoint`, `upload/artifact`, `tasks.instructions_ref/transcript`, `checkpoints.workspace_ref/checkpoint`, `tasks.result/artifact`; artifact blob `artifact`). `grep retention=` shows writers pass `transcript` (submit.py:40,49), `checkpoint` (activity.py:537, dsh/session.py:86) and `artifact` (activity.py:693) | PASS |
| 2.5 AuditRepository.append | integration test | `tests/integration/test_audit_log.py::test_append_joins_the_callers_transaction` (a rolled-back append leaves nothing; actor starts `cli:`; class `audit`) | PASS |
| 3.1 replay with old `task` payloads | `pytest tests/test_task_workflow.py` | `tests/test_task_workflow.py::test_task_workflow_replay` PASSED (all 14 in the file passed). I decoded the fixture `tests/fixtures/task_workflow_history.json` independently: `3 payload(s) with retention_class task` (WorkflowExecutionStarted input and 2 ActivityTaskScheduled inputs) | PASS |
| 3.2 questions truncated | unit test with 21 questions of 600 chars | `tests/test_finish_task.py::test_questions_are_truncated` (21 x 600 -> 20 x 500, summary 2000), `::test_short_questions_are_unchanged` | PASS |
| 3.3 64 KiB history guard | 20 x 500 passes; a seeded 65 KiB payload fails | `tests/integration/test_history_payloads.py::test_twenty_long_questions_stay_under_the_limit` PASSED (real Workflow through the workers, `needs_input` with 20 x 500 questions and a 2,000-char summary). `tests/test_history_guard.py::test_a_seeded_65_kib_payload_fails` and 5 more PASSED. Session guard `tests/integration/conftest.py::history_payload_guard`: no failure after the 279-test or the 249-test run. **I also ran it live** (below) | PASS |
| 4.1 docs | `check_plans.py` and the link check pass | `Validated 8 implementation plan(s); 0 error(s)`; lychee `0 Errors`. I read the additions: schemas.md (blob_refs, audit_log, new columns, classes, outbox pattern), threat-model.md (C18, R9 no encryption at rest / clear-text backups, R10 app role owns audit_log, R11 72 h history residual), decision-log.md (2 entries dated 2026-11-20) | PASS |

### Task 1.1: the round trip, done by hand (`.verify/m0007/`)

Commands:
- `docker exec -u postgres pmverify3a-db-1 psql -c "CREATE DATABASE verify_m0007 OWNER praxismesh TEMPLATE template0"`, then `CREATE EXTENSION IF NOT EXISTS pg_search CASCADE` (as `tests/support/scratch_db.py` does).
- `uv run --env-file infra/.env alembic -c common/persistence/alembic.ini -x database=verify_m0007 upgrade 0006`, then `psql < seed.sql`, `upgrade 0007`, `downgrade 0006` and `upgrade 0007`. Output is in `roundtrip.log`.

The seed (`seed.sql`) has 4 tasks:
- `t-ok`, succeeded: instructions, 2 inputs, and 2 artifacts with JSON class `audit`. One artifact shares its blob `aa03` with an input.
- `t-fail`, failed.
- `t-ask`, needs_input, with an `audit` artifact `cc02`.
- `t-run`, running.

It also has 2 checkpoints (one with a session ref, one with `session_ref` NULL), 2 agent_events (one with `blob_ref`), 13 blob_objects including an orphan, and one row in each other application table.

Observed after `upgrade 0007` (identical again after downgrade and upgrade):

```
 holder_table | holder_key  |  holder_column   |  blob_key   | task_id | request_id | retention_class | live
 agent_events | t-ok/1      | blob_ref         | sha256/ff01 | t-ok    | req-A      | transcript      | t
 checkpoints  | t-ok/1/1/0  | session_ref      | sha256/ee02 | t-ok    | req-A      | checkpoint      | t
 checkpoints  | t-ok/1/1/0  | workspace_ref    | sha256/ee01 | t-ok    | req-A      | checkpoint      | t
 checkpoints  | t-run/1/1/0 | workspace_ref    | sha256/ee03 | t-run   | req-B      | checkpoint      | t
 tasks        | t-ask       | instructions_ref | sha256/cc01 | t-ask   | req-B      | transcript      | t
 tasks        | t-ask       | result           | sha256/cc02 | t-ask   | req-B      | artifact        | t
 tasks        | t-fail      | instructions_ref | sha256/bb01 | t-fail  | req-A      | transcript      | t
 tasks        | t-ok        | input_refs       | sha256/aa02 | t-ok    | req-A      | transcript      | t
 tasks        | t-ok        | input_refs       | sha256/aa03 | t-ok    | req-A      | transcript      | t
 tasks        | t-ok        | instructions_ref | sha256/aa01 | t-ok    | req-A      | transcript      | t
 tasks        | t-ok        | result           | sha256/aa03 | t-ok    | req-A      | artifact        | t
 tasks        | t-ok        | result           | sha256/aa04 | t-ok    | req-A      | artifact        | t
 tasks        | t-run       | instructions_ref | sha256/dd01 | t-run   | req-B      | transcript      | t
(13 rows)
```

`blob_objects` classes, before (0006) -> after (0007):

| Blob | Before | After |
|---|---|---|
| `0rphan` | task | ephemeral |
| `aa01` | task | transcript |
| `aa02` | task | transcript |
| `aa03` | task | artifact (strongest of input and artifact) |
| `aa04` | audit | artifact |
| `bb01` | task | transcript |
| `cc01` | task | transcript |
| `cc02` | audit | artifact |
| `dd01` | task | transcript |
| `ee01`, `ee02`, `ee03` | task | checkpoint |
| `ff01` | task | transcript |

All 13 have `has_last_put = t`, and `removed_at`, `removed_by` and `bucket_deleted_at` are null.

Table classes after 0007:

| Class | Tables |
|---|---|
| `transcript` | agent_events, agent_messages, agent_sessions, event_logs, idempotency_keys, task_inbox, task_messages |
| `checkpoint` | checkpoints |
| `ephemeral` | event_batches, message_wakes |
| `artifact` | sample_orders |
| `audit` | task_attempts, tasks, usage_ledger |

The server defaults match the same mapping (`'transcript'::text` etc.). `audit_log` defaults to `'audit'`, and blob_objects and blob_refs have none.

`ended_at`:

```
 t-ask   | needs_input | 2026-10-04 00:00:00+00 | 2026-10-04 00:00:00+00
 t-fail  | failed      | 2026-10-03 00:00:00+00 | 2026-10-03 00:00:00+00
 t-ok    | succeeded   | 2026-10-02 03:04:05+00 | 2026-10-02 03:04:05+00
 t-run   | running     | 2026-10-05 00:00:00+00 |
```

`audit_log | 1` (the table and its trigger exist).

After `downgrade 0006`:
- `to_regclass` is NULL for `blob_refs` and `audit_log`.
- None of the new columns remain (`(0 rows)`).
- The table classes are back to their 0006 values (checkpoints `task`, idempotency_keys `audit`, sample_orders `task`, ...).

The unindexed check (R2), run as `PYTHONPATH=$PWD uv run --env-file infra/.env python .verify/m0007/unindexed.py` (`unindexed.log`):

```
unindexed after migration: []
unindexed with event index row removed: [Reference(blob_key='sha256/ff01', holder_table='agent_events', holder_key='t-ok/1', holder_column='blob_ref', task_id='t-ok', request_id='req-A', retention_class='transcript')]
```

The second line is a control: I deleted one index row inside a rolled-back transaction, and the check found it.

Observation (no finding): the downgrade does not exactly undo the class changes for blobs. The orphan stays `ephemeral` instead of returning to `task`, and `aa03` (input and artifact) becomes `audit` instead of `task`. The plan limits downgrade to before new writes, and `test_migration_0007` asserts the same mapping. The scratch database was dropped afterwards (`DROP DATABASE verify_m0007 WITH (FORCE)`).

### Task 1.2 / R14: manual probe as the app role (`m0007/audit_trigger.log`, `audit_truncate.log`)

`psql -h 127.0.0.1 -U praxismesh -d verify_m0007` (`current_user = praxismesh`):
- `INSERT` -> `id 1, retention_class audit`
- `UPDATE` -> `ERROR:  audit_log is append-only: UPDATE refused`
- `DELETE` -> `ERROR:  audit_log is append-only: DELETE refused`
- The row is still `1 | x`.

`TRUNCATE audit_log` inside a transaction then rolled back: `rows_after_truncate 0`. The app role can therefore truncate the table. Threat model R10 already accepts this residual until Phase 9 ("can `TRUNCATE` the table or disable its trigger"), so it is not a finding against R14, which names only UPDATE and DELETE.

### Task 3.3: the guard, live (`15-guard-live.log`)

`.verify/guard_live.py` starts two real Workflows on the pmverify3a Temporal, on a task queue no worker polls: one with a 1 KiB input and one with a 65 KiB input. It runs the suite's `guard_failure` after each start, then terminates both:

```
small only: None
with 65 KiB: 1 history payload(s) over 65536 bytes:
verify-big-68cc2c13 event 1 (workflow_execution_started_event_attributes): 66590 bytes
terminated verify-small-68cc2c13 verify-big-68cc2c13
```

The 20 x 500 case passed both as a real Workflow (`test_history_payloads`) and under the session guard.

## 2d. Each delivered requirement

| Req | Observed evidence | Holds? |
|---|---|---|
| R1 indexed with holder, same transaction | `test_upload_refs::test_submit_uploads_are_held_by_their_task_before_record_task` (two inputs and instructions held by the task before `record_task`); `test_index_writers::test_refused_fenced_checkpoint_leaves_no_index_row`; `::test_a_failed_index_write_rolls_back_its_holder_row`; the record_task, checkpoint, event and end_task writer tests | Yes |
| R2 pre-existing refs indexed; ended tasks get ended_at | My round trip: 13 index rows covering every notes.md#refs column, `unindexed after migration: []`, `ended_at` set for succeeded, failed and needs_input and null for running; `test_migration_0007_backfills_remaps_and_round_trips` | Yes |
| R4 new writes carry the D3 class, never `task` | `test_task_e2e::test_scripted_task_end_to_end` (rows and index); `test_index_writers::test_checkpoint_inserts_index_their_blobs` (`checkpoint`); `test_migration_0007::test_new_defaults_and_checks` (an `event_logs` insert without a class reads `transcript`). The `agent_events` default is `'transcript'::text` in my scratch DB. `test_retention::test_task_is_never_written` | Yes |
| R5 old `task` histories decode | `test_task_workflow::test_task_workflow_replay` over a fixture with 3 `retention_class: task` payloads (counted independently); `test_retention::test_old_payloads_still_decode` | Yes |
| R14 app role refused UPDATE/DELETE | `test_audit_log::test_app_role_cannot_change_audit_rows[UPDATE...]`, `[DELETE...]`; manual probe errors quoted above | Yes (TRUNCATE residual accepted as threat-model R10) |
| R18 no history payload over 64 KiB in the suite | Session guard passed after both integration runs; `test_history_payloads::test_twenty_long_questions_stay_under_the_limit`; the live probe shows the guard catches 65 KiB | Yes |
| R19 existing rows move to D3 classes; `audit` artifact -> `artifact` | My round trip: every table's `task`/`audit` rows remapped as tabulated; `aa04` and `cc02` (JSON class `audit`) carry `artifact` in both `blob_refs` and `blob_objects` | Yes |
| R20 end_task sets ended_at | `test_index_writers::test_end_task_sets_ended_at_and_indexes_artifacts[succeeded|failed|needs_input]` | Yes |

## 3. Demo

Not applicable to this phase: the plan's demo belongs to phase 03.

## Findings

**F1 (documentation, existing before this phase): the integration suite fails while the documented workers are running.**

Running the stack as README directs (`make up`, `make migrate`, `make workers-up`) and then `uv run --env-file infra/.env pytest -m integration` (or `make smoke`) fails 4 Phase 2 messaging tests:
- `test_comms_mcp.py::test_a_send_wakes_a_sleeping_recipient_as_the_comms_role`
- `test_dispatcher.py::test_a_wake_waits_for_a_stopped_dispatcher_and_is_then_delivered`
- `test_dispatcher.py::test_a_wake_for_a_closed_workflow_is_deleted_and_logged`
- `test_dispatcher.py::test_a_wake_sent_while_its_row_is_signalled_is_kept`

The cause: the orchestrator container's dispatcher deletes the tests' wake rows. Its log shows `"msg": "wake for a closed workflow dropped", "workflow_id": "inbox-closed-40fc8afc"`. The failure is reproducible: all 4 failed again on rerun with the workers up, and all 4 passed after `make workers-down` (`4 passed in 5.81s`). A full `make smoke` with the workers down gave `249 passed`.

No document (README, AGENTS.md "Checks", runbook) says to stop the workers before running the integration suite. CI avoids the problem only because it runs `make smoke` before `make workers-check`. Phase 01 does not cause this.

**F2 (flaky test, outside the phase): `tests/test_runner_conformance.py::test_refusals_are_logged_with_ids[dsh]`.**

It failed once in the full run (`KeyError: 'refused tool call'` at tests/test_runner_conformance.py:422) and passed on an immediate rerun (`11-rerun-workers-up.log`). This phase did not change the test file. It did change `harness_activity/tools.py` (13 lines, the question truncation), and I did not trace whether that change touches refusal logging.

**Blocked:**
- gitleaks and actionlint are not installed on this host (`which: no gitleaks`, `which: no actionlint`).
- The link check used the local lychee 0.24.2 image, not CI's pinned action, so the version may differ.

## Changes I made

- I created and dropped the scratch database `verify_m0007` on the pmverify3a db.
- I started 2 probe Workflows (`verify-small-68cc2c13`, `verify-big-68cc2c13`) on the pmverify3a Temporal and terminated them.
- I ran `make workers-down`, then `make workers-up` again.
- I rebuilt the `praxismesh-worker:dev` / `praxismesh-dsh:dev` tags from this commit through `make workers-up`.
- I made no source, test or documentation edits. Every file I wrote is under `.verify/`.

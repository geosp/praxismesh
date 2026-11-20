## Contract review: phase 01 (R1, R2, R4, R5, R14, R18, R19, R20), diff 8cc4355..a50c358

**Verdict:** no Blocker or Major findings. Every delivered requirement has code that enforces it and at least one test that would fail without it. I found 12 Nits: gaps in what the tests can observe, and small mismatches with the contract text. I ran nothing, as the brief required, so this is from reading the code and tests only.

### Promise map (where each promise is enforced, and the test that would fail)

**R1 (indexed in the same transaction).** I checked every place it applies:
- **Row writers:**
  - `record_task`: `common/persistence/repositories.py` ~L90-104; test `tests/integration/test_index_writers.py::test_record_task_indexes_instructions_and_inputs`.
  - `insert_fenced` and `insert`: through `_index_checkpoint` (repositories.py L430, L454, L498); tests `test_checkpoint_inserts_index_their_blobs` and `test_refused_fenced_checkpoint_leaves_no_index_row`. That second test is R1's second scenario.
  - Event publish: `common/events/table.py:100-107`; test `test_event_publish_indexes_attachments`.
  - `end_task`: `common/persistence/messages.py:303-314`; test `test_end_task_sets_ended_at_and_indexes_artifacts`.
  - I grepped every `INSERT INTO tasks|checkpoints|agent_events` and `UPDATE tasks` in non-test code. No other writer exists, and `TaskRepository.complete` is removed.
- **Uploads:**
  - The submit's uploads: `orchestrator/submit.py:36-50`, where the task ID is now minted first.
  - Workspace: `harness_activity/activity.py:536`. Artifacts: activity.py:693. DSH session: `harness_activity/dsh/session.py:85`.
  - Production wires `RecordingBlobStore` in `workers/main.py:162` and `orchestrator/cli.py:95`.
  - Tests: `tests/integration/test_upload_refs.py`, and the index assertions in `tests/integration/test_task_e2e.py`.

**R2 (backfill).** Migration 0007 `REFERENCES` and its backfill insert (`0007_blob_refs_and_classes.py:84-123, 213-218`), and `ended_at` set from `updated_at` (L212). Tests: `test_migration_0007.py::assert_migrated` asserts `refs.unindexed == []` and the `ended_at` values. `tests/test_retention.py::test_reference_query_matches_the_migration` keeps the migration's query and `refs.REFERENCES` identical.

**R4 (new classes).**
- Writers use the new classes: `submit.py`, `activity.py:537,693`, `dsh/session.py:86`.
- Checkpoint inserts no longer hardcode `'task'`.
- The migration sets each table's server default from `TABLES`.
- `current_class` stops `task` being written, in `common/blob_store/base.py`, `s3.py` and `memory.py`, and in `refs.index_keys` and `RecordingBlobStore.put`.
- Tests: `test_task_e2e.py` (classes of rows and index rows), `test_retention.py::test_task_is_never_written` and `::test_stronger_never_returns_task`, `test_migration_0007.py::test_new_defaults_and_checks`.

**R5 (old histories decode).** `RetentionClass` keeps `task` (`common/schemas/base.py:13`). Test: `tests/test_task_workflow.py::test_task_workflow_replay`. I confirmed its fixture holds 3 payloads with `retention_class: task`. `test_retention.py::test_old_payloads_still_decode` covers decoding outside replay.

**R14 (audit log refuses changes).** A trigger raises on BEFORE UPDATE OR DELETE (migration L171-185). Test: `tests/integration/test_audit_log.py::test_app_role_cannot_change_audit_rows`, run as the app role through `make_engine`.

**R18 (no history payload over 64 KiB).**
- `tests/support/history_guard.py`, run by the session fixture in `tests/integration/conftest.py`.
- Questions truncated in `harness_activity/tools.py:226-229`.
- Tests: `tests/test_history_guard.py` (the seeded 65 KiB payload), `tests/integration/test_history_payloads.py` (20 questions of 500 characters), `tests/test_finish_task.py::test_questions_are_truncated` (21 questions of 600 characters).

**R19 (class remap).** Migration L201-226: the table remap, and each blob's class set from its strongest index row, or `ephemeral` with none. Test: `test_migration_0007.py`. It includes an old `audit` artifact that becomes `artifact` in both `blob_refs` and `blob_objects`, and a downgrade and upgrade round trip.

**R20 (`ended_at`).** `messages.py:303-305`. Test: parametrised over `succeeded`, `failed` and `needs_input`, plus a retried call.

**Decisions stated as rules:**
- **D2 (in-scope parts):**
  - One helper, `refs.index_refs`/`index_keys`, does every write.
  - On a conflict the stronger class wins, a GC mark is cleared and a delete's mark stays (`refs.py:165-174`; test `test_conflict_keeps_the_stronger_class_and_a_delete_mark`).
  - An upload reference names no request.
  - Expiry is computed, not stored (`refs.expired` and `refs.rowless_uploads`; tests in `test_refs.py`).
- **D3:**
  - Lifetimes, order and the `task` rank (`common/persistence/retention.py`, `base.py:RETENTION_ORDER`).
  - Every table's class checked against notes.md#d3 (`test_every_app_table_has_its_d3_class`).
  - Checks still allow `task` (`test_new_defaults_and_checks`).
- **D9:** truncation at the source; schemas unchanged.
- **D10 steps 1-2:** `RecordingBlobStore.put` collects the bytes, then in one transaction upserts `blob_objects` (clearing the marks and setting `last_put_at`) and writes the upload reference, then uploads (repositories.py:656-695). Test: `test_repeat_put_clears_a_removal_and_keeps_the_stronger_class`.

### Findings

No Blockers. No Majors.

**Nits** (location, what, why):

1. `tests/integration/test_task_e2e.py:76` and `tests/integration/test_dsh_outcomes.py:298` (R4, D3). A newly written row's `BlobRef` JSON can carry `audit`, because `S3BlobStore.put` takes the class from the object's old metadata (`s3.py`, `stronger(current, retention)`), and the tests were loosened to accept it. The plan says S3 metadata "is never read for one". It isn't used for a lifetime (the index and `blob_objects` say `artifact`), but the stored JSON for new writes isn't the D3 class. I rate it Nit because nothing decides from it.
2. `tests/support/history_guard.py:81` (R18). The guard skips any run it can't find. `test_task_e2e.py::test_duplicate_task_id_rejected` deletes its first run, so that history is never checked. "No Workflow history of the suite" therefore has one exception. It's a Nit because that run has the same shape as runs that are checked.
3. `tests/integration/conftest.py:28` (R18). If Temporal can't be reached at teardown, the guard only warns and the suite passes. The failing path through `pytest.fail` in session teardown is also never exercised. Only `large_payloads` is unit-tested.
4. `tests/integration/test_upload_refs.py:34-37` (R1, first scenario). The scenario says "two input files", but the test submits one. With an inner `MemoryBlobStore`, it also never observes the S3 path. The code is per-key, so this is a Nit.
5. R1 and R20 "in the same transaction": only the refused fenced checkpoint is observed. No test makes the index write fail inside `record_task`, `end_task` or `publish` to show that the holder row rolls back with it. One way to test it: inject a failing `index_keys`, for example by monkeypatching it to raise, and assert the row is absent.
6. `harness_activity/dsh/session.py:85` (R1). No test observes that the DSH session upload is held by its task. `test_dsh_runner_parts` uses `MemoryBlobStore`, which ignores `task_id`, and no DSH integration test reads `blob_refs`. Dropping `task_id=self.task_id` would fail no test.
7. `common/persistence/repositories.py:680-693` (D10, task 2.2, "`blob_objects` locked first"). The lock order can't be observed with single-session tests. It matters only for phase 02's concurrent removals.
8. Migration `_default` (R4). After 0007, no test reads back the default class of a newly inserted row in `idempotency_keys`, `event_batches`, `task_messages` or `task_inbox`. Only `event_logs` and the tables the e2e test covers are checked. It's a Nit because the defaults come from the same `TABLES` dict that `test_migration_0007_uses_the_same_classes` checks.
9. `harness_activity/activity.py:511` and `:724` (D9). Questions loaded back from a checkpoint's `finish` reach `TurnOutcome` without the cap; only `summary` is re-truncated. A checkpoint written before the change with more than 20 questions would pass through. The rollout drains Workflows first, so this is a Nit.
10. Migration `downgrade` (Rollout: "maps classes back"). `event_batches` rows remapped to `ephemeral` stay `ephemeral` after a downgrade, not `task`. The old check allows the value, so this is a Nit.
11. `common/persistence/refs.py:339-342` (task 1.4, notes.md#d2 "for each bucket object that has none"). Reindex skips bucket objects whose key isn't a content key. The docstring says so; it's a slight narrowing of the notes.
12. `docs/security/threat-model.md`, accepted risk R9. It says "`backups/` is git-ignored", but `.gitignore` at a50c358 has no `backups` entry. Backups arrive in phase 03, so the claim is early rather than harmful.

### Relevant files
- /home/geo/develop/praxismesh/common/persistence/migrations/versions/0007_blob_refs_and_classes.py
- /home/geo/develop/praxismesh/common/persistence/refs.py
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/common/events/table.py
- /home/geo/develop/praxismesh/common/blob_store/s3.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/harness_activity/dsh/session.py
- /home/geo/develop/praxismesh/tests/support/history_guard.py
- /home/geo/develop/praxismesh/tests/integration/conftest.py
- /home/geo/develop/praxismesh/tests/integration/test_task_e2e.py
- /home/geo/develop/praxismesh/tests/integration/test_upload_refs.py
- /home/geo/develop/praxismesh/docs/security/threat-model.md

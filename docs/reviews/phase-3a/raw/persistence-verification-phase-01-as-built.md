<!-- Verbatim verifier report (Phase 3A persistence plan, phase 01 gate verification, as-built claims, code and docs at bbfe1ce); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-as-built.md per docs/reviews/README.md rule 1. -->

# As-built documentation check: Phase 3A persistence plan, phase 01

- Checkout: `/tmp/claude-1000/-home-geo-develop-praxismesh/5562944e-be36-4ae6-b40e-bb1b87da77f8/scratchpad/verify-phase3a-01`
- code_sha = docs_sha = `bbfe1ceb5cdc5e36138a4d9fbdbc10d117259844` (`git rev-parse HEAD` printed it; the only untracked path is `.verify/`)
- Live stack: Compose project `pmverify3a` (all containers `Up`/healthy; `alembic_version` = `0007`). No `praxismesh-*` container or volume was touched.
- I did not write to any database. Probes were `psql -U postgres` SELECTs and `\d` inside `pmverify3a-db-1`, one Python check inside a `SET TRANSACTION READ ONLY` transaction, and one `temporal operator namespace describe` from a throwaway `temporalio/admin-tools:1.32.2` container on network `pmverify3a_default`.
- I unset VIRTUAL_ENV and removed `.venv` entries from PATH before every `uv run`.
- Raw probe output is in `.verify/asbuilt-probe-schema.txt`, `asbuilt-probe-roles.txt`, `asbuilt-probe-classes.txt`, `asbuilt-probe-temporal.txt` and `asbuilt-probe-unindexed.txt`. The probe script is `.verify/asbuilt_unindexed.py`.

## Verdict

Every claim in the four sections this phase owed (the phase 01 block of schemas.md, the threat model's C18/R9-R11 and assets row, and the two decision-log entries) is either confirmed or clearly labelled as later-phase work. **No Blocker and no Major findings.**

There are three Nit findings. Each is an older as-built sentence that still names the Phase 1-2 classes. Two are in the architecture overview and one is earlier in schemas.md. Migration 0007 made all three untrue.

## Findings (contradicted or unverifiable)

| # | Severity | Location | Claim (quoted) | Evidence |
|---|---|---|---|---|
| N1 | Nit | docs/roadmap/schemas.md:41-42 (Phase 2 events as-built paragraph) | "All three carry retention class `task`." (`agent_events`, `event_logs`, `event_batches`) | Migration 0007 remaps these tables (`0007_blob_refs_and_classes.py` TABLES: `event_logs`/`agent_events` -> `transcript`, `event_batches` -> `ephemeral`). Live server defaults: `agent_events 'transcript'`, `event_logs 'transcript'`, `event_batches 'ephemeral'`. Live rows: `agent_events task-rows=0 classes=transcript`, `event_batches task-rows=0 classes=ephemeral`. The paragraph is scoped "as built for ... migration 0005", so it is historically true. It still contradicts the phase 01 paragraph 30 lines further down the same document. |
| N2 | Nit | docs/architecture/overview.md:204 (Phase 2 "Event tables" row) | "All carry retention class `task` and are listed in `APP_TABLES`." | Same evidence as N1. `APP_TABLES` membership is still true (`retention.py` `TABLE_CLASS`). |
| N3 | Nit | docs/architecture/overview.md:75 (Phase 1 `run_harness_turn` row) | "finishes with outputs as `audit` artifacts" | Artifacts are now class `artifact`: `harness_activity/activity.py:693` `self.blobs.put(data, retention="artifact", task_id=turn.task_id)`. The `end_task` index rows are `artifact` (`retention.py` REFERENCE_CLASS `("tasks","result"): "artifact"`). Live: `tasks | result | artifact | 41` and `upload | | artifact | 37`. Live `blob_objects` classes are `artifact,checkpoint,transcript`, none `audit`. |

These three sentences are not phase 01's deliverable (task 4.1 lists schemas.md's new sections; the overview is phase 03's work), but they now state the wrong class for current code.

No claim was unverifiable. The labelled-future claims are listed at the end.

## Claim-by-claim results

### docs/roadmap/schemas.md:70-96 (phase 01 as-built)

| # | Claim | Result | Evidence |
|---|---|---|---|
| S1 | Classes `ephemeral` 1 day, `checkpoint` 7 d, `transcript` 30 d, `artifact` 90 d, `audit` kept | Confirmed | `common/persistence/retention.py:18-25` DEFAULT_LIFETIME (`audit: None`); `common/schemas/base.py:13` `RetentionClass = Literal["ephemeral","checkpoint","transcript","artifact","audit","task"]` |
| S2 | Lifetimes are counted from `tasks.ended_at`; `ephemeral` is counted from the write | Confirmed | `common/persistence/refs.py:298-319` `expired()`: `t.ended_at + make_interval(secs => life) < :now OR (retention_class='ephemeral' AND r.created_at + ... < :now)`. Note: an `ephemeral` reference also expires 1 day after `ended_at`. No phase 01 writer creates `ephemeral` references; REFERENCE_CLASS has none and no `put` caller passes `ephemeral`. |
| S3 | `task` stays readable, ranks as `transcript`, nothing writes it | Confirmed | `common/blob_store/base.py:21-28` RETENTION_ORDER `"task": 2` = `transcript`; `DEFAULT_LIFETIME["task"]` = 30 d. Writers call `current_class()` (`refs.py:175`, `repositories.py:681`). Every `put` caller passes a new class (`orchestrator/submit.py:40,49`, `harness_activity/activity.py:537,693`, `harness_activity/dsh/session.py:86`), and record_task inserts `'audit'` (`repositories.py:66`). Live: `task-rows=0` in all 17 tables (`asbuilt-probe-classes.txt`). |
| S4 | Each table's class is notes.md#d3's table (`TABLE_CLASS`) | Confirmed | `retention.py:32-50` matches `notes.md:83-91`. Live server defaults match TABLE_CLASS for all 15 tables that have one; `blob_objects` and `blob_refs` have no default (TABLE_CLASS `None`). `uv run pytest -q tests/test_retention.py tests/test_history_guard.py` -> `20 passed in 0.33s`. |
| S5 | "every check still allows `task`" | Confirmed | Live: every `*_retention_class_check` is `ANY (ARRAY['ephemeral','checkpoint','transcript','artifact','audit','task'])` (17 tables). |
| S6 | `blob_refs` columns: `holder_table`, `holder_key` (the holder's primary key as text), `holder_column`, `task_id`, `request_id`, class, `created_at`, `removed_at`, `removed_by`, one row per holder and blob key | Confirmed | Live `\d blob_refs`: those columns plus `blob_key`; `PRIMARY KEY (holder_table, holder_key, holder_column, blob_key)`; `created_at` default `CURRENT_TIMESTAMP`. Holder keys match the live PKs: checkpoints `PRIMARY KEY (task_id, turn, attempt, seq)` vs `refs.py:111` `f"{task_id}/{turn}/{attempt}/{seq}"`; agent_events `PRIMARY KEY (workflow_id, "offset")` vs `refs.py:115`; tasks `(task_id)`. |
| S7 | `request_id` is null for an upload | Confirmed | `refs.py:179-183` writes `NULL` when `holder.table == UPLOAD`. Live: `upload` rows `with_req 0` (609 rows); every other holder has a request ID on every row. |
| S8 | Every row that stores a `BlobRef` (`tasks`, `checkpoints`, `agent_events`) writes its index rows in its own transaction | Confirmed | `record_task` `repositories.py:91-106`, inside the insert's `engine.begin()`; checkpoints `insert_fenced` `:402-432` and `insert` `:434-456` call `_index_checkpoint` in the same transaction; event publish `common/events/table.py:98-107`; `tasks.result` via `end_task` `messages.py:300-317`. A JSON scan of every json column (`asbuilt-probe-classes.txt`) found blob keys only in those holders' columns. The read-only `refs.unindexed()` on the live DB returned `unindexed references: 0`. |
| S9 | Every upload made for a task is held by the task (`upload`, task ID, '') | Confirmed | `refs.py:119-120` `Holder(UPLOAD, task_id, "")`; `RecordingBlobStore.put` `repositories.py:720-729`. Every production `put` passes `task_id`: `submit.py:37-50` (minted at :36 before the upload), `activity.py:536,693`, `dsh/session.py:85`. Live: 609 `upload` rows. |
| S10 | Removed references stay, marked; expiry is computed, never stored | Confirmed | No production code runs `DELETE FROM blob_refs`; the only `UPDATE blob_refs` statements are in tests. No expiry column exists in `\d blob_refs` or `\d blob_objects`. `retention.py:6` says "nothing stores an expiry time". |
| S11 | `audit_log`: `actor` (`cli:<OS user>`), `action`, `subject`, `operation_id`, `details`, class `audit`; trigger refuses UPDATE and DELETE | Confirmed | Live `\d audit_log` shows these columns, `retention_class` default `'audit'`, and `Triggers: audit_log_append_only BEFORE DELETE OR UPDATE ... FOR EACH ROW`. pg_trigger `tgenabled = O`. The function raises `'audit_log is append-only: % refused'` (migration 0007). The actor default is `audit.py:15-22` `cli_actor()`. |
| S12 | `details` holds counts and IDs, never content | Confirmed (as a convention) | `audit.py:37-38` docstring. No production caller of `AuditRepository.append` exists yet (grep finds only the class), so no writer could break the rule. Live `audit_log.details` contains no blob keys (0 rows). |
| S13 | `tasks.ended_at` is set by `end_task` | Confirmed | `messages.py:304-311` sets `ended_at = CURRENT_TIMESTAMP ... WHERE ended_at IS NULL`. No other `UPDATE tasks` statement exists outside the migration backfill (`0007:211`). The other `ended_at` writes in repositories.py (:179, :222, :267, :333) are on `task_attempts`. Live: succeeded 69/69, needs_input 6/6 and failed 24/24 have `ended_at`; running 0/234. |
| S14 | `blob_objects.removed_at`, `removed_by`, `last_put_at` (set on each `put`), `bucket_deleted_at` | Confirmed | Live `\d blob_objects` shows all four columns; `last_put_at` is NOT NULL, default `CURRENT_TIMESTAMP`. `put` sets `last_put_at = now()` on insert and on conflict (`repositories.py:697-705`). Edge case: for a task that a delete marked, an existing row keeps its `last_put_at` (`:709-718`, `SET key = blob_objects.key`), per decision-log D10. Nothing in this checkout writes `delete:` marks (only tests do), so this branch cannot run on the current system. |
| S15 | Outbox pattern: commit a row with the write; one drainer acts idempotently and deletes the row only after the other service accepts; `message_wakes`, drained by the dispatcher into `inbox` Signals, is the only instance; no general outbox table | Confirmed | `messages.py:523-530` inserts the wake in the sender's transaction. `orchestrator/dispatcher.py:77-102` runs `DELETE` in a per-row transaction and `rollback()`s it unless `_signal` returns true (accepted, or the Workflow is gone, `:104-118`). The live table list has no outbox table. |

### docs/security/threat-model.md

| # | Claim | Result | Evidence |
|---|---|---|---|
| T1 | Assets row (line 18): `blob_refs` and `audit_log` (append-only tombstones of removals) are in the `praxismesh` database | Confirmed | Both tables are in `praxismesh` (`pg_tables`). "Tombstones of removals" is the table's purpose. Removal writers arrive in phase 02; no production code appends yet (S12). |
| T2 | C18 (line 62): append-only for the app role via a trigger; test `tests/integration/test_audit_log.py::test_app_role_cannot_change_audit_rows` | Confirmed | The trigger is live (S11). The test exists at `test_audit_log.py:22`, uses `make_engine()` (the app role, `settings.py:14` `APP_DB_USER = "praxismesh"`) and expects `"audit_log is append-only"`. |
| T3 | R9 (line 76): no encryption at rest; SeaweedFS objects and databases are clear text; `backups/` is git-ignored; backups "from Phase 3A's backup" | Confirmed; backups are labelled future | No encryption or SSE option in `common/` or `infra/` (grep `ServerSideEncryption|SSECustomer|encrypt` found nothing). `git check-ignore -v backups/x.dump` -> `.gitignore:40:/backups/`. The backup itself is phase 03's work and is labelled as such. |
| T4 | R10 (line 77): the app role owns `audit_log`, so it can TRUNCATE or disable the trigger; one role for workers, CLI and migrations | Confirmed | Live `audit_log` owner `praxismesh`; `has_table_privilege('praxismesh','audit_log','TRUNCATE') = t`. A PostgreSQL table owner can run `ALTER TABLE ... DISABLE TRIGGER`; I did not try it because the brief forbids writes. Migrations run as the app role (`migrations/env.py:3`, `app_database_url`); workers and the CLI use `APP_DB_USER`. |
| T5 | R11 (line 78): histories keep summary, questions and outcome for `TEMPORAL_RETENTION`, 72 h by default; `finish_task` bounds summary to 2,000 characters and 20 questions of 500 | Confirmed | `infra/.env.example:31` `TEMPORAL_RETENTION=72h`; compose default `${TEMPORAL_RETENTION:-72h}`. Live namespace describe: `"workflowExecutionRetentionTtl": "259200s"` (= 72 h). Bounds: `harness_activity/tools.py:209-214,233` (`QUESTIONS_MAX = 20`, `QUESTION_MAX_CHARS = 500`, `summary[:2000]`) and `activity.py:723` `summary=result.summary[:2000]`. |

### docs/roadmap/decision-log.md

| # | Claim | Result | Evidence |
|---|---|---|---|
| D1 | Line 10: classes as in S1-S3 | Confirmed | See S1-S5. |
| D2 | Line 10: every stored `BlobRef` and every upload for a task is indexed in its writer's transaction | Confirmed | See S8 and S9; live `unindexed references: 0`. |
| D3 | Line 10: `tasks.ended_at` anchors expiry | Confirmed | See S2 and S13. |
| D4 | Line 10: `audit_log` is append-only for the app role | Confirmed | See S11 and T2. |
| D5 | Line 10: `finish_task` keeps at most 20 questions of 500 characters | Confirmed | See T5. |
| D6 | Line 10: the integration suite fails if any Workflow history payload exceeds 64 KiB | Confirmed (code) | `tests/support/history_guard.py:18` `LIMIT_BYTES = 64 * 1024`. `tests/integration/conftest.py:15-25` is a session autouse fixture that calls `pytest.fail` when a payload is too large or Temporal is unreachable. `tests/test_history_guard.py` passed in the run above. I did not run the integration suite here; this was a documentation check. |
| D7 | Line 10: threat model gains C18 and R9-R11 | Confirmed | threat-model.md:62 and :76-78. |
| D8 | Line 10: nothing is removed until phase 02 | Confirmed | No production delete of `blob_refs`; no `audit_log` appender; `DELETE_OPERATION` (`refs.py:37`) is used only as a mark. `RecordingBlobStore.delete` (`repositories.py:742-745`) exists from earlier phases, but no production caller of `blobs.delete` was found among the `put`/`delete` call sites grepped. |
| D9 | Line 9: `put` takes the task lock, writes the upload reference with the delete's mark, keeps the blob's mark and skips the upload unless another holder is live | Confirmed | `repositories.py:688-731`: `_TASK_LOCK`, then `delete_mark`, then the marked insert or lock, then `index_keys(..., removed_by=deleted)`, and it returns without `inner.put` when `deleted is not None and not live`. |
| D10 | Line 9: an orphan is a bucket object with no live reference and no removal mark | Confirmed | `refs.py:268-294` `orphaned()`. |
| D11 | Line 9: `end_task` does nothing once `ended_at` is set | Confirmed | `messages.py:304-311`: `WHERE ... ended_at IS NULL`; returns when `rowcount == 0`. |
| D12 | Line 9: phase 02's delete takes each task's lock before any `blob_objects` lock | Future (labelled) | Phase 02's work, not a claim about the current system. The ordering the current `put` uses is confirmed (lock order comment `repositories.py:690-693`). |

### docs/architecture/overview.md

No statement about phase 01's blob references, the payload guard or `ended_at` is present. That absence is expected and is not a finding. The only retention-class statements are N2 (line 204) and N3 (line 75) above. The `TEMPORAL_RETENTION` lines (18, 36, 43, 48) agree with T5.

## Claims labelled future (not checked as current)

- R9: backups under `backups/` "from Phase 3A's backup" (phase 03).
- Decision log line 10: removal by phase 02's `gc` and `request delete`, and the rollout order (a procedure, not system behaviour).
- Decision log line 9: phase 02's delete lock order.
- R10 and R11 mitigations in Phase 9.

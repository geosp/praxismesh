# Reviews · Phase 3A persistence and data lifecycle

## 2026-11-19 · design-review · plan · round 1 · changes-requested
Pinned at 417e8f9. Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ (raw: docs/reviews/phase-3a/raw/persistence-design-review-round-1-*.md). Structure check: 1 warning (303 body lines, budget 250).

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Blocker | codebase fit, zoom out | Uploading bytes again during or after their removal is unhandled: `put` never clears `removed_at` and S3 skips an existing object, so live blobs read as expired or are deleted | fixed: R22, D10, notes#revive, phase 02 task 1.3 |
| F2 | Blocker | codebase fit, zoom out | A row that outlives its freed reference (`tasks.instructions_ref`, `input_refs`) becomes "unindexed", and D4 then blocks GC for good | fixed: D2 (removed references stay marked), Terms (live, unindexed, dangling), notes#d2 |
| F3 | Blocker | fresh reader | "Request" is never defined; what identifies a request's tasks and where `blob_refs.request_id` comes from is missing | fixed: Terms (Request) |
| F4 | Major | codebase fit | `tasks.result` is written by `MessageRepository.end_task`, not `TaskRepository.complete` (unused); expiry must share `end_task`'s transaction | fixed: notes#refs, R20, phase 01 task 2.3 (`end_task` indexes and sets expiry in its transaction) |
| F5 | Major | codebase fit, zoom out | D5's "referenced within one turn" is false for submitted inputs and artifacts; notes#refs wrongly says `checkpoints.finish` holds outputs | fixed: D2 and D5 (uploads held by their task), notes#refs corrected, phase 01 task 2.2 |
| F6 | Major | codebase fit, zoom out, fresh reader | `tasks` has no end-time column; row expiry for tables keyed by session or workflow, `ephemeral`'s anchor and the backfill of ended tasks are undefined | fixed: `tasks.ended_at` (D1, R20), notes#d3 expiry anchors, backfill in notes#d2 |
| F7 | Major | codebase fit, zoom out | Column defaults keep writing `task`; whether checks still allow `task` during rollout is unsaid; checkpoint inserts hardcode `'task'` | fixed: D3, notes#d3 (new defaults; checks keep `task`), phase 01 tasks 1.1, 2.4 |
| F8 | Major | codebase fit, zoom out | S3 object metadata and `RETENTION_ORDER` also encode classes; where `task` ranks and which record of class is remapped is unsaid | fixed: D3, notes#d3 (index authoritative, metadata unchanged, `task` ranks as `transcript`), phase 01 task 1.3 |
| F9 | Major | codebase fit, zoom out | A schema cap on `questions` breaks replay and fails turns; truncate in `finish_task_body` instead | fixed: D9 (truncate in `finish_task_body`), phase 01 task 3.2 |
| F10 | Major | codebase fit | The unindexed and dangling checks are needed in phases 01-02 but built in phase 03 | fixed: phase 01 task 1.4; R2 uses the check |
| F11 | Major | codebase fit | Deleting events directly bypasses `TableTransport.prune` and `retained_base`, so `tail` shows silent gaps; ADR-0009's partitioning consequence is unaddressed | fixed: D11, notes#redact, phase 02 task 1.4 |
| F12 | Major | codebase fit, zoom out | The append-only trigger does not bind the app role, which owns the table; "audit until purged" has no purge path | fixed: R14 reworded, Risks (owner role accepted until Phase 9), D3 and Non-goals (audit kept, no purge) |
| F13 | Major | zoom out, fresh reader | A tombstone written last is lost on a crash and its counts are undefined across batches | fixed: R13, D6, notes#d6 (tombstone per batch in transaction 1) |
| F14 | Major | zoom out | Restore into a clean Compose stack fails on existing schemas and cannot be retried after a partial load; GC during a backup is not excluded | fixed: D8, notes#d8 (recreate databases, `make reset` after a partial load), D4 lock shared with backup, R23, phase 03 task 2.2 |
| F15 | Major | zoom out, codebase fit | Delete holes: terminated tasks block it forever, joins race it (no request lock), and Temporal histories keep content for 72 h and in backups | fixed: D12, R21, notes#redact (request lock, `record_task` lock for joins, `--force`, Temporal residual), phase 01 task 4.1 |
| F16 | Major | fresh reader | Summary cites wrong R numbers, says "deletes everything" though rows are redacted, says two databases not three, and omits the class migration and GC's refusal | fixed: Summary rewritten |
| F17 | Major | fresh reader | Undefined: §4.13, `blob_objects`, "the four tables", `questions`; R9's dependence on `removed_at`; GC tombstone granularity | fixed: Terms (§4.13, `blob_objects`, `questions`), Why (names the tables), R9, R13 |
| F18 | Major | fresh reader | R18 is stated as absolute but enforced only by a test over the integration suite | fixed: R18 scoped to the integration suite; D9 states the bound by design |
| F19 | Major | fresh reader, zoom out | No repair path for references written by old workers during rollout; GC stays blocked | fixed: Rollout (stop workers first), D4 and phase 01 task 1.4 (`reconcile --reindex`) |
| F20 | Major | fresh reader | plan.md does not map requirements to phases | fixed: Phases table Delivers column |
| F21 | Nit | codebase fit, zoom out | `agentctl task output` reads through a bare `S3BlobStore`; R9 needs the recording store | fixed: notes#d6, phase 02 task 1.1 |
| F22 | Nit | codebase fit, zoom out | `RecordingBlobStore.delete` deletes the `blob_objects` row that `removed_at` lives on | fixed: notes#revive, phase 02 task 1.2 (inner store only) |
| F23 | Nit | codebase fit | The existing replay fixture already carries `retention_class: task`; reuse it for R5 | fixed: phase 01 task 3.1 reuses the fixture |
| F24 | Nit | codebase fit, fresh reader | D8's title says "two dumps"; there are three | fixed: D8 title |
| F25 | Nit | codebase fit | `result.failure_reason` can hold content and is not redacted | fixed: notes#redact |
| F26 | Nit | zoom out | Two concurrent GC or delete runs are not serialised | fixed: D4 advisory lock, phase 02 task 1.5 |
| F27 | Nit | zoom out | notes#redact cites "task 2.4"; the check is phase 02 task 3.1 | fixed: notes#redact cites phase 02 task 3.1 |
| F28 | Nit | fresh reader | Readability: the Summary's risk sentence, D6's first sentence, D5's chain, "plans" for tables and documents, repeated facts, multi-rule R4, R8, R10, R11, R13, R15-R17, "owner" used twice, "batches of" what | fixed: Summary, D5, D6, D1, Terms (Holder); R4, R8, R11, R13, R15, R16 split or reworded (R19, R23) |

After the fixes (2026-11-19): `plan-tool check` reports 0 errors and 1 warning (379 body lines, budget 250). The growth is the new requirements (R19-R23, one rule each), decisions (D10-D12) and Terms the findings asked for; kept rather than moved to notes.md.

## 2026-11-19 · design-review · plan · round 2 · changes-requested
Pinned at c6efe44. Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ (raw: docs/reviews/phase-3a/raw/persistence-design-review-round-2-*.md). Structure check: 1 warning (379 body lines, budget 250). Reopened: F8, F11, F15 (their fixes did not hold; see F50, F30, F29).

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F29 | Major | codebase fit, zoom out | Reopens F15: `_REQUEST_LOCK` is transaction-scoped, so batched deletes release it; a joining submit's upload references carry the request ID before `record_task` and get removed | fixed: D12, R24, notes#redact (session-level request lock, fixed task list, select by list), phase 02 task 3.2 |
| F30 | Major | codebase fit, zoom out | Reopens F11: `TableTransport.prune` opens its own transaction, has no batch limit and marks no references, so it cannot share D6's batch transaction | fixed: D11, notes#d6, phase 02 task 1.4 (`prune` takes the connection, a limit, marks references) |
| F31 | Major | codebase fit | `message_wakes` as `ephemeral` from `created_at` deletes undelivered wakes, contradicting ADR-0010 | fixed: D3, notes#d3 (wake rows expire after the recipient ends) |
| F32 | Major | codebase fit, zoom out | References written after `end_task` (stale attempts, issue #74) never get an expiry | fixed: D2, notes#d2 (expiry computed at GC time), R20 narrowed, R6 scenario |
| F33 | Major | codebase fit, zoom out | "No `tasks` row after 24 h" cannot tell a queued Workflow from one that never started; its inputs are removed | fixed: D5, notes#d2 (Temporal describe before expiring row-less uploads), R7 scenario, phase 02 task 2.1 |
| F34 | Major | zoom out | Backfilling `last_put_at` from `created_at` makes recently re-put blobs look old | fixed: notes#d2, Rollout (`last_put_at` backfilled to the migration time) |
| F35 | Major | codebase fit | A rerun cannot tell which marked blobs are still in the bucket; work grows without bound | fixed: `bucket_deleted_at` (What changes, D6, notes#d6, notes#revive) |
| F36 | Major | codebase fit, zoom out | Bucket objects with no `blob_objects` row are invisible to GC and reconcile, though notes#d8 relies on GC removing them | fixed: Terms (orphaned = bucket object), notes#d2 checks and reindex, notes#d8, R8, phase 01 task 1.4 |
| F37 | Major | codebase fit | Restore's drop-and-recreate loses the database grants of `init.sh` and `roles.sh` (`praxis_comms` CONNECT) | fixed: D8, notes#d8 (`infra/db/databases.sh`, `roles.sh` rerun), R16 scenario, phase 03 task 2.2 |
| F38 | Major | zoom out | Downgrade fails once new code wrote new classes (old `RetentionClass`, histories, `RETENTION_ORDER`); the CLI version is not in Rollout | fixed: Rollout (backup first; downgrade only before new writes, otherwise restore) |
| F39 | Major | fresh reader | Summary omits the Temporal history residual, the `questions` truncation and 64 KiB test, and the stop-workers rollout | fixed: Summary |
| F40 | Major | fresh reader | `end_task` and the session, message and tool-result tables are never introduced | fixed: Terms (`end_task`, content tables, request lock) |
| F41 | Major | fresh reader | Lifetime anchors, the redaction list and which rows a delete removes or redacts live only in notes.md | fixed: D3 (anchors), D12 (removed vs redacted), R11 points to D12 |
| F42 | Major | fresh reader | D5 vs D2: an upload reference of a task with no row is live yet has no stated expiry | fixed: D5, notes#d2 |
| F43 | Major | fresh reader | Terms describes `blob_objects` upload times and removal mark as existing; Impact lists them as new | fixed: What changes (new columns), Terms (`blob_objects` existing columns) |
| F44 | Major | fresh reader | Impact's "no Workflow code changes" vs R5's decoding of `task`; where the type widens is unsaid | fixed: What changes, Impact (`RetentionClass` widens; Workflow code unchanged) |
| F45 | Nit | codebase fit | `event_batches` has `seen_at`, not `created_at`, and publish already deletes its rows after 600 s | fixed: notes#d3 (`event_batches` left to publish) |
| F46 | Nit | codebase fit | A string marker in `result.questions` (a list) or a `None` `failure_reason` breaks `TaskResult` validation | fixed: notes#redact (markers keep `TaskResult` valid), phase 02 task 3.2 |
| F47 | Nit | codebase fit | The demo's "expired read" after a delete never reaches `BlobExpired` (artifacts emptied); only GC does | fixed: phase 03 task 3.2 (expired read after GC) |
| F48 | Nit | codebase fit | ADR-0007 asks new attempt write paths to take the fence or justify; the unfenced upload reference is not justified | fixed: D10, notes#d2 (fence) |
| F49 | Nit | codebase fit, zoom out | `put`'s new task argument and forced upload change the `BlobStore` protocol and `MemoryBlobStore`; not in What changes | fixed: What changes, notes#revive, phase 01 task 2.2 |
| F50 | Nit | codebase fit, zoom out | Reopens F8: "S3 object metadata is left as written" is false; `put` still rewrites it via `copy_object` | fixed: D3, notes#d3 (S3 metadata) |
| F51 | Nit | codebase fit | `put` locks `blob_objects` then `blob_refs`; a removal does the reverse; no fixed lock order | fixed: notes#revive, notes#d6 (`blob_objects` first) |
| F52 | Nit | codebase fit | The existing `agentctl events prune` removes indexed holders without marks or tombstones | fixed: D4, D11, notes#d6, phase 02 tasks 1.2, 1.4 |
| F53 | Nit | codebase fit, zoom out | D4's lock must be session-level and its key named; `backup.sh` cannot hold it from a shell | fixed: D4, D8 (`pg_advisory_lock(3, 0)`, `agentctl backup`), phase 02 task 1.5, phase 03 task 2.1 |
| F54 | Nit | codebase fit | A second Compose project in the CI `stack` job exceeds its 45-minute budget (about 32 used) | fixed: notes#d8, phase 03 task 2.3 (same project after `make reset`) |
| F55 | Nit | zoom out | notes#d3 says `blob_objects` and `blob_refs` expire "with its references"; marked rows must stay | fixed: notes#d3 |
| F56 | Nit | zoom out | One task uploading the same bytes under two classes keeps the first class; the stronger should win | fixed: notes#d2 |
| F57 | Nit | zoom out | R23's refusal checks only `tasks` and the bucket, not the `temporal` database | fixed: R23, notes#d8 |
| F58 | Nit | fresh reader | Readability and terms: Summary cites R21 for the wrong clause; multi-rule R1, R6, R7, R13, R17, R20, R22; minor undefined names (`RecordingBlobStore`, `finish_task_body`, `make reset`, `schemas.md` path); plan vs roadmap phase numbering; owner date repeated | fixed: Summary, Terms, R6, R7, R13, R17, R20, R22 reworded, owner date stated once |

After the fixes (2026-11-20): `plan-tool check` reports 0 errors and 1 warning (410 body lines, budget 250), kept for the same reason as round 1. Reopened F8, F11 and F15 are resolved by F50, F30 and F29.

## 2026-11-20 · waiver · design-review round cap
The project owner approved a third design-review round (the skill stops after two), with the codebase-fit and zoom-out lenses only, because the round-2 fixes F29, F32 and F33 change the removal design. The fresh-reader lens is not rerun.

## 2026-11-20 · design-review · plan · round 3 · changes-requested
Pinned at f3453cd (round cap waived above). Reviewers: codebase fit ✅ · zoom out ✅ (raw: docs/reviews/phase-3a/raw/persistence-design-review-round-3-*.md). Fresh reader not run, by the waiver. Structure check: 1 warning (410 body lines, budget 250).

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F59 | Major | codebase fit, zoom out | The last attempt of an ended task still passes the fence, so after a delete it can write checkpoints, events and sessions, and its upload-reference upsert clears the delete's mark | fixed: R25, D12, notes#redact (fencing attempt row), notes#d2 (a delete mark stays), phase 02 task 3.2 |
| F60 | Major | codebase fit | The drill as an integration test runs `make reset` inside `make smoke`, wiping a developer's stack and later tests' Workflows; the `make up` precondition is unsaid | fixed: notes#d8, phase 03 task 2.3 (`make drill`, opt-in, own CI step, `make up` first) |
| F61 | Major | codebase fit | `event_batches` rows of each task's last 600 s are never removed: `publish` prunes only its own log on its next publish | fixed: notes#d3 (`event_batches` expire from the task end), phase 02 task 2.1 |
| F62 | Major | zoom out | Blobs named only in Temporal state at migration time (queued inputs, carried artifacts) get no index row and become orphans 24 h later | fixed: Rollout (drain open Workflows before migrating) |
| F63 | Major | zoom out | A backup taken with workers running can restore Workflows ahead of their rows; nothing detects it | fixed: D8, notes#d8, phase 03 task 2.1 (backup stops the workers during the dumps) |
| F64 | Major | zoom out | The backfilled index rows' class is unsaid; copied from JSON, old artifacts (`audit`) never expire and `task` enters `blob_refs` | fixed: notes#d2 backfill, R19 scenario, phase 01 task 1.1 |
| F65 | Nit | codebase fit, zoom out | notes#d6 step 1 marks references before locking `blob_objects`, inverting `put`'s order | fixed: notes#d6 step 1, phase 02 task 1.2 |
| F66 | Nit | codebase fit | notes#redact omits `sample_orders`, `task_inbox` and `message_wakes` | fixed: notes#redact |
| F67 | Nit | codebase fit | `prune`'s new arguments must be optional or the `EventTransport` protocol and `MemoryTransport` change | fixed: notes#d6, phase 02 task 1.4 |
| F68 | Nit | codebase fit, zoom out | `events prune` gets neither `--dry-run` nor the D4 lock | fixed: D4, notes#d6, phase 02 tasks 1.4, 1.5 |
| F69 | Nit | codebase fit | Phase 02 task 1.5 locks `agentctl backup`, which phase 03 creates | fixed: phase 02 task 1.5, phase 03 task 2.1 |
| F70 | Nit | codebase fit | Reconcile's exit status 1 would fail `make restore` in the drill, which expects one dangling reference | fixed: D8, notes#d8, phase 03 task 2.2 |
| F71 | Nit | codebase fit | `blob_refs.request_id` for upload references is unsaid (nullable?) | fixed: notes#d2 |
| F72 | Nit | codebase fit | Unused `TaskRepository.complete` writes `result` without indexing it | fixed: phase 01 task 2.1 |
| F73 | Nit | codebase fit | How the migration test gets a database at 0006 is unsaid (app role has no CREATEDB) | fixed: phase 01 task 1.1 |
| F74 | Nit | codebase fit, zoom out | R23's Temporal check: by API or SQL (ADR-0002), and scoped to the app namespace (system Workflows) | fixed: notes#d8, phase 03 task 2.2 (Temporal API, app namespace) |
| F75 | Nit | codebase fit | notes#d8 says comparing Workflows with rows is Phase 9, but R17 compares unended tasks with closed Workflows | fixed: notes#d8 |
| F76 | Nit | codebase fit | notes#refs states the task-ID reorder as if it were current code | fixed: notes#refs |
| F77 | Nit | codebase fit | `infra/db/databases.sh` needs a Compose mount; phase 02 task 1.4's verify is a claim, not a test | fixed: notes#d8, Impact, phase 03 task 2.2; phase 02 task 1.4 verify is a kill test |
| F78 | Nit | zoom out | `put`'s `force` flag adds nothing under the row-lock protocol | fixed: D10, notes#revive, phase 01 task 2.2 (no `force`) |
| F79 | Nit | zoom out | The bucket step's `last_put_at < removed_at` test uses transaction-start times and can skip a blob forever | fixed: notes#revive (mark check under the lock only) |

After the fixes (2026-11-20): `plan-tool check` reports 0 errors and 1 warning (420 body lines, budget 250). Every finding of rounds 1-3 is resolved. The project owner accepted the round-3 fixes without a fourth round ("Apply and approved", 2026-11-20); the concurrency paths are checked again by each phase's implementation review.

## 2026-11-20 · approved · plan
Approved by the project owner ("Apply and approved") after design-review round 3; the plan and phases 01-03 are approved.

## 2026-11-20 · impl-review · phase 01 · round 1 · changes-requested
Diff base 8cc4355..a50c358 (frozen review commit a50c358). Reviewers: contract ✅ · failure and retry ✅ · scope and composition ✅ (raw: docs/reviews/phase-3a/raw/persistence-impl-review-phase-01-round-1-*.md). Structure check: 0 errors, 1 warning (420 body lines, budget 250); all 13 tasks ticked.

| ID | Sev | Lens | Req | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| F80 | Major | failure, scope | D10, R25, R10 | `put` clears a blob's removal mark unconditionally, so a deleted task's late upload of the same bytes re-uploads them with no live reference; no check (orphaned, expired, rowless) ever reaches them and old refs read deleted content (plan gap, notes#revive step 2) | fixed: tests/integration/test_upload_refs.py::test_a_deleted_tasks_late_upload_of_the_same_bytes_revives_nothing, test_refs.py::test_orphans_with_their_age; repositories.py `put`, refs.py `orphaned`; D10, notes#revive, notes#d2 |
| F81 | Major | scope | D2, R25 | The delete mark is kept per (task, blob) row: a deleted task's stale attempt uploading new bytes inserts a fresh live upload reference | fixed: test_upload_refs.py::test_a_deleted_tasks_late_upload_of_new_bytes_leaves_no_live_reference; `put` takes `TASK_LOCK` and writes the delete's mark (refs.py `delete_mark`, `index_keys(removed_by=)`); notes#redact task locks, phase 02 task 3.2 |
| F82 | Major | failure | R11, R25 | A retried `end_task` (worker died before Temporal recorded completion) rewrites `tasks.result` after a delete redacted it | fixed: test_index_writers.py::test_a_retried_end_task_keeps_a_redaction; messages.py `end_task` no-op once ended; notes#redact |
| F83 | Nit | all | R4, D3 | New `BlobRef`s carry the class from old S3 metadata (`audit`); S3 repeat-put over `task` metadata untested; two tests loosened to accept it | deferred: S3 metadata never decides a lifetime (D3); revisit with phase 02 `BlobExpired` reads |
| F84 | Nit | all | R18 | History guard only warns when Temporal is unreachable, skips runs a test deleted, waits a fixed 2 s; its failing path is not exercised | fixed: tests/test_history_guard.py (three `guard_failure` tests); guard fails when Temporal is unreachable |
| F85 | Nit | all | D9 | A turn resumed from a pre-change checkpoint passes untruncated questions into the result (rollout drains first) | fixed: test_harness_activity.py::test_finish_shortcut_bounds_old_questions; activity.py outcome uses `bounded_questions` |
| F86 | Nit | failure, scope | D10, R9 | DB commits before `inner.put`; a failed upload leaves a live ref with no object (`BlobNotFound`, not `BlobExpired`) until a retry | accepted: the order notes#revive prescribes; a retry heals it |
| F87 | Nit | contract | R1, R20 | No test makes the index write fail inside `record_task`/`end_task`/`publish` to show the holder row rolls back | fixed: test_index_writers.py::test_a_failed_index_write_rolls_back_its_holder_row (test only; code already correct) |
| F88 | Nit | contract | R1 | The DSH session upload's `task_id` is unobserved by any test | fixed: test_dsh_runner_parts.py::test_session_capture_is_held_by_its_task |
| F89 | Nit | contract, scope | R1 | The submit-upload test uses one input file; R1's scenario names two | fixed: test_upload_refs.py submit test uses two input files plus one duplicate |
| F90 | Nit | contract | D10 | `blob_objects`-first lock order is unobservable by single-session tests | accepted: exercised by phase 02 concurrent-removal tests |
| F91 | Nit | contract, scope | R4 | Server defaults of `idempotency_keys`, `event_batches`, `task_messages`, `task_inbox`, `agent_events` not read back after 0007 | accepted: defaults come from the `TABLES` dict a test checks |
| F92 | Nit | contract, failure | Rollout | Downgrade is lossy: rows remapped to `ephemeral` stay `ephemeral` | accepted: downgrade limits are documented in the plan Rollout |
| F93 | Nit | contract | D4 | Reindex skips bucket objects whose key is not a content key | accepted: documented narrowing; non-content keys are reported as orphans |
| F94 | Nit | contract | docs | Threat model says `backups/` is git-ignored; `.gitignore` has no entry yet | fixed: `.gitignore` `/backups/` |
| F95 | Nit | failure | tests | Scratch databases are left behind if the test process is killed | accepted: UUID names avoid collisions; `make reset` clears them |
| F96 | Nit | scope | R1 | Uploads for a colliding user task ID are held by the existing task before `TaskAlreadyExists` | accepted: harmless mis-attribution; the uploads expire with that task |
| F97 | Nit | scope | D3 | `index_keys` never refreshes `created_at`, so a re-put `ephemeral` blob ages from its first write | accepted: nothing writes `ephemeral` yet; revisit when something does |
| F98 | Nit | scope | R1 | A retried `end_task` with a different artifact list leaves the earlier refs live | fixed: by F82 (a retried `end_task` changes nothing) |
| F99 | Nit | scope | D11 | `events prune` deletes `agent_events` rows and leaves their `blob_refs` live until phase 02 | deferred: phase 02 task 1.4 rewires `events prune` (D11) |
| F100 | Nit | scope | D2, D3 | A stale attempt's unnamed artifact upload is kept 90 days after the task ends | deferred: note on issue #74 (unnamed stale-attempt uploads) |
| F101 | Nit | scope | D5 | `rowless_uploads` ages by per-blob `last_put_at`, so another task's re-put restarts the window | accepted: conservative (keeps blobs longer, never shorter) |

After the fixes (2026-11-20): every Major fixed test first, each test confirmed failing with its fix reverted; `plan-tool check` 0 errors, 1 warning. Round 2 (fresh failure and scope lenses) pending.

## 2026-11-20 · impl-review · phase 01 · round 2 · passed
Diff base 8cc4355..dccc8ff (frozen review commit dccc8ff). Reviewers (the lenses that raised round 1's Majors): failure and retry ✅ · scope and composition ✅ (raw: docs/reviews/phase-3a/raw/persistence-impl-review-phase-01-round-2-*.md). Contract not rerun (raised no Major). F80-F82 did not come back. Repeats of closed findings (F83, F84's deleted-run and settle parts, F86, F95, F99, F101) stay closed.

| ID | Sev | Lens | Req | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| F102 | Nit | failure | R2, R20 | A worker started too early runs the old `end_task`, leaving an ended task with `ended_at` null; `reindex` does not repair it, so its blobs never expire | open |
| F103 | Nit | failure | R20 | Since F82, a retried `complete_task` returns usage from a fresh ledger read while `tasks.result` keeps the first call's values | open |
| F104 | Nit | failure | D10 | `put` for a deleted task uploads when the blob row is unmarked, though notes say "live for another holder"; a cleared-mark orphan is re-uploaded (still reached by `orphaned`) | open |
| F105 | Nit | failure | tests | `scratch_database` creates the database before its `try`; a failed setup step leaves it behind | open |
| F106 | Nit | scope | R18 | `make restart-check` and `make workers-check` start Workflows in the CI stack job but are outside the pytest session guard | open |
| F107 | Nit | scope | R18, D9 | The guard measures each `Payload`, not an event's whole `Payloads`; equal today (one argument per Activity) | open |
| F108 | Nit | scope | R18 | The 20-question test is ASCII only and `openai` only; 4-byte UTF-8 still fits under 64 KiB | open |
| F109 | Nit | scope | R8, D5 | `reindex` gives a bucket-only object `last_put_at = now()`, restarting its window (by notes#d2) | open |
| F110 | Nit | scope | R17, drill | Integration tests leave `audit_log`, fake `blob_refs` and row-less upload refs in the stack database; phase 03's drill reconcile, run after `make smoke` in CI, will report them | open |
| F111 | Nit | scope | R2 | The migration test seeds only a `succeeded` ended task, not `failed` or `needs_input` | open |
| F112 | Nit | scope | R14 | The append-only trigger is per row: an `UPDATE`/`DELETE` matching no rows succeeds (no data can change) | open |
| F113 | Nit | scope | R4 | Tests still `put(..., retention="task")`; mapped to `transcript`, never stored | open |

## 2026-11-20 · impl-review · phase 01 · round 3 · passed
Targeted follow-up of the verification fix only. Diff base 619593b..56c0170 (frozen review commit 56c0170: `common/persistence/migrations/env.py`, `tests/integration/test_migration_0007.py`). Reviewers: contract ✅ (raw: docs/reviews/phase-3a/raw/persistence-impl-review-phase-01-round-3-contract.md). Failure and scope not run: the diff adds no retry, resume, limit or scope mechanism.

| ID | Sev | Lens | Req | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| F114 | Nit | contract | tests | `fileConfig` still replaces root handlers with alembic.ini's stderr handler (WARNING) after an in-process migration; a later `capsys` stderr test could see its lines | deferred: phase 02 (`migrate()` skips `fileConfig` in-process) |
| F115 | Nit | contract | tests | The regression test checks `disabled`, not that a `praxis.harness` warning still reaches `caplog` after `migrate` | deferred: phase 02 (assert a `caplog` warning after `migrate`) |
| F116 | Nit | contract | tests | The test sits in the 0007 file and migrates to 0007; `test_database.py` is the general home | deferred: phase 02 (move the test to `test_database.py`) |

## 2026-11-20 · verification · phase 01 · pass
code_sha = docs_sha = 56c0170 (on origin/docs/92-phase-3a-01-verification). Record: docs/reviews/phase-3a/verification-persistence-01.md; raw: docs/reviews/phase-3a/raw/persistence-verification-phase-01-*.md. Fixed during verification: F1 (README, dc83f97), F2 (in-process Alembic disabled loggers, 56c0170), N1-N3 (dc83f97).

## 2026-11-20 · done · phase 01
Tests, acceptance and verification passed at 56c0170 (verification-persistence-01.md); impl review round 3 passed; F114-F116 deferred to phase 02.

## 2026-11-20 · impl-review · phase 02 · round 1 · changes-requested
Diff base 9a81933..8012f6b (frozen review commit 8012f6b). Reviewers: contract ✅ · failure and retry ✅ · scope and composition ✅ (raw: docs/reviews/phase-3a/raw/persistence-impl-review-phase-02-round-1-*.md; the contract report was re-typed from the agent's hand-back after save-report refused my snippets). Before the round: the full integration suite from a clean worktree with `infra/.env` from the example, workers stopped: 320 passed.

| ID | Sev | Lens | Req | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| F117 | Major | contract | R25, R11 | The openai `SQLAlchemySession` (`agent_messages`) and `sample_mcp.record_order` (`idempotency_keys`, `sample_orders`) never check the fence, so a forced-deleted attempt still writes content rows | fixed: fence.refuse_if_deleted in the session store's add_items (lock held across the insert) and record_order; test_a_deleted_tasks_conversation_and_tool_writes_are_refused |
| F118 | Major | contract, scope | R25, D12 | The fencing row is `(max turn + 1, 1)`; `AttemptRepository.start` at that turn passes the fence and upserts over it | fixed: NO_NEWER_ATTEMPT refuses any write once a `deleted` row exists; test_an_attempt_of_a_later_turn_is_fenced_too |
| F119 | Major | contract, failure, scope | R8, R15 | An orphan with a non-content key gets a row whose checksum fails `BlobRef` validation in the bucket step, so every later removal fails in `finish_pending` | fixed: refs.is_content_key in gc's orphan step and the engine, keys reported as unrecognised; test_an_object_that_is_not_a_content_key_is_reported_not_removed, test_the_engine_never_records_a_key_that_is_not_a_content_key |
| F120 | Major | contract | R6 | gc's rules for sessions, messages, inbox, idempotency keys, sample orders and the 30-day event prune have no gc test | fixed: test_every_row_rule_and_the_event_prune_expire_with_their_task |
| F121 | Major | contract | D3 | `ROW_RULES`, `DELETE_ROWS` and `EVENT_RETENTION` restate `TABLE_CLASS`; a changed or new class drifts silently | fixed: RowRule.retention reads TABLE_CLASS, DELETE_ROWS picks gc's rules; tests/test_lifecycle_rules.py |
| F122 | Major | failure, scope | R24, R15 | A rerun of a killed delete rebuilds the task list from `request_id`, so a task that joined in between is deleted, or blocks the rerun if running | fixed: a rerun resumes the unfinished delete's task list; completion tombstone; test_a_rerun_finishes_the_killed_deletes_own_task_list |
| F123 | Major | failure, scope, contract | R11 | Redaction skips any value that starts with `[deleted `, so model output can keep content (and the result's artifacts) unredacted | fixed: exact marker pattern in Python and SQL; test_content_that_only_looks_redacted_is_redacted |
| F124 | Major | scope, failure | R6, R10, D10 | `put` uploads after its commit, outside the row lock; a removal that marks and bucket-deletes in between leaves an object no later run removes | fixed: put uploads inside its transaction, under the row lock; test_an_upload_in_flight_during_a_delete_leaves_no_object_behind |
| F125 | Nit | contract, failure, scope | R25, D10 | `delete_mark` recognises a deleted task only by a `delete:` reference mark; a task whose first batch marked no upload can revive a blob | fixed: delete_mark also reads the `deleted` attempt row; test_a_deleted_task_with_no_upload_left_still_revives_nothing |
| F126 | Nit | failure, scope | R3 | `_mark_free_blobs` checks freedom and marks in separate statements; a key with no `blob_objects` row is not locked, so a racing `put` can be marked | fixed: placeholder rows before the lock, free check and mark in one UPDATE (no deterministic test: a statement-level race) |
| F127 | Nit | contract, failure, scope | D4 | A dry run holds its row, blob and task locks until the end of the run | accepted: documented in the runbook (Removing data) |
| F128 | Nit | contract, failure | D4 | A dry run skips `finish_pending`, so its plan omits earlier runs' bucket deletes | accepted: documented in the runbook; a real run reports finished_from_earlier_runs |
| F129 | Nit | contract, scope | D4 | The delete's first batch has no 500 cap (it must take every task lock at once) | accepted: the first batch must take every task lock at once (review F81) |
| F130 | Nit | contract | R7, R21, D5 | `workflow_status` is tested only through fakes; a wrong namespace reads as `missing` | accepted: phase 03's drill and acceptance run against real Temporal |
| F131 | Nit | contract | R9, R10 | Removal tests use `MemoryBlobStore`; S3 delete, listing pagination and `LastModified` are not observed | accepted: phase 03's drill and acceptance run against SeaweedFS |
| F132 | Nit | contract, scope | R6, R7, R10, R22 | Gaps in assertions: gc keeps the next resubmit, kept tasks' workspaces readable, references marked, workspace blobs unreadable after a delete, upload refs in the kill test, `audit_log` kept, gc to `task output` | fixed: the listed assertions in test_gc, test_request_delete, test_removal_kills, test_revive, test_blob_expired |
| F133 | Nit | contract | tests | `test_blob_expired.py` marks blobs on the stack database and leaves them for the next stack `gc` | fixed: test_blob_expired uses a scratch database |
| F134 | Nit | contract | reuse | Duplicates: the checkpoint holder key SQL, the event-refs query, two session-lock helpers and the lock SQL, `RefKey` vs `refs.Holder`, the placeholder `blob_objects` insert, two `drain` closures, test helpers (`tombstones`, `one`/`count`, event builders, fake Temporal) | fixed: shared test helpers in tests/support/lifecycle.py; one session-lock helper, lock SQL from its key, one _drain, checkpoint holder SQL from refs. RefKey kept (it adds the blob key to a holder) |
| F135 | Nit | scope | R13 | gc's steps 3-5 count batches that committed nothing; `finish_pending` deletes are not reported | fixed: Totals counts only committed batches, reports finished_from_earlier_runs; test_an_orphan_uploaded_after_the_listing_is_kept_and_not_counted |
| F136 | Nit | failure | D6 | Placeholder rows keep 0 bytes and `application/octet-stream` after a revive | accepted: placeholder size and type are never read; the key and checksum are |
| F137 | Nit | failure | R9 | `check_live` then `inner.get` can give `BlobNotFound` if a bucket step lands between them | accepted: a tiny race that ends in BlobNotFound, a clear error |
| F138 | Nit | failure | D4 | An unlock in `finally` on a broken connection hides the original error | fixed: session_lock suppresses an unlock error on a broken connection |
| F139 | Nit | failure | R12, R21 | A forced end skips `end_task`'s message closing; open questions of a forced task stay open | accepted: every task in the request has ended by then; messaging refuses an ended recipient |
| F140 | Nit | failure | R13 | A dry run rolls back a zero-count first batch even with `record_empty` | fixed: a dry run keeps a record_empty batch (no dedicated test) |
| F141 | Nit | failure, scope | task 1.5, 3.3 | Concurrency is tested only for prune; kill tests have no forced delete or join between runs | fixed: test_a_second_gc_or_a_delete_fails_at_once_while_gc_runs |
| F142 | Nit | contract | docs | The Phases table shows phase 02 as approved 0/10; the runbook says "no other request holds" (the rule is "no other live holder") and "checkpoint, event or message" | fixed: Phases table, runbook (holders, writes refused, forced reasons, dry-run limits, unrecognised keys), overview draft |
| F143 | Nit | engineer | R21 | (Engineer decision, 2026-11-20) Show why a forced task counted as ended (`closed` or `missing`) in the output, the dry run and the first tombstone | fixed: Totals.forced, the report and the first tombstone; test_force_says_why_each_task_counted_as_ended |

After the fixes (2026-11-20): every Major fixed test first; each new test failed before its fix and again with the fix reverted, except F126 and F140 (noted). Round 2 (fresh contract, failure and scope lenses) offered.

## 2026-11-21 · impl-review · phase 02 · round 2 · changes-requested
Diff base 9a81933..dd999f3 (frozen review commit dd999f3). Reviewers: contract ✅ · failure and retry ✅ (resumed after a usage limit) · scope and composition ✅ (raw: docs/reviews/phase-3a/raw/persistence-impl-review-phase-02-round-2-*.md). Full integration suite at dd999f3 from a clean worktree, workers stopped: 332 passed, 1 failed (F149). Closed findings raised again stay closed: F130 (contract M2, Temporal mapping untested), F127 (dry-run locks), F128, F136, F137, F139. F129 comes back with new evidence (F146). No fixed finding came back.

| ID | Sev | Lens | Req | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| F144 | Major | contract | R10, D4 | `request delete` never checks for unindexed references, so an unindexed input or checkpoint blob of a deleted request stays readable | fixed: request delete refuses while a reference of its tasks is unindexed; test_a_delete_refuses_while_a_reference_of_its_tasks_is_unindexed |
| F145 | Major | failure, scope | R6, R15, D6 | A re-upload whose `put` transaction never commits (killed CLI, dropped connection) puts bytes back under a row still marked with `bucket_deleted_at` set; neither `pending` nor `orphaned` ever sees it | fixed: refs.returned and gc's bucket step for bytes back under a removed row; test_bytes_back_under_a_removed_row_are_removed_again |
| F146 | Major | scope, contract, failure | D4, R13 | The delete's first batch marks every upload reference of the request in one transaction with no 500 cap; since F125 the fencing row is already the delete mark, so the uploads can move to the capped later batches (F129 reopened on new evidence) | fixed: the first batch only fences; uploads are marked in capped later batches; test_a_large_request_is_deleted_in_batches_of_at_most_500 |
| F147 | Nit | contract | R11 | The `failure_reason` redaction has no test | fixed: test_a_failed_tasks_failure_reason_is_redacted |
| F148 | Nit | contract | reuse | `refs.reindex` still matches `_CONTENT_KEY` directly; `DELETED` repeats the clause inside `NO_NEWER_ATTEMPT`; the `Collect` comment says "before any lock" though task locks come first | fixed: one `deleted` clause in fence.py, reindex uses is_content_key, the Collect comment corrected |
| F149 | Nit | coordinator | tests | `test_a_final_flush_that_times_out_raises_events_unavailable` (0.3 s flush budget) failed once in the full run at dd999f3 and passed 5/5 alone and in both earlier full runs; its code is not in this diff | accepted: passes alone (5/5) and in earlier full runs, its code is outside this diff; the full run at the fix commit confirms |
| F150 | Nit | contract | docs | The overview says `test_blob_expired.py` runs on the stack database (now a scratch one); the runbook says a busy delete "changed nothing", but each try first finishes earlier runs' bucket deletes | fixed: overview test list and runbook (busy delete, unindexed refusal) |
| F151 | Nit | contract, failure, scope | R24, D12 | During a TaskBusy retry the request lock is released and the list re-read by `request_id`; a running joiner makes the delete refuse (no task is changed) | accepted: a running joiner makes the delete refuse; no task is changed |
| F152 | Nit | contract | R24 | A resumed delete's message redaction (`sender_task` or `recipient_task` in the list) rewrites a later joiner's messages to or from the deleted tasks | accepted: only a joiner's messages to or from the deleted tasks, which are part of the deleted work |
| F153 | Nit | contract | R25 | After a delete, an attempt can still settle its `usage_ledger` row and finish its `task_attempts` row (audit rows, no content) | accepted: audit rows with no content (R25 is about content and references) |
| F154 | Nit | failure, scope | D12 | `put` holds the task lock for its whole upload, so a forced delete during an upload longer than the ~10 s retry budget ends busy; the pooled connection held by `add_items` adds pool pressure | accepted: the cost of F124's upload under the row lock; the operator reruns, the message says so |
| F155 | Nit | failure, scope | D4 | A checkpoint batch caps rows at 500 but can mark up to 1,000 references; whether D4's rows include marks is unstated | accepted: a checkpoint batch is bounded at 500 rows and 1,000 marks |
| F156 | Nit | failure | D4 | A cancelled unlock on a healthy connection returns it to the pool still holding the session lock (only matters to a long-lived caller; the CLI disposes its engine) | accepted: only a long-lived caller would keep the lock; the CLI disposes its engine |
| F157 | Nit | scope | R13 | A deleted task's late upload writes marks (the delete's operation or `delete:<task>`) that no tombstone counts | accepted: a late upload's marks are not removals |
| F158 | Nit | scope | task 1.4 | "A GC killed after a prune batch" is tested through a hand-built event batch, not a killed `gc` run | accepted: the engine-level test exercises the same transaction a killed gc batch runs |
| F159 | Nit | scope | D12 | `pg_advisory_lock` for the request lock has no timeout; a stuck holder makes `request delete` hang | accepted: transaction-level holders of the request lock are short |
| F160 | Nit | contract | reuse | More duplicates: `_ref` vs `make_ref`, `_ensure_rows` vs `reindex`'s insert, `event_batch.collect` vs `_prune`'s range, the empty-batch test, `workflow_status` placement, near-identical task builders, `set_last_put`, `pausing_run` | accepted: harmless at this size; workflow_status placement and Bucket move with phase 03's reconcile |
| F161 | Nit | contract | R8, D5 | The window compares the database's `last_put_at` with the CLI host's clock | accepted: one machine, one clock |
| F162 | Nit | contract | R10 | A reference to a non-content key is never marked (follows from F119) | accepted: follows from F119 (non-content keys are never recorded) |
| F163 | Nit | contract | task 3.1 | `session_ids` finds sessions only through checkpoints | accepted: both runners write their sessions under the task ID, as checked |
| F164 | Nit | contract, failure | R13, R15 | Kill tests raise in-process; a real process death (the session lock's release) is not observed | accepted: phase 03's drill stops a real process |

After the fixes (2026-11-21): every Major fixed test first; each new test failed before its fix and again with the fix reverted. This was the last round (the second): nothing is left open.

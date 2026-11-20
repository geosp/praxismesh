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
| F80 | Major | failure, scope | D10, R25, R10 | `put` clears a blob's removal mark unconditionally, so a deleted task's late upload of the same bytes re-uploads them with no live reference; no check (orphaned, expired, rowless) ever reaches them and old refs read deleted content (plan gap, notes#revive step 2) | open |
| F81 | Major | scope | D2, R25 | The delete mark is kept per (task, blob) row: a deleted task's stale attempt uploading new bytes inserts a fresh live upload reference | open |
| F82 | Major | failure | R11, R25 | A retried `end_task` (worker died before Temporal recorded completion) rewrites `tasks.result` after a delete redacted it | open |
| F83 | Nit | all | R4, D3 | New `BlobRef`s carry the class from old S3 metadata (`audit`); S3 repeat-put over `task` metadata untested; two tests loosened to accept it | open |
| F84 | Nit | all | R18 | History guard only warns when Temporal is unreachable, skips runs a test deleted, waits a fixed 2 s; its failing path is not exercised | open |
| F85 | Nit | all | D9 | A turn resumed from a pre-change checkpoint passes untruncated questions into the result (rollout drains first) | open |
| F86 | Nit | failure, scope | D10, R9 | DB commits before `inner.put`; a failed upload leaves a live ref with no object (`BlobNotFound`, not `BlobExpired`) until a retry | open |
| F87 | Nit | contract | R1, R20 | No test makes the index write fail inside `record_task`/`end_task`/`publish` to show the holder row rolls back | open |
| F88 | Nit | contract | R1 | The DSH session upload's `task_id` is unobserved by any test | open |
| F89 | Nit | contract, scope | R1 | The submit-upload test uses one input file; R1's scenario names two | open |
| F90 | Nit | contract | D10 | `blob_objects`-first lock order is unobservable by single-session tests | open |
| F91 | Nit | contract, scope | R4 | Server defaults of `idempotency_keys`, `event_batches`, `task_messages`, `task_inbox`, `agent_events` not read back after 0007 | open |
| F92 | Nit | contract, failure | Rollout | Downgrade is lossy: rows remapped to `ephemeral` stay `ephemeral` | open |
| F93 | Nit | contract | D4 | Reindex skips bucket objects whose key is not a content key | open |
| F94 | Nit | contract | docs | Threat model says `backups/` is git-ignored; `.gitignore` has no entry yet | open |
| F95 | Nit | failure | tests | Scratch databases are left behind if the test process is killed | open |
| F96 | Nit | scope | R1 | Uploads for a colliding user task ID are held by the existing task before `TaskAlreadyExists` | open |
| F97 | Nit | scope | D3 | `index_keys` never refreshes `created_at`, so a re-put `ephemeral` blob ages from its first write | open |
| F98 | Nit | scope | R1 | A retried `end_task` with a different artifact list leaves the earlier refs live | open |
| F99 | Nit | scope | D11 | `events prune` deletes `agent_events` rows and leaves their `blob_refs` live until phase 02 | open |
| F100 | Nit | scope | D2, D3 | A stale attempt's unnamed artifact upload is kept 90 days after the task ends | open |
| F101 | Nit | scope | D5 | `rowless_uploads` ages by per-blob `last_put_at`, so another task's re-put restarts the window | open |

# Reviews · Phase 3A persistence and data lifecycle

## 2026-11-19 · design-review · plan · round 1 · changes-requested
Pinned at 417e8f9. Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ (raw: docs/reviews/phase-3a/raw/persistence-design-review-round-1-*.md). Structure check: 1 warning (303 body lines, budget 250).

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Blocker | codebase fit, zoom out | Uploading bytes again during or after their removal is unhandled: `put` never clears `removed_at` and S3 skips an existing object, so live blobs read as expired or are deleted | open |
| F2 | Blocker | codebase fit, zoom out | A row that outlives its freed reference (`tasks.instructions_ref`, `input_refs`) becomes "unindexed", and D4 then blocks GC for good | open |
| F3 | Blocker | fresh reader | "Request" is never defined; what identifies a request's tasks and where `blob_refs.request_id` comes from is missing | open |
| F4 | Major | codebase fit | `tasks.result` is written by `MessageRepository.end_task`, not `TaskRepository.complete` (unused); expiry must share `end_task`'s transaction | open |
| F5 | Major | codebase fit, zoom out | D5's "referenced within one turn" is false for submitted inputs and artifacts; notes#refs wrongly says `checkpoints.finish` holds outputs | open |
| F6 | Major | codebase fit, zoom out, fresh reader | `tasks` has no end-time column; row expiry for tables keyed by session or workflow, `ephemeral`'s anchor and the backfill of ended tasks are undefined | open |
| F7 | Major | codebase fit, zoom out | Column defaults keep writing `task`; whether checks still allow `task` during rollout is unsaid; checkpoint inserts hardcode `'task'` | open |
| F8 | Major | codebase fit, zoom out | S3 object metadata and `RETENTION_ORDER` also encode classes; where `task` ranks and which record of class is remapped is unsaid | open |
| F9 | Major | codebase fit, zoom out | A schema cap on `questions` breaks replay and fails turns; truncate in `finish_task_body` instead | open |
| F10 | Major | codebase fit | The unindexed and dangling checks are needed in phases 01-02 but built in phase 03 | open |
| F11 | Major | codebase fit | Deleting events directly bypasses `TableTransport.prune` and `retained_base`, so `tail` shows silent gaps; ADR-0009's partitioning consequence is unaddressed | open |
| F12 | Major | codebase fit, zoom out | The append-only trigger does not bind the app role, which owns the table; "audit until purged" has no purge path | open |
| F13 | Major | zoom out, fresh reader | A tombstone written last is lost on a crash and its counts are undefined across batches | open |
| F14 | Major | zoom out | Restore into a clean Compose stack fails on existing schemas and cannot be retried after a partial load; GC during a backup is not excluded | open |
| F15 | Major | zoom out, codebase fit | Delete holes: terminated tasks block it forever, joins race it (no request lock), and Temporal histories keep content for 72 h and in backups | open |
| F16 | Major | fresh reader | Summary cites wrong R numbers, says "deletes everything" though rows are redacted, says two databases not three, and omits the class migration and GC's refusal | open |
| F17 | Major | fresh reader | Undefined: §4.13, `blob_objects`, "the four tables", `questions`; R9's dependence on `removed_at`; GC tombstone granularity | open |
| F18 | Major | fresh reader | R18 is stated as absolute but enforced only by a test over the integration suite | open |
| F19 | Major | fresh reader, zoom out | No repair path for references written by old workers during rollout; GC stays blocked | open |
| F20 | Major | fresh reader | plan.md does not map requirements to phases | open |
| F21 | Nit | codebase fit, zoom out | `agentctl task output` reads through a bare `S3BlobStore`; R9 needs the recording store | open |
| F22 | Nit | codebase fit, zoom out | `RecordingBlobStore.delete` deletes the `blob_objects` row that `removed_at` lives on | open |
| F23 | Nit | codebase fit | The existing replay fixture already carries `retention_class: task`; reuse it for R5 | open |
| F24 | Nit | codebase fit, fresh reader | D8's title says "two dumps"; there are three | open |
| F25 | Nit | codebase fit | `result.failure_reason` can hold content and is not redacted | open |
| F26 | Nit | zoom out | Two concurrent GC or delete runs are not serialised | open |
| F27 | Nit | zoom out | notes#redact cites "task 2.4"; the check is phase 02 task 3.1 | open |
| F28 | Nit | fresh reader | Readability: the Summary's risk sentence, D6's first sentence, D5's chain, "plans" for tables and documents, repeated facts, multi-rule R4, R8, R10, R11, R13, R15-R17, "owner" used twice, "batches of" what | open |

<!-- Verbatim subagent report (Phase 3A persistence plan design-review round 2, fresh reader, at c6efe44); reviewers: fresh-subagent (design-reader); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged with save-report). -->

Review of /home/geo/develop/praxismesh/docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md

## From the Summary

The change gives stored data a lifecycle. Every row or task upload that points at a blob also records that reference in a new index, inside the same transaction. Existing data is moved to five retention classes. Operator commands then delete expired data and delete a whole request: they remove its blobs and blank out its content while keeping IDs, statuses and usage, and each batch leaves an append-only tombstone. Backup and restore cover three PostgreSQL databases and SeaweedFS, and a reconcile command lists inconsistencies. The main risk is deleting a blob that is still in use, because identical bytes share one stored object. The plan guards against it in four ways: a blob is deleted only when the index shows no live reference, `gc` refuses to run while any reference is unindexed, re-uploading the bytes revives a deleted blob, and every command has a dry run.

## From the whole plan

Phases 1-2 label every blob and row with a retention class but never delete anything. Storage only grows, including blobs orphaned by stale attempts (issue #74). No one can ask whether a blob is still used, and there is no delete-on-request or restore. The plan adds:
- a `blob_refs` index, written alongside its holder and backfilled by migration 0007, plus `tasks.ended_at` so expiry can count from when a task ends;
- the five §4.13 classes with set lifetimes;
- an append-only `audit_log` for tombstones;
- on-demand `agentctl gc`, `request delete` and `reconcile`. Each batch is one transaction that updates rows, references, blob marks and the tombstone. The bucket is deleted afterwards, and removed blobs raise `BlobExpired`;
- `make backup` / `make restore`;
- a cap on `questions` and a test that keeps Temporal history payloads at or under 64 KiB.

The goal is to meet §4.13 and the Phase 3A roadmap tasks 1, 2, 9 and 10.

## How the existing system works, per this plan

A task runs as a Temporal Workflow. Each turn runs a harness Activity, and failed runs are retried as attempts. Checkpoint inserts are fenced, so a stale attempt can upload blobs that no row names. Blobs live in SeaweedFS under content keys (`sha256/<hex>`), so identical bytes share one object. `RecordingBlobStore` writes one `blob_objects` row per blob. `BlobRef`s sit inside JSON columns of `tasks`, `checkpoints` and `agent_events`. Every row and blob currently carries the class `task` or `audit`, and nothing is ever removed. Tasks are grouped into requests by `request_id`, with a request lock. Events are pruned by `TableTransport.prune`, which advances a retained base. Phase 2 wake rows already follow the outbox pattern. Temporal keeps Workflow histories for 72 hours.

## Summary vs plan

- Major, Summary vs D12: the Summary says deleting a request removes and redacts its content. It leaves out that Temporal histories keep the summary, questions and outcomes for 72 hours, and in backups, after a delete. Someone reading only the Summary would think the delete is complete. This is a privacy-relevant limit and belongs there.
- Major, Summary vs R18/D9: there is no mention of the `questions` truncation or the 64 KiB history test. That is a whole requirement, a code change in `finish_task_body`, and a full line under "What changes".
- Major, Summary vs Rollout: there is no mention that workers must be stopped for migration 0007, or that a downgrade loses the tombstones and cannot bring removed blobs back.
- Nit, Summary: R21 is cited next to "keeping IDs, statuses and usage", but R21 is about `--force` for closed Workflows, and `--force` is never mentioned.
- Nit, Summary: R5 (old `task` class must still decode) and R20 (`ended_at` set by `end_task`, which anchors expiry) are not mentioned, though `ended_at` is what makes expiry work.
- Nit, Summary: "Plan A of Phase 3A; plans C and D follow" leaves the reader wondering where B is. Why explains it (the first two plans were merged into A), but only later.

## Sections I couldn't paraphrase

None. I could paraphrase every section, though several depend on notes.md (see below).

## Undefined project-specific terms

- Major: `end_task`. It is central to R20 and D12, but the plan never says whether it is an Activity, a persistence function or a CLI path, or who calls it.
- Major: "messages, sessions and tool results" (R11), and `agent_sessions` / `session_id` (Assumptions). These tables are never introduced, and the plan never says how they relate to a request.
- Nit: `RecordingBlobStore`. It is named in Terms but never explained (is it a wrapper around `BlobStore`?).
- Nit: `finish_task_body`. Only `finish_task` is defined.
- Nit: "the existing request lock" (D12). What it locks, and where, is not stated.
- Nit: `TableTransport.prune` and "retained base" (D11). These are only partly explained, through ADR-0009.
- Nit: "wake rows" and "wake dispatcher" (D7).
- Nit: "each template's `turn_timeout`" (D5). Templates are never introduced.
- Nit: `make reset` (D8).
- Nit: `agentctl tail` (D11), and `agentctl task output` / `task status` (implied as existing).
- Nit: `schemas.md`. No path is given.
- Nit: "phase 03 task 2.3" (Why) and "phase 02 task 3.1" (Assumptions). These clash with this plan's own Phases 01-03 table, so it is unclear whether they mean roadmap phases or plan phases.
- Nit: "the threat model" (D12, Risks). Its location is not given.

## Places where the parts don't connect

- Major, R11: the list of content columns to redact exists only in notes.md#redact, so the requirement cannot be checked from the plan.
- Major, D3 / Terms "Expiry": the plan gives no start point for `transcript` 30 days and `artifact` 90 days (task end? write?). Terms says "notes.md#d3 gives each table's anchor", and R19 and the Risks section also send the class mapping to notes.md#d3. The core lifetime rules therefore depend on an outside file.
- Major, D5 vs D2 / Terms: an upload is held by its task, yet D5 also covers "uploads of a task that never got a `tasks` row". Such a reference is indexed (so the blob is not an orphan) and live (`end_task` never runs, so it never gets an expiry). The plan never says how the 24-hour window applies to it, or which holder or expiry it has.
- Major, D6 / R10 / R11: "remove or redact the rows" never says which rows a request delete removes (checkpoints? artifacts? events via prune?) and which it redacts. R10 says artifacts become unreadable, and R11 says rows are redacted and kept.
- Major, Terms vs What changes vs Impact (`blob_objects`): Terms describes `blob_objects` as already having "upload times, removal mark". Impact lists "`blob_objects` removal mark and upload time" as new data. What changes never mentions adding them. So it is unclear whether these columns exist today.
- Major, Impact "no Workflow code changes" vs R5: R5 requires Workflow code to decode a `BlobRef` with class `task` while the class set changes. This probably lives in `common/schemas/`, but the plan never says how Workflow code keeps decoding unchanged.
- Nit, R2: "the unindexed-reference check" is delivered in Phase 01, but the check seems to be `reconcile`, which Phase 03 delivers. The plan doesn't say which check R2 means.
- Nit, R2 / Rollout: migration 0007 "backfills the end times", but the plan never says where the end time of an already-ended task comes from.
- Nit, D4: `reconcile --reindex` and `make restore` are not said to take the advisory lock. Can `--reindex` run during a `gc`?
- Nit, D8 vs R23: if restore refuses any stack with data, the reason it then drops and recreates the databases is unexplained (presumably the Temporal schema already exists).
- Nit, R17: the plan doesn't say how reconcile tells a task that never ended from one still running.
- Nit, D2: "a Temporal payload codec (replay breaks once a blob is deleted)" is a rejected option that is hard to follow without more context.

## Readability

- Reread, Why: "The project owner split Phase 3A into four plans on 2026-11-19 and merged the first two, so this plan is A."
- Reread, D2: "Removed references stay, marked, so a kept row whose blob is gone is not unindexed." (double negative)
- Reread, D5: "Since uploads are held by their task (D2), the window covers only orphans and the uploads of a task that never got a `tasks` row…"
- Reread, Summary: "Every row that names a blob, and every upload made for a task, writes a row in a new reference index…" (rows writing rows)
- Repeated, "`gc` refuses while any reference is unindexed": stated in the Summary, D4, Risks and Rollout. Fine as a safety point, but D4 could be the one source.
- Repeated: "(project owner, 2026-11-19)" appears about 8 times. It could be stated once.
- Several rules in one requirement, R1: row writes and uploads.
- Several rules in one requirement, R6: expired rows/references, and blobs with no live reference.
- Several rules in one requirement, R7: rows/references before expiry, and blobs with a live reference.
- Several rules in one requirement, R13: one tombstone per batch, written in the same transaction, the listed fields, and no content.
- Several rules in one requirement, R17: four lists plus read-only.
- Several rules in one requirement, R20: set `ended_at`, and set every reference's expiry.
- Several rules in one requirement, R22: clear the mark, and upload again.
- Long sentences: none clearly over 40 words. The longest (D8 restore, Summary's last sentence, D12's Temporal sentence) are about 30-35 words.

<!-- Verbatim subagent report (Phase 3A persistence plan design-review round 1, fresh reader, at 417e8f9); reviewers: fresh-subagent (design-reader); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged with save-report). -->

File read: /home/geo/develop/praxismesh/docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md (313 lines, read in full). I opened no other file.

## From the Summary

This plan gives stored data a lifecycle. It adds a blob reference index, written in the same transaction as each row that names a blob. Operator commands use the index to garbage-collect expired data by retention class, to delete everything a request stored, and to leave an append-only audit record of each removal. Reading a removed blob reports "expired". It also adds `make backup` and `make restore` for the databases and SeaweedFS, a reconciliation report for after a restore, and a test that keeps large payloads out of Temporal histories. The main risk is deleting a blob that is still in use, because blobs are keyed by content hash and can be shared across tasks. The mitigations are to delete a blob only when no reference to it is left, and to offer a dry run on every command.

## From the whole plan

Phases 1 and 2 label every blob and row with a retention class but never remove anything. Storage only grows, stale attempts leave orphaned blobs (issue #74), and since references sit inside JSON columns nobody can tell whether a blob is still used. The plan adds a `blob_refs` index, written transactionally and backfilled by migration 0007. It replaces the old classes (`task`, `audit`) with five lifetimes (ephemeral 1d, checkpoint 7d, transcript 30d, artifact 90d, audit kept). It adds an append-only `audit_log` and three on-demand CLI commands, each with `--dry-run`: `gc`, `request delete` (removes blobs, redacts content rows, keeps IDs and usage) and `reconcile`. Removal goes index first, then bucket, then tombstone, so a rerun after a crash is safe. The plan also adds manual backup and restore (into a clean stack only) and a 64 KiB history-payload test with a cap on `questions`. The aim is to meet the §4.13 requirements: bounded storage, delete on request with an audit trail, and a tested backup and restore drill.

## How the existing system works, per this plan

Workers and an `agentctl` CLI write tasks, checkpoints, artifacts, events, sessions and messages to a PostgreSQL database, `praxismesh`, now at migration 0006. Bytes go to SeaweedFS under content-hash keys (`sha256/<hex>`), so identical bytes share one object. Rows name blobs through `BlobRef` values inside JSON columns of four tables, and every blob and row carries a retention class (today `task` or `audit`). Nothing is ever deleted. `BlobRef`s with `retention_class` also appear in Temporal Workflow histories, and Temporal keeps two databases of its own. Checkpoint writes are fenced per attempt, which is why a superseded attempt can leave unreferenced uploads (ADR-0007). Phase 2's message wake rows are committed with the message and drained by a dispatcher. There is apparently a `blob_objects` table, though the plan never says what it holds.

## Summary vs plan

- **Major. Summary, R-number citations.** The Summary's R references are off by one, as if written against an older numbering:
  - It cites R5-R8 for retention GC, but R5 is about replaying old histories; GC is R6-R8.
  - It cites R15-R17 for backup and restore, but R15 is rerun safety; backup and restore are R16-R17.
  - R14 (append-only) and R15 (rerun safety) are never mentioned under their own subject.
- **Major. Summary vs R11.** The Summary says the delete removes "everything a request stored". R11 says content rows are redacted and kept, with IDs, statuses and usage retained. A reader of the Summary would expect the rows to be deleted.
- **Major. Summary vs R16 and D8.** The Summary says "both PostgreSQL databases", but its own diagram and D8 list three databases (`praxismesh`, `temporal`, `temporal_visibility`). D8's title says "two dumps" and R16 says "three stores". The count is never consistent.
- **Major. Summary omits the retention-class migration (R4, R5, D3).** Remapping every existing row and blob to new classes, and keeping `task` decodable for replay, is a data migration with its own risk. The Summary does not mention it.
- **Major. Summary's risk mitigation is incomplete.** The plan's main guard against over-deleting is that GC refuses to run while any reference is unindexed (D4, Risks), plus the 24 h safety window (D5). The Summary names only the dry run and the "no remaining reference" rule.
- **Nit. Summary omits the `questions` cap (D9).** This is a behaviour change to a task-facing schema.
- **Nit. Summary omits that restore only works into a clean stack (R16).**
- **Nit. Summary diagram omits the `blob_objects.removed_at` marking step** that D6 makes central to crash safety.

## Sections I couldn't paraphrase

No section was impossible to paraphrase at the surface. Two came close:
- **Major. Phases.** The table gives task counts (10/7/7) but no tasks, and no mapping from requirements to phases. I can say "three phases" and nothing more.
- **Major. R10-R12 and the request concept.** I can restate these requirements, but not what a "request" is in today's system (see section 6, first finding).

## Undefined project-specific terms

- **Major. §4.13.** It is the source of the classes, the outbox pattern, the delete-by-request rules and the drill, but its content is only summarised in passing.
- **Major. "request".** There is no definition in Terms, and D1 defers the requests table to plan C.
- **Major. `blob_objects`.** D6, R8 (upload age) and R9 (removal date) rely on this table, but it is never introduced. Impact lists only its new `removed_at` column.
- **Major. "the four tables" (Why, notes.md#refs).** They are never named.
- **Major. `questions`.** It is never explained: which output, produced by whom, or what happens when the cap is exceeded (reject or truncate).
- **Nit.** "harness attempt", "stale/superseded attempt", "fence/fenced checkpoint insert", "workspace" (R1) and "turn" are not explained; the reader would need ADR-0007.
- **Nit.** `record_task`, `APP_TABLES`, `turn_timeout` and "template" are not explained.
- **Nit.** "wake rows" and "dispatcher" (D7) are explained only as "committed with the message, drained by a dispatcher".
- **Nit.** "Claim Check" (What changes, R18 heading) is never tied to its meaning here.
- **Nit.** "Plans C and D": if this is the first of three, why aren't the others called B and C? This plan's own letter is never given.
- **Nit.** The "redaction marker" value and which columns count as "content columns" are both left to notes.md#redact.
- **Nit.** "Compose stack", "fake model" and "Phase 4 gateway" are used without explanation.
- **Nit.** "Owner" means both the project owner and the owner of a reference (Terms).

## Places where the parts don't connect

- **Blocker. R10-R12, D2 (`request_id`), D1.** Delete-by-request is a core deliverable, but D1 says requests arrive with plan C. The plan never says what identifies a request today, how its tasks are found, or where `blob_refs.request_id` comes from. Without that, `request delete` can't be built from this document.
- **Major. Summary risk, D5, D6: GC racing with writers.** Keys are content hashes, so a new task can reference an existing key between D6's transaction (which marks it `removed_at`) and the object delete. The same can happen with an old orphan that a writer dedups onto instead of uploading again. This is exactly the "deleting too much" risk, and no mechanism addresses it: no locking, and no rule for what happens when a key with `removed_at` set is written again. D5's argument that "a blob still waiting for its reference is always younger than the window" fails when the bytes already exist and no new upload takes place.
- **Major. D4 and Rollout.** GC refuses while any reference is unindexed. Rollout admits that old workers still running during deploy write unindexed references, which reconcile only reports. Nothing re-indexes them, so after a sloppy deploy GC is blocked with no documented way to unblock it.
- **Major. Terms "Expiry" vs D3.** Expiry is defined as task end time plus lifetime, but `ephemeral` is "1 day after write". D3 also never says which data is `ephemeral`. `audit` is kept "until purged", but nothing purges, and R14 forbids the app role from deleting audit rows. Rows without a task are not covered either.
- **Major. R4 and Risks.** The table-to-class mapping, which is the single source checked by the `APP_TABLES` test, lives only in notes.md (D3 "Details"). D3 here lists data kinds, not tables. You need notes.md to know what R4's migration does.
- **Major. R9.** "a blob that a removal recorded" depends on `blob_objects.removed_at` (D6), but R9 and What changes never say so. Which removal R9 "names" (an audit row? a date only?) is also left open.
- **Major. R13 and R15 vs D6.** The tombstone is written last and must list counts of rows, references and blobs. After a crash, the rerun has to rebuild those counts after the index transaction has already committed. How it does so, and how it keeps "one tombstone per delete", is not described.
- **Major. R13.** Tombstone granularity for GC is never stated (per run, per class, per blob). Only the delete case is specified.
- **Major. R18 vs D9.** R18 is worded as an absolute ("No Workflow history payload may exceed 64 KiB"), but the only mechanism is a test over the integration suite. There is no runtime check, so production payloads are not bounded by anything stated.
- **Major. Phases.** Nothing maps R1-R18 or D1-D9 to Phases 01-03, so "acceptance" in Phase 03 has no stated criteria.
- **Nit. D4.** "batches of 500" doesn't say batches of what, and doesn't say how batching squares with the atomicity of a single request delete.
- **Nit. R16 and D8.** Dump order is stated, but consistency across three dumps and a bucket copy of a running stack is not discussed beyond running reconcile afterwards.
- **Nit. Impact.** "`retention_class` ... checks on every application table" (check constraints) appears nowhere else.
- **Nit. Why.** The backup "drill" in Phase 3A has no requirement or task of its own.
- **Nit. R12 and Terms "Ended task".** `needs_input` counts as ended, so a request waiting for user input can be deleted. This may be intended, but it isn't stated. Whether other statuses exist (queued, cancelled) is also unknown.

## Readability

- **Nit. Summary.** "Only an index with no remaining reference may remove a blob": the wrong subject made me reread it. It means a blob may be removed only when the index shows no remaining reference.
- **Nit. D6.** "deletes the index and row changes in one transaction that records the blob keys it freed in `blob_objects.removed_at`, then ...": "deletes ... changes" is garbled and I had to reread it.
- **Nit. D5.** The 35-word chain "An attempt uploads ..., and no template's ..., so a blob still waiting ..." took a reread.
- **Nit. D1.** "plans, revisions and budgets to plan D" uses "plans" for both database tables and these documents.
- **Nit. Repetition.** Content-hash sharing appears in the Summary, in Why and in R3.
- **Nit. Repetition.** Restore-into-a-clean-stack appears in R16, D8 and Risks.
- **Nit. Repetition.** GC refusing while references are unindexed appears in D4 and Risks.
- **Nit. Multi-rule requirements.**
  - R4: writers assign classes, and the migration remaps.
  - R8: remove after the window, and keep until then.
  - R10: remove references, and remove orphaned blobs.
  - R11: redact, and keep rows.
  - R13: write tombstones, exclude content, and one tombstone per request in the example.
  - R15: finish correctly, and one tombstone.
  - R16: backup scope, and restore only into a clean stack.
  - R17: list three kinds, and change nothing.
- No sentence clearly exceeds 40 words.

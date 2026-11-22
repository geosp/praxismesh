---
id: ADR-0012
title: Index every stored blob reference in its holder's transaction, and give every table and blob a retention class
status: accepted
date: 2026-11-21
issue: "#92"
related:
  - docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md
  - docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle/notes.md
  - docs/adr/0007-fence-harness-attempts-in-one-transaction.md
supersedes: null
superseded_by: null
---

# ADR-0012: Index every stored blob reference in its holder's transaction, and give every table and blob a retention class

## Context and problem statement

Large values (instructions, inputs, artifacts, checkpoints, transcripts) live in the blob store as
content-addressed objects (`sha256/<hex>`); rows and Temporal histories hold only `BlobRef`s
(§2, §4.13). Before Phase 3A, nothing recorded which rows named which blob, so nothing could say
when a blob was no longer needed, what it held, or which references a restored backup had lost.
The same bytes can be held by several tasks (content addressing), and a removed blob can be
uploaded again by a later request. §4.13 asks for retention by class (checkpoint, transcript,
artifact, audit) and for deletion by request with tombstones.

## Considered options

- An explicit reference index (`blob_refs`, one row per holder and blob) written in the holder
  row's transaction, with a per-blob row (`blob_objects`) that records the class and any removal
  mark.
- Scanning the JSON columns that hold `BlobRef`s at GC time.
- A Temporal payload codec that moves large payloads to blobs.

## Decision outcome

Chosen option: "An explicit reference index written in the holder row's transaction", because it
is the only option where a blob's live holders are a query, not a search, and where a new holder
column cannot be missed silently: GC refuses while any stored reference is unindexed. Scanning was
rejected as slow and easy to get wrong when a column is added; a payload codec was rejected because
replaying a history fetches its payloads, so removing one would break replay.

How it is used (plan D2, D3, D10):
- Every writer of a row that holds a `BlobRef` indexes it through the one helper in
  `common/persistence/refs.py`, in the same transaction as the row (and inside ADR-0007's fence
  where the row is fenced). An upload indexes a reference held by its task. Removed references
  stay, marked, so a kept row still has its index row.
- Every application table has one class from §4.13 (`ephemeral`, `checkpoint`, `transcript`,
  `artifact`, `audit`) and an anchor in `common/persistence/retention.py` (`TABLE_CLASS`). No
  expiry is stored: it is computed from the class and the task's `ended_at`, so a late upload
  expires with its task. S3 object metadata never decides a lifetime.
- Uploading bytes again revives a removed blob (it clears the removal mark under the key's
  `blob_objects` row lock), except for a task a delete has marked, whose upload revives nothing.

### Consequences

- Good, because GC, delete-by-request, reconcile and restore checks are queries over
  `blob_refs` and `blob_objects`, and a reference lost in a restore is listed as dangling.
- Good, because a blob shared by two tasks stays while either holds it.
- Bad, because every future table or column that holds a `BlobRef` must index it in its writer
  and must have a class; a writer that forgets leaves an unindexed reference, which makes `gc`
  refuse until `agentctl reconcile --reindex` repairs it.
- Bad, because each write of a holder row does one more insert in its transaction.
- Follow-up: Phase 3A's plans C and D (requests, plans, revisions, budgets) add tables that must
  follow this ADR.

### Confirmation

- `tests/test_retention.py::test_every_app_table_has_its_d3_class` fails when a table has no class.
- `tests/integration/test_gc.py::test_gc_refuses_while_a_reference_is_unindexed` and
  `agentctl reconcile`'s unindexed list catch a holder written without its index row.
- `tests/integration/test_index_writers.py` checks each writer indexes in its own transaction.

## Links

- Issue #92; implementation plan docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle (R1-R5,
  R19, R22; D2, D3, D10; notes.md#d2, notes.md#d3, notes.md#revive); plan §4.13.

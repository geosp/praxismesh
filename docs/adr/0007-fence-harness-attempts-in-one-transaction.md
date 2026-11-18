---
id: ADR-0007
title: Fence every harness attempt's writes in one locked transaction per task
status: accepted
date: 2026-11-17
issue: "#62"
related:
  - docs/plans/2026-11-15-dsh-production-harness/plan.md
  - docs/adr/0005-adopt-dsh-as-primary-agent-harness.md
supersedes: null
superseded_by: null
---

# ADR-0007: Fence every harness attempt's writes in one locked transaction per task

## Context and problem statement

A harness turn runs as a Temporal Activity. Temporal retries it as a new attempt when a
worker dies, a heartbeat times out or a deadline passes, and the old attempt may still be
running: a worker that lost its connection, or a DSH runtime still finishing a request.
Two attempts of the same turn, or an attempt of an older turn, can then write
checkpoints, attempt outcomes, usage and artifact references for the same task.

The migration plan requires that a stale attempt writes no checkpoint or attempt outcome
(R6) and returns no artifact reference or outcome (R7), for both runners
(`openai_agents` and `dsh`). A check made before a write, in its own transaction, races
a new attempt that starts between the check and the write.

## Considered options

- A fence in the write's own transaction: take a per-task lock, check that no newer
  (turn, attempt) exists, then write.
- A separate pre-check (`is this attempt still current?`) before each write.
- Rely on Temporal alone: let the Workflow ignore a stale Activity's result.

## Decision outcome

Chosen option: "A fence in the write's own transaction", because only a check made under
the same lock and in the same transaction as the write holds when a newer attempt starts
concurrently (R6, R7).

- The lock is `pg_advisory_xact_lock(hashtext(task_id))`.
- Attempt start, the checkpoint insert, the usage-ledger dispatch and the attempt finish
  each take it and check that no newer (turn, attempt) row exists. A stale start,
  checkpoint or finish raises `FenceRejected`; a stale ledger dispatch is refused (the
  gateway denies the request as superseded). When the runner has not failed, the Activity
  then raises `Superseded` and writes nothing more.
- A refusal (a template-version mismatch, or a DSH worker that cannot serve) inserts an
  uncounted `refused` row under the same lock, without the newer-attempt check, so it
  fences older attempts too.
- Three writes skip the newer-attempt check, and must stay bounded as they are:
  - closing unfinished rows (`close_unfinished`) touches only rows at or below the writer's
    attempt (`through_attempt`), or the whole task at task completion;
  - charging unsettled requests (`close_unknown`), which runs when a DSH attempt opens and
    when it fails, takes the lock but touches only earlier attempts of the same turn (below
    the writer's attempt at open, through it on a failure); a stale attempt's charge can
    still rewrite those usage columns (a known deviation, migration plan F106);
  - settling a ledger row with a response's usage (`settle`) updates only the writer's own
    row while it is still unsettled, so a request that a newer attempt has already closed
    stays closed.
  When a runner fails, the attempt's own fenced finish may be refused (and is then
  skipped); the failure still propagates to Temporal.
- Artifact references leave the Activity only in the result of a successful fenced
  finish. A pre-upload currency check is an early exit, not the guarantee.
- The fence applies to every runner through the shared `run_harness_turn` seam, not to
  DSH alone.

Rejected: the separate pre-check, because it races a new attempt; Temporal alone, because
a stale Activity's database writes (checkpoints, usage) happen before and regardless of
whether the Workflow uses its result.

### Consequences

- Good, because recovery, budget and result contracts hold under concurrent attempts for
  every runner.
- Good, because the rule is one lock and one check, the same at every write.
- Bad, because writes for one task serialize on its lock; a long transaction would delay
  that task's other attempts (not observed at the current scale; Unknown at larger scale).
  The lock key is a 32-bit hash, so two tasks can occasionally share a lock.
- Bad, because a stale attempt can still upload blobs that nothing references: artifact
  blobs (`audit` class, kept indefinitely) and the workspace and session blobs of a
  checkpoint whose fenced insert is then refused (`task` class, 30 days). Retention records
  lifetimes only; deletion arrives in Phase 3A.
- Follow-up: any new write path for attempts (Phase 2 events, a new runner) must take the
  fence or justify why it need not. The repository still offers unfenced writers
  (`CheckpointRepository.insert`, and `AttemptRepository.finish` with `fenced=False`, its
  default); new attempt code uses the fenced forms.
- Follow-up: Phase 3A garbage collection should remove unreferenced audit blobs.

### Confirmation

Integration tests in `tests/integration/test_persistence_phase1.py`
(`test_stale_attempt_cannot_checkpoint_or_finish`,
`test_fenced_insert_waits_for_a_concurrent_start`, `test_start_waits_for_the_task_lock`,
`test_refusal_fences_older_attempts`, `test_late_stale_start_is_refused`),
`tests/integration/test_harness_activity.py`
(`test_newer_attempt_mid_run_fences_the_finish`,
`test_newer_attempt_before_publication_blocks_artifacts`) and
`tests/integration/test_dsh_usage.py` (`test_stale_attempt_cannot_dispatch`), run by CI's
`stack` job. Review item: a new attempt write path names its fence.

## Links

- [Migration plan](../plans/2026-11-15-dsh-production-harness/plan.md), D10, R6, R7; notes.md#d10; notes.md#rollout (deferred deviations, F106).
- [ADR-0005](0005-adopt-dsh-as-primary-agent-harness.md): existing recovery contracts are preserved.

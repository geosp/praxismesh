<!-- Verbatim subagent report (Phase 3A persistence plan design-review round 3, codebase fit, at f3453cd); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged with save-report). -->

## Review: Phase 3A persistence and data lifecycle plan (at f3453cd)

I found 3 Major issues and 13 Nits, and no Blockers. Most of what the plan and notes say about the code is accurate. These claims check out:
- `TaskRepository.complete` is unused.
- `agent_events.blob_ref` is unused.
- `checkpoints.finish` is `{status, summary, questions}`.
- `S3BlobStore.put` uses `head_object` and `copy_object`, and `RecordingBlobStore.put` uploads before it upserts.
- `_REQUEST_LOCK` is `pg_advisory_xact_lock(2, hashtext(:r))`, and joins are checked only by `request_exists`.
- The replay fixture has exactly 3 payloads carrying `retention_class: task`.
- `finish_task_body` truncates the summary to 2,000 characters and is shared by both runners.
- `max_wall_time_cap` is PT1H, `TEMPORAL_RETENTION` defaults to 72h, and the CI `stack` job has a 45-minute timeout.

Every requirement is delivered by some task, and the task order builds, apart from one Nit below.

### Major

**M1. Late writes from the last attempt can undo a request delete.**
- Where: Decisions › D12, notes.md#redact, R10, R11; phase 02 task 3.2.
- What is wrong: the delete serializes only on the request lock. The writes an attempt makes after its task has ended are fenced only by the task lock plus the "no newer attempt" check.
  - `CheckpointRepository.insert_fenced` (`common/persistence/repositories.py:387-417`) and `TableTransport.publish` (`common/events/table.py:61-68`) check only `NO_NEWER_ATTEMPT` (`common/persistence/fence.py:23-26`).
  - That check passes for the newest attempt of a task that ended by timeout, cancel or terminate. `complete_task` only closes its attempt rows (`orchestrator/activities.py:258`) and does not block later inserts.
  - The notes already expect such writers: stale uploads happen "possibly after the task has ended" (notes.md:32-33).
- Effect: after a delete commits, that attempt can still insert a checkpoint (with `finish` text and live `blob_refs` rows) or publish events above the new retained base. Content becomes readable again, against R10 ("none of its ... checkpoints ... can be read") and R11. Neither the dangling check nor reconcile would flag it. The same applies to `--force` with a terminated Workflow (R21).
- Fix: make fenced attempt writes refuse once the task has ended, or once their own attempt row is no longer `started`. If the delete instead takes each task's lock, state the lock order: comms writes take the task lock and then the request lock (`messages.py:357-365`), while the delete takes the request lock and then the task lock.

**M2. The backup drill as an integration test would wipe the developer's stack.**
- Where: phase 03 task 2.3, notes.md#d8 ("The drill in CI").
- What is wrong: task 2.3 makes the drill an integration test that runs `make reset`. `make smoke` runs everything under `tests/integration` (`Makefile:108-109`), and `make reset` deletes all volumes (`Makefile:94-97`).
- Effect:
  - Anyone running `make smoke` locally would lose their stack's data, and it comes back only if the restore succeeds. AGENTS.md says to ask before materially irreversible actions.
  - Tests that run after it inside the same `smoke` run would see a stack that has been reset and restored.
  - The R18 history test, which runs over the suite's Workflows, would lose them.
- Also missing: D8's restore steps assume the stack is up, so after `make reset` someone must run `make up` first. The plan never says this.
- Fix: make the drill a separate opt-in target (for example `make drill`) that runs as its own step in the CI `stack` job, and name the `make up` precondition.

**M3. `event_batches` rows are never removed.**
- Where: notes.md#d3, which lists `event_batches` as "not GC's: `publish` already deletes rows after 600 s (`seen_at`)"; R6.
- What is wrong: `publish` deletes old rows only for its own workflow, and only when that workflow publishes again (`common/events/table.py:79-85`). The batches from each task's last 600 seconds of events therefore stay forever.
- Effect: an `ephemeral` table that grows without bound. This goes against R6 and the plan's own "Storage only grows" problem statement. A request delete also leaves these rows behind.
- Fix: have GC remove `event_batches` rows past the horizon, or rows of ended tasks.

### Nits

- notes.md#d6, step 1: it says to mark references and *then* lock `blob_objects`, yet also says "Locks are taken `blob_objects` first". As written it can deadlock with revive when the same `(upload, task, key)` row is involved, for example an unchanged workspace re-uploaded by a late attempt. Lock the candidate keys first.
- notes.md#redact: the table does not say what a delete does to `sample_orders`, `task_inbox` or `message_wakes` (all per-task rows listed in d3). R11 can't be checked for them.
- D11: `prune` is part of the `EventTransport` Protocol, which `MemoryTransport` also implements (`common/events/transport.py:342`, `common/events/memory.py:75`). The new connection and limit arguments need to be optional, or the Protocol updated, or mypy will fail.
- D4 against phase 02 tasks 1.4 and 1.5: D4 says every removal command has `--dry-run`, but `events prune` gets neither `--dry-run` nor the `(3, 0)` lock. A prune running during a backup can free blobs between the dump and the bucket copy (D8's ordering argument).
- Phase 02 task 1.5: it gives `agentctl backup` the lock, but that command is only created in phase 03 task 2.1.
- Phase 03 task 1.1 against D8: reconcile exits 1 when it lists anything, and the restore "ends with reconcile". The drill expects one dangling reference, so the exit code would fail `make restore`.
- notes.md#d2 / Decisions › D10: `index_refs` takes `request_id`, but upload references get only `task_id` from `put`. Say whether `blob_refs.request_id` is nullable.
- Phase 01 task 2.1: `TaskRepository.complete` (`repositories.py:91-99`) writes `result` without indexing it. Remove it or index it, or `gc`'s unindexed check could block on it if anything calls it.
- R2 / phase 01 task 1.1: the plan doesn't say how a test gets a database at 0006. The app role can't connect to other databases (`tests/integration/test_database.py:36-39`) and has no CREATEDB, so the test must use the superuser or downgrade the shared database.
- Decisions › D8 / R23 and ADR-0002 ("the application never reads" Temporal's databases): say whether "temporal holds no Workflow execution" is checked through Temporal's API or by direct SQL. If by SQL, note the ADR-0002 exception.
- notes.md#d8 says "comparing Workflows with rows is Phase 9", but R17 and phase 03 task 1.1 compare unended tasks against closed Workflows. The wording is inconsistent.
- notes.md:35 says "`prepare_task` mints the task ID before it uploads" as if it were true today. It is not: `orchestrator/submit.py:34-44` mints it after the uploads. Phase 01 task 2.2 makes the change.
- Phase 03 task 2.2: `infra/db/databases.sh` needs a mount in `infra/docker-compose.yml` (see lines 28-30 for the current ones), which the Impact section doesn't list. Phase 02 task 1.4's check ("a crash between prune and tombstone is impossible ...") is a claim, not a test.

### ADRs

No Decision contradicts an ADR in force:
- D10 justifies writing the upload reference outside the fence, as ADR-0007 asks of new write paths.
- D11 explicitly argues that batched prunes are the "or equivalent" ADR-0009 allows.
- D3 keeps wake rows until their recipient has ended, as ADR-0010 requires.

The only ADR point is the ADR-0002 Nit above.

Files reviewed:
- /home/geo/develop/praxismesh/common/persistence/repositories.py
- /home/geo/develop/praxismesh/common/persistence/messages.py
- /home/geo/develop/praxismesh/common/persistence/fence.py
- /home/geo/develop/praxismesh/common/events/table.py
- /home/geo/develop/praxismesh/common/events/transport.py
- /home/geo/develop/praxismesh/orchestrator/submit.py
- /home/geo/develop/praxismesh/orchestrator/activities.py
- /home/geo/develop/praxismesh/orchestrator/cli.py
- /home/geo/develop/praxismesh/harness_activity/activity.py
- /home/geo/develop/praxismesh/Makefile
- /home/geo/develop/praxismesh/infra/db/init.sh
- /home/geo/develop/praxismesh/infra/docker-compose.yml
- /home/geo/develop/praxismesh/tests/integration/test_database.py

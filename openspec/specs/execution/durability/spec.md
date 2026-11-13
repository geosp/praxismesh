# execution/durability Specification

## Purpose

A task survives the loss of its worker: session and workspace are checkpointed during a harness turn and restored on another worker, and side effects are not repeated (plan §4.2; Phase 1 task 8; accept criteria).

## Requirements

### Requirement: Mid-turn checkpoints
At the start of every inner turn, including the first, a harness turn SHALL record a checkpoint: a workspace snapshot stored through `BlobStore` and the session position, committed in `checkpoints`. A checkpoint SHALL count as acknowledged once its row is committed. (Plan: Phase 1 task 8; §4.2 separate workspace checkpoints, a transcript alone cannot restore files.)

#### Scenario: Checkpoint after an edit
- **WHEN** an inner turn writes a file in the workspace
- **THEN** a new checkpoint row exists whose workspace snapshot contains that file, and whose session position equals the number of session items saved for that turn

### Requirement: Recovery on another worker
When a worker stops mid-turn, the next attempt SHALL run on any worker of the template's queue and restore the latest checkpoint (ordered by turn, attempt and sequence), discarding session items recorded after it. Worker affinity SHALL NOT be required. (Plan: Phase 1 task 8 and accept criteria; §4.2; owner decision 2026-11-11: under Compose, stop one worker container.)

#### Scenario: Lost before the first checkpoint
- **WHEN** an attempt is lost before it records any checkpoint for the task
- **THEN** the next attempt starts fresh from the input files and the instructions, with an empty session

#### Scenario: Latest turn wins
- **WHEN** turn 1 had three attempts and turn 2 has recorded its first checkpoint
- **THEN** restore uses turn 2's checkpoint, not a later-numbered attempt of turn 1

#### Scenario: Worker stopped after edits
- **WHEN** worker A is stopped after an acknowledged checkpoint that includes workspace edits
- **THEN** worker B resumes the same task (same task and Workflow IDs), the edits are present, the conversation continues, and the task completes

### Requirement: No duplicated side effects
Every MCP tool with an effect outside the workspace SHALL take an idempotency key derived from the task ID, the tool name and its canonical arguments, and SHALL apply its effect at most once per key, returning the recorded result on a repeat. `run_command` is treated as workspace-only in Phase 1; its effects outside the workspace are an accepted risk until the Phase 5 sandbox. (Plan: Phase 1 accept criteria; §4.2 idempotency keys, test pod termination between side effect and checkpoint.)

#### Scenario: Crash between effect and checkpoint
- **WHEN** a worker is stopped while the sample server holds `record_order`'s response after committing its effect, and the resumed task calls it again with the same arguments
- **THEN** the order exists once, and the second call returns the recorded result

#### Scenario: Identical calls within one task
- **WHEN** a task calls `record_order` twice with the same arguments
- **THEN** one order is recorded; this is the sample tool's intended behavior, and a tool that needs repeats adds a sequence number to its arguments

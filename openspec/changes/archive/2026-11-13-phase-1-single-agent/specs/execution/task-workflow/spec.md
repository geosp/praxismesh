# Spec Delta

## Purpose

The durable task: `TaskWorkflow` on the stable orchestration queue drives harness turns, accounts turns and budgets, and retries infrastructure failures only (plan Phase 1 task 9; §4.1 turn definitions).

## ADDED Requirements

### Requirement: Turn and budget accounting
`TaskWorkflow` SHALL run harness turns until one returns `done` or `needs_input`, or until the profile's `max_turns`, token or wall-time budget is exhausted, and SHALL end with a `TaskResult` recording the status, harness turns, tokens, attempt count and artifacts. Retried attempts SHALL NOT count as harness turns. (Plan: Phase 1 task 9; §4.1 distinguish inner turns, task turns, attempts, timeout and token budget.)

#### Scenario: Budget exhausted
- **WHEN** harness turns keep returning `continue` until `max_turns` is reached
- **THEN** the task ends `failed` with the reason "turn budget exhausted", and its last checkpoint is kept

#### Scenario: Retries are not turns
- **WHEN** a harness turn fails twice on infrastructure errors and then succeeds
- **THEN** the task's harness-turn count rises by one and its attempt count by three

### Requirement: Infrastructure retries only
Harness-turn Activities SHALL be retried for infrastructure failures (lost worker, timeout, unavailable storage) and SHALL NOT be retried for capability, budget or invalid-input errors. (Plan: Phase 1 task 9.)

#### Scenario: Capability error is final
- **WHEN** a harness turn raises a capability error
- **THEN** the task ends `failed` without another attempt

### Requirement: Deterministic and small
`TaskWorkflow` SHALL do no I/O outside Activities, SHALL carry only IDs and `BlobRef`s in its inputs and outputs, and SHALL have replay tests against recorded histories and time-skipping tests with mocked Activities. (Plan: §2 deterministic Workflow code and bounded histories; §8 every Workflow has replay and time-skipping tests.)

#### Scenario: Replay
- **WHEN** the replay test runs the current `TaskWorkflow` against the committed histories
- **THEN** it replays without a non-determinism error

### Requirement: One run per task ID
A task's Workflow ID SHALL be its `task_id`, minted by the CLI when the request gives none. Temporal SHALL reject a second start while it remembers the first run, and the `tasks` table SHALL reject it permanently, before any harness turn runs. (Plan: §4.2 idempotency; Phase 1 accept criterion "no duplicated external side effects".)

#### Scenario: Resubmitting a finished task
- **WHEN** a task has completed and the same `task_id` is submitted again, including after Temporal's retention period
- **THEN** it is rejected (by Temporal, or by `record_task` with `TaskAlreadyExists`), and no harness turn runs

### Requirement: Lost attempts count against the budget
A harness turn's reported usage SHALL include the tokens and tool calls of earlier attempts of the same turn that were lost, taken from their last heartbeat details. `needs_input` SHALL end the task with status `needs_input`. (Plan: §4.1 token budget; §4.5 budgets; Phase 2 adds answering questions.)

#### Scenario: Worker lost mid-turn
- **WHEN** an attempt is lost after heartbeating 50,000 tokens and the next attempt uses 20,000
- **THEN** the turn's outcome reports at least 70,000 tokens against the task budget

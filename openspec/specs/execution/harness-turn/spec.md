# execution/harness-turn Specification

## Purpose

One harness turn: a bounded harness invocation inside a Temporal Activity, configured from the worker template, behind one `HarnessRunner` interface for both runners (plan §4.1; Phase 1 task 7).

## Requirements

### Requirement: Bounded, template-configured harness turn
`run_harness_turn` SHALL run one harness invocation of at most the template's `inner_max_turns` inner turns, within the template's `turn_timeout`, using the template's model, endpoint, MCP servers, skills bundle and tools. It SHALL return a structured `TurnOutcome` (status, latest checkpoint, usage, a summary of at most 2 KB, questions, and output `BlobRef`s). (Plan: Phase 1 task 7; §4.1; §5 `TaskResult`.)

#### Scenario: Scripted harness turn
- **WHEN** a harness turn runs with a scripted model that calls a tool and then calls `finish_task` with status `done`
- **THEN** it returns `done` with the tool-call and token counts, and its workspace change is in the recorded checkpoint

#### Scenario: Inner-turn limit reached
- **WHEN** the scripted model keeps calling tools past `inner_max_turns`
- **THEN** the harness turn stops at the limit and returns `continue`

### Requirement: One HarnessRunner interface
`run_harness_turn` SHALL call runners only through `HarnessRunner`, and a conformance suite SHALL check any runner against the fake model: template-only configuration, heartbeat and checkpoint hooks, cumulative usage, and ending through `finish_task`. Phase 1 SHALL implement only the `openai_agents` runner. (Plan: §4.1 stable `HarnessRunner` interface; §2 harness licensing; owner decisions 2026-11-11.)

#### Scenario: Conformance
- **WHEN** the conformance suite runs the `openai_agents` runner against the fake model
- **THEN** every contract case passes, and the request log shows only the template's tools and instructions

### Requirement: Heartbeats with bounded progress
A harness turn SHALL heartbeat at an interval shorter than the template's `heartbeat_timeout`, with details limited to the latest checkpoint ID, the inner turn, and tool-call and token counts. (Plan: §4.1 heartbeat with bounded progress metadata.)

#### Scenario: Heartbeat details
- **WHEN** a harness turn has recorded a checkpoint
- **THEN** its next heartbeat carries that checkpoint ID and no workspace or transcript content

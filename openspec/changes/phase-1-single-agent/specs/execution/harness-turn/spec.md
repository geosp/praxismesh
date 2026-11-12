# Spec Delta

## Purpose

One harness turn: a bounded harness invocation inside a Temporal Activity, configured from the worker template, behind one `HarnessRunner` interface for both runners (plan §4.1; Phase 1 task 7).

## ADDED Requirements

### Requirement: Bounded, template-configured harness turn
`run_harness_turn` SHALL run one harness invocation of at most the template's `inner_max_turns` inner turns, within the template's `turn_timeout`, using the template's model, endpoint, MCP servers, skills bundle and tools. It SHALL return a structured `TurnOutcome` (status `done`, `continue` or `needs_input`, the latest checkpoint, usage and a summary of at most 2 KB), with large content referenced as `BlobRef`s. (Plan: Phase 1 task 7; §4.1; §5 `TaskResult`.)

#### Scenario: Scripted harness turn
- **WHEN** a harness turn runs with a scripted model that calls a tool and then answers
- **THEN** it returns `done` with the tool-call and token counts, and its workspace change is in the recorded checkpoint

#### Scenario: Inner-turn limit reached
- **WHEN** the scripted model keeps calling tools past `inner_max_turns`
- **THEN** the harness turn stops at the limit and returns `continue`

### Requirement: Both runners behind HarnessRunner, openai_agents by default
Harness runners SHALL implement one `HarnessRunner` interface. The `openai_agents` runner SHALL be the default; the `claude_sdk` runner SHALL be selectable by template and installed only as an optional extra. The Claude runner SHALL set `strict_mcp_config`, an empty `setting_sources`, `skills` limited to the bundle, and `allowed_tools` from the template. (Plan: §4.1; §2 harness licensing; owner decision 2026-11-12.)

#### Scenario: Claude runner discovers nothing implicitly
- **WHEN** the Claude runner starts in a workspace that contains its own `.claude/` settings or skills
- **THEN** those settings and skills are not loaded, and only the template's MCP servers and skills are available

### Requirement: Heartbeats with bounded progress
A harness turn SHALL heartbeat at an interval shorter than the template's `heartbeat_timeout`, with details limited to the latest checkpoint ID, the inner turn, and tool-call and token counts. (Plan: §4.1 heartbeat with bounded progress metadata.)

#### Scenario: Heartbeat details
- **WHEN** a harness turn has recorded a checkpoint
- **THEN** its next heartbeat carries that checkpoint ID and no workspace or transcript content

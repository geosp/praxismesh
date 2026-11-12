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
Harness runners SHALL implement one `HarnessRunner` interface. The `openai_agents` runner SHALL be the default; the `claude_sdk` runner SHALL be selectable by template and installed only as an optional extra. (Plan: §4.1; §2 harness licensing; owner decision 2026-11-11.)

#### Scenario: Default runner
- **WHEN** the committed `local-default` template is loaded
- **THEN** its harness is `openai_agents`, and the worker starts without the Claude extra installed

### Requirement: Claude runner isolation
The Claude runner SHALL restrict its tools (`tools`, exact `allowed_tools`, `permission_mode="dontAsk"`), load only the template's MCP servers (`strict_mcp_config`) and skills (a local plugin, no setting sources), and start the CLI with an explicit minimal environment. (Plan: §4.1 disable implicit discovery, verify prohibited capabilities.)

#### Scenario: Claude runner discovers nothing implicitly
- **WHEN** the Claude runner runs against the fake model in a workspace with its own `.claude/` settings, skills and `.mcp.json`, and the worker environment holds a canary credential
- **THEN** the request it sends lists only the allowed tools and skills, and the canary is not visible to its commands

### Requirement: Heartbeats with bounded progress
A harness turn SHALL heartbeat at an interval shorter than the template's `heartbeat_timeout`, with details limited to the latest checkpoint ID, the inner turn, and tool-call and token counts. (Plan: §4.1 heartbeat with bounded progress metadata.)

#### Scenario: Heartbeat details
- **WHEN** a harness turn has recorded a checkpoint
- **THEN** its next heartbeat carries that checkpoint ID and no workspace or transcript content

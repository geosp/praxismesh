# Spec Delta

## Purpose

What an agent may do comes from versioned worker templates, never from requests or profiles: `AgentProfile`, `WorkerTemplate` and `McpServer` definitions, their loaders, and the template-only capability rule (plan §4.10, §5; Phase 1 tasks 1 and 10).

## ADDED Requirements

### Requirement: Versioned definitions with validated loaders
`AgentProfile`, `WorkerTemplate` and `McpServer` SHALL be Pydantic schemas with a `schema_version`, loaded from YAML under `registry/` and validated on load. A template SHALL be identified by `name@version` plus a content hash, and every task SHALL record the template version and hash it ran with. (Plan: Phase 1 task 1; §5; §4.10 immutable template versions.)

#### Scenario: Valid definitions load
- **WHEN** the loaders read the committed `registry/` files
- **THEN** every profile, template and MCP server validates, and each template exposes its version and content hash

#### Scenario: Changed template without a version bump
- **WHEN** a template file's content changes but its `version` does not
- **THEN** the loader reports the hash mismatch against the recorded version instead of silently using the new content

### Requirement: Capabilities come from templates only
The harness configuration (model, MCP servers, skills, tools) SHALL come only from the worker template. Profiles and requests SHALL reject unknown fields; a request carries only a profile name, instructions and input files. One that names a skill, MCP server or tool SHALL be rejected before any Workflow starts, naming the field. (Plan: Phase 1 task 10; §4.1; §5 "No MCP/skills fields".)

#### Scenario: Request injects a capability
- **WHEN** a task request includes a skill, an MCP server or a tool
- **THEN** submission fails naming the rejected field, and no Workflow is started

#### Scenario: Profile injects a capability
- **WHEN** a profile file contains an `mcp_servers`, `skills` or `tools` field
- **THEN** loading it fails naming the field

### Requirement: Only allowed tools are callable
A harness SHALL expose only the template's MCP tools (filtered to each server's `tools_allowed`), the template's skills bundle, and the built-in workspace tools. The command tool SHALL be offered only when the template lists `cli_tools`, and SHALL refuse a command whose program is not listed. (Plan: Phase 1 task 10; §4.1 verify allowed and prohibited capabilities.)

#### Scenario: Prohibited tool call
- **WHEN** a model calls an MCP tool that is not in `tools_allowed`, or runs a program not in `cli_tools`
- **THEN** the call is refused with an explicit error in the tool result, and the refusal is logged with the task and attempt IDs

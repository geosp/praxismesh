# Agent definitions (the real copy)

One Markdown file per agent: `<agent-name>.md`. `uv run .agents/sync_agents.py` turns each file into:

| Harness | Output | Body becomes |
|---|---|---|
| Claude Code | `.claude/agents/<name>.md` | system prompt (Markdown body) |
| GitHub Copilot | `.github/agents/<name>.agent.md` | agent instructions (Markdown body) |
| Codex CLI | `.codex/agents/<name>.toml` | `developer_instructions` |

## Format

```markdown
---
name: design-reviewer            # required; lowercase kebab-case; must match the file name
description: >-                  # required; when to use this agent
  Reviews an implementation contract against project requirements. Use for independent design review.

# Optional per-harness blocks. Keys are copied verbatim into that harness's file.
# Tool names are NOT translated, so each block uses its own harness's names.
# Set a block to `false` to skip generating the agent for that harness.
claude:
  tools: Read, Grep, Glob
  model: inherit
copilot:
  tools: [read, search]
codex:
  model_reasoning_effort: high
---

Instructions for the agent, in Markdown. This body is shared by all harnesses,
so keep it harness-neutral: describe the role, its inputs, and the output it must produce.
```

Check field names against each harness's current docs. The generator does not validate harness-specific keys.

- Claude Code subagents: `name`, `description`, `tools`, `model`, …
- Copilot custom agents: `name`, `description`, `tools`, `model`, …
- Codex custom agents: `name`, `description`, `developer_instructions` (required), plus optional config keys such as `model` and `sandbox_mode`.

Never edit the generated files. They carry a "generated" header and are overwritten or deleted by the sync.

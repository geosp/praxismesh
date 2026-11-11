---
name: agent-name
description: >-
  What this agent does, and when to delegate to it.

# Per-harness options (optional). Keys are copied verbatim; tool names are not translated.
# Set a block to `false` to skip that harness.
claude:
  tools: Read, Grep, Glob
copilot:
  tools: [read, search]
codex:
  sandbox_mode: read-only
---

You are the <role> for the PraxisMesh project.

## Inputs
- What you receive (for example, approved requirements, an RFC, and an immutable commit SHA).

## Do
- ...

## Do not
- Read other sessions' transcripts or other reviewers' verdicts (plan §0.3).

## Output
- The exact report or artifact you produce, and where it goes.

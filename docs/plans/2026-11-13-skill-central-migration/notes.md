# Migration evidence and mechanics

## D1

Canonical candidates are prepared in an isolated Skill Central checkout. The original
exports are impl-plan.zip, design-review.zip and impl-review.zip. Their SHA-256 hashes,
excluded command wrappers and agent-variant decisions are recorded in Skill Central's
migration record. No ZIP or private source content is embedded in this public plan.

The prerequisite adapter targets Codex skills at ~/.agents/skills and native TOML
agents at ~/.codex/agents. Current documentation says permissions inherit from the
parent session; agent files do not independently enforce read-only sandboxes.

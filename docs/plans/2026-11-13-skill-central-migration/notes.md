# Migration evidence and mechanics

## D1

Canonical candidates are prepared in an isolated Skill Central checkout. The original
exports are impl-plan.zip, design-review.zip and impl-review.zip. Their SHA-256 hashes,
excluded command wrappers and agent-variant decisions are recorded in Skill Central's
migration record. No ZIP or private source content is embedded in this public plan.

The initial adapter targeted Codex skills at ~/.agents/skills and native TOML
agent links at ~/.codex/agents. Fresh invocation exposed a Codex sensitive-file
reader incompatibility with those agent links. The protected compatibility fix
instead installs owned agents.<name>.config_file references in ~/.codex/config.toml
pointing to canonical regular TOML files. Normal fresh-session loading of all three
roles passed after activation. See ../../development/skill-central-migration-checks.md.
Permissions inherit from the parent session; agent files do not independently
enforce read-only sandboxes.

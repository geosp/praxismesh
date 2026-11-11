# Skills

Each skill is a folder here: `<domain>-<capability>/SKILL.md`, plus optional `scripts/`, `references/` and `assets/`.
Names follow the [skill naming convention](../README.md#skill-naming-convention). Start from [../templates/skill/SKILL.md](../templates/skill/SKILL.md).

This folder is read by Codex directly and by Claude Code and GitHub Copilot through the `.claude/skills` symlink.

| Skill | Purpose |
|---|---|
| [docs-design](docs-design/SKILL.md) | Write a full RFC, short RFC or ADR on a draft PR (provisional) |
| [review-design](review-design/SKILL.md) | Independent design review of an OpenSpec change and its RFC; informal or phase-gate mode |
| [review-implementation](review-implementation/SKILL.md) | Independent review of code and tests against the change's contract; informal or phase-gate mode |
| [verify-phase](verify-phase/SKILL.md) | Independent verification: reproduce acceptance tests and demo, check as-built claims, in a disposable checkout of the frozen commit |
| [github-pr](github-pr/SKILL.md) | Prepare and open a pull request linked to a GitHub issue |
| `openspec-*` (6) | OpenSpec workflows: explore, propose, apply-change, update-change, sync-specs, archive-change. **Generated** by OpenSpec; do not edit (see below) |

## OpenSpec skills (generated)

The `openspec-*` folders and `.openspec-target` are written by `openspec init --tools agents` / `openspec update` (OpenSpec 1.17.0, delivery `skills`, profile `core`). Do not edit them by hand; `openspec update` overwrites them. They need the `openspec` CLI on PATH.

Use only the `agents` target. Do not run `openspec init` with `claude` or `codex`: through the `.claude/skills` symlink both write the same files, and each `openspec update` then rewrites them with alternating wording. Do not add `github-copilot` either; it creates a duplicate set in `.github/skills/` (Copilot already reads `.claude/skills`). `openspec update` prints "Detected new tool: GitHub Copilot" because `.github/` exists; ignore it.

The specialist review skills are still pending under plan §0.3.

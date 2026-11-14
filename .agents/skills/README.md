# Skills

Project-owned skills live here and are read by Codex directly and by Claude Code
and Copilot through `.claude/skills -> ../.agents/skills`.

| Skill | Purpose |
| --- | --- |
| [docs-design](docs-design/SKILL.md) | Standalone RFCs and durable ADRs |
| [verify-phase](verify-phase/SKILL.md) | Independent executable verification and demo evidence |
| [github-pr](github-pr/SKILL.md) | Prepare issue-linked pull requests |

The reusable `impl-plan`, `design-review` and `impl-review` suite and reviewer
agents are maintained and installed from Skill Central. Do not copy them here.
See [planning and installation](../../docs/development/planning.md) and
[phase-gate rules](../../docs/reviews/README.md).

## OpenSpec skills (generated)

Historical note: OpenSpec 1.17.0 generated the former `openspec-*` skills using the
shared agents target. Revision 2.12 retires this workflow and removes those
folders and target metadata. Do not run OpenSpec init/update to recreate them.
Historical specs and archives remain under openspec/.

# Planning and review with Skill Central

New work uses the owner-maintained Skill Central `implementation-planning` suite:
`impl-plan`, `design-review`, and `impl-review`. Its canonical skills, helper and
reviewer agents are external to this public repository. Keep project-specific
skills (`verify-phase`, `docs-design`, `github-pr`) here. Never duplicate the suite
in `.agents/skills` or generate its reviewer agents here.

## Installation and cutover

This document is a prepared cutover candidate. Merge it only after Skill Central's
Codex/intake prerequisites and suite changes pass protected review and merge, and
fresh-session discovery is confirmed. Record the actual protected suite revision
in the PR before merging; a feature-branch candidate is not an activation source.

From your approved Skill Central checkout on protected main:

```bash
uv run skill-central install --harness all --dry-run
uv run skill-central install --harness all
uv run skill-central doctor --harness all
```

The installer owns individual links and refuses unmanaged destinations. Codex
skills use `~/.agents/skills`, agents use `~/.codex/agents/*.toml`; Claude/Copilot
have their own user discovery roots. Preserve and explicitly quarantine conflicting
legacy user paths before activation; never force or overwrite them. Restart each
harness and confirm discovery and a sample plan/review on Linux and macOS. Keep
original ZIP exports and old evidence; cleanup needs separate authorization.

Contributors without the private suite can author the same Markdown contracts and
run every public CI check. The suite automates the workflow; it is not a runtime
or CI dependency. New tooling must not fetch the private repository or require
private credentials for fork CI.

The protected suite revision `5cfdf5f4d25769dcffaecd47c40f2c87c1e167cc` is now
installed locally; doctor and repeat-install checks pass. See the
[activation evidence](skill-central-migration-checks.md#local-activation-2026-11-14).
Fresh Linux tests pass for Codex and Claude planning-skill invocation, but Codex
reviewer loading fails through the installed symlink. A direct canonical-file
reference worked only in a session-level diagnostic. A protected installer fix,
remaining harness invocation checks, user Linux/macOS confirmation and independent
cutover review remain merge prerequisites; doctor alone does not satisfy them.

## Authoritative documents

`PROJECT_PLAN.md` governs scope, sequencing, constraints and phase gates. New
approved `docs/plans/YYYY-MM-DD-<slug>/plan.md` contracts define requirements,
scenarios and design decisions; their phase files contain tasks and Verify steps.
Link requirements to project-plan sections and identify any existing guarantees
being amended. The [incorporated baseline](../requirements/baseline.md) preserves
Phase 0/1 guarantees. Existing OpenSpec specs and changes are historical records;
do not run OpenSpec init/update or author new changes there.

Use `docs/adr/` for durable decisions, following existing numbering. Review
accepted ADRs before making changes; supersede through a new ADR without editing
old decisions. Separate phase RFCs are optional: the implementation plan carries
requirements and design. Existing RFCs and review evidence remain unchanged.

## PraxisMesh phase gates

Follow [the review protocol](../reviews/README.md), which overrides the shared
skills' informal defaults. Review committed contracts and immutable code revisions
in separate fresh sessions. Give reviewers no implementer transcript or prior
verdicts. Implementation review uses `git diff <base>..<code_sha>`, never the
working tree. Reviewers report findings and do not fix their own work.

Run `verify-phase` after implementation review; reproduce acceptance and the live
demo and check cumulative as-built claims. The light/full tier separation in
project plan §7.0 remains in force. Do not tick phase tasks until their tests,
acceptance and demo pass. Invoke reviews and verification explicitly while tasks
remain unticked, then record closure and resume the shared lifecycle. A helper's
PASS only checks plan state, not execution evidence or authorization to merge.

The coordinator checks evidence SHA linkage and required checks on the latest
head before closure. No missing reviewer, blocked verification or unrun demo
counts as success. The owner merges; agents do not change protection or secrets.

## Public validation

```bash
uv run .github/scripts/check_plans.py
uv run .agents/sync_agents.py --check
```

The project validator checks local requirements, scenarios, task verification,
coverage and completion evidence references without executing imported skills.
The full shared helper remains in Skill Central and can additionally check a plan
through `uv run <Skill Central>/skills/impl-plan/plan-tool.py check <plan>`.
CI cannot prove review independence or a demo outcome; the coordinator verifies
those claims against the saved evidence.

Codex discovery paths and inherited agent permissions were checked against the
[official skills documentation](https://developers.openai.com/codex/skills) and
[official subagent documentation](https://developers.openai.com/codex/subagents)
on 2026-11-13. Live activation checks remain pending.

[Candidate validation and remaining gates](skill-central-migration-checks.md) records
what was actually tested and what remains before activation.

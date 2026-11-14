# Skill Central cutover candidate checks

- Date: 2026-11-13
- Status: prepared candidate; not activated and not a phase-gate verdict.
- Owner approved migration scope and retiring active OpenSpec.
- PraxisMesh baseline: the tree delivered by PR #57, main bfa79d1.

## Executed checks

| Check | Result |
| --- | --- |
| uv sync --locked | Passed |
| Ruff check and format check | Passed; 229 Python files formatted |
| mypy | Passed; 90 source files |
| uv run pytest | 161 passed, 91 integration tests deselected by normal configuration |
| Focused plan/CI/tool-pin/agent-generator tests | 87 passed |
| Project plan validator | One plan, zero errors |
| Skill Central plan helper on migration plan | Zero errors and warnings |
| Generated local agents | Three files current; obsolete reviewer outputs pruned through generator |
| actionlint 1.7.12 | Passed |
| Lychee 0.24.2, CI offline/fragments options | Passed; no broken links |
| Gitleaks 8.30.1 on candidate diff | Passed before candidate commit |
| Historical specs, archives, Phase 0/1 evidence and phase RFC contents | Unchanged |

The sandboxed full test run stalled at Temporal's native replay test and was
interrupted. The full suite then passed outside that sandbox. Dependency downloads
used temporary caches; source checkouts and personal installation paths were not
modified by validation. No integration/model demo was needed or claimed for this
development-tooling candidate; production runtime files are unchanged.

## External prerequisites

Skill Central has two prepared branches: Codex/bundled-intake prerequisites and the
implementation-planning suite. Its full candidate passed 148 tests, Ruff,
structural/catalog checks, three skill validators and staged security checks.
An independent informal forward test passed 21 lifecycle checks; reported wording
and ZIP ambiguity issues were corrected with regression coverage. This is not an
independent PraxisMesh phase review or live cross-harness verification.

## Remaining gates

Create/link tracking issues and publish draft PRs through the normal workflow.
Protected CI and owner merge must complete for Skill Central prerequisites and
suite before activation. Verify doctor and discovery/invocation in fresh supported
Linux/macOS harness sessions, record the actual protected suite revision in the
cutover PR, and obtain independent cutover review before the owner merges it.
During candidate preparation, user installation links, original ZIPs, quarantine
directories and repository settings were unchanged. No merges were performed by
the implementation session. The later activation state is recorded below.


## Local activation, 2026-11-14

The owner merged Skill Central PR #54 as
`58b5ff10cf6c8f718c9e9c9a0cbc404285dc681b` and PR #55 as
`5cfdf5f4d25769dcffaecd47c40f2c87c1e167cc`. The latter is the protected suite
revision installed locally. The active Skill Central checkout is clean on main.

The active manager predated Codex TOML validation, so the update was executed
using management code from a detached checkout of the protected merged revision.
It validated the candidate before fast-forwarding the active checkout and recorded
the prior revision. Its post-update doctor correctly reported missing new links;
installation resolved those findings without overwriting existing entries.

- Installation preview: 44 new owned links, 60 existing links unchanged; no conflicts.
- Installation: completed for Codex, Claude Code, Copilot and Antigravity.
- Doctor: passed for all four harnesses.
- Repeat dry run: 104 unchanged managed links, zero pending changes.
- Active repository validation and generated catalog freshness: passed.
- Installed helper on a temporary copy of the migration plan: zero errors/warnings;
  status correctly reports a draft with zero of three phase tasks completed.
- Copilot's skill registry lists impl-plan, design-review and impl-review.
- Antigravity's agent registry lists design-reader, design-reviewer and impl-reviewer.
- Versions: Codex 0.169.0-alpha.11.1, Claude Code 2.1.311, Copilot 1.0.110,
  Antigravity 1.5.8.

Original ZIPs were retained. No quarantine, source deletion, repository-setting
change or merge was performed by this session. No private installation-state or
session-log files are included in this record.

Fresh model-backed invocation checks remain pending explicit authorization. Registry
listing, symlink health and helper execution do not establish that an agent invoked
a skill correctly. User confirmation from fresh Linux/macOS harness sessions and
independent cutover review remain required before the owner merges PraxisMesh #59.

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

At installation time, fresh model-backed invocation was pending explicit
authorization. The owner subsequently authorized these checks; results follow.
Registry listing, symlink health and helper execution alone do not establish
correct skill invocation or reviewer loading.


## Fresh Linux session checks, 2026-11-14

The owner explicitly authorized sending the installed skill instructions and temporary
migration plan to the four model services. All sessions used the same temporary plan;
its files remained byte-for-byte unchanged. No reviewer verdict or task completion was
claimed from these installation smoke tests. Raw session logs are not committed.

| Harness | Observed result | Verdict |
| --- | --- | --- |
| Codex | Discovered impl-plan normally, ran its helper, reported the expected title, draft state, 0/3 phases and tasks, and design-review next step; both review skills were available | Planning skill passed |
| Claude Code | Invoked /impl-plan status, ran the helper, and reported the same expected state and next step without edits | Planning skill passed |
| Copilot | Registry discovery passed, but model invocation exited with No supported model available | Invocation blocked by model configuration/availability |
| Antigravity | Skill expansion reached a Bash helper call; headless command approval was denied, so the response was empty; a session-only narrow allow-rule retry was also denied | Invocation incomplete; not passed |

### Codex reviewer-agent incompatibility

Normal custom design-reader invocation failed with agent type currently not
available. The CLI diagnostic was Symbolic link loop (os error 40) while applying
the role configuration. No built-in agent was substituted.

This is consistent with the current official Codex implementation:
[role loading](https://github.com/openai/codex/blob/main/codex-rs/core/src/agent/role.rs)
uses [a sensitive-file reader](https://github.com/openai/codex/blob/main/codex-rs/exec-server/src/regular_file.rs)
that refuses a symlink at the final path component. The native TOML is valid;
owned symlink delivery is incompatible with this observed Codex build.

A separate fresh session with a session-only agents.design-reader.config_file
override pointing directly at the canonical regular file succeeded: design-reader
read only the specified plan and returned its summary. No installed link or
persistent user configuration was changed. This is a successful diagnostic of a
possible direct-reference approach, not a completed installer fix.

Before cutover, correct and independently review Codex agent delivery through the
protected Skill Central workflow, then activate and rerun normal reviewer loading.
The public PraxisMesh cutover must remain draft. Copilot and Antigravity invocation,
user Linux/macOS confirmation, and independent cutover review also remain pending.
Doctor passing is insufficient to claim those capabilities work.


## Post-merge Codex activation, 2026-11-14

The owner merged Skill Central PR #56. The managed updater advanced the actual
canonical checkout to protected main revision
`ec3b7d71ebdb08556c0d5b4d8c988305a89e37d9`, then the merged installer migrated
exactly three owned Codex reviewer links to owned `config_file` references in the
normal user configuration. Canonical sources and original ZIPs remain preserved.
Unrelated configuration bytes and file mode were compared before and after and
remained unchanged. Doctor passed for all four harnesses; a repeat preview showed
104 unchanged entries and zero pending changes.

A fresh, ephemeral Codex session using ordinary installed user configuration,
with no session-level role overrides, successfully invoked `design-reader`,
`design-reviewer` and `impl-reviewer`. Each received only the temporary migration
plan and returned an accurate one-sentence summary in a fresh context. No built-in
role was substituted. This resolves the earlier Codex loading blocker; this was
an installation smoke test, not an independent cutover review.

The PraxisMesh cutover remains draft pending independent cutover review, successful
Copilot and Antigravity invocation, and owner confirmation in fresh Linux/macOS
sessions. The earlier failure records above describe the superseded installation
and remain as historical evidence.


## Owner cross-platform confirmation, 2026-11-14

Asked whether the installed planning and review skills had been tested in fresh
Linux and macOS sessions, including the outstanding Copilot and Antigravity
invocations, the owner replied: “All passed.” This records owner confirmation for
the supported harness/platform matrix. It does not replace the earlier observed
Linux results or claim those headless failures were reproduced as passing here.
Independent cutover review and latest-head CI remain required before owner merge.


## Independent cutover reviews and corrective checks, 2026-11-14

Fresh read-only sessions completed the three-lens implementation review at
`5da23105ed20156e33b0a225dc3d3876218e5ddb` and two design-review rounds, ending in
PASS at `96aa6670531251509bb53a70c229c57e0eb922c8`. All required reviewers completed;
reports disclose automatic project-instruction visibility. The reports and
resolutions are linked from the migration plan's reviews.md.

The implementation Nit correction rejects completed parent plans with unfinished
phases. Both regression cases failed before the fix, passed afterward, and failed
again when the fix was removed. The full suite passed: 165 tests, 91 integration
cases deselected by normal configuration. Ruff, formatting, mypy, public/shared
plan checks and offline links passed. No later runtime or validator code changed;
subsequent changes record evidence and clarify the reviewed documentation.

Design review identified ADR-0003's old Phase 4A artifact requirement. Proposed
ADR-0004 reconciles it while carrying every other ADR-0003 decision and required
demo forward. ADR-0003 remains unchanged. ADR-0004 requires owner acceptance with
the cutover; the review does not accept it for the owner. Migration task boxes
remain unticked and no runtime phase closure is claimed. Require CI on the final
PR head and owner merge approval.

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
No user installation links, original ZIPs, quarantine directories or repository
settings were changed. No merges were performed.

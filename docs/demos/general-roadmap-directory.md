# Roadmap navigation maintenance walkthrough

Date: 2026-11-14. Tested implementation:
`64cc13657ca601a4b225f24444f28869fffba519`.
Contract: [rename plan](../plans/2026-11-14-roadmap-directory/plan.md), phase 01.
Environment: Linux, Python 3.11.17; Gitleaks 8.30.1, actionlint 1.7.12,
Lychee 0.24.2. Pinned tool versions match the workflow. This is documentation and
CI maintenance evidence recorded by the implementer, not runtime phase closure
or an independently executed verify-phase verdict.

## Prerequisites and entry points

Use a checkout at the tested commit, `uv sync --locked`, the approved installed
planning helper, and the CI-pinned scanner/workflow/link binaries on PATH.
The contract's [verification procedure](../plans/2026-11-14-roadmap-directory/notes.md#verification-procedure)
defines commands and preservation comparisons. No model, credential, GPU or
running application service is needed for the navigation/canary walkthrough.

## Observed navigation

| Step | Action | Expected | Observed | Result |
| --- | --- | --- | --- | --- |
| 1 | Read PROJECT_PLAN.md and follow its Phase 2 index link | New roadmap phase exists | docs/roadmap/phases/phase-2.md exists | pass |
| 2 | Follow the phase's Read first links | Architecture/schema guidance remains available | Every local Read first destination resolves | pass |
| 3 | Open the linked schema guidance and check anchors | Schema sections remain intact | Schema file is byte-identical to baseline; offline fragment checks pass | pass |
| 4 | Open docs/README.md and follow roadmap/ and plans/ | Separate locations and roles | Both directories exist; docs/plan is absent | pass |
| 5 | Run installed helper list docs/plans --all | Only implementation contracts discovered | Two contracts; no roadmap file | pass |

Navigation was checked by reading Markdown and resolving local destinations;
no browser UI or running application behavior is claimed.

## Preservation and failure checks

| Check | Observed | Result |
| --- | --- | --- |
| Baseline-byte reconstruction using the maintenance manifest | 147 baseline historical files compared; six records contain exactly 15 inventoried destination edits; every other byte unchanged | pass |
| Roadmap inventory/content | All 19 counterparts exist; 18 byte-identical; decision-log differs only by the single approved organization entry | pass |
| Scanner configuration comparison | Same defaults, target rule, AND condition and line expression; only exact new schema path added | pass |
| Execute secrets-job canary with pinned scanner | Approved lines suppressed at both schema paths; exact three positive file/line/rule locations detected | pass |
| Failure: temporary configuration omits new schema path | Canary rejected unexpected findings | pass |
| Failure: temporary configuration changes AND to OR | Canary rejected missing required findings | pass |
| Recovery: execute with intended configuration | Canary passed again | pass |

The workflow canary was executed directly from its YAML run body, adapting only
its pinned binary location to the local installed path and RUNNER_TEMP to a new
temporary directory. Mutations used temporary configuration copies only; the
working configuration was not weakened. Fixture directories were deleted after
execution, and dummy values/raw scanner output were not committed.

## Repository checks

- `uv sync --locked`: passed.
- Ruff check and format check: passed, 240 formatted files.
- `uv run mypy`: passed, 90 source files.
- `uv run pytest`: 165 passed, 91 normally deselected, 32.12 seconds.
- Generated agents: three files current.
- Public/shared plan checks: two plans validated; rename helper zero errors/warnings.
- actionlint, offline links/fragments and whitespace: passed.
- File-aware Gitleaks HEAD-lineage scan: passed, including the committed rename.

A default scan of all local refs reports a pre-existing issue in an unmerged
local-only commit outside the baseline's ancestry; the baseline configuration
reports the same issue. Reachable baseline and candidate-lineage scans passed.
A pathless stdin diff scan also raised warnings; it cannot apply exact file-path
exceptions, so no PASS is claimed for that invocation. No new suppression was
added for either observation. See the contract notes for the distinction.

## Delivery status

Independent implementation review is saved separately. Latest-head CI and final
owner delivery approval remain required. Task boxes stay open until the
coordinator's delivery checks pass. This walkthrough starts no runtime phase and
changes no completed phase evidence beyond authorized navigation destinations.

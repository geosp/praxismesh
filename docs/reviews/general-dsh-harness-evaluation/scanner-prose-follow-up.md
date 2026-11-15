# Targeted scanner follow-up

- mode: targeted-scanner-follow-up
- session: fresh
- date: 2026-11-14
- code_sha: `295d5d30566a8007319c55face1756ecea94fd38`
- diff_base: `c10d609409e83ab9e0fbbc137e45329d4cf4c796`
- verdict: **pass** for the specified scanner/CI scope
- checkout: `/tmp/praxismesh-dsh-prose-scanner-check`

This is an explicitly targeted affected-scope review and execution check, not a third full implementation review or a runtime rerun. AGENTS.md and docs/reviews/README.md were read. No implementer transcript or earlier review verdict was used. The immutable acceptance report was read programmatically only to extract its line beginning `Root checks passed:` as scanner fixture data; its claims were not evaluated or adopted. No SDK, Docker, model, service, or deployment execution was performed. This report grants no phase closure, adoption approval, waiver, or change to the SHA of earlier evidence.

## Code-review findings

No open blocker, major, or minor findings in this delta.

1. `.gitleaks.toml` preserves `[extend] useDefault = true` and both pre-existing schema and artifact allowlists. The new entry targets only `generic-api-key`, combines the anchored exact report path and line regex with `condition = "AND"`, and applies the regex to `line`. Its regex spells out the complete known statement, escapes punctuation, anchors both ends, and permits only leading/trailing whitespace around that statement. Arbitrary changed prose or appended material is outside that exception.
2. `.github/scripts/check_gitleaks_artifact_allowlist.py` preserves artifact fixtures and adds known report prose, changed prose, separate and appended generated credentials, a sibling report path, and an unrelated path. It compares the exact set of file/line/rule findings, so extra detections and missing detections both fail. The scanner runs with redaction, a timeout, captured output, and temporary fixture cleanup. The report is used only as a fixture source. The independent probes below additionally exercised whitespace, same-basename and extension paths, and a second scanner rule.
3. `.github/workflows/ci.yml` changes only the canary step's descriptive name. Its invocation remains `python3 .github/scripts/check_gitleaks_artifact_allowlist.py --gitleaks ./gitleaks` after the pinned scanner installation; the existing schema canary and commit scan remain active. Actionlint accepted the workflow.

## Execution evidence

All commands ran with the checkout above as working directory. `G` below means `/tmp/praxismesh-migration-tools/gitleaks`; `R` means `/tmp/praxismesh-dsh-verify-65d03f0/.venv/bin/ruff`; `M` means `/tmp/praxismesh-dsh-verify-65d03f0/.venv/bin/mypy`. These external paths supplied executable tools only; their checkouts were not modified. Gitleaks was `8.30.1`, actionlint `1.7.12`, Ruff `0.17.4`. Initial Python was `3.14.10`; the production canary was also run with `3.11.17`.

| Exact command or saved reproducible step | Expected | Observed output/result | Result |
| --- | --- | --- | --- |
| `git rev-parse HEAD`; `git status --porcelain -- .gitleaks.toml .github/scripts/check_gitleaks_artifact_allowlist.py .github/workflows/ci.yml` | Frozen revision; clean reviewed files | `295d5d30566a8007319c55face1756ecea94fd38`; status output empty | pass |
| `python3 .github/scripts/check_gitleaks_artifact_allowlist.py --gitleaks /tmp/praxismesh-migration-tools/gitleaks` | Known metadata/prose allowed; changed lines, separate/appended keys, sibling/unrelated paths detected | `scoped canaries passed: exact metadata/prose suppressed; changed lines, added keys and other paths detected` (exit 0; `canary.log`) | pass |
| `TMPDIR="$PWD/.verify" /home/geo/.local/bin/python3.11 .github/scripts/check_gitleaks_artifact_allowlist.py --gitleaks /tmp/praxismesh-migration-tools/gitleaks` | Same behavior on Python floor | Same success line; `python311_canary_exit=0` (`canary-py311.log`) | pass |
| `python3 .verify/exercise_scanner.py` | Valid TOML, active defaults, rule/path/line scoping, Python 3.11 grammar | `syntax/config passed: Python 3.11 grammar, valid TOML, defaults active, generic-api-key AND exact path AND full-line match` | pass |
| Same saved script: scratch config with final prose allowlist removed | Canary fails on extra detections | `missing-prose: canary exit=1; artifact canary failed: exact path/line/digest restrictions changed` | pass |
| Same saved script: scratch final allowlist uses OR | Canary fails on suppressed required detections | `broadened-or: canary exit=1; artifact canary failed: exact path/line/digest restrictions changed` | pass |
| Same saved script: scratch final line regex loses start/end anchors | Canary fails on broadened line matching | `broadened-line: canary exit=1; artifact canary failed: exact path/line/digest restrictions changed` | pass |
| Same saved script: scratch `useDefault = false` | Canary fails when default detection is absent | `missing-defaults: canary exit=1; artifact canary failed: scanner did not report expected findings` | pass |
| Same saved script: independent boundary fixture scanned with production config | Whitespace allowed; prefixes, suffixes, changed prose, same basename elsewhere and `.bak` suffix detected | `additional boundaries passed: whitespace suppressed; prefix/suffix/changed prose and same-basename/extension paths detected (5 expected findings)` | pass |
| Same saved script: added synthetic independent rule in scratch config | Other rules still detect otherwise allowlisted line | `rule boundary passed: synthetic independent rule remains active on allowlisted whitespace statement` | pass |
| `/tmp/praxismesh-dsh-verify-65d03f0/.venv/bin/python .verify/run_schema_canary.py` | Existing CI schema canary remains effective | `schema CI canary exit=0`; `canary passed: both schema paths bounded; ordinary file detected` | pass |
| `git merge-base main 295d5d30566a8007319c55face1756ecea94fd38` | Resolve exact feature lower bound | `432519c8183fefa176aed6d1fe7de99addd3ad3b` | pass |
| `G git --config .gitleaks.toml --redact --log-opts=295d5d30566a8007319c55face1756ecea94fd38 .` | Complete frozen ancestry has no findings | `62 commits scanned.`; `scanned ~3589668 bytes (3.59 MB)`; `no leaks found`; `ancestry_exit=0` (`ancestry-scan.log`) | pass |
| `G git --config .gitleaks.toml --redact --log-opts=432519c8183fefa176aed6d1fe7de99addd3ad3b..295d5d30566a8007319c55face1756ecea94fd38 .` | Exact frozen feature range has no findings | `18 commits scanned.`; `scanned ~702400 bytes (702.40 KB)`; `no leaks found`; `feature_exit=0` (`feature-scan.log`) | pass |
| `/tmp/praxismesh-migration-tools/actionlint` | Workflow syntax and expressions accepted | Empty diagnostics; `actionlint_exit=0` (`actionlint.log`) | pass |
| `R check --no-cache .github/scripts/check_gitleaks_artifact_allowlist.py` | Changed Python passes lint | `All checks passed!`; `ruff_check_exit=0` (`ruff-check.log`) | pass |
| `R format --check --no-cache .github/scripts/check_gitleaks_artifact_allowlist.py` | Formatting accepted | `1 file already formatted`; `ruff_format_exit=0` (`ruff-format.log`) | pass |
| `M --cache-dir .verify/mypy .github/scripts/check_gitleaks_artifact_allowlist.py` | Changed scanner code type-checks | `Success: no issues found in 1 source file`; `mypy_exit=0` (`mypy.log`) | pass |
| `git diff --check c10d609409e83ab9e0fbbc137e45329d4cf4c796..295d5d30566a8007319c55face1756ecea94fd38` | No diff whitespace errors | Empty diagnostics; `diff_check_exit=0` (`diff-check.log`) | pass |

The two saved Python drivers contain the exact subprocess scanner arguments and assertions. `run_schema_canary.py` extracts and executes the unchanged CI schema-canary shell body with `bash -e`, redirects scanner output into `.verify/schema-canary.log`, and sets temporary runner/tool paths under `.verify`. It does not replace the scanner with a mock. Scanner match text and credential/operator values are not reproduced in this report.

## Source-equality boundary

The supplied independently tested runtime commit is `65d03f0fdb56d8939e99d67156ddea398185a21f`. Equality establishes the boundary for this targeted follow-up; it does not establish or restate any runtime verdict.

Command:

```bash
git diff --exit-code 65d03f0fdb56d8939e99d67156ddea398185a21f HEAD -- src tests spikes infra pyproject.toml uv.lock .agents .claude .codex AGENTS.md CLAUDE.md Makefile .python-version .node-version
```

Observed: empty diff, `runtime_equality_exit=0` (`runtime-equality.log`). Candidate Python, tests, composition/infra, dependency declarations and lock, skill/agent inputs and listed build/version inputs are unchanged. The comprehensive inventory below also establishes that no other non-documentation path changed.

`git diff --name-status 65d03f0fdb56d8939e99d67156ddea398185a21f HEAD` produced exactly:

```text
M .github/scripts/check_gitleaks_artifact_allowlist.py
M .github/workflows/ci.yml
M .gitleaks.toml
A docs/demos/general-dsh-harness-evaluation-01.md
M docs/plans/2026-11-14-dsh-harness-evaluation/reviews.md
A docs/reviews/general-dsh-harness-evaluation/verification-acceptance.md
A docs/reviews/general-dsh-harness-evaluation/verification-as-built.md
A docs/reviews/general-dsh-harness-evaluation/verification.md
M docs/spikes/dsh-harness.md
A docs/spikes/dsh-phase01-verification-evidence.json
```

Saved as `source-inventory.log`. Documentation paths were inventoried, not consumed as prior verdicts. Only the three scanner/CI paths differ outside docs.

All temporary mutations were confined to copies under `.verify/missing-prose`, `.verify/broadened-or`, `.verify/broadened-line`, `.verify/missing-defaults`, and `.verify/second-rule.toml`; no frozen source was mutated, so no source restoration was necessary. Other fixtures, helpers, logs and mypy cache are under `.verify`. The initial stock-canary run used its existing automatically cleaned temporary-directory implementation; subsequent Python 3.11 and mutation runs set TMPDIR under `.verify`.

Final `git status --porcelain --untracked-files=no` was empty and HEAD remained the frozen SHA. No commits, branches, settings, GitHub writes, or user's working-copy changes were made. Shell startup emitted unrelated read-only cache/symlink warnings; all listed checks completed without escalation. No unresolved or blocked checks within this specified scope.

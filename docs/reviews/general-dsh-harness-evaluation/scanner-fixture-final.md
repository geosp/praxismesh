# Final fixture follow-up: PASS

- code_sha: `90fd53058e3045a27a7ebe4cd05222a66acf03a8`
- diff base: `592ff7206a9598b8cb2b537a7a67fdcef9b33392`
- Checkout: `/tmp/praxismesh-dsh-canary-final`; scanner: gitleaks `8.30.1`.
- Scope: only `.github/scripts/check_gitleaks_artifact_allowlist.py` in the stated diff. This is a test-fixture-only affected follow-up, not a full DSH gate, phase closure, adoption decision or waiver.

The seven-line helper diff replaces randomized fixture generation with a deterministic public SHA-256 test vector and adds missing/unexpected `(file, line, rule)` diagnostics. Scanner invocation, return-code validation, expected finding set, observed-set construction and strict set equality are unchanged. Thus the helper change does not broaden allowlisting or weaken detection logic. `.gitleaks.toml` and the entire CI workflow are byte-for-byte unchanged from the diff base. All ten current canary runs detected the expected adversarial locations; both negative mutations were rejected.

Reproduction driver: `python3 .verify/run-checks.scratch`. It sets `TMPDIR` to the checkout's `.verify` and disables Python bytecode writes. Exact commands and redacted outcomes follow; empty git output is represented explicitly. The history scan captures scanner output in memory and retains only count/summary lines, without credential, endpoint or match text.

| Check / exact command or step | Expected | Observed |
|---|---|---|
| frozen HEAD: `git rev-parse HEAD` | Exit 0 | Exit 0; 90fd53058e3045a27a7ebe4cd05222a66acf03a8 |
| diff base: `git rev-parse 592ff72` | Exit 0 | Exit 0; 592ff7206a9598b8cb2b537a7a67fdcef9b33392 |
| config and CI unchanged: `git diff --exit-code 592ff72..90fd530 -- .gitleaks.toml .github/workflows/ci.yml` | Exit 0; empty diff | Exit 0; (no output) |
| Canary, 10 consecutive executions: `python3 .github/scripts/check_gitleaks_artifact_allowlist.py --gitleaks /tmp/praxismesh-migration-tools/gitleaks` | Exit 0; exact approved lines suppressed, all 10 expected locations detected | Exit 0; scoped canaries passed: exact metadata/prose suppressed; changed lines, added keys and other paths detected |
| missing-prose-rule: `python3 /tmp/praxismesh-dsh-canary-final/.verify/missing-prose-rule/.github/scripts/helper.scratch --gitleaks /tmp/praxismesh-migration-tools/gitleaks` | Exit 1; reject altered allowlist and print location-only diagnostics | Exit 1; missing finding locations: []<br>unexpected finding locations: [('docs/reviews/general-dsh-harness-evaluation/verification-acceptance.md', 1, 'generic-api-key'), ('docs/reviews/general-dsh-harness-evaluation/verification-acceptance.md', 6, 'generic-api-key')]<br>artifact canary failed: exact path/line/digest restrictions changed |
| OR: `python3 /tmp/praxismesh-dsh-canary-final/.verify/OR/.github/scripts/helper.scratch --gitleaks /tmp/praxismesh-migration-tools/gitleaks` | Exit 1; reject altered allowlist and print location-only diagnostics | Exit 1; missing finding locations: [('docs/reviews/general-dsh-harness-evaluation/notes.md', 1, 'generic-api-key'), ('docs/reviews/general-dsh-harness-evaluation/verification-acceptance.md', 2, 'generic-api-key'), ('docs/reviews/general-dsh-harness-evaluation/verification-acceptance.md', 3, 'generic-api-key'), ('docs/reviews/general-dsh-harness-evaluation/verification-acceptance.md', 4, 'generic-api-key'), ('other/notes.md', 2, 'generic-api-key')]<br>unexpected finding locations: []<br>artifact canary failed: exact path/line/digest restrictions changed |
| Ruff check: `/tmp/praxismesh-dsh-verify-aef2214/.venv/bin/ruff check --no-cache .` | Exit 0 | Exit 0; All checks passed! |
| Ruff format: `/tmp/praxismesh-dsh-verify-aef2214/.venv/bin/ruff format --check --no-cache .` | Exit 0 | Exit 0; 265 files already formatted |
| targeted mypy: `/tmp/praxismesh-dsh-verify-aef2214/.venv/bin/mypy --cache-dir /tmp/praxismesh-dsh-canary-final/.verify/mypy-cache .github/scripts/check_gitleaks_artifact_allowlist.py` | Exit 0 | Exit 0; Success: no issues found in 1 source file |
| feature-history scan: `/tmp/praxismesh-migration-tools/gitleaks git --config .gitleaks.toml --redact --log-opts=432519c8183fefa176aed6d1fe7de99addd3ad3b..90fd53058e3045a27a7ebe4cd05222a66acf03a8 .` | Exit 0; no leaks | Exit 0; 10:13PM INF 20 commits scanned.<br>10:13PM INF scanned ~715145 bytes (715.15 KB) in 129ms<br>10:13PM INF no leaks found |
| source unchanged: `git diff --exit-code HEAD` | Exit 0 | Exit 0; (no output) |

Negative checks create scratch copies under `.verify/missing-prose-rule` and `.verify/OR`, with unchanged helper contents saved as `.github/scripts/helper.scratch` so broad lint does not treat the copies as Python source. They copy the artifact and programmatically extract only the exact `Root checks passed:` statement as fixture data; no report verdict or other earlier evidence is consulted. The missing-rule copy removes only the final prose allowlist block. The OR copy changes only that block's `condition = "AND"` to `condition = "OR"`. Both modified configs remain under `.verify`; frozen source was never changed, so no source restoration was necessary.

The missing-rule mutation reports unexpected findings at report lines 1 and 6; the OR mutation reports missing findings at report lines 2, 3 and 4, the sibling report path and the other path. Both diagnostic directions identify only file, line and rule. Raw structured command evidence is in `.verify/results.json`.

No unresolved issue or blocked check remains within this narrow scope. No SDK, Docker, models, production services, settings, branches or commits were changed.

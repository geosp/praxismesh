# DSH evaluation Phase 01 demo evidence

- Scope: isolated spike Phase 01 for issue #62; not runtime Phase 1 or an adoption decision.
- code_sha = docs_sha = `aef22144d3e2a48af13cf921774ef6745e971af7`.
- Checkout: `/tmp/praxismesh-dsh-verify-aef2214`; fresh independent verification.
- Reproduction: `spikes/dsh-harness/README.md`; contract `docs/plans/2026-11-14-dsh-harness-evaluation/phases/01-controlled-runtime.md`.
- Commit: https://github.com/geosp/praxismesh/commit/aef22144d3e2a48af13cf921774ef6745e971af7 ; PR: https://github.com/geosp/praxismesh/pull/63 .
- Environment: Linux x86_64, glibc 2.43, Python 3.11.17, uv 0.13.5, Docker 29.9.3; gitleaks 8.30.1, actionlint 1.7.12, lychee 0.24.2.
- SDK/runtime: pinned 0.2.2rc2; container base `python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`.
- Built image: `sha256:c14bb74bdc355e1e9b765c380b63e9b99b8fb45ec53e78fb691f6c58e3c0bbc3`.

Only `local` uses the real configured private model. The other cases execute the real SDK/runtime with scripted responses and establish control behavior only. No functional probe was retried. No candidate module/native binary was executed on the host. The operator's noncredential URL was loaded into `VLLM_BASE_URL` without printing its value; no credential, deployment .env or populated home was copied.

## Exact setup, checks and observed commands


README expectation: "Expected outcome: exit 0 and a JSON record with observed boundary requests, tool-body entries and `container_absent: true`." Startup has no model requests; catalog is one request. Root checks expect exit 0. Canary negative checks expect detection. Exact command and original output are preserved below.

| Check | Exact command | Expected | Observed quote | Exit | Status | Log |
| --- | --- | --- | --- | --- | --- | --- |
| root-sync | `uv sync --locked` | exit 0 | `  cause: error resolving DNS /   cause: failed to lookup address information: Temporary failure in name resolution / hint: `attrs` (v26.1.0) was included because `praxismesh` (v0.0.0) depends on `mcp` (v2.3.0) which depends on `jsonschema` (v4.26.0) which depends on `attrs`` | 2 | BLOCKED (sandbox DNS; prerequisite retry recorded) | .verify/acceptance-logs/root-sync.log |
| isolated-sync | `uv sync --project spikes/dsh-harness --locked --python 3.11` | exit 0 | ` + pyyaml==6.0.3 /  + typing-extensions==4.16.0 /  + typing-inspection==0.4.5` | 0 | PASS | .verify/acceptance-logs/isolated-sync.log |
| preflight | `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/preflight.py` | exit 0 | `  "composition_sha256": "8609f86ba37530e145f9e8efe8103748ed9bc2856d213f83bcb945fcf18e8dad", /   "environment_sha256": "c581df47358cb4972ea951c6ffe715b5d0218a702c5c9311d93d9ab47f2fa421" / }` | 0 | PASS | .verify/acceptance-logs/preflight.log |
| docker-pull | `docker pull python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39` | exit 0 | `Digest: sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39 / Status: Image is up to date for python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39 / docker.io/library/python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39` | 0 | PASS | .verify/acceptance-logs/docker-pull.log |
| isolated-tests | `spikes/dsh-harness/.venv/bin/python -m pytest -c spikes/dsh-harness/pyproject.toml spikes/dsh-harness/test_probe.py spikes/dsh-harness/test_corrections.py spikes/dsh-harness/test_final_corrections.py -q` | exit 0 | `FAILED spikes/dsh-harness/test_probe.py::test_gateway_rejects_alternate_routes_and_enforces_admission_ceiling / FAILED spikes/dsh-harness/test_corrections.py::test_gateway_shutdown_joins_stalled_provider_handler / 2 failed, 28 passed in 1.25s` | 1 | BLOCKED (sandbox sockets; prerequisite retry recorded) | .verify/acceptance-logs/isolated-tests.log |
| root-sync-network | `uv sync --locked` | exit 0 | ` + urllib3==2.8.0 /  + uvicorn==0.54.0 /  + websockets==16.1.1` | 0 | PASS | .verify/acceptance-logs/root-sync-network.log |
| docker-build | `docker build --network none --build-arg SPIKE_UID="$(id -u)" --build-arg SPIKE_GID="$(id -g)" --iidfile /tmp/praxis-dsh-image-id spikes/dsh-harness` | exit 0 | `#6 naming to moby-dangling@sha256:c14bb74bdc355e1e9b765c380b63e9b99b8fb45ec53e78fb691f6c58e3c0bbc3 done / #6 unpacking to moby-dangling@sha256:c14bb74bdc355e1e9b765c380b63e9b99b8fb45ec53e78fb691f6c58e3c0bbc3 done / #6 DONE 0.0s` | 0 | PASS | .verify/acceptance-logs/docker-build.log |
| isolated-format | `uv run ruff format --check --no-respect-gitignore --exclude '' spikes/dsh-harness/*.py` | exit 0 | `8 files already formatted` | 0 | PASS | .verify/acceptance-logs/isolated-format.log |
| root-format | `uv run ruff format --check .` | exit 0 | `22 + print(Path(rec["log"]).read_text()[-1800:]) /    \| / 1 file would be reformatted, 254 files already formatted` | 1 | INVALID (verifier helper contamination; clean rerun recorded) | .verify/acceptance-logs/root-format.log |
| root-ruff | `uv run ruff check .` | exit 0 | `   \| / Found 4 errors. / [*] 2 fixable with `--fix`.` | 1 | INVALID (verifier helper contamination; clean rerun recorded) | .verify/acceptance-logs/root-ruff.log |
| root-agents | `uv run .agents/sync_agents.py --check` | exit 0 | `Installed 1 package in 2ms / ok: 3 generated agent file(s) up to date` | 0 | PASS | .verify/acceptance-logs/root-agents.log |
| isolated-ruff | `uv run ruff check --no-respect-gitignore --exclude '' spikes/dsh-harness/*.py` | exit 0 | `All checks passed!` | 0 | PASS | .verify/acceptance-logs/isolated-ruff.log |
| root-plans | `uv run .github/scripts/check_plans.py` | exit 0 | `Validated 3 implementation plan(s); 0 error(s)` | 0 | PASS | .verify/acceptance-logs/root-plans.log |
| isolated-tests-network | `spikes/dsh-harness/.venv/bin/python -m pytest -c spikes/dsh-harness/pyproject.toml spikes/dsh-harness/test_probe.py spikes/dsh-harness/test_corrections.py spikes/dsh-harness/test_final_corrections.py -q` | exit 0 | `..............................                                           [100%] / 30 passed in 2.35s` | 0 | PASS | .verify/acceptance-logs/isolated-tests-network.log |
| root-mypy | `uv run mypy` | exit 0 | `Success: no issues found in 90 source files` | 0 | PASS | .verify/acceptance-logs/root-mypy.log |
| root-ruff-clean | `uv run ruff check .` | exit 0 | `All checks passed!` | 0 | PASS | .verify/acceptance-logs/root-ruff-clean.log |
| root-format-clean | `uv run ruff format --check .` | exit 0 | `254 files already formatted` | 0 | PASS | .verify/acceptance-logs/root-format-clean.log |
| startup | `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py startup --image "$(cat /tmp/praxis-dsh-image-id)"` | exit 0 | `{"exit": 0, "cleanup_ok": true, "container_absent": true, "gateway_stopped": null, "grace_met": true}` | 0 | PASS | .verify/acceptance-logs/startup.log |
| actionlint | `/tmp/praxismesh-migration-tools/actionlint -no-color` | exit 0 | `(no output)` | 0 | PASS | .verify/acceptance-logs/actionlint.log |
| links | `/tmp/praxismesh-migration-tools/lychee --offline --no-progress --include-fragments --hidden --exclude-path '\.claude/skills' --exclude-path '\.git/' --exclude-path '\.venv' './**/*.md'` | exit 0 | `🔍 379 Total (in 32ms) 🔗 221 Unique ✅ 309 OK 🚫 0 Errors 👻 70 Excluded` | 0 | PASS | .verify/acceptance-logs/links.log |
| artifact-canary | `python3 .github/scripts/check_gitleaks_artifact_allowlist.py --gitleaks /tmp/praxismesh-migration-tools/gitleaks` | exit 0 | `artifact canary passed: exact digest suppressed; changed digest, added keys and other path detected` | 0 | PASS | .verify/acceptance-logs/artifact-canary.log |
| gitleaks | `/tmp/praxismesh-migration-tools/gitleaks git --config .gitleaks.toml --redact .` | exit 0 | `9:38PM INF 162 commits scanned. / 9:38PM INF scanned ~5921406 bytes (5.92 MB) in 244ms / 9:38PM WRN leaks found: 1` | 1 | FAIL (historical generated-canary false positive) | .verify/acceptance-logs/gitleaks.log |
| root-pytest | `uv run pytest` | exit 0 | `tests/test_tool_pins.py .                                                [ 97%] / tests/test_workspace.py ....                                             [100%] / ===================== 165 passed, 91 deselected in 34.56s ======================` | 0 | PASS | .verify/acceptance-logs/root-pytest.log |
| gitleaks-canary | `/bin/sh .verify/gitleaks-canary.sh` | exit 0 | `9:39PM INF scanned ~393 bytes (393 bytes) in 10.8ms / 9:39PM WRN leaks found: 4 / canary passed: both schema paths bounded; ordinary file detected` | 0 | PASS | .verify/acceptance-logs/gitleaks-canary.log |
| link-canary | `/tmp/praxismesh-migration-tools/lychee --offline --no-progress .verify/link-canary/canary.md` | exit 2 (broken link detected) | `[.verify/link-canary/canary.md]: / [ERROR] file:///tmp/praxismesh-dsh-verify-aef2214/.verify/link-canary/does-not-exist.md (at 1:1) \| File not found. Check if file exists and path is correct / 🔍 1 Total (in 0s) 🔗 1 Unique ✅ 0 OK 🚫 1 Error` | 2 | PASS | .verify/acceptance-logs/link-canary.log |
| gitleaks-diagnostic | `/tmp/praxismesh-migration-tools/gitleaks git --config .gitleaks.toml --redact --report-format json --report-path .verify/gitleaks-redacted.json .` | exit 0 | `9:39PM INF 162 commits scanned. / 9:39PM INF scanned ~5921406 bytes (5.92 MB) in 309ms / 9:39PM WRN leaks found: 1` | 1 | FAIL (historical generated-canary false positive) | .verify/acceptance-logs/gitleaks-diagnostic.log |
| catalog | `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py catalog --image "$(cat /tmp/praxis-dsh-image-id)"` | exit 0 | `{"exit": 0, "cleanup_ok": true, "container_absent": true, "gateway_stopped": true, "grace_met": true}` | 0 | PASS | .verify/acceptance-logs/catalog.log |
| gitleaks-pr | `/tmp/praxismesh-migration-tools/gitleaks git --config .gitleaks.toml --redact --log-opts="952d01e097332905ba56d6c26e1e342431f8f394..aef22144d3e2a48af13cf921774ef6745e971af7" .` | exit 0 | `9:39PM INF 12 commits scanned. / 9:39PM INF scanned ~310858 bytes (310.86 KB) in 148ms / 9:39PM INF no leaks found` | 0 | PASS | .verify/acceptance-logs/gitleaks-pr.log |
| prerequisites | `uname -m; getconf GNU_LIBC_VERSION; spikes/dsh-harness/.venv/bin/python --version; uv --version; docker --version; /tmp/praxismesh-migration-tools/gitleaks version; /tmp/praxismesh-migration-tools/actionlint -version; /tmp/praxismesh-migration-tools/lychee --version` | exit 0 | `installed by downloading from release page / built with go1.26.1 compiler for linux/amd64 / lychee 0.24.2` | 0 | PASS | .verify/acceptance-logs/prerequisites.log |
| capability | `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py capability --image "$(cat /tmp/praxis-dsh-image-id)"` | exit 0 | `{"exit": 0, "cleanup_ok": true, "container_absent": true, "gateway_stopped": true, "grace_met": true}` | 0 | PASS | .verify/acceptance-logs/capability.log |
| poison | `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py poison --image "$(cat /tmp/praxis-dsh-image-id)"` | exit 0 | `{"exit": 0, "cleanup_ok": true, "container_absent": true, "gateway_stopped": true, "grace_met": true}` | 0 | PASS | .verify/acceptance-logs/poison.log |
| denied-tool | `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py denied-tool --image "$(cat /tmp/praxis-dsh-image-id)"` | exit 0 | `{"exit": 0, "cleanup_ok": true, "container_absent": true, "gateway_stopped": true, "grace_met": true}` | 0 | PASS | .verify/acceptance-logs/denied-tool.log |
| native-text | `spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py native-text --image "$(cat /tmp/praxis-dsh-image-id)"` | exit 0 | `{"exit": 0, "cleanup_ok": true, "container_absent": true, "gateway_stopped": true, "grace_met": true}` | 0 | PASS | .verify/acceptance-logs/native-text.log |
| local | `VLLM_BASE_URL="$(cat .verify/local-model-url)" spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py local --deadline 180 --image "$(cat /tmp/praxis-dsh-image-id)"` | exit 0 | `{"exit": 0, "cleanup_ok": true, "container_absent": true, "gateway_stopped": true, "grace_met": true}` | 0 | PASS | .verify/acceptance-logs/local.log |
| final-cleanup | `python3 .verify/check-cleanup.txt` | exit 0 | `python3: can't open file '/tmp/praxismesh-dsh-verify-aef2214/.verify/check-cleanup.txt': [Errno 2] No such file or directory` | 2 | INVALID (verifier invoked scratch helper before creating it; no service operation occurred) | .verify/acceptance-logs/final-cleanup.log |
| final-cleanup-evidence | `python3 .verify/check-cleanup.txt` | exit 0 | `{"run_id": "praxis-dsh-8317cf5bfd77", "docker_listing_exit": 0, "matching_containers": "", "scratch_exists": false, "matching_result_digest_count": 1, "ok": true} / {"run_id": "praxis-dsh-cafdf5adf3fd", "docker_listing_exit": 0, "matching_containers": "", "scratch_exists": false, "matching_result_digest_count": 1, "ok": true} / {"run_id": "praxis-dsh-cc8801b558f3", "docker_listing_exit": 0, "matching_containers": "", "scratch_exists": false, "matching_result_digest_count": 1, "ok": true}` | 0 | PASS | .verify/acceptance-logs/final-cleanup-evidence.log |

## Probe observations and run IDs


Only local is a real-model run. Scripted probes execute the real container SDK/runtime but prove control behavior only. R4–R9, TaskResult mapping, cancellation injection, token accounting and benchmark adoption are outside this phase.

### capability

Result: `.verify/raw-results/capability-07f2c5e2459a.json`; manifest digest: `ee710ba32625c579772eab0748db61e3a238ec42338785dfefcb904b9b445709`.

Observed candidate output (sanitized):
```json
{"case": "capability", "initialized": true, "profile": "sdk-minimal", "host_environment_absent": true, "direct_ip_blocked": true, "unapproved_gateway_path_blocked": true, "finish_reason": "completed", "policy_unchanged": true, "response_hash": "e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286", "quote_matches": true}
```

Boundary requests: 4; admitted tool body records: `[{"tool": "lookup_price", "admitted": true}, {"tool": "lookup_stock", "admitted": true}]`. Cleanup evidence: `{"container_absent": true, "cleanup_ok": true, "gateway_stopped": true, "cleanup_command_exit": 0, "grace_met": true, "observations": 20, "observation_seconds": 10.018}`.

### catalog

Result: `.verify/raw-results/catalog-8317cf5bfd77.json`; manifest digest: `d7c0763e5389ff1555f4df4b94c4401df1c2511400c34f53dad17781b52f2395`.

Observed candidate output (sanitized):
```json
{"case": "catalog", "initialized": true, "profile": "sdk-minimal", "host_environment_absent": true, "direct_ip_blocked": true, "unapproved_gateway_path_blocked": true, "finish_reason": "completed", "policy_unchanged": true, "response_hash": "e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286"}
```

Boundary requests: 1; admitted tool body records: `[]`. Cleanup evidence: `{"container_absent": true, "cleanup_ok": true, "gateway_stopped": true, "cleanup_command_exit": 0, "grace_met": true, "observations": 20, "observation_seconds": 10.02}`.

### denied-tool

Result: `.verify/raw-results/denied-tool-cafdf5adf3fd.json`; manifest digest: `dbc2d70751b86f3320d3614754aa71c98611c74622360f6c3845b4d3031b68f5`.

Observed candidate output (sanitized):
```json
{"case": "denied-tool", "initialized": true, "profile": "sdk-minimal", "host_environment_absent": true, "direct_ip_blocked": true, "unapproved_gateway_path_blocked": true, "finish_reason": "completed", "policy_unchanged": true, "response_hash": "e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286"}
```

Boundary requests: 2; admitted tool body records: `[]`. Cleanup evidence: `{"container_absent": true, "cleanup_ok": true, "gateway_stopped": true, "cleanup_command_exit": 0, "grace_met": true, "observations": 20, "observation_seconds": 10.012}`.

### local

Result: `.verify/raw-results/local-cc8801b558f3.json`; manifest digest: `be19b80bb00671cc7593718f4b70d6831bc747d5e0ba2bd933febe63c6283e2a`.

Observed candidate output (sanitized):
```json
{"case": "local", "initialized": true, "profile": "sdk-minimal", "host_environment_absent": true, "direct_ip_blocked": true, "unapproved_gateway_path_blocked": true, "finish_reason": "completed", "policy_unchanged": true, "response_hash": "122075797970321a08deecb7bb8afe7dbe8437bf989266e4f7cc2d5923d55bd9", "quote_matches": true}
```

Boundary requests: 3; admitted tool body records: `[{"tool": "lookup_price", "admitted": true}, {"tool": "lookup_stock", "admitted": true}]`. Cleanup evidence: `{"container_absent": true, "cleanup_ok": true, "gateway_stopped": true, "cleanup_command_exit": 0, "grace_met": true, "observations": 20, "observation_seconds": 10.011}`.

### native-text

Result: `.verify/raw-results/native-text-05b81e25d1e5.json`; manifest digest: `d490ae2cc9c15e3363dadb1952a0a68d16f0c1c6403d3623b9a32cba883d5a5a`.

Observed candidate output (sanitized):
```json
{"case": "native-text", "initialized": true, "profile": "sdk-minimal", "host_environment_absent": true, "direct_ip_blocked": true, "unapproved_gateway_path_blocked": true, "finish_reason": "completed", "policy_unchanged": true, "response_hash": "e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286"}
```

Boundary requests: 2; admitted tool body records: `[]`. Cleanup evidence: `{"container_absent": true, "cleanup_ok": true, "gateway_stopped": true, "cleanup_command_exit": 0, "grace_met": true, "observations": 20, "observation_seconds": 10.013}`.

### poison

Result: `.verify/raw-results/poison-0a098e74a624.json`; manifest digest: `becaad04432e720180124c3e79833a83acb2b395bbd83ffaa9502b5ce5b8df97`.

Observed candidate output (sanitized):
```json
{"case": "poison", "initialized": true, "profile": "sdk-minimal", "host_environment_absent": true, "direct_ip_blocked": true, "unapproved_gateway_path_blocked": true, "finish_reason": "completed", "policy_unchanged": true, "response_hash": "e7f099332273bb2648ff5ac9c4b14e5d7abe7f977ca9a1097001ce7bd93bb286", "quote_matches": true}
```

Boundary requests: 5; admitted tool body records: `[{"tool": "lookup_price", "admitted": true}, {"tool": "lookup_stock", "admitted": true}]`. Cleanup evidence: `{"container_absent": true, "cleanup_ok": true, "gateway_stopped": true, "cleanup_command_exit": 0, "grace_met": true, "observations": 20, "observation_seconds": 10.013}`.

### startup

Result: `.verify/raw-results/startup-3215bea510f8.json`; manifest digest: `d4170d53f105c099c2babcfc4190024e4095040168e24a1bc07324f45dbe9dc5`.

Observed candidate output (sanitized):
```json
{"case": "startup", "initialized": true, "profile": "sdk-minimal", "host_environment_absent": true, "direct_ip_blocked": true}
```

Boundary requests: 0; admitted tool body records: `[]`. Cleanup evidence: `{"container_absent": true, "cleanup_ok": true, "gateway_stopped": null, "cleanup_command_exit": 0, "grace_met": true, "observations": 21, "observation_seconds": 10.013}`.


## Permission/failure cases and cleanup

`denied-tool` and `native-text` each observed a rejected boundary operation, zero admitted tool bodies, and unchanged policy. Poison discovery exercised malicious inputs without broadening grants. These are permission checks; Phase 02 crash recovery, cancellation injection, token budgets and TaskResult mapping were not demonstrated.

All seven result records show `cleanup_ok: true`, `container_absent: true`, and `grace_met: true`; six model cases also record gateway shutdown (startup starts none). Exact-name Docker daemon listings independently returned no matching containers after execution; each scratch directory was absent. The ten-second observation windows have 20–21 absence checks. Exact cleanup commands and digest cross-checks are retained in `.verify/check-cleanup.txt` and `.verify/acceptance-logs/final-cleanup-evidence.log`. No broad Docker prune or unrelated service teardown occurred. The worktree, ignored environments, raw evidence and operator scratch input remain for collection.

Root suite: 165 passed, 91 intentionally deselected integration/model cases. Isolated suite: 30 passed. Original sandbox DNS/socket permission failures are preserved with authorized unchanged-command retries. A verifier-owned scratch helper initially contaminated root lint; it was renamed and the clean checks passed without source edits.

The extra whole-repository gitleaks scan exited 1 with one generated-canary assignment false positive at `.github/workflows/ci.yml:161`, commit `bc7fe4889d85cf3059f2a5a9676fb1ccb5738c3c`, rule `generic-api-key`. The commit is outside frozen ancestry (`git merge-base --is-ancestor ...` exit 1); PR-range scan `952d01e097332905ba56d6c26e1e342431f8f394..aef22144d3e2a48af13cf921774ef6745e971af7` passed. Raw redacted failure retained, not silently replaced. Both scanner canaries pass. Local GitHub dependency-review action was unavailable; hosted check on frozen commit reports success (informational). No production stack or benchmark run is claimed.

Demo result: **pass** for all seven Phase 01 probe items. This evidence does not close Phase 01 or establish Phase 02/adoption readiness.

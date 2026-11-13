---
review: verification
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: [docs/adr/0001-keep-default-openspec-schema.md, docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 9472d20d3b5e5d7cee1542ffedf9c25335defadd
docs_sha: f2789d505755397bfdd40a88106a04a0b192f3cf
diff_base: n/a
session: fresh (shared with implementation review; independence between them waived under section 7.0)
date: 2026-11-13
verdict: blocked
reviewers:
  - { lens: acceptance and demo, status: completed }
  - { lens: as-built claims, status: completed }
---

# Phase 1 final verification: PR #53

**Blocked.** All executed deterministic acceptance tests passed. No current
architecture contradiction or implementation defect was identified. The real
local-model endpoint is unavailable from the documented prerequisites, preventing
the required real-model sample, benchmark and live worker-container-loss demo.
A skipped or unavailable dependency is not a pass. Phase 1 remains open.

This is a fresh independent session from the implementer. Phase 1's light-tier
exception knowingly waives independence between the preceding implementation
review and this verification, against the same code SHA. Two fresh verifier
agents with no inherited conversation ran sequentially: acceptance/demo, then
as-built. Neither received implementation reasoning or an earlier review verdict.
The second received only the running services, configuration location/ports and
an existing task ID needed for read-only probes, not the first verifier's verdict.

All previous reports, FAIL verdicts, benchmark records and demo evidence remain
unchanged. This report and its evidence use new paths. No implementation source
or tests were edited. The original working checkout remained clean.

## Inputs and environment

Requirements: `docs/plan/phases/phase-1.md`, approved
`docs/rfcs/phase-1-single-agent.md`, `AGENTS.md`, `PROJECT_PLAN.md`, gate protocol
and verify-phase skill. Setup/demo: README, Makefile, `infra/.env.example`, and
only the reproduction instructions from `docs/demos/phase-1.md`. As-built docs
were read with `git show` at the pinned docs revision: architecture overview,
RFC as-built sections, README and demo instructions.

Disposable checkout: `/tmp/praxismesh-pr53-final-verify`, detached at code_sha.
Its own `.verify/acceptance.env` came from the committed example with placeholder
credentials, separate project `praxismesh-pr53-finalverify` and independent
ports. No working-copy secret was read or copied. Python 3.11.17, uv 0.13.5,
Docker 29.9.3, Compose v5.7.1, openai-agents 0.24.0, temporalio 1.36.0.
The external `VLLM_BASE_URL` stayed empty. `workers-check` deliberately pointed
its own workers at the documented deterministic fake model. The difference
between configured external endpoint and active fake override is explicit.

See [full acceptance command ledger](final-pr53-evidence/acceptance-results.md)
and [48-row as-built claim inventory](final-pr53-evidence/asbuilt-results.md).
These subreports are preserved as produced; consolidated decisions below close
complementary evidence gaps without rewriting their independent observations.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Pinned commits and remote containment | `git cat-file -t` and `git branch -r --contains` for each SHA after fetch | Commit objects on remote | Both are commits, both contained by remote correction branch; PR head equals docs_sha | pass |
| Docs describe tested code | `git diff --stat <code_sha> <docs_sha> -- . ':!docs'` | Empty | Empty; complete diff adds three docs/reviews files only | pass |
| Secrets and transcripts | Skill's `git grep` and `git ls-tree` checks at both SHAs | No credential or session transcript | Only scanner's own regex matched; three Pre-0 JSONL files inspected as documented per-task measurements, not session transcripts | pass |
| Tested-code CI, informational | `gh api .../commits/<code_sha>/check-runs` | Informational | total_count 0; latest docs-only head separately has all checks green | informational |
| Locked environment | `uv sync --locked` | Install pinned environment | 90 packages resolved; 86 installed; exit 0 after network escalation | pass |
| Isolated stack and migration | `make up`, `make migrate`, with own ENV_FILE | Healthy and migration 0003 | Healthy stack; upgrade 0002 to 0003 completed; exit 0 | pass |
| Unit, replay, time-skipping | `uv run pytest` | All pass | 157 passed, 91 deselected; exit 0 | pass |
| Integration acceptance | `make smoke ENV_FILE=.verify/acceptance.env` | Deterministic suites pass | 82 passed, 4 real-model tests skipped; exit 0 | pass deterministic; model items blocked |
| T1 actual metric values | Smoke includes `test_activity_metrics_are_recorded` | Nonzero input/output deltas, actual bytes and duration | All 16 Activity integration tests pass, including strengthened test; assertions pin 20/7 tokens, independently packed bytes and 0.75 seconds | pass |
| T2 CLI context and streams | Unit includes `test_submit_writes_contextual_json_log_to_stderr` | Known workflow ID, stderr JSON, independent stdout JSON | Unit suite passed; exact regression test included | pass |
| Container end-to-end | `make workers-check`; `task-output`; `task-status` | Explicit simulated task completes with stored visible artifact | succeeded, 1 turn/attempt, 400/40 tokens, artifact and one order; Workflow COMPLETED | pass, simulated |
| Workspace/session recovery and effect idempotency | `make recovery-check` | All five documented process-loss tests pass | 5 passed in 58.50 seconds, including edit/effect recovery in later turn | pass, simulated |
| Unauthorized capability submission | CLI `--request .verify/rogue.json` | Explicit error, exit 2 | Names forbidden mcp_servers/skills; exit 2 | pass |
| Full tracing and metrics | `make observability-up`; documented v3 Jaeger and Prometheus probes | CLI-to-result trace plus three scrape targets | One 20-span trace across CLI/orchestrator/template, model/tool calls and complete_task; all scrapes up=1, tokens 400/40 | pass, simulated task |
| Real-model sample and visible result | README/RFC real-model workers-up/task/output steps | Real-model useful work using approved skill/MCP | Endpoint absent; no fake substitution | blocked |
| Live real-model worker-container loss | `make demo-worker-loss` after real-model workers-up | Same logical task resumes with context and edits | Not run because endpoint absent; process-loss suite does not replace this item | blocked |
| Real-model benchmark and regression limit | `make benchmark ENV_FILE=.verify/acceptance.env` | At least 9/10 against 10/10 baseline | Exit 2: `VLLM_BASE_URL is not set; the benchmark needs a real model` | blocked |
| As-built code and available runtime probes | Fresh second verifier | Documentation matches observed mechanism | 48 grouped claim rows; no material contradiction; task, artifacts, stores, checkpoint/order metadata, status, metrics and UIs confirmed | pass for available probes; real-model claims blocked |

The acceptance logs give exact commands and output for each step. Initial sandbox
DNS/socket denials were resolved with escalation. An initial env rejection of
optional observability port keys was resolved using README-permitted shell
overrides; a legacy Jaeger API 404 was resolved using the documented v3 API.
These diagnostic attempts did not cause an acceptance failure. Only committed
example placeholders were used. No undocumented prerequisite was required for
the successfully executed checks.

## As-built claims: consolidated assessment

The [full inventory](final-pr53-evidence/asbuilt-results.md) records every grouped
claim and its source locations. The following consolidates both fresh briefs:

| Claim (quoted) | Location | Status | Evidence |
|---|---|---|---|
| Registry/profile/template, template queues and TaskWorkflow/Activities | Architecture Phase 1 component table | confirmed | Pinned code paths plus independent status/output probes and container task |
| Session/workspace checkpoints, heartbeat and cross-worker recovery | Architecture durability section | confirmed for deterministic execution; real-model behavior unverifiable | Five process-loss tests, including edit restore, stale-attempt fencing and later-turn recovery; Activity integration tests for usage, budgets and attempts |
| Side effects are idempotent and capabilities template-only | Architecture sample MCP/CLI rows | confirmed for exercised scenarios | Effect-before-checkpoint crash test passed; forbidden raw JSON submission rejected |
| JSON logs and client-to-model/tool traces | Architecture observability row | confirmed for deterministic task | CLI regression test; integration tracing suite; independently observed connected 20-span trace and worker scrape counters |
| Real-model task/recovery and 10/10 benchmark | Architecture historical observations, demo and benchmark sections | unverifiable in this run | External endpoint empty; benchmark diagnostic confirms dependency unavailable |
| Dated memory samples, old example positions and earlier SDK/grace-period experiments | Architecture historical notes; RFC/demo | unverifiable historical observations | No corresponding historical runtime snapshot in this checkout; not presented as new observations or current fixed guarantees |

As-built subreport AB-U2 (read-only brief could not force recovery) is closed for
current deterministic guarantees by the separate acceptance recovery/integration
and unit execution. AB-U3 (UI alone cannot prove trace ancestry) is closed by
the acceptance tracing test and independent v3 trace observation. Neither closure
upgrades a fake-model result to real-model evidence. AB-U1 remains blocked by the
missing real model. AB-U4 is a disclosed historical Nit, not a new implementation
finding; a future pass must explicitly accept its historical evidence limitation
or supply applicable renewed evidence under the verify-phase pass rule.

## Findings and remaining dependencies

No new implementation Blocker or Major was identified by this bounded assessment.
The missing endpoint is an unavailable verification dependency, not an inferred
implementation defect. The concrete gate requirement is plan section 8 and Phase
1 Accept: closure requires real local-model execution and a benchmark rerun.
A model-specific tool/protocol regression could pass deterministic tests; this is
why the missing real-model observations prevent PASS.

| ID | Kind | Location | Expected / observed | Action |
|---|---|---|---|---|
| V-D1 | Gate dependency, unavailable | README model setup; Phase 1 Accept; benchmark rule | Real endpoint needed; `VLLM_BASE_URL` empty, benchmark exits 2 | Configure an independently supplied documented endpoint, rerun real-model sample/benchmark/live demo, save new evidence |
| V-N1 / AB-U4 | Nit, historical evidence limit | As-built dated observations | Historical numbers not independently reconstructed; no contradiction | Keep dated provenance; explicitly accept limitation or refresh relevant evidence before unconditional verification PASS |

Unrelated implementation Nits remain deferred. No cleanups or fixes were made
in the reviewing/verifying session, and existing verdicts were not changed.

## Verdict

**blocked**, under verify-phase Step 5: no executed acceptance check failed and
no current as-built claim was contradicted, but required real-model checks could
not run because their dependency was unavailable. Prior benchmark/demo PASS
claims are not independent verification for this code snapshot.

The [new demo evidence](../../demos/phase-1-final-pr53.md) has versions, exact
commands, task/workflow/trace identifiers, expected versus observed, recovery
cases, explicit blocked steps and cleanup. It is not a phase closure record.

## Cleanup and coordinator handoff

The isolated services were left up between the sequential verifiers. The main
session then ran `make workers-down`, `make observability-down` and `make reset`,
all with this project's own ENV_FILE and port overrides. The combined command
exited 0; containers, network and pgdata/seaweeddata volumes for only
`praxismesh-pr53-finalverify` were removed. Output is preserved in
`final-pr53-evidence/cleanup.log`. The disposable worktree is removed after
evidence preservation. The user's original checkout has the same HEAD
`f2789d505755397bfdd40a88106a04a0b192f3cf` and empty status as before verification.

[Coordinator steps](final-pr53-coordinator.md) give the precise remaining gates,
latest-head checks, source-diff check, external head-SHA recording and owner-only
merge/issue-close commands. No merge, settings change, task check-off, OpenSpec
archive or Phase 1 closure was performed here.

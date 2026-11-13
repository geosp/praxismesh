---
review: verification
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: [docs/adr/0001-keep-default-openspec-schema.md, docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 9472d20d3b5e5d7cee1542ffedf9c25335defadd
docs_sha: f2789d505755397bfdd40a88106a04a0b192f3cf
diff_base: n/a
session: fresh (continuation of light-tier review/verification session; independence between review and verification waived under section 7.0)
date: 2026-11-13
verdict: pass
reviewers:
  - { lens: real-model acceptance and demo, status: completed }
  - { lens: real-model as-built claims, status: completed }
---

# Phase 1 verification after model endpoint became available

**PASS for the combined pinned-code gate verification.** The earlier
[blocked report](final-verification-pr53.md) and its verdict remain unchanged.
This continuation resolves its missing-model dependency with new real-model
execution, combined with the deterministic acceptance/recovery evidence already
observed independently in this same session at the exact same code revision.
No implementation source, tests, approved requirements or benchmark baseline
changed between the two runs. Phase 1 remains open pending coordinator approval.

## Inputs, independence and revisions

Code: `9472d20d3b5e5d7cee1542ffedf9c25335defadd`.
Documentation: `f2789d505755397bfdd40a88106a04a0b192f3cf`.
Previous reviewed correction base: `60fe15d0fd755c391cbe79c0084f7def7b38c7db`.
The [three-lens targeted implementation review](final-targeted-pr53.md) remains
PASS; no source change required another review.

The user supplied an updated model URL. Only its credential-free base URL and
model name were selected from the user's configuration. No API key or other
working-copy credential was copied. The verifier built its own env file from
`infra/.env.example` with placeholder secrets, a new project and distinct ports.
The model URL is redacted from preserved HTTP logs.

Two new fresh `verifier` agents ran sequentially without inherited conversation:
acceptance/demo, then read-only as-built. They received the pinned code/docs,
Phase 1 plan, approved RFC, setup/demo instructions, gate protocol and their
bounded briefs. The second received running services, its own configuration
location, ports and existing task IDs, not the first verifier's verdict or
implementation reasoning. It independently checked persisted results and traces.

The coordinating session remains independent from the implementer. Independence
between implementation review and verification is knowingly waived under the
Phase 1 light-tier exception. This dependency-unblocked continuation does not
reopen the implementation review or deferred unrelated Nits.

Direct coordinator checks repeated: both `git cat-file -t` outputs are `commit`;
remote containment after fetch includes `origin/fix/44-phase-1-followup-fixes`
for both pinned SHAs; `git diff --stat <code_sha> <docs_sha> -- . ':!docs'` is
empty. Credential-pattern scan again found only the scanner's own regex in the
skill; the previously inspected Pre-0 JSONL files remain per-task measurements,
not session transcripts. Direct code-SHA CI has no attached check-runs; PR #53's
source-identical docs head has successful required CI. Latest-head checks remain
a separate coordinator obligation.

## Checks: combined independent evidence

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Unit/replay/time-skipping | Earlier `uv run pytest` at same code SHA | All pass | 157 passed, 91 deselected | pass, preserved execution |
| Integration including T1 metric values | Earlier `make smoke` at same code SHA | Deterministic suites pass | 82 passed; strengthened token/byte/duration assertions executed | pass, preserved execution |
| Recovery after edits, effect-window replay, fencing, later-turn recovery | Earlier `make recovery-check` at same code SHA | Five tests pass | 5 passed, real DB/S3 with labeled fake model | pass, preserved execution |
| Previously skipped model compatibility | `uv run --env-file .verify/real-model.env pytest -m integration tests/integration/test_model_endpoints.py -v` | Model/list, Messages/chat and unreachable diagnostic | 5 passed, exit 0; no skips | pass, new execution |
| Real model configuration | Model probes and workers-up | Served spark and real endpoint in both workers | Advertised spark/qwen3.8-flash-next; both endpoint matches true, fake_endpoint false | pass |
| Real sample using skill and MCP | Documented `make task`, task-status/output | Validated result and visible correct file | succeeded; 1 turn/attempt, 5 inner turns; 10,311 input/947 output tokens; total 52.00 | pass |
| Skill and MCP consumption | Safe function/read-path metadata and trace | Approved skill and shop tool used | Read `.skills/order-desk/SKILL.md`; lookup/stock/order and workspace tools observed | pass |
| Real container loss/replacement | `make demo-worker-loss` | Acknowledged checkpoint, different worker, same logical task completes | worker-a killed; attempt 1 lost, attempt 2 done on worker-b; same Workflow COMPLETED | pass |
| Conversation and outputs after replacement | Checkpoint metadata, task-status/output | Context continues; completed useful output; intended orders once | Position 4 to replacement 5 to final 40; output 64.85; four orders/keys once | pass for live observed case |
| Forbidden capability request | CLI raw request | Explicit rejection, exit 2 | Names forbidden mcp_servers/skills, exit 2 | pass |
| Real benchmark | `make benchmark ENV_FILE=.verify/real-model.env` | At least 9/10 against 10/10 baseline | 10/10, all task checks ok and statuses succeeded; exit 0; zero tasks lost | pass |
| Benchmark identity | Independent raw JSON/baseline/registry comparison | Same model/template/harness/prompt identities | spark, local-default@1, openai-agents 0.24.0, template/prompt hashes match | pass |
| Distributed tracing | Independent Jaeger v3 ancestry probes | Real-task connected CLI-to-result/model/tool trace | Sample 24 spans, recovery 23, three services; no missing external parents | pass |
| Worker metrics | Independent Prometheus probes | All targets up and successful-workload families populated | Three up; duration, heartbeat, tokens, tools and checkpoint size/time families present | pass |
| As-built current runtime | Fresh read-only verifier | Claims match code and observations | No material contradiction; all touched current claims corroborated with the combined evidence below | pass |

Exact commands, exits, versions, model identities, observations and diagnostics:
[acceptance ledger](model-pr53-evidence/real-acceptance-results.md),
[as-built ledger](model-pr53-evidence/real-asbuilt-results.md), and
[benchmark measurements](model-pr53-evidence/real-model-benchmark-2026-11-13.md).
The benchmark overlapped sample/recovery traffic on the shared model server;
its workers used separate queues. Its 210.2-second aggregate task wall time is
an observed measurement under that concurrency, not an isolated performance
claim. The threshold compares pass counts, and no task was lost.

## As-built claims and limits

| Current claim and location | Status | Combined evidence |
|---|---|---|
| Real task uses template capabilities and yields validated output (Phase 1 Accept; RFC demo 1) | confirmed | Successful real sample, approved skill read-path metadata, shop tool spans/effects and correct visible artifact |
| Worker loss continues the same logical task on replacement (overview durability; RFC demo 2) | confirmed | Lost/done attempts on distinct container IDs, persisted same task/Workflow/session, positions 4 to 5 to 40, final output |
| Workspace edits restore after worker loss; effect/checkpoint-window retry does not duplicate effects (Phase 1 Accept; durability spec) | confirmed by separately executed automated evidence | Earlier five-test recovery suite at this exact code SHA exercised those failures; live real-model kill checkpoint had no files and is not substituted for those assertions |
| Logs carry known IDs, stdout remains JSON, actual metric values recorded (observability baseline; T1/T2) | confirmed | Earlier unit/Activity integration execution, current real CLI context and populated runtime metrics |
| Client-to-result trace through model/tool calls (overview observability; demo 4) | confirmed | Two fresh independent probes of connected real sample/recovery traces; sample 24 spans includes 5 model and 7 tool calls |
| Benchmark rerun at phase closure, identity recorded, at most one task lost (plan 8; RFC benchmark) | confirmed | Current raw 10/10 results, identity comparison, unchanged baseline |

The real container kill happened before edits: its lost-attempt snapshots are
empty. It did not force a duplicate effect call in the effect/checkpoint window.
Those are complementary to the earlier independently executed automated tests,
not missing claims silently inferred from a successful final file. The second
verifier's read-only evidence gaps for these failure injections are closed by
that earlier execution; it did not receive another verifier's verdict as input.

Tool-error series were not emitted by this successful real workload; the labeled
instrument exists and emits after an error. This is not a contradiction or a
new requirement to inject another error here. Prior negative capability and
runner tests remain applicable. Physical GPU placement, weight fingerprints and
server version are not established by an advertised model ID; no such new
capability claim is made.

Dated resource samples and SDK experiments remain historical background. Their
previously disclosed Nit stays deferred under the user's bounded-scope instruction;
it is not reopened as a current runtime requirement or silently marked newly
measured. This continuation confirms current contractual behavior and current
benchmark measurements. No current contractual runtime claim is left blocked or
unverified by the combined execution evidence.

## Findings and verdict

No new implementation finding, current as-built contradiction, acceptance failure
or unavailable dependency remains. Under verify-phase Step 5, **pass**: all
required acceptance and demo behaviors now have observed execution evidence at
the same frozen code revision. [New demo evidence](../../demos/phase-1-model-pr53.md)
records the real-model continuation without overwriting the earlier blocked demo.

The automatic approval reviewer rejected one proposed scratch raw-trace-save
probe before execution. A revised probe completed using whitelisted metadata
only; no raw trace or session transcript was saved. This did not block verification.
Source, tests, approved specs and baseline were not changed. Only documented
benchmark output artifacts were generated inside the disposable checkout.

## Cleanup and coordinator gate

The documented workers-down, observability-down and reset commands completed
with combined exit 0 for only `praxismesh-pr53-modelverify`, using its own ENV_FILE.
Its containers, network and pgdata/seaweeddata volumes were removed; output is in
`model-pr53-evidence/real-cleanup.log`. The disposable checkout is removed after
evidence preservation. Original working HEAD remains
`f2789d505755397bfdd40a88106a04a0b192f3cf` with empty tracked/untracked git status;
this session did not modify the user's ignored configuration or original stack.

[Current coordinator handoff](model-pr53-coordinator.md) gives the remaining
latest-head checks, external revision recording and owner-only merge commands.
No phase checkbox, issue state, OpenSpec archive, repository setting or merge
was changed by this reviewing/verifying session.

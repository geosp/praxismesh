---
phase: 1
code_sha: 9472d20d3b5e5d7cee1542ffedf9c25335defadd
docs_sha: f2789d505755397bfdd40a88106a04a0b192f3cf
date: 2026-11-13
verdict: pass
---

# Phase 1 real-model demo continuation: PR #53

The previously missing endpoint is now available. This is new independent
execution evidence, preserving the earlier blocked report/demo unchanged.
It completes the real-model portion of the same pinned-code gate assessment.
The final verification verdict is recorded separately after the fresh as-built
check; Phase 1 is not marked closed here.

## Environment and entry points

Disposable checkout `/tmp/praxismesh-pr53-model-verify`, at code_sha above.
Instructions/as-built docs at docs_sha above. Model alias `spark`, response model
`qwen3.8-flash-next`; no API key required. Only the credential-free model URL and
model name came from the user's updated configuration. No working-checkout
credentials were copied. Own configuration started from `infra/.env.example`.

Python 3.11.17, uv 0.13.5, Docker 29.9.3, Compose v5.7.1;
locked openai-agents 0.24.0 and temporalio 1.36.0. Independent project
`praxismesh-pr53-modelverify`, ports DB25432, Temporal27233, UI28080, S328333,
Prometheus29090, Jaeger26686, OTLP24318. Model host is omitted from committed
logs. The workers used the real endpoint; no fake-model override was applied.

Setup and commands ran inside this disposable checkout:

```sh
UV_CACHE_DIR=/tmp/praxismesh-pr53-docs-uv-cache uv sync --locked
export PROMETHEUS_PORT=29090 JAEGER_UI_PORT=26686 OTLP_HTTP_PORT=24318
make up ENV_FILE=.verify/real-model.env
make migrate ENV_FILE=.verify/real-model.env
make observability-up ENV_FILE=.verify/real-model.env
make workers-up ENV_FILE=.verify/real-model.env
uv run --env-file .verify/real-model.env pytest -m integration tests/integration/test_model_endpoints.py -v
make task ENV_FILE=.verify/real-model.env PROMPT="We need to order 3 units of SKU-1 and 2 units of SKU-2. Use the order-desk skill: look up prices and stock, record each order, and write order-summary.md." OUTPUT=order-summary.md
make task-output ENV_FILE=.verify/real-model.env ID=task-28f42876-96df-4d29-b33f-49147c786e18 FILE=order-summary.md
make task-status ENV_FILE=.verify/real-model.env ID=task-28f42876-96df-4d29-b33f-49147c786e18
make benchmark ENV_FILE=.verify/real-model.env
make demo-worker-loss ENV_FILE=.verify/real-model.env
make task-status ENV_FILE=.verify/real-model.env ID=task-4a3b7cb0-243a-4bcb-bc9f-5be377ca6fac
make task-output ENV_FILE=.verify/real-model.env ID=task-4a3b7cb0-243a-4bcb-bc9f-5be377ca6fac FILE=order-summary.md
docker start praxismesh-pr53-modelverify-worker-a-1
```

Benchmark overlapped sample/recovery traffic on the shared model server. Its
host workers used separate task queues, so the killed Compose worker could not
hold a benchmark task. Reported wall times are observations under this overlap,
not isolated performance measurements. The benchmark baseline was not rewritten.

## Expected versus observed

| Demo / acceptance step | Expected | Observed | Result |
|---|---|---|---|
| Real endpoint/API compatibility | Served model, Messages and chat work | All five endpoint tests passed, including unreachable diagnostic | pass |
| Real sample, skill and MCP | Visible file and validated TaskResult | succeeded; one turn/attempt, five inner turns; approved skill read and shop tool calls confirmed | pass |
| Visible sample output | Skill's table format and correct total | SKU-1 qty 3 at 12.50 = 37.50; SKU-2 qty 2 at 7.25 = 14.50; total 52.00 | pass |
| Container loss after checkpoint | Different worker completes same logical task | attempt 1 lost on a98e50a564f0 after docker kill; attempt 2 done on 76545c5ea27e; same task/Workflow COMPLETED | pass |
| Conversation survives | Persisted conversation continues | Kill checkpoint position 4; final checkpoint position 40, same session/task ID | pass |
| Nonduplicated effects and completed recovery output | One order per requested SKU | Four requested orders once each; output total 64.85 | pass |
| Recovery after workspace edits and effect-before-checkpoint replay | Lost edits restored; effect not repeated | Earlier independent five-test recovery suite at this exact code SHA passed; this live kill occurred before edits | pass by earlier automated evidence; not newly demonstrated live |
| Unauthorized capability request | Explicit rejection | CLI names forbidden mcp_servers/skills, expected exit 2 | pass |
| Trace from submission to result | One connected CLI/Workflow/Activity/model/tool trace | 24 spans, three services, five model and seven tool calls, descendants of submit | pass |
| Worker metrics | Three targets up and real counters present | All three up=1 after worker restart; real token and Activity samples captured | pass |
| Real benchmark at phase gate | At least 9/10 against 10/10 baseline | 10/10, all succeeded, exit 0; zero lost | pass |

The real kill checkpoint `:1:1:1` contained no files. Final checkpoint
`:1:2:5` contained `order-summary.md`. This live run therefore demonstrates
container replacement and conversation continuity; it does not prove preservation
of pre-kill edits or force an effect/checkpoint-window replay. Those claims retain
the separately observed automated evidence at the same frozen revision:
[prior recovery log](../reviews/phase-1/final-pr53-evidence/acceptance-recovery.log).
No test was rerun or claimed passed solely from the existence of an earlier
implementation report.

## Identifiers and durable evidence

- Sample task/Workflow: `task-28f42876-96df-4d29-b33f-49147c786e18`.
- Recovery task/Workflow: `task-4a3b7cb0-243a-4bcb-bc9f-5be377ca6fac`.
- Sample trace: `c7f267797fb7f3d7ae71cce6c7b7e441`.
- Sample tokens: 10,311 input, 947 output.
- Benchmark total task wall time: 210.2 seconds, with the overlap caveat above.

[Exact command ledger and observations](../reviews/phase-1/model-pr53-evidence/real-acceptance-results.md),
[benchmark per-task measurements](../reviews/phase-1/model-pr53-evidence/real-model-benchmark-2026-11-13.md),
[container-loss output](../reviews/phase-1/model-pr53-evidence/real-worker-loss.log),
and [safe checkpoint metadata](../reviews/phase-1/model-pr53-evidence/real-checkpoints.json)
are preserved under distinct paths. Optional read-only evidence inspectors are
saved as text beside them; no raw sessions or trace payloads are committed.

## Cleanup

Leave the isolated services up only between the sequential verifiers. Then run:

```sh
make workers-down ENV_FILE=.verify/real-model.env
make observability-down ENV_FILE=.verify/real-model.env
make reset ENV_FILE=.verify/real-model.env
```

Use the same shell port overrides and own project configuration. The final
verification report records observed teardown and disposable-worktree removal.
The original checkout, its ignored user configuration, and its existing stack
are outside this teardown.

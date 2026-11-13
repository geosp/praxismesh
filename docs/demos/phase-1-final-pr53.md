---
phase: 1
code_sha: 9472d20d3b5e5d7cee1542ffedf9c25335defadd
docs_sha: f2789d505755397bfdd40a88106a04a0b192f3cf
date: 2026-11-13
verdict: blocked
---

# Phase 1 final PR #53 demo reproduction

This is new independent evidence; the original `phase-1.md` demo and all prior
reports are preserved. **Overall demo: blocked.** Deterministic container and
process-loss checks passed, but no real-model endpoint was available. Previous
implementation runs do not count as this run's observations. Phase 1 stays open.

## Environment

Frozen disposable checkout: `/tmp/praxismesh-pr53-final-verify`, at the code SHA
above. As-built instructions were read at the docs SHA above. The coordinating
session is fresh from the implementer; independence between implementation review
and verification is waived by the Phase 1 light-tier exception. Acceptance/demo
and as-built checks used separate fresh verifier agents, sequentially.

Python 3.11.17, uv 0.13.5, Docker 29.9.3, Compose v5.7.1,
openai-agents 0.24.0, temporalio 1.36.0, pytest 9.2.0,
opentelemetry-sdk 1.45.2. Stack uses the repository's digest-pinned images.

Configuration was copied only from `infra/.env.example`, with its example
placeholder values, into `.verify/acceptance.env`; no working-copy secrets were
read or copied. README documents a separate project and ports per checkout:

| Setting | This run |
|---|---|
| Compose project | `praxismesh-pr53-finalverify` |
| DB / Temporal / UI / S3 | `25432` / `27233` / `28080` / `28333` |
| Prometheus / Jaeger / OTLP HTTP | `29090` / `26686` / `24318` |
| External model | Unconfigured: `VLLM_BASE_URL` empty |
| Worker model after `workers-check` | `http://fake-model:8765`, explicitly deterministic |

`PRAXIS_SAMPLE_DB_URL` used the new host DB port. The CLI trace exporter used
`http://127.0.0.1:24318`. Observability ports were shell overrides because the env
validator does not accept those optional keys in ENV_FILE; README permits shell
overrides. Docker/socket/network commands needed sandbox escalation, which
succeeded. These environment restrictions were not product failures.

## Exact reproduction commands

All commands ran inside the disposable checkout. `UV_CACHE_DIR` pointed to
its `.verify/uv-cache`. In addition to copying the example and adjusting the
project/ports as documented, the verifier ran:

```sh
uv sync --locked
export PROMETHEUS_PORT=29090 JAEGER_UI_PORT=26686 OTLP_HTTP_PORT=24318
make up ENV_FILE=.verify/acceptance.env
make migrate ENV_FILE=.verify/acceptance.env
uv run pytest
make smoke ENV_FILE=.verify/acceptance.env
make observability-up ENV_FILE=.verify/acceptance.env
make workers-check ENV_FILE=.verify/acceptance.env
make task-output ENV_FILE=.verify/acceptance.env ID=task-0403d014-d086-4264-9207-859372e12408 FILE=order-summary.md
make task-status ENV_FILE=.verify/acceptance.env ID=task-0403d014-d086-4264-9207-859372e12408
make recovery-check ENV_FILE=.verify/acceptance.env
printf '%s\n' '{"profile":"default","instructions":"Order SKU-1.","skills":["rogue-skill"],"mcp_servers":["rogue-mcp"]}' > .verify/rogue.json
uv run --env-file .verify/acceptance.env python -m orchestrator.cli task submit --request .verify/rogue.json
make benchmark ENV_FILE=.verify/acceptance.env
```

The permission request exited 2 with the required explicit rejection; benchmark
exited 2 because the real-model prerequisite was unavailable. All other commands
above exited 0. The benchmark diagnostic is evidence of a block, not a pass.

## Checklist: expected versus observed

| Required demo / acceptance item | Expected | Observed in this run | Result |
|---|---|---|---|
| Real-model sample uses approved skill/MCP, produces visible file and validated TaskResult | Real local-model task succeeds | No external model endpoint configured; not attempted through a fake as a substitute | blocked |
| Container integration with labeled fake | Scripted task produces result and artifact | `workers-check` succeeded, 1 turn, 1 attempt, 400 input/40 output tokens; output below | pass, simulated |
| Worker lost after acknowledged workspace checkpoint | Replacement preserves edits and conversation | Automated process-SIGKILL recovery and later-turn edit/effect checks passed; live real-model container-loss walkthrough unavailable | automated pass; live demo blocked |
| Crash between effect and next checkpoint | Exactly one committed external side effect | `test_side_effect_not_repeated_after_crash` passed; recovery suite 5/5 | pass, simulated |
| Forbidden MCP/skill override | Explicit rejection | `error: a task request may not set mcp_servers, skills: capabilities come only from the worker template`, exit 2 | pass |
| Same logical task before/after worker replacement, completed output shown | Live real-model replacement with same task/workflow | Deterministic recovery tests passed; container-loss real-model walkthrough not run | blocked live demo |
| Trace from submission through Workflow/Activity/model/tool to result | One connected trace | One 20-span trace across CLI/orchestrator/template, including complete_task, using deterministic task | pass simulated; real-model trace blocked |
| Worker metrics | Scrapes up and token samples | All 3 worker targets up=1; 400 input/40 output tokens observed | pass |
| Benchmark at phase closure, compared with 10/10 baseline | At least 9/10 | `VLLM_BASE_URL is not set; the benchmark needs a real model` | blocked |

Automated results: unit/replay/time-skipping **157 passed, 91 deselected**;
stack smoke **82 passed, 4 model tests skipped**; recovery **5 passed**.
Smoke includes the strengthened metric regression test, asserting both token
directions, byte sum from independently packed workspaces, and 0.75 seconds of
controlled checkpoint duration. The CLI stream/context test passed in unit tests.
No new mutation runs are claimed by this independent verification.

## Visible simulated result and identifiers

- Task/Workflow: `task-0403d014-d086-4264-9207-859372e12408`.
- Temporal run: `01a1d552-a25d-7eb6-9694-e07b75d9229c`.
- Request: `req-90e39822-9804-4856-8fb0-d4ff998faf7f`.
- Trace: `b4bb71b0cde997d5854308f92d106a5f`.
- Latest checkpoint: `task-0403d014-d086-4264-9207-859372e12408:1:1:4`,
  session position 9; `task-status` showed Workflow `COMPLETED`, task `succeeded`,
  and one SKU-1 order of quantity 3.
- Artifact: `order-summary.md`, 105 bytes,
  `sha256:fa7034119c3338fc83da4e49d68dc45df4fab7e66569092749898d9263513bac`.
- Template `local-default@1`,
  `sha256:6122e8de71a551797b991d7ce87c701c366623076a63135b2f40e3f4b6e7f7ee`.

Visible artifact output included:

```text
# Order summary
| SKU-1 | 3 | 12.50 | 37.50 |
```

The recovery suite observed all five named tests passing:
`test_recovery_after_workspace_edits`, `test_side_effect_not_repeated_after_crash`,
`test_checkpoint_matches_session_position`,
`test_superseded_attempt_comes_back_and_writes_nothing`, and
`test_recovery_in_a_later_turn_with_edit_and_effect`.
These are process-loss checks, distinct from the blocked live container demo.

Exact observability probes and summaries are in
[acceptance results](../reviews/phase-1/final-pr53-evidence/acceptance-results.md).
[Preserved command logs](../reviews/phase-1/final-pr53-evidence/acceptance-recovery.log)
and the [verification report](../reviews/phase-1/final-verification-pr53.md)
provide the observed outputs. Raw trace payloads, scratch env and session data
are excluded from committed evidence.

## Cleanup

After the second fresh verifier completes, stop only this isolated project:

```sh
make workers-down ENV_FILE=.verify/acceptance.env
make observability-down ENV_FILE=.verify/acceptance.env
make reset ENV_FILE=.verify/acceptance.env
```

The exported observability port overrides above apply during teardown too.
`reset` deletes only this disposable project's newly created volumes; it must
never target the user's project. Actual cleanup result is recorded in the
verification report and command log. The user's original checkout and stack are
not part of teardown.

## Remaining work

Provide the documented real-model endpoint in an independently configured
checkout and rerun the blocked real-model steps, preserving this evidence.
No phase/demo box may be checked from these blocked results. Historical demo
PASS claims have not been rewritten or used to pass this run.

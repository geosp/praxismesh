# DSH research and probe matrix

## Scope

Evaluate DSH as the runtime executing agents, with Temporal around it. This is
separate from personal assistant installations and Skill Central. Research is
read-only: no upstream package was installed/executed, no model request was made,
and no production configuration changed. No compatibility check has passed yet.

## Upstream

Inspected official revision, 2026-11-14:
`39163dd30f703a79079e2d2446545cff3c453738`.
Freeze sources and artifacts together before live tests. The SDK source manifest
allows Python >=3.10 but declares a source-build version of 0.0.0.dev0. Select a
matching published SDK/runtime pair with recorded provenance or build that source
using upstream instructions; never equate an arbitrary wheel with this commit.

Pinned primary sources:

- [SDK manifest](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/python/sdk/pyproject.toml): package and Python constraints.
- [Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/python/sdk/README.md): subprocess client, explicit home, restoration and input routing.
- [Python API](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/python/sdk/src/deepseek_harness/api.py): synchronous API requiring a bounded async bridge.
- [SDK server](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/packages/sdk/server/README.md): protocol admission and approvals.
- [Model adapter](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/packages/llm/llm-pi-ai/README.md): self-hosted/OpenAI-compatible routes, model catalog and retries.
- [Agent loop](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/packages/core/agent-loop/README.md): lifecycle and request-admission extension points.
- [Tools](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/packages/core/tools/README.md): guards and cooperative cancellation.
- [Persistence API](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/packages/session/session-persistence/README.md): owned handles and flush barriers.
- [JSONL provider](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/packages/session/session-persistence-jsonl/README.md): durable files, interrupted writes and writer ownership.
- [Safety notice](https://github.com/deepseek-ai/deepseek-harness/blob/39163dd30f703a79079e2d2446545cff3c453738/SAFETY.md): experimental status and isolation limits.

SDK documentation describes restored history, not restored external processes.
High-level input can invoke native commands; a response timeout does not establish
cancellation. A full home may contain credentials/settings. Test these boundaries;
do not assume an explicit home alone prevents implicit workspace discovery.
Distinguish Python-visible controls from hooks requiring an in-process plugin.

No Python convenience method named cancel appeared in the inspected public
API/client method list. That does not establish absence of cancellation: inspect
the wire protocol and native hooks, then test cooperative stop and process cleanup.

## Existing seams

Local reference revision: `432519c8183fefa176aed6d1fe7de99addd3ad3b`.

| Source | Current behavior | Spike consequence |
| --- | --- | --- |
| harness_activity/runner.py, HarnessRunner | OpenAI SDK Session, pre-model callback and cumulative Usage | Session boundary needs evaluation beyond adding a runner class |
| harness_activity/activity.py, _run | SQLAlchemySession, truncation to checkpoint position, workspace snapshots | Establish equivalent DSH state position and acknowledgement barrier |
| Same file, before_model_call | Checks newer attempt, checkpoints and token budget | Prove request admission and authoritative-state fencing |
| harness_activity/config.py | Builds grants/model route from trusted template | Reject task-supplied grants and personal discovery |
| registry/loader.py | Supports only openai_agents in production | Keep prototype registration outside production |
| tests/test_runner_conformance.py | Runner/MCP/usage/outcome expectations | Reuse observable expectations in isolated probes |
| tests/benchmarks/run.py | Ten tasks; at most one lost task allowed | Preserve baseline, record candidate checks independently |

## Probe procedures

Every implemented probe needs a reproducible command, expected/observed output,
sanitized result and exact artifact/composition pins in the spike README.

| Contract | Procedure | Required evidence |
| --- | --- | --- |
| R1 | Record artifacts, source relation, platform, Python, digests, licenses and startup | Reproduction works or unavailable/mismatched prerequisites are blocked |
| R2 | Real local task with approved sample skill and disposable MCP fixture | Observe local request, skill use and allowed MCP call; no remote fallback |
| R3 | Poison discovery, submit native-command-shaped task text, request forbidden tools/plugins | Authority unchanged; forbidden execution rejected |
| R4 | Pause around flush, workspace snapshot and acknowledgement; kill worker; restore clean | Acknowledged pair restored without old disk |
| R4 | Interrupt after idempotent fixture commit but before result persistence | No duplicate fixture effect; boundary/limitations explicit |
| R4 | Hold old attempt while new one takes ownership | No authoritative checkpoint/outcome from superseded work |
| R5 | Stall provider/tool, cancel Activity, inspect processes after configured grace | Bounded stop and no surviving owned work |
| R6 | Count requests including retry/compaction at model boundary | Complete usage reconciliation and no admission after exhaustion |
| R7 | Explicit done/continue/needs-input plus malformed/error paths | Validated result mapping without free-text success inference |
| R8 | Same ten fixture checks; rerun current runner for context | Existing regression rule, all outcomes and comparison metrics recorded |
| R9/R10 | Inventory services/auxiliary work and all failed/blocked gates | Supported recommendation, no hidden durable coordinator |

Use uv for the separate Python project. Pin plugin-build tools separately; do not
add candidate dependencies to the production lockfile. Use explicit disposable
home/workspace/fixture storage and identify teardown paths before running. This
research host is Linux x86_64; that does not prove other worker-platform support.

Keep model and granted capability semantics comparable. Record both baseline and
candidate-added prompt sections and hashes rather than silently claiming identical
prompts. Any custom integration plugin must disclose its supported hooks and cost.
Stateful-process restoration, snapshot export and relocation remain questions for
execution, not claims established by these documents.

## Evidence and decision

R1–R7 and R10 are hard gates before adoption is recommended. Apply the existing
R8 regression rule without overwriting docs/benchmarks/baseline.json. Report time,
usage and complexity without inventing latency/cost tolerance. The owner assesses
those trade-offs after measurement; a failed hard gate cannot be traded away.

Missing dependencies remain blocked. Deterministic stubs establish control behavior
only; local-model execution and benchmark acceptance require the real endpoint.
Publish docs/spikes/dsh-harness.md with pins, reproduction commands, outcomes,
failure/recovery checks, teardown and limitations. A favorable result leads to a
separate ADR and migration plan covering session abstraction, checkpoint encoding,
worker packaging, capability policy, registry versioning and Phase 2 event mapping.
No production adoption is performed by this spike.

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

## Stop and cleanup policy

Before every probe, write a sanitized run manifest under the isolated spike's
verification output, freeze its digest with the tested code/configuration SHA,
and refuse to start if a field below is missing, nonpositive or inconsistent.
The manifest is a test input, not values reconstructed after the outcome.

| Field | Selection rule before execution |
| --- | --- |
| Probe identity | Run, root session, Activity attempt and composition/artifact digests |
| Effective limits | Actual selected profile/template limits and remaining task budgets; record the derived minima and units |
| Stop trigger | Model-step limit, wall deadline or explicit cancel; identify the trusted barrier that triggers it |
| Cleanup grace | 5 seconds after the trigger for owned runtime/child work to cease |
| Observation deadline | 10 seconds after the trigger; continue observing after early shutdown to detect restarted work |
| Owned work | Record process-group/cgroup identity and descendants; never signal unrelated processes by a reused PID |
| Clock and oracle | Independent monotonic observer timestamps and process/fixture observations, separate from candidate notifications |

Current local-default@1 has eight inner model turns, a ten-minute turn timeout,
and a 30-second heartbeat timeout; derive actual task-level minima from the
selected profile and remaining budget rather than copying those ceilings blindly.
Live-task probes retain those inherited limits. The deterministic stall fixtures
use a two-second wall deadline; the turn-limit fixture admits at most two model
steps. Explicit-cancel fixtures wait for independent request/tool-entry evidence,
then record and send cancellation immediately. Declare all overrides in the
manifest; no probe may silently widen production-derived ceilings.

Pass requires stopping owned work within the five-second grace and observing no
surviving/restarted work through the ten-second deadline. A runtime return or RPC
timeout alone cannot pass. If graceful cancellation fails, safely terminate only
the recorded disposable process group and mark R5 failed even if forced cleanup
succeeds. A surviving process or continued fixture operation is a failure.
The controller enforces the observation deadline even when the candidate hangs.
These are explicit spike control-test bounds, not a new production performance SLA.

## Independent usage ledger

All experiment model traffic must pass through a trusted observer outside the DSH
process: an instrumented local HTTP gateway in front of the deterministic provider
or approved vLLM endpoint. Restrict model egress to that gateway; reject alternate
routes. Inventory main, retry and auxiliary providers before running. Candidate
notifications are comparison data, never the ledger's authority.

The gateway records candidate ingress attempts (including denials) separately
from physical upstream provider dispatches, response dispositions and provider
usage. No unexpected ingress request may disappear from evidence. An admission
guard may live in the trusted bridge/gateway, but its decisions and location must
be explicit; it cannot turn dispatched work into an apparent denial afterward. A trusted fixture executor independently
records each admitted tool-body entry, including an execution that later errors;
model-proposed calls and denied calls are separate observations. Every granted
model-facing tool needs this execution observation; missing coverage fails R6.

| Quantity | Authoritative unit and reconciliation |
| --- | --- |
| Provider attempts | One upstream provider HTTP dispatch, including retries; keep denied candidate ingress attempts in a separate counter |
| Input/output tokens | Separate integer provider usage fields observed at the boundary; never add total_tokens again or double-count cache breakdowns |
| Tools | Admitted tool-body entries observed by the trusted fixture executor, not proposal count |
| Logical steps | Separate diagnostic identity; do not equate it with physical retry attempts |
| Correlation | Run/session/Activity-attempt plus gateway-issued physical-request ID; propagate a trusted logical-step/purpose tag where supported |
| Outcomes | Success, known pre-generation failure, cancellation or unknown usage, retaining all attempts |

Order ledger records by observer sequence. Match candidate counters and plugin
telemetry to request IDs or an explicitly unambiguous serialized fixture sequence;
reconcile sums for the complete root activity and any admitted descendants or
auxiliary requests. An unmatched request, ambiguous join, unobserved tool execution,
or unexplained nonzero difference fails the probe. Capture IDs, counts, hashes and
sanitized outcomes, not credentials or raw user transcripts.

Never convert missing usage to zero. Deterministic fixtures declare whether failure
preceded generation; live records without an authoritative usage result remain
unknown. Deny further model admission while unresolved usage prevents a safe budget
decision, and do not claim R6 passes with an unresolved accounting gap. Demonstrated
missing control/observability is a failed gate; infrastructure preventing evaluation
is blocked. A matching candidate self-report cannot resolve missing boundary data.

Required deterministic probes use scripted providers with independently known
usage; these establish control behavior, not real-model compatibility:

1. Exhaustion: budget 10 total input-plus-output tokens. The first response reports
   7 input and 3 output tokens and requires continuation. The next model admission
   must be denied; upstream provider-dispatch count stays exactly one, with any denied ingress attempts reported separately. A watchdog ends the
   probe and checks that no late request arrives during the observation window.
2. Retry: first dispatch fails before generation (fixture-proven zero usage), then
   one retry returns 7 input plus 3 output tokens. Expect two upstream provider dispatches,
   total usage 10, and denial of any third provider dispatch. Record any denied candidate ingress separately. Record retry and logical-step
   counts separately.
3. Auxiliary: after a separately recorded setup stage, force one known auxiliary
   request such as compaction with a fresh measured budget of 10. Its scripted
   usage is 4 input plus 6 output tokens. The same admission guard must prevent a
   subsequent main or auxiliary request; retain setup costs separately rather than
   hiding them. Failure to route this path through the observer is an R6 failure.

Record the expected request sequence and fixture responses in the pre-run manifest.
Exercise tool success, tool failure and policy denial to verify the separate tool
counter semantics. For live local runs, use the same gateway path and reconcile
observed provider usage; do not infer live counts from the deterministic fixture.

## Outcome checklist

Use existing harness_activity/tools.py and runner.py, orchestrator/workflow.py and
common/schemas/task.py as the reference semantics. Record the intermediate runner
outcome, Activity disposition and final task result separately.

- **O1 Explicit completion:** a validated finish_task completion produces runner
  done; the existing workflow can produce a succeeded TaskResult with valid refs.
- **O2 Continuation:** no explicit completion or an exhausted inner step allowance
  cannot turn arbitrary assistant text into success; preserve continuation and
  checkpoint semantics and validate the eventual workflow disposition separately.
- **O3 Needs input:** a validated needs-input completion preserves questions and
  maps through the existing workflow to needs_input.
- **O4 Invalid completion:** malformed status/payload/reference is rejected. A
  later valid correction may complete; the malformed payload itself cannot succeed.
- **O5 Error/retry:** classify model/protocol/infrastructure errors against the
  existing continuation/failure/retry contract; record the disposition without
  fabricating completion or replacing recoverable errors with immediate success.

## Benchmark comparison checks

- **B1 Identity:** the same ten existing task checks and selected local model;
  identify template/prompt/composition/hardware differences.
- **B2 Regression:** the preserved recorded baseline is 10/10; at most one lost
  task is the existing threshold, independent of mandatory hard gates.
- **B3 Completeness:** record every pass, failure and blocked task; an incomplete
  run cannot claim benchmark acceptance.
- **B4 Provenance and metrics:** retain original baseline files; record candidate
  pins, prompts/hashes, request/tool/token counts and wall time separately.

## Evidence and decision

R1–R7 and R10 are hard gates before adoption is recommended. Apply the existing
R8 regression rule without overwriting docs/benchmarks/baseline.json. Report time,
usage and complexity without inventing latency/cost tolerance. The owner assesses
those trade-offs after measurement; a failed hard gate cannot be traded away.

A demonstrated lack of a usable session/workspace barrier fails R4. If a missing
prerequisite prevents evaluating the barrier, mark it blocked rather than declaring
it absent. The report must identify which case occurred.

Missing dependencies remain blocked. Deterministic stubs establish control behavior
only; local-model execution and benchmark acceptance require the real endpoint.
Publish docs/spikes/dsh-harness.md with pins, reproduction commands, outcomes,
failure/recovery checks, teardown and limitations. A favorable result leads to a
separate ADR and migration plan covering session abstraction, checkpoint encoding,
worker packaging, capability policy, registry versioning and Phase 2 event mapping.
No production adoption is performed by this spike.

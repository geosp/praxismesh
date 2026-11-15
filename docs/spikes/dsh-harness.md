# DSH primary-harness compatibility evaluation

Date: 2026-11-14. Tracking: [issue #62](https://github.com/geosp/praxismesh/issues/62).
Contract: [approved implementation plan](../plans/2026-11-14-dsh-harness-evaluation/plan.md).

Phase 01 established an isolated, controlled DSH runtime. Phase 02 tested recovery,
bounded stop, usage accounting, TaskResult mapping and the ten-task benchmark; its
author-run results are in [Phase 02 results](#phase-02-results), corrected after
implementation review in [Round 1 corrections and rerun](#round-1-corrections-and-rerun).
The owner waived the second review round and independent verification, closed the
spike as a success and chose to adopt DSH through a separate ADR and migration plan.
No production replacement follows from this spike itself.

The sections before Phase 02 are the historical Phase 01 record and are unchanged.

## Reproduction and identity

Use the [spike README](../../spikes/dsh-harness/README.md) for setup, probes,
expected output and teardown. [artifacts.json](../../spikes/dsh-harness/artifacts.json)
records exact published wheels, native executable/sidecar and SDK source hashes,
container base/image IDs and platform. The isolated
[uv.lock](../../spikes/dsh-harness/uv.lock) pins transitive dependencies.

The research snapshot was `39163dd30f703a79079e2d2446545cff3c453738`.
Execution uses published SDK/runtime 0.2.2rc2, associated with official tag
[`dsh-v0.2.2-rc.2`](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.2.2-rc.2)
at `ddac96760b6edf8fa0fe17cbdcf0b512f4c12b2c`. The research snapshot is 614
commits ahead of that release. Relevant release SDK `api.py`/`client.py`
byte-match the installed wheel. This establishes source correspondence for those
files, not a verified source build of the native binary. PyPI provenance endpoints
returned 404; no build attestation is claimed. Runtime `--version` reported
`0.2.2-rc.2`; its carrier manifest reports `0.0.0-dev`.

Executed platform: Linux x86_64, CPython 3.11, Docker, unprivileged UID/GID 1000.
The SDK is imported and native runtime launched only in Docker. uv stages its
separate environment on the host. Production dependencies and registry are unchanged.

## Composition inventory

The release's [minimal profile](https://github.com/deepseek-ai/deepseek-harness/blob/ddac96760b6edf8fa0fe17cbdcf0b512f4c12b2c/packages/bundle/sdk-minimal/cordis.patch.yml)
is overlaid by [composition.yaml](../../spikes/dsh-harness/composition.yaml).
The following inventory distinguishes services present from model-visible tools.

| Component | Effective behavior in Phase 01 |
| --- | --- |
| SDK app/server, inventory, logging | Explicit `sdk-minimal`; disposable home; normal run completion API |
| LLM services, retry, token meter | Local pi-ai provider through gateway; provider retry count zero; DeepSeek provider disabled |
| Session, projection, JSONL persistence, checkpoint policy | Present; title generation disabled; durable recovery consistency untested |
| Agent/loop, native tool executor, system prompt | One root session, empty agent definitions, one parallel tool call; no child-agent tool |
| Timer and jobs services | Internal timer only; jobs service disabled; no competing durable coordinator exercised |
| Filesystem, sandbox, working-directory, attachment, subprocess and terminal services | Internal dependencies remain; workspace-write policy; file/directory and persistent shell tools disabled |
| Compaction/image offload | Disabled; auxiliary accounting probes belong to Phase 02 |
| Skill services | Only read-only granted `order-desk`; default roots and watching disabled |
| MCP client | Disposable stdio fixture; only price/stock tools; no database or order mutation |
| MCP resource tools | Disabled |

The corrected model-visible tool catalog is exactly `skill`,
`mcp__sample-shop__lookup_price` and `mcp__sample-shop__lookup_stock`.
Gateway admission and result validation reject any catalog or model change.
`auxiliary_inventory` in each manifest identifies disabled producers and the
bounds/accounting observation points for admitted internal timer, skill and MCP paths. These observations and the
profile inventory do not prove every latent service path is fully accounted for;
R6/R10 auxiliary reconciliation remains Phase 02 work. Temporal/PraxisMesh retains
production orchestration. This spike does not instantiate another durable coordinator.

The prompt includes the DSH minimal persona and skill catalog plus a trusted
ordinary-text prefix and the quote task as a separate data block. It does not use
the production `finish_task` prompt. Prompt request hashes are retained per run;
this task is not a benchmark comparison or TaskResult conformance result.

## Preliminary observations

The initial pre-review walkthrough below tested source commit
`6eec0b0d19580113477286b6cfbe627235d07ac3`. Sanitized
[run manifests/results](dsh-phase01-evidence.json) retain per-run source hashes,
artifact/configuration digests, gateway observations and fixture admissions.
Every container was absent after cleanup. These are execution results, not an
independent review or verification verdict.

| Probe | Outcome | Seconds | Completion requests | Container absent |
| --- | --- | --- | --- | --- |
| startup | pass | 1.268 | 0 | yes |
| catalog | pass | 2.166 | 1 | yes |
| capability | pass | 2.274 | 4 | yes |
| poison | pass | 2.102 | 4 | yes |
| denied-tool | pass | 2.353 | 2 | yes |
| native-text | pass | 2.049 | 2 | yes |
| local | pass | 8.854 | 3 | yes |

Repository checks passed: locked sync, Ruff lint/format, mypy (90 files), generated
agent sync, plan validation, and 165 tests (91 deselected integration tests). The
isolated controller suite passed 15 tests. The full root suite uses deterministic
fixtures; only the `local` walkthrough above establishes real-model capability.

| Probe | Required observation |
| --- | --- |
| startup | Real SDK/runtime initializes without provider traffic |
| catalog | Actual declared tool catalog reaches the boundary |
| capability | Scripted provider causes actual granted skill read and both MCP calls |
| poison | Workspace/home/user discovery poison absent from model context |
| denied-tool | Actual unknown-tool rejection, zero fixture tool-body entries |
| native-text | Command-shaped text reaches model as task data; no policy expansion |
| local | Real spark requests, skill read, both MCP calls, exact JSON quote |

The first real local attempt loaded the skill and executed price/stock, but its
final answer failed strict JSON parsing. It remains a failed attempt. Tightening
the instruction to require raw JSON produced a passing recheck. Completion text
alone is never evidence of Phase 02 TaskResult conformance.

Other exploratory failures were preserved in ignored local results: Docker's
default noexec tmpfs prevented native addon loading; a numeric UID with no home
caused a native cache failure; an early low-level idle event initially yielded
zero model requests. Remediation uses executable disposable scratch, a dedicated
account and supported high-level run completion with independent boundary evidence.
The zero-request result is invalid evidence, even though its old controller exited
zero. A regression test now rejects that case. The dependency environment was also
rebuilt from the lock after an overly broad lint invocation touched staged files;
artifact verification passed before subsequent execution.

## Remaining gates

Phase 01 independent review/verification and owner completion approval remain due.
Phase 02 has not started. Its approved tasks cover clean-worker session/workspace
recovery and side-effect/attempt fencing (R4), bounded stop (R5), independent
complete accounting (R6), explicit structured completion semantics (R7), the same
ten-task benchmark (R8), and the final recommendation (R9/R10). Missing prerequisites
must be blocked; a demonstrated missing runtime guarantee must be failed.

There is no new production harness adapter, schema, template version, event
mapping, ADR or change to the closed Phase 1 evidence in this spike.


## Approved review corrections

The owner approved all seven round-1 findings. The corrected controller verifies
all executable dependency bytes in a private read-only snapshot, fails on unknown
Docker state, and observes the full ten-second cleanup window. Host gateway sockets
and handlers are tracked and stopped; run manifests identify the exact UUID scratch
path. Title/jobs/resource producers are disabled. Config/plugin/provider poisons and
an attempted introduced plugin operation supplement skill discovery probes; both
the gateway and evidence oracle enforce the exact tool/model grants.

Seven regression tests failed before correction. Temporarily reverting each fix
made its own test fail; restoring the fixes returned the suite to green. The full
corrected suite has 22 tests. A second independently located locked uv install
reproduced the complete environment digest after canonicalizing RECORD entries
for unmounted launcher scripts. No executable source or native file is excluded.
Fresh frozen-run evidence and the final implementation review follow these changes;
the original pre-review results above remain preserved.

Corrected walkthrough source: `75a3746ba8159059070c1565f086fdf8db154b53`.
[Corrected manifests, results and mutation-test outcomes](dsh-phase01-corrections-evidence.json)
retain the original record separately. All seven probes passed; each container
was confirmed absent throughout observation, and all started host gateways stopped.

| Probe | Outcome | Completion requests | Cleanup observation seconds |
| --- | --- | --- | --- |
| startup | pass | 0 | 10.015 |
| catalog | pass | 1 | 10.014 |
| capability | pass | 4 | 10.016 |
| poison | pass | 5 | 10.034 |
| denied-tool | pass | 2 | 10.02 |
| native-text | pass | 2 | 10.016 |
| local | pass | 3 | 10.012 |

Corrected checks: 22 spike tests and 165 repository tests passed (91 integration
tests deselected); lint/format, mypy, locked sync, agent sync, plan validation and
offline links passed. The earlier artifact-hash gitleaks false positive remains
unresolved; scanner policy was not changed. Final independent review and
verification remain due.


## Second-round corrections and targeted validation

The owner approved the four additional findings from the final full review.
Mandatory cleanup precedes decoding of potentially truncated tool evidence;
result persistence follows in a protected finally block. Runtime code, composition, dependency files and the
complete granted skill tree execute from private verified snapshots; the host
gateway also loads its snapshot. Cleanup measures gateway and container shutdown
against one original stop trigger. The manifest digest identifies the exact saved
bytes, including the newline; earlier records retain their original hashing policy.

Eight targeted regression cases failed before implementation. The full isolated
suite now has 30 cases. Four temporary reversions each made the corresponding
regression fail. Both full review reports remain frozen, including the disclosed
correction-summary exposure. Subsequent review is limited to these four findings;
there is no third full review or claim that the earlier limitation disappeared.

Targeted walkthrough source: `8772f7d95f73f5325d5c79a79f56311c08650780`.
[Complete targeted evidence](dsh-phase01-targeted-evidence.json) retains both
real-model attempts as well as all deterministic probes and mutation checks.

| Probe | Outcome | Completion requests | Shared grace met | Observation seconds |
| --- | --- | --- | --- | --- |
| startup | pass | 0 | True | 10.014 |
| catalog | pass | 1 | True | 10.019 |
| capability | pass | 4 | True | 10.014 |
| poison | pass | 5 | True | 10.018 |
| denied-tool | pass | 2 | True | 10.065 |
| native-text | pass | 2 | True | 10.014 |
| local attempt 1 | fail: empty final answer | 3 | True | 10.012 |
| local attempt 2 | pass | 3 | True | 10.013 |

The first local run completed skill and tool use but returned an empty final
answer; its strict quote check failed. One unchanged recheck passed. Both runs had
the same first provider-request hash, so no prompt/composition adjustment explains
the recheck. This is evidence of intermittent final-answer behavior, not a claim
of stable local-model completion or Phase 02 TaskResult conformance. Both attempts
met cleanup checks. All 30 isolated tests, lint/format, mypy, locked sync, agent
sync, plan validation and offline links passed. Independent targeted review remains
due; the previous full review verdicts and the scanner false positive remain
preserved.


The [fresh targeted follow-up](../reviews/general-dsh-harness-evaluation/targeted-follow-up-01.md)
passed all four second-round corrections at
`33a532b2fd039e3d715dae6e64290190e84ecd2c`, with no residual correction-specific
findings. It inspected the committed evidence without executing the candidate.
This limited PASS preserves both earlier full-review verdicts and their stated
independence limitation. It does not establish independent runtime verification,
stable local-model completion, scanner clearance, phase closure or adoption.


## Scanner false-positive disposition

The owner approved a narrowly scoped reviewed exception. The installed SDK api.py
bytes match the recorded SHA-256. The new generic-api-key allowlist requires both
exact artifact-manifest path and the complete line containing that one digest.
It suppresses no other rule, path, changed digest or appended credential text.
The [artifact canary](../../.github/scripts/check_gitleaks_artifact_allowlist.py)
runs in CI beside the original schema canary. It verifies suppression of the exact
metadata line while detecting a changed digest, an added key, an appended key and
the same metadata line at another path. Temporarily broadening the exception to
OR made the canary fail; restoring AND passed. The existing schema canary also
passed. The feature-branch commit scan passed with no leaks using the corrected
configuration. Historical reports preserve their earlier unresolved scanner status.


## Initial independent execution verification

The initial fresh verification at aef22144d3e2a48af13cf921774ef6745e971af7
reproduced all seven probes on first functional attempts, 165 root tests and 30
isolated tests. Its verdict was fail because the as-built description incorrectly
placed result persistence before evidence decoding. The runtime correctly cleans
up first and persists afterward in finally. The initial report, both verifier
assessments and demo are preserved separately; no failed verdict is overwritten.

The author corrected that ordering and qualified current setup/verification text
about provenance, historical observations, executable tmpfs and disk requirements.
The historical source/experiment narrative and records remain here. No runtime,
test, manifest or acceptance behavior changed. Fresh verification of the corrected
published revision remains due.


## Corrected-revision independent verification

[Fresh independent verification](../reviews/general-dsh-harness-evaluation/verification.md)
passed at code_sha = docs_sha
`65d03f0fdb56d8939e99d67156ddea398185a21f`. Two fresh verifiers independently
reproduced acceptance and audited current as-built claims. All seven first-run
probes passed, including one real local-model quote; 165 repository tests and 30
isolated tests passed. All 11 hosted checks passed at that frozen revision.
[Demo evidence](../demos/general-dsh-harness-evaluation-01.md) and
[new raw result/manifest records](dsh-phase01-verification-evidence.json) preserve
observations and cleanup. Native build ancestry remains explicitly unestablished;
Phase 02 guarantees and stable workload reliability are not claimed.

The initial failed verification remains preserved. The earlier implementation
review-independence limitation still requires the owner's decision. No phase
closure, task completion checkboxes, production adoption or merge is recorded.


## Phase 01 completion

The owner accepted the documented procedural review limitation and authorized
closure after CI. All eleven evidence-head checks passed; the shared done gate
passed. Phase 01 is done (3/3 tasks), with the
[coordinator record](../reviews/general-dsh-harness-evaluation/closure.md)
identifying the waiver, passing evidence and exact source-equivalence boundaries.
Historical failed verdicts and local-model failures remain unchanged. Final
closure-record CI is a delivery prerequisite on PR63, which remains draft.

Phase 02 remains unstarted. This completion establishes the isolated controlled
runtime and authority probes; recovery, full accounting, cancellation, explicit
TaskResult outcomes, workload benchmark and adoption assessment remain future work.


## Phase 02 results

Frozen source: `2c900dbff72f016c12d6c5f621cd3b7c84430423`. Every probe below ran
once from that commit with a clean tree, back to back, on 2026-11-15. All 46 run
manifests name that commit. [Sanitized manifests, results and driver summaries](dsh-phase02-evidence.json)
retain request hashes, ledgers, tool-body entries and cleanup observations; the
repository root is replaced by `<repo>`, and a pinned gitleaks 8.30.1 scan found
no leaks. These are author-run results, not independent review or verification.
Reproduction commands are in the [spike README](../../spikes/dsh-harness/README.md).

Host: Linux x86_64, 32 CPUs, 46 GiB RAM. The runner checked between runs that
available memory stayed above 4 GiB, that no spike container remained and that the
source was still frozen; every check passed (about 40 GiB available throughout).

### Requirement status

| Req | Status | Evidence |
| --- | --- | --- |
| R1 Reproducible | pass, with limitation | Pins in artifacts.json and uv.lock; benchmark image adds pinned git. Native build provenance remains unestablished (Phase 01). |
| R2 Local capabilities | pass | Phase 01 `local` probe; ten real benchmark tasks used the local model, granted skill, shop tools and commands. |
| R3 No authority expansion | pass | Phase 01 poison, denied-tool and native-text probes; the benchmark gateway rejects any catalog or model change. |
| R4 Recovery | pass under the spike barrier | Clean-worker restore, one business effect after retry, superseded attempt fenced; `lost-after-finish` completes from the acknowledged finish. |
| R5 Bounded stop | pass | Stalled model/tool, cancelled model/tool and step limit all stopped cooperatively within 5 s; no surviving work through 10 s. |
| R6 Accounting | pass | Exhaustion, retry, auxiliary and tool probes reconciled; all ten live benchmark attempts reconciled, zero unknown usage. |
| R7 Result contract | pass | Twelve TaskWorkflow cases (O1–O5 plus lost-after-finish) gave the expected TaskResult. |
| R8 Benchmark | pass | 10/10 against the 10/10 baseline; 0 lost. |
| R10 Orchestration | pass | Temporal owns dispatch and retries; DSH jobs, child agents and auxiliary producers disabled except measured manual compaction. |

R9 is this report. No requirement failed or was blocked in the frozen run.

### Recovery, stop and accounting

| Probe | Result |
| --- | --- |
| recovery | pass; conversation and edit restored without the old worker's disk; 1 business effect; superseded attempt rejected |
| exhaustion | 1 dispatch (7+3 tokens), next admission denied |
| retry | 2 dispatches for 1 logical step, total 7+3, third dispatch denied |
| auxiliary | native compaction 4+6 tokens under a fresh budget of 10, then denied |
| tools | 6 dispatches, every granted tool observed by the trusted executor; ungranted call never entered it |
| stall-model, stall-tool | cooperative stop within grace; 10 s observation clean |
| cancel-model, cancel-tool | cooperative stop within grace; 10 s observation clean |
| step-limit | third step refused; cooperative stop within grace |

The checkpoint barrier is a spike mechanism, not a DSH API. The controller
holds the next model request, relies on DSH's checkpoint policy flushing earlier
results, pauses the container with one tool call in flight at most, then captures
`home/sessions/` and `workspace/`. Cancellation was delivered through the Temporal
SDK's Activity test environment, not a deployed worker's heartbeat transport.

### Outcome mapping

All twelve cases ran through the existing `TaskWorkflow`, orchestrator Activities,
Postgres and S3 on a unique queue prefix. Completion validation reuses the
production `finish_task` wrapper in the trusted host executor.

| Case | TaskResult |
| --- | --- |
| done | succeeded, artifact read back |
| plain-text, inner-limit | failed after six outer turns |
| needs-input | needs_input, question preserved |
| invalid-status, invalid-payload, invalid-reference | first completion refused; later valid completion succeeded |
| retry-model, retry-protocol, retry-infrastructure | succeeded after two attempts |
| bad-request | failed after one attempt |
| lost-after-finish | succeeded after two attempts; second attempt started no container and made no dispatch; lost attempt's 7+3 tokens kept |

### Benchmark

Same ten tasks and checks, `default` profile, `local-default@1` template, model
`spark` on the local vLLM endpoint. Template prompt hash matches the baseline
(`sha256:9de242ae…`). Baseline: openai-agents 0.24.0, recorded 2026-11-12;
`docs/benchmarks/baseline.json` was read, not written.

| Totals | Baseline | DSH candidate |
| --- | --- | --- |
| Passed | 10/10 | 10/10 |
| Tokens in / out | 140,774 / 9,741 | 162,409 / 12,340 |
| Tool calls | 105 (harness count) | 96 (executed tool bodies) |
| Model dispatches | not recorded | 65 |
| Wall time | 225 s | 415 s |

Every task finished in one turn and one attempt. Differences the comparison does not
control for:

- DSH adds its `sdk-minimal` system prompt; the template prompt is a trusted first-turn input, not per-call instructions.
- Tools are presented over MCP with an `mcp__task__` prefix. File and shop tools run on the host; commands run in the container through `docker exec`.
- Each model request pauses the container for a checkpoint. This and `docker exec` add integration overhead to wall time.
- Tool counts measure different things.

The plan sets no latency or cost threshold; these figures are for owner judgement.

### Failures and corrections before the frozen run

All are retained in ignored `.runs/` records.

- The Phase 01 gateway's eight-request cap ran before admission. In a live
  benchmark run, t01's ninth request was refused without a recorded step denial, and
  the bridge classified inner-step exhaustion as a retryable failure instead of
  continuation. Fixed in `287e574`; a regression test pins it. t08 later exercised
  the corrected continuation path live.
- The bridge restarted the model after an already acknowledged finish, and a lost
  attempt's usage dropped out of the turn total. Both now follow the production
  Activity (`6fb6a4a`).
- The first t01 smoke run failed with an unexplained Temporal `RPCError` from the
  result wait; its native attempt was then cancelled by driver shutdown. It did not
  recur.
- Chained long runs on a 15 GiB host (before a BIOS change to the GPU memory
  reservation) left the desktop unresponsive. No kernel OOM event was recorded.
  Task containers are now limited to 512 MiB and one CPU, successful attempt trees
  are removed, and drivers refuse to start below 4 GiB available.

### Recommendation

The evidence supports **writing a separate adoption proposal**: an ADR and a
migration plan. It does not support adopting DSH now. Every hard gate passed in
this isolated spike, and the benchmark met the regression rule. Before an adoption
decision, the proposal should address:

- **Independent confirmation.** These results need the phase's independent review
  and verification.
- **Preview runtime.** DSH 0.2.2rc2 is a release candidate, upstream calls it
  experimental, and native build provenance is unestablished.
- **Checkpoint barrier.** Consistency depends on a spike mechanism (held request,
  checkpoint-policy flush, container pause). Production needs a supported DSH
  export/flush contract or an equivalent reviewed barrier.
- **Integration work.** Session abstraction and checkpoint encoding, worker
  packaging with a container per attempt, capability presentation over MCP,
  registry harness versioning, and Phase 2 event mapping.
- **Cost.** About 15% more input tokens and roughly 1.8× wall time in this
  integration, partly from spike overhead.
- **Deployment cancellation.** It is tested through the SDK test environment only.

Adoption, any production change, and the ADR are owner decisions outside this spike.

### Teardown

Each run removed its container and host gateway, executor and fixture threads, and
confirmed absence for ten seconds. No spike container remained after the frozen
run. Successful task-attempt scratch trees were removed; failed ones remain under
the ignored `.runs/` directory. Production deployment, registry, templates and the
benchmark baseline are unchanged.


## Round 1 corrections and rerun

The [implementation review](../plans/2026-11-14-dsh-harness-evaluation/reviews.md)
of `bc4227c` requested changes: 10 Majors, 23 Nits. The main point was that the
results above claimed R4, R6 and R7 more broadly than the bridge enforced, and
that retry, loss and multi-attempt paths never ran live. The fixes are in
`d2d782c`, each with a regression test in `test_task_policy.py`:

- Usage: heartbeats keep settled tokens while a request is in flight; every
  failure path records ledger totals; unknown usage is classified before exit
  codes and never retried; an exhausted turn reports its totals.
- Ownership: claims follow the Temporal turn/attempt order; a superseded attempt
  writes no attempt row, artifact or publication.
- Checkpoints: a pair is acknowledged only when the newest tool-call ID is in
  DSH's session files; checkpoint limits are not retried; workspace snapshots
  skip links and the skill mount, as production does.
- Skill: DSH's skill plugins are disabled. The template bundle is mounted and
  indexed as in production and read through the executor's `read_file`, so every
  skill read is observed. DSH's own skill loader is therefore not evaluated.
- Stop: SIGTERM must stop the container within 5 s or the attempt fails; new
  `deadline` and `cancel` cases run through `TaskWorkflow` and a real worker.
- Manifests are validated before launch; ceilings come from the template.

Every probe was rerun once from `d2d782c` with a clean tree; all 50 manifests name
that commit. [Sanitized evidence](dsh-phase02-r2-evidence.json); pinned gitleaks
found no leaks. The earlier evidence file is kept unchanged.

| Group | Result |
| --- | --- |
| Recovery, 4 accounting, 5 bounded-stop probes | all passed |
| Outcome cases through `TaskWorkflow` | 14/14 passed, including `lost-after-finish`, `deadline`, `cancel` |
| DSH benchmark | 10/10, 0 lost; 11 attempts, all reconciled, zero unknown usage |
| Production runner, same day | 10/10 (openai-agents 0.24.0), recorded in `docs/benchmarks/2026-11-15-local-default.*` |

| Totals | Production runner, 2026-11-15 | DSH candidate |
| --- | --- | --- |
| Tokens in / out | 123,169 / 9,793 | 159,526 / 12,009 |
| Tool calls | 97 | 112 executed tool bodies, 28 of them skill reads |
| Wall time | 223 s | 419 s |

t01 used a second outer turn after reaching the step limit, through the corrected
continuation path. Evidence scope, stated plainly:

- R4 passes under the spike barrier (held request, session-marker check,
  container pause). It is not a DSH-provided export API.
- R5 cancellation was tested through the SDK test environment and one real worker
  on a local Temporal server, not a deployed multi-host worker.
- Live loss of a request mid-generation has unknown usage and stops the turn
  (fail-closed); production would retry it.
- The second review round and independent verification were waived by the owner.

Owner decision, 2026-11-15: the spike is closed as a success, and DSH adoption
proceeds through a new ADR and a reviewed migration plan.

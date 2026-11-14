# DSH primary-harness compatibility evaluation

Date: 2026-11-14. Tracking: [issue #62](https://github.com/geosp/praxismesh/issues/62).
Contract: [approved implementation plan](../plans/2026-11-14-dsh-harness-evaluation/plan.md).

The isolated runtime can execute the local quote task with the granted skill and
MCP tools. This is preliminary Phase 01 evidence. Recovery, cancellation, complete
accounting, TaskResult mapping and benchmark suitability have not been established.
No adoption recommendation or production replacement follows from these results.

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

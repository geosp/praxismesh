# DSH primary-harness compatibility spike

Isolated experiment for [issue #62](https://github.com/geosp/praxismesh/issues/62)
and the [approved contract](../../docs/plans/2026-11-14-dsh-harness-evaluation/plan.md).
Production dependencies, templates and dispatch remain unchanged.

## Candidate selection

The artifact inventory records research snapshot
39163dd30f703a79079e2d2446545cff3c453738, selected matching Python SDK/runtime
version 0.2.2rc2, and the dsh-v0.2.2-rc.2 source-tag association at
ddac96760b6edf8fa0fe17cbdcf0b512f4c12b2c. These are candidate-selection metadata;
this spike does not independently establish native binary build provenance.
Artifact identities and digests are recorded in artifacts.json and uv.lock.

Upstream code runs only in the disposable Docker environment. The isolated uv
project stages dependencies; it does not activate a user DSH installation. No
upstream binary or populated home is committed. Generated run state is ignored.

## Reproduce Phase 01

Run from the repository root on Linux x86_64 with glibc >= 2.28, Python 3.11,
uv and access to a Docker daemon. Reserve disk for staged dependencies,
the container image and one private dependency copy per simultaneous probe. The runtime has a bundled Node executable and rg sidecar;
no system Node, pnpm or plugin build is needed for this composition.

```bash
uv sync --project spikes/dsh-harness --locked --python 3.11
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/preflight.py
docker pull python@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
docker build --network none --build-arg SPIKE_UID="$(id -u)" --build-arg SPIKE_GID="$(id -g)" --iidfile /tmp/praxis-dsh-image-id spikes/dsh-harness
spike_image=$(cat /tmp/praxis-dsh-image-id)
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py startup --image "$spike_image"
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py capability --image "$spike_image"
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py poison --image "$spike_image"
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py denied-tool --image "$spike_image"
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py native-text --image "$spike_image"
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_probe.py local --deadline 180 --image "$spike_image"
```

The image content ID, source commit/file hashes, skill-tree hashes, composition, lock and selected
limits are frozen in `.runs/praxis-dsh-*-manifest.json` before candidate startup.
Each `.runs/<case>-*.json` result references SHA-256 of the exact persisted
manifest bytes, including their final newline. Rebuilt images
may have a different content ID; pass the trusted local build ID explicitly.
Without `--image`, the controller uses the exact image in artifacts.json.
Unavailable/mismatched dependencies or images prevent a successful run.
Preflight hashes every mounted dependency file; installer RECORD entries for
unmounted launchers are canonicalized, as documented in artifacts.json. Missing or mismatched executable bytes block startup.

Only `local` calls a real model. It reads `VLLM_BASE_URL` and optional
`VLLM_API_KEY` from the environment or ignored `infra/.env` as data, accepts only
private/loopback addresses, and requests model `spark`. Configure the existing
local vLLM deployment first. There is no hosted fallback. The actual key remains
in the host gateway; the candidate receives a fixture-only key. Neither model
endpoint values nor keys belong in evidence.

All other model responses are deterministic scripts. They exercise the real SDK,
runtime, skill loader and MCP client, but establish control behavior only.
Expected outcome: exit 0 and a JSON record with observed boundary requests,
tool-body entries and `container_absent: true`. `startup` has no model requests;
`catalog` is an additional one-request discovery probe.

## Isolation and limits

The container has no IP network, host credentials or Docker socket. It mounts
only a verified private dependency snapshot, four verified snapshot code/config files, the snapshotted granted
`order-desk` directory, and one disposable state directory. The dependency snapshot is a sibling of that
state directory and is never exposed through its writable mount. Bytecode caches
are excluded and Python uses a separate empty scratch cache prefix. Code,
composition and the complete skill tree are also copied into private snapshots
and checked against the pre-run manifest. Docker and the host gateway load those
snapshots; later edits to source directories do not change the run. Its root is read-only;
capabilities are dropped; no-new-privileges, 1 GiB memory, two CPUs and 128 PIDs
are enforced. A dedicated unprivileged account has a disposable real home.
Scratch tmpfs is executable in this composition; input snapshot mounts stay read-only.

A loopback relay forwards only fixed model paths through the run's Unix socket.
The host boundary permits at most eight completion requests and only the trusted
configured endpoint. The two MCP tools operate on in-memory fixture prices/stock.
Title generation, jobs, MCP resource tools, compaction and image offload are
disabled. The gateway enforces the exact three-tool catalog and spark model.
There is no order mutation, shell, subagent or scheduling tool. The quote test
deliberately uses a subset of the production template's capabilities.

The controller bounds each run by its declared wall deadline. It closes and joins
the host gateway listener, handlers and provider sockets, attempts container
removal within the remaining five-second grace, then observes the exact
container name through the ten-second window. Both bounds use the same original
stop-trigger timestamp, including time spent shutting down the gateway. Absence requires a successful Docker daemon listing; daemon
errors are unknown state and fail the run. Mandatory cleanup and result
persistence run independently of tool-log decoding; truncated or invalid evidence
marks the result failed after teardown. Forced
cleanup cannot turn a failed/deadline run into a pass. This is **not** the Phase 02
R5 cancellation/barrier-injection test or the R6 token-budget test.
The full Phase 02 stop oracle is explicitly marked pending. No heartbeat or
Temporal Activity is launched in Phase 01.

## Phase 02 recovery probe

```bash
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_recovery.py --image "$spike_image"
```

This scripted-provider probe exercises the pinned native SDK/runtime and MCP client.
Its separate `recovery-composition.yaml` grants only three recovery fixture tools.
The controller hashes this overlay before execution and stages all Python files
in the same verified private code snapshot. The candidate mounts that snapshot
read-only. It never mounts the host authority database.

The controller holds the model request following a workspace edit. The pinned
[checkpoint policy](https://github.com/deepseek-ai/deepseek-harness/blob/ddac96760b6edf8fa0fe17cbdcf0b512f4c12b2c/packages/session/session-checkpoint-policy/README.md)
flushes the preceding results before that request reaches the adapter. With one
tool at a time and auxiliary producers disabled, pausing the container freezes
the remaining candidate writers. The controller captures only `home/sessions/`
and `workspace/`, checks the conversation marker and edit, and acknowledges the
pair in a host-owned SQLite transaction with `synchronous=FULL`.

Worker-loss injection kills the exact owned container before releasing the held
response. Each replacement deletes the preceding worker's writable state and
restores only the acknowledged pair into a new directory. It calls the public
`resume_session` API. The gateway observes the restored conversation, while the
trusted fixture executor checks the actual restored note contents.

A second interruption holds an idempotent effect's response after its business
transaction commits. Retrying from the acknowledged pair enters the body again
but leaves one business effect. A further attempt is superseded while its tool
response is held; the tool's final ownership check and bridge checkpoint/outcome
publications reject that old attempt. Attempt and operation identities are bound
by host-created fixture endpoints, not supplied by the model.

The JSON manifest/result records live under `.runs/`. The probe closes host
gateway/executor threads and observes their absence along with the owned
container for ten seconds after each injected loss. Successful scratch trees
are removed; failed scratch trees remain for diagnosis. This R4 fixture is not
a Temporal cancellation test, a structured TaskResult adapter, or benchmark
acceptance. Those are separate Phase 02 tasks.

## Phase 02 accounting probes

Run these sequentially using the same pinned image:

```bash
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_accounting.py exhaustion --image "$spike_image"
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_accounting.py retry --image "$spike_image"
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_accounting.py auxiliary --image "$spike_image"
spikes/dsh-harness/.venv/bin/python spikes/dsh-harness/run_accounting.py tools --image "$spike_image"
```

A host gateway records every ingress and a separate HTTP fixture records provider
dispatches. A serialized guard refuses further dispatch after token exhaustion or
unresolved usage. Unknown usage remains unknown. The gateway buffers bounded
responses to settle their usage before releasing them to DSH. The full candidate
stream still reaches the SDK; buffering is an integration difference.

Exhaustion admits one response with 7 input and 3 output tokens under a budget of
10. Retry enables one native provider retry: the first fixture dispatch fails
before generation, then the retry consumes 7+3 tokens. Both physical attempts
belong to the same logical step; later ingress denials stay in the ledger.
Only the independently recorded fixture failure may establish zero usage.

The auxiliary composition enables manual compaction, with automatic compaction
disabled, 1024 tokens of headroom, a 128-token summary output cap and one retained
token. Three completed setup turns are counted under a separate budget. The
controller then admits one native `/compact` request under a fresh budget of 10;
its response reports 4+6 tokens. A subsequent main request must be refused.
All remaining auxiliary producers stay disabled.

The tool probe separately exercises a missing-note failure, three successful body
entries covering every granted tool, and an ungranted-tool proposal refused by
DSH without entering the fixture executor. Its budget is 1000 tokens. SDK
`assistant/message` usage events are reconciled with provider totals, including
setup and compaction. Embedded copies of usage in stream events are diagnostic
only; they are never added again. Native completion here ends a control probe;
arbitrary assistant text does not establish a succeeded TaskResult.

## Phase 02 bounded execution probes

These controllers use the repository's trusted root uv environment for Temporal's
SDK; the candidate SDK still runs only in Docker. Run sequentially:

```bash
uv run python spikes/dsh-harness/run_bounds.py stall-model --image "$spike_image"
uv run python spikes/dsh-harness/run_bounds.py stall-tool --image "$spike_image"
uv run python spikes/dsh-harness/run_bounds.py cancel-model --image "$spike_image"
uv run python spikes/dsh-harness/run_bounds.py cancel-tool --image "$spike_image"
uv run python spikes/dsh-harness/run_bounds.py step-limit --image "$spike_image"
```

Stalled calls have a two-second deadline measured from independent provider or
tool-body entry. The tool fixture also starts a child Python process inside the
candidate namespace. The step guard admits two model steps and refuses the next.
Cancellation cases launch the candidate inside a Temporal SDK Activity context,
heartbeat every 50 ms, then call `ActivityEnvironment.cancel()` immediately after
independent entry observation. This tests SDK Activity cancellation delivery; it
does not test a deployed worker's heartbeat transport or server-side scheduling.

The bridge sends SIGTERM to the exact owned container. Its Python driver handles
that signal by calling the public SDK `close()` method, which attempts runtime
shutdown before bounded termination. A pass requires the container to disappear
cooperatively within five seconds. Forced removal afterward cannot establish a
pass. The controller then closes host fixture resources and observes all owned
work through the same ten-second window, using the original stop timestamp.
Failed results and disposable diagnostic trees stay under `.runs/`.

Only the deterministic fixture can prove zero generation cost for an interrupted
request held before generation. Other missing usage stays unknown and closes
further admission. These stop probes do not establish structured completion or
benchmark acceptance.

## Phase 02 structured outcome probes

These run the existing `TaskWorkflow`, orchestrator Activities, Postgres and S3
from local infrastructure, with an isolated DSH implementation of
`run_harness_turn` on a unique `dsh-spike-*` queue prefix. Production workers
never receive these tasks. Run sequentially from the repository root:

```bash
uv run --env-file infra/.env python spikes/dsh-harness/run_tasks.py all --image "$spike_image"
```

The candidate receives none of the host environment. Its only task tool is
`finish_task`, whose catalog and validation come from the existing
`harness_activity/tools.py` wrapper running in the trusted host executor.
Scripted provider responses cover O1–O5 in the plan's outcome checklist:

| Case | Expected TaskResult |
| --- | --- |
| done | succeeded, one trusted artifact ref read back from S3 |
| plain-text, inner-limit | failed after six outer turns; text or invalid completion never succeeds |
| needs-input | needs_input with the question preserved |
| invalid-status, invalid-payload, invalid-reference | first completion refused; a later valid completion succeeds |
| retry-model, retry-protocol, retry-infrastructure | succeeded after exactly two Temporal attempts |
| bad-request | failed after one attempt; invalid input is non-retryable |

The bridge acknowledges a paused-container session/workspace pair before each
model admission and publishes the finish record under the attempt fence. Only
host-produced files become artifact refs; model-supplied refs are rejected.
Unknown usage cannot be published as zero tokens. Each attempt follows the
same cleanup and observation policy as the bounded probes.

## Checks and cleanup

```bash
spikes/dsh-harness/.venv/bin/python -m pytest -c spikes/dsh-harness/pyproject.toml spikes/dsh-harness/test_probe.py spikes/dsh-harness/test_corrections.py spikes/dsh-harness/test_final_corrections.py -q
PYTHONPATH=spikes/dsh-harness uv run pytest -q -p no:cacheprovider spikes/dsh-harness/test_completion.py
uv run ruff check --no-respect-gitignore --exclude '' spikes/dsh-harness/*.py
uv run ruff format --check --no-respect-gitignore --exclude '' spikes/dsh-harness/*.py
```

Normal teardown removes the named container and its run home/workspace/socket.
It retains ignored result/manifest JSON. After a controller crash, identify the
exact container from its manifest and use `docker rm -f <that-container-name>`;
use the exact `scratch_directory` recorded in that manifest after it stops.
UUID-named directories are never reused. Unknown cleanup state preserves the directory.
To reset the entire disposable spike environment, remove this spike's `.venv/`
and `.runs/` after confirming no spike containers or gateway processes remain. Do not prune Docker or
remove unrelated images, volumes, homes or deployment state.

Observed results, failed attempts and remaining work are in the
[spike report](../../docs/spikes/dsh-harness.md). Phase 01 remains subject to
independent review and verification; production adoption is a separate decision.

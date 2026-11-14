# DSH primary-harness compatibility spike

Isolated experiment for [issue #62](https://github.com/geosp/praxismesh/issues/62)
and the [approved contract](../../docs/plans/2026-11-14-dsh-harness-evaluation/plan.md).
Production dependencies, templates and dispatch remain unchanged.

## Candidate selection

The inspected research snapshot is 39163dd30f703a79079e2d2446545cff3c453738.
The published matching Python SDK/runtime pair selected for Phase 01 is
0.2.2rc2, associated with the official dsh-v0.2.2-rc.2 source tag at
ddac96760b6edf8fa0fe17cbdcf0b512f4c12b2c. This is a separately identified
release candidate, not a claim that the published wheels were built from the
research snapshot. Source evidence is refreshed against the release before use.
Artifact identities and digests are recorded in artifacts.json and uv.lock.

Upstream code runs only in the disposable Docker environment. The isolated uv
project stages dependencies; it does not activate a user DSH installation. No
upstream binary or populated home is committed. Generated run state is ignored.

## Reproduce Phase 01

Run from the repository root on Linux x86_64 with glibc >= 2.28, Python 3.11,
uv and access to a Docker daemon. Allow about 1 GiB for staged dependencies and
the container image. The runtime has a bundled Node executable and rg sidecar;
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

The image content ID, source commit/file hashes, composition, lock and selected
limits are frozen in `.runs/praxis-dsh-*-manifest.json` before candidate startup.
Each `.runs/<case>-*.json` result references that manifest digest. Rebuilt images
may have a different content ID; pass the trusted local build ID explicitly.
Without `--image`, the controller uses the exact image in artifacts.json.
Unavailable/mismatched dependencies or images prevent a successful run.
Preflight hashes every mounted dependency file; installer RECORD entries for
unmounted launchers are canonicalized, as documented in artifacts.json. A clean
locked install into a second directory reproduced the same environment digest.

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
only a verified private dependency snapshot, four reviewed code/config files, the granted
`order-desk` directory, and one disposable state directory. The dependency snapshot is a sibling of that
state directory and is never exposed through its writable mount. Bytecode caches
are excluded and Python uses a separate empty scratch cache prefix. Its root is read-only;
capabilities are dropped; no-new-privileges, 1 GiB memory, two CPUs and 128 PIDs
are enforced. A dedicated unprivileged account has a disposable real home.
Native addon loading requires executable scratch tmpfs; other mounts stay read-only.

A loopback relay forwards only fixed model paths through the run's Unix socket.
The host boundary permits at most eight completion requests and only the trusted
configured endpoint. The two MCP tools operate on in-memory fixture prices/stock.
Title generation, jobs, MCP resource tools, compaction and image offload are
disabled. The gateway enforces the exact three-tool catalog and spark model.
There is no order mutation, shell, subagent or scheduling tool. The quote test
deliberately uses a subset of the production template's capabilities.

The controller bounds each run by its declared wall deadline. It closes and joins
the host gateway listener, handlers and provider sockets, attempts container
removal within five seconds, then observes the exact container name through the
ten-second window. Absence requires a successful Docker daemon listing; daemon
errors are unknown state and fail the run. Forced
cleanup cannot turn a failed/deadline run into a pass. This is **not** the Phase 02
R5 cancellation/barrier-injection test or the R6 token-budget test.
The full Phase 02 stop oracle is explicitly marked pending. No heartbeat or
Temporal Activity is launched in Phase 01.

## Checks and cleanup

```bash
spikes/dsh-harness/.venv/bin/python -m pytest -c spikes/dsh-harness/pyproject.toml spikes/dsh-harness/test_probe.py spikes/dsh-harness/test_corrections.py -q
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

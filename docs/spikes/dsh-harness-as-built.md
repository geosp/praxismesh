# DSH Phase 01: as-built verification inputs

This document describes the isolated spike's implemented behavior. Its companion
[README](../../spikes/dsh-harness/README.md) supplies setup, probe commands and
teardown. The contract is
[Phase 01](../plans/2026-11-14-dsh-harness-evaluation/phases/01-controlled-runtime.md).
It makes no claim about production adoption or completion of Phase 02.

## Components and data flow

The host controller runs one disposable Docker container per probe. The candidate
Python SDK launches its bundled native DSH runtime inside that container. DSH
loads the pinned sdk-minimal profile and the trusted composition overlay. The
host imports no DSH SDK/runtime module.

The container has no IP network. Its local HTTP relay accepts only the fixed
model routes and forwards through a run-specific Unix socket. The host gateway
either produces explicitly scripted test responses or forwards to the configured
private/loopback vLLM endpoint. Only the `local` case uses that endpoint, selecting
model `spark`. There is no hosted fallback.

The granted `order-desk` skill and stdio MCP fixture implement the quote task.
The fixture exposes only `lookup_price` and `lookup_stock`, using disposable
in-memory values; SKU-1 has unit price 12.5 and stock 3. It records admitted tool
body entries. It neither accesses a business database nor places orders.

Production dispatch, Temporal Workflows/Activities, registry templates/locks,
schemas and the completed runtime Phase 1 evidence are unchanged. No Temporal
Activity, heartbeat, independent durable scheduler or child agent is launched.

## Artifact and authority boundaries

The separate uv project pins SDK/runtime 0.2.2rc2 and transitive dependencies.
artifacts.json identifies the release/source relationship, native binaries,
platform and container base. Preflight verifies individual critical artifacts and
the complete mounted dependency tree. Bytecode caches are excluded and use a new
scratch prefix; RECORD entries for unmounted launcher scripts are canonicalized.

Code, configuration, dependencies and the complete skill-file tree are copied
into private snapshots and validated against the manifest. Docker mounts only
read-only snapshots and one writable disposable state directory. The host gateway
also imports its code snapshot. Editing original inputs after staging cannot
change the candidate's mounted inputs. Changed copied inputs fail validation.

The root is read-only, Linux capabilities are dropped, no-new-privileges is set,
and memory, CPU and PID limits apply. A dedicated unprivileged account uses a
disposable home. Scratch tmpfs is configured executable in this composition.
Host credentials and the Docker socket are absent from the candidate.

Only three model-visible tools are admitted: `skill`,
`mcp__sample-shop__lookup_price` and `mcp__sample-shop__lookup_stock`. The gateway
and result oracle reject changed tool/model catalogs. Default skill discovery is
disabled. Command-shaped task text follows a trusted ordinary-text prefix in a
separate data block. Poison fixtures exercise skill/config/plugin/provider input;
the introduced tool operation is rejected.

Title generation, jobs, MCP resource tools, compaction and image offload are
disabled. Agent definitions are empty; shell/file tools are disabled. Internal
timer and admitted skill/MCP paths have bounds/accounting observation points in
the run manifest. Full auxiliary accounting is Phase 02 work.

## Outcomes, observation and teardown

Each manifest identifies the source commit, file/skill/artifact/composition hashes,
image, run identity, exact scratch path and limits before candidate startup. Its
digest covers the exact persisted UTF-8 bytes, including the final newline.
Each result records that digest and boundary/tool observations without endpoint
values, credentials or raw model transcripts.

The SDK's supported high-level completion mechanism and actual boundary/tool
evidence determine probe outcomes; an initial idle event cannot establish success.
Quote probes require the exact raw JSON result. Completion without the expected
JSON fails the quote check. Reliable completion and TaskResult conformance remain
Phase 02 questions; a successful quote does not establish those guarantees.

The wall deadline bounds candidate execution. Gateway and container cleanup share
the original stop-trigger clock, a five-second grace and a ten-second observation
window. Successful daemon listings establish container absence; errors are unknown
state and fail cleanup. Owned gateway sockets/handlers are closed and joined.
Cleanup precedes evidence decoding. Result persistence runs afterward in a
protected finally block, so malformed logs cannot skip teardown or prevent a
failed result from being recorded. Invalid evidence fails the recorded result. Forced cleanup does not
convert a timeout/failure to success. Unknown/live state preserves its scratch path
for explicit recovery. Normal teardown removes only this run's container/state.

These are Phase 01 controls. Consistent recovery, idempotent effects, attempt
fencing, cancellation injection, complete token accounting, explicit TaskResult
mapping and the ten-task benchmark have not been established.

## Independent verification prerequisites

Use a clean disposable checkout and the README's documented Linux/Python/uv/Docker
prerequisites. Configure the existing local model through `VLLM_BASE_URL` in the
verification process environment. An operator may supply that non-credential URL
as a scratch input and load it into the environment without printing it. Do not
copy a deployment `.env`, credentials, or populated runtime homes into the checkout.
If authentication is required but no authorized credential is available, mark
the real-model step blocked. No mock substitutes for that step.

Run the root checks from AGENTS.md, the isolated regression suite, startup,
capability, poison, denied-tool, native-text and local probes. The optional catalog
case provides a one-request discovery check. Capture commands, versions, exact
expected/observed outcomes and cleanup observations. Preserve any failed attempt;
do not silently retry until a passing result appears. Keep evidence scoped to
this spike and retain the distinction between scripted controls and real-model work.

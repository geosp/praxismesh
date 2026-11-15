# Notes · Run production agents on DSH

## D2

| Spike module | Production role |
| --- | --- |
| `task_policy.py` | failure classification, heartbeat progress, attempt order, manifest validation |
| `usage_ledger.py`, `task_boundary.py` | gateway admission and usage ledger |
| `recovery_boundary.py` (`ToolExecutor`), `bench_tools.py` | executor with production tool and skill semantics |
| `recovery_store.py` | barrier capture, mapped onto checkpoint rows and blobs |
| `task_activity.py` | `DshRunner` and the attempt lifecycle |

The spike's frozen evidence (`docs/spikes/dsh-phase02-r2-evidence.json`) is the
expected behaviour for each ported case.

## D3

| Option | Grant needed | Why not chosen |
| --- | --- | --- |
| Paired DSH container per worker (chosen) | none | - |
| Container per attempt via Docker socket | Docker socket | root-equivalent on the host |
| Container per attempt via socket proxy | proxy with create/remove rights | one more privileged component to secure |
| Per-attempt Pod | namespace-scoped RBAC | Kubernetes only; the MVP runs on Compose |
| LXC/Incus per attempt | Incus API | second host runtime; still needs start rights |
| Docker-in-Docker | privileged container | privileged |

Compose settings the pair needs: `cgroupns: private`, a writable cgroup v2 subtree
for the launcher, a tmpfs-backed attempt volume, `network_mode: none` and a
read-only root for the DSH container.

Fallback if cgroup freeze is unavailable: SIGSTOP the attempt's process group. Its
limit: a process that leaves the group escapes the freeze, so commands must not be
able to `setsid` (the separate UID and a seccomp profile enforce it).

## D6

Trigger: every model request after the first one of an attempt.

1. The gateway holds the request. DSH's checkpoint policy flushes earlier tool
   results to session files before sending a request (Assumptions).
2. The newest tool-call ID in the request must appear in the session files.
3. The launcher freezes the attempt cgroup.
4. The worker captures the session blob and workspace, then commits the
   checkpoint row through the D10 fence.
5. The cgroup is thawed and the request released.

A failed barrier writes no checkpoint and is a retryable infrastructure failure.

## D7

The migration is additive:
- `task_attempts.tokens_in/tokens_out` become nullable; `usage_known boolean not null default true`;
- `usage_ledger(task_id, turn, attempt, request_id, dispatched_at, input_tokens, output_tokens, settled_at)`;
- `checkpoints.session_ref jsonb null, session_digest text null`; `session_position` stays an integer (0 for DSH).

`usage_known` is added to `Progress`, `TurnOutcome`, `ExecutionAttempt` and
`TaskResult`. Deploy order: migration, orchestrator, then workers. Rolling code back
below this migration is not supported.

## D9

The gateway writes a `usage_ledger` row before dispatch and settles it on the
response. The next attempt of a turn finds unsettled rows from earlier attempts,
sets `usage_known = false` on their attempt rows, and charges each unsettled
request `context_window + max_tokens` (both from the template). This replaces
the spike's fail-closed admission denial.

## R14

DSH features turned off, by composition id (spike `composition.yaml`):
`jobs`, `session-title`, `mcp-resources`, `compaction-basic`, `image-offload`,
`tool-fs`, `tool-working-directory`, `persistent-bash`, `persistent-pwsh`, the
`dsh-skill*` plugins, `agent-loop.agents: []` (no delegation) and
`includeDefaultRoots: false` (no discovery).

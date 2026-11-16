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

Compose settings the pair needs: `cgroupns: private`, `cap_add: [SYS_ADMIN]` (for the
launcher only), `no-new-privileges`, `apparmor:unconfined` (so AppArmor on Ubuntu hosts
does not block the launcher's cgroupfs remount and private mount namespace; commands drop
all capabilities and get the seccomp filter), a tmpfs-backed attempt volume,
`network_mode: none` and a read-only root for the DSH container.

### Probe result (phase 01 task 0.1, 2026-11-15)

`infra/dsh/isolation-probe.sh` (run command in its header) in the pinned Python
base image, Docker on Fedora (cgroup v2, SELinux enforcing). Rerun after review
round 1 with tree-level checks:

| Check | Default caps | `SYS_ADMIN` |
| --- | --- | --- |
| Remount cgroupfs rw, create sub-cgroup, freeze and `cgroup.kill` a 3-process tree | no | yes |
| SIGSTOP a process group (every member in state `T`) | yes | yes |
| Command UID via `setpriv` | yes | yes |
| Per-attempt mount namespace (`unshare -m`) | no | yes |
| Command with all caps dropped: cannot escape cgroup, cannot mount, no effective caps | - | yes |
| Command cannot create a user namespace | - | **no** |

Phase 02 task 1.1 (2026-11-15): in the DSH image (`infra/dsh/Dockerfile`), with the
launcher's seccomp filter applied to commands, all 13 probe checks pass, including
`command_userns_blocked`.

Docker rejects `--sysctl user.max_user_namespaces=0`. Conditions for phase 02:
- the launcher alone holds `SYS_ADMIN`;
- every command runs through `setpriv --inh-caps=-all --bounding-set=-all --no-new-privs` as a separate UID;
- the launcher installs a seccomp filter on each command that rejects `CLONE_NEWUSER`
  in `clone`/`unshare` and makes `clone3` return `ENOSYS`;
- the probe's user-namespace check must then pass.

Fallback if cgroup freeze is unavailable: SIGSTOP the attempt's process group. Its
limit: a process that leaves the group escapes the freeze, so commands must not be
able to `setsid` (the separate UID and a seccomp profile enforce it).

## D4

Commands run as UID 4242 with every capability dropped, `no_new_privs`, the seccomp
filter blocking new user namespaces, and a private mount view that shows only their
own workspace (as `/work`) and a per-attempt `/tmp` (impl-review F63). The image adds
no packages beyond the granted `cli_tools` to its pinned base; the base's userland
stays, and the command check reads only the first word, so the boundary is the UID,
capabilities, seccomp and mount view, not the binary list (F89).

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
`TaskResult`. An attempt row holds the turn's cumulative usage through that attempt:
NULL tokens when one of its own requests (or, for a lost attempt, one up to it) was
never observed; numbers with `usage_known = false` when they include a D9 charge
(impl-review F69). A turn that fails for good, is cancelled or runs out of attempts
charges its own unsettled requests, since no later attempt will (F59).

Deploy order: migration, orchestrator, then workers. Rolling code back
below this migration is not supported.

## D9

The gateway writes a `usage_ledger` row before dispatch and settles it on the
response. The next attempt of a turn finds unsettled rows from earlier attempts,
sets `usage_known = false` on their attempt rows, and charges each unsettled
request the template's `context_window` as input and the DSH composition's per-request
output cap (2048 tokens, `DSH_MAX_OUTPUT_TOKENS`) as output. The gateway clamps every
request's `max_tokens` to that cap, so the charge bounds what a request can have used.
A turn that ends with no later attempt (cancel, a non-retryable failure, attempts
exhausted) charges its own unsettled rows (impl-review F59). The count is derived from the
ledger rows each time, so a later attempt charges the same amount even if the attempt
that first closed them was lost. This replaces the spike's fail-closed admission denial.

## R14

DSH features turned off, by composition id (spike `composition.yaml`):
`jobs`, `session-title`, `mcp-resources`, `compaction-basic`, `image-offload`,
`tool-fs`, `tool-working-directory`, `persistent-bash`, `persistent-pwsh`, the
`dsh-skill*` plugins, `agent-loop.agents: []` (no delegation) and
`includeDefaultRoots: false` (no discovery).

## D10

- The lock is `pg_advisory_xact_lock(hashtext(task_id))`, taken by `start`, the fenced
  checkpoint insert, the fenced finish, `assert_current` and `record_refusal`.
- `record_refusal` inserts its `refused` row under the lock without the newer-attempt check;
  `close_unfinished` is unfenced but touches only rows at or below the writer.
- Artifact references exist only in the `TurnOutcome` that `_finish` returns after the fenced
  finish succeeds. A stale attempt may still upload audit artifact blobs that nothing
  references: `assert_current` before upload is an early exit, not a guarantee.

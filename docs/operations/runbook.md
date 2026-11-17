# Operations runbook: agent harnesses

How to deploy the DSH harness, switch the `default` profile between DSH and
`openai_agents`, and handle a DSH worker that refuses to serve. Background:
[DSH migration plan](../plans/2026-11-15-dsh-production-harness/plan.md),
[ADR-0005](../adr/0005-adopt-dsh-as-primary-agent-harness.md),
[ADR-0006](../adr/0006-per-attempt-isolation-boundary-for-dsh.md).

## What runs where

| Profile | Harness | Template | Workers (Compose) |
| --- | --- | --- | --- |
| `default` | `dsh` | `local-dsh` | `dsh-a`/`worker-dsh-a`, `dsh-b`/`worker-dsh-b` |
| `dsh` | `dsh` | `local-dsh` | the same two pairs |
| `openai` | `openai_agents` | `local-default` | `worker-a`, `worker-b` |

A task's template is fixed when it is submitted. Changing a profile never moves
a running task to another harness.

Each DSH pair is a worker and its DSH container sharing one attempt volume
(`dsh-attempts-a`, `dsh-attempts-b`), which no other service mounts. A pair
runs one attempt at a time. DSH tasks take about 1.9x the wall time of
`openai_agents`, so `default` needs both pairs.

## Deploy

In this order:

1. Apply database migrations: `make migrate`. Migration 0004 and later are
   required by both harnesses.
2. Restart the orchestrator, then build and start every worker:
   `make workers-up`. This starts the orchestrator, `worker-a`, `worker-b`, and
   both DSH pairs, and builds the DSH image (`praxismesh-dsh:dev`).
3. Check: `make status`, then one task per profile:

   ```bash
   make task PROFILE=default PROMPT="Order 3 units of SKU-1 and write order-summary.md." OUTPUT=order-summary.md
   make task PROFILE=openai  PROMPT="Order 3 units of SKU-1 and write order-summary.md." OUTPUT=order-summary.md
   ```

   The result's `template` is `local-dsh` for the first and `local-default` for
   the second.

**Code rolls forward only.** The harness seam, the attempt fence and workflow
cancellation changed the `openai_agents` path too. Fix forward rather than
reverting the code, and never run code older than migration 0004 against a
database that has it. To move work off DSH, switch the profile (below); don't
deploy older code.

## Switch `default` to another harness, and back

A profile switch is a registry edit, not a code change. The same steps switch
to DSH and revert to `openai_agents`.

1. **Pause submissions.** A profile resolves twice: when the task is submitted
   (from the submitter's checkout) and again in the orchestrator. Both must
   have the new registry before a task is submitted on `default`.
2. **Edit** `registry/profiles/default.yaml`:

   | Target | `harness` | `allowed_templates` |
   | --- | --- | --- |
   | DSH (current) | `dsh` | `[local-dsh]` |
   | `openai_agents` (revert) | `openai_agents` | `[local-default]` |

3. **Lock:** `make registry-lock`. The lock records template hashes only, so a
   profile edit leaves it unchanged; it matters if a template changed too. CI
   fails on a stale lock.
4. **Rebuild and restart:** `make workers-up`. The registry ships in the worker
   image, so this rebuilds it and restarts the orchestrator and the workers
   whose image changed.
5. **Update the submitters' checkouts** to the same commit, then resume
   submissions.
6. **Check** with one `make task PROFILE=default ...`: its `template` is the new
   one.

Tasks already running keep their template and finish on the harness they
started on. Leave that harness's workers up until they drain (below).

Step 4 restarts every worker, the DSH workers too. An attempt in flight is lost
and retried on the restarted worker from its last checkpoint, with no repeated
side effect; the lost attempt's usage is charged conservatively, so that task's
result reports `usage_known: false` (plan D9).

## Drain

A task's workflow checks its deadline only before a turn, so a task can run for
its profile's wall time plus one last turn's `schedule_to_close`
(6 × `turn_timeout`). For `local-dsh` today that is 30 min + 60 min = **90
minutes** after the last task was submitted on it.

Before stopping a harness's workers, check that no task resolved to its
template is still open, in the Temporal UI or with `make task-status ID=...`.
Stopping the DSH pairs early leaves those tasks waiting on `tpl.local-dsh`
until the pairs return.

## A DSH worker that refuses to serve

A DSH worker serves only while its DSH container is reachable, clean and
reports the runtime digests pinned in `registry/registry.lock`. Otherwise it
refuses without spending an attempt and stops polling:

| When | What you see |
| --- | --- |
| At start-up | the worker exits 1 with a `CapabilityError` naming the template |
| During a turn | the worker logs "worker cannot serve its queue" and exits 3 |

Compose restarts it, and it keeps refusing until the cause is fixed: **watch
for either restart loop** (`make logs`, or `docker compose ps` showing a
restarting `worker-dsh-*`).

Causes and fixes:

- **Pin mismatch**: the DSH image was built from other requirements or control
  files than the lock pins. Rebuild with `make workers-up` from the same commit
  as the registry, or relock after an intended DSH upgrade.
- **Dirty container**: leftover attempt processes, cgroups or attempt trees.
  Restart the DSH container (`dsh-a` or `dsh-b`); its attempt volume is tmpfs,
  so nothing survives the restart.
- **Unreachable launcher**: the DSH container is down or still starting. Start
  it; its worker recovers on the next restart.

A refusing pair takes no tasks, so the other pair carries the load. With both
refusing, `default` and `dsh` tasks wait on the queue until a pair recovers or
`default` is switched back.

## Known deviations

Deferred on purpose; none blocks operation (plan notes.md#rollout):

- An `unresolved usage` denial starts no exit timer (impl-review F103).
- A stale attempt's usage charge writes usage columns without the fence (F106).
- Launcher replies to `poll` have no timeout (F111).

## Follow-up: the upstream checkpoint barrier

Checkpoint consistency uses PraxisMesh's own barrier (plan D6): before each
model request after the first, the gateway holds the request, checks that the
newest tool call reached DSH's session files, freezes the attempt, captures and
commits the checkpoint, then releases it. This relies on DSH flushing tool
results to session files before each request, which DSH does not document.

When upgrading DSH:

- Rerun the plan's R18 outcome cases (`tests/integration/test_dsh_outcomes.py`)
  before changing the pin. A change in flush behaviour shows up as failed
  barriers: retryable infrastructure failures with no checkpoint.
- If a release ships a supported flush or export API, replace the barrier with
  it (ADR-0005 condition 2) through a new plan.
- Refresh the licence notices: `uv run .github/scripts/check_dsh_licences.py export`.

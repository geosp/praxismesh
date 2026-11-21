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
runs one attempt at a time. DSH tasks took about 1.3x the wall time and input
tokens of `openai_agents` in the same-day benchmarks of 2026-11-17, so `default`
keeps two pairs, as it had two `openai_agents` workers.

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

1. **Pause submissions, then let the last ones start.** A profile resolves
   twice: when the task is submitted (from the submitter's checkout) and again
   in the orchestrator, when the workflow starts. Both must have the new
   registry before a task is submitted on `default`. A task submitted just
   before the pause but not yet resolved by the orchestrator fails for good if
   the new registry rejects its template, so wait until every recent task shows
   its first attempt (`make task-status ID=...`) before step 4.
2. **Edit** `registry/profiles/default.yaml`:

   | Target | `harness` | `allowed_templates` |
   | --- | --- | --- |
   | DSH (current) | `dsh` | `[local-dsh]` |
   | `openai_agents` (revert) | `openai_agents` | `[local-default]` |

   In the same pull request (changes reach `main` only through one), update
   what states which harness `default` runs on:
   - `tests/test_registry.py::test_default_profile_runs_on_dsh`, which pins
     the switch; CI fails until it matches;
   - the header comment of `registry/profiles/default.yaml`;
   - the profile table at the top of this runbook and the "Profiles" row in
     `docs/architecture/overview.md`;
   - a line in `docs/roadmap/decision-log.md` with the reason.
   - comments that say which harness `default` runs on: find them with
     `git grep -n "default" -- registry/profiles infra Makefile` (today: the
     three profile files, `infra/docker-compose.yml`, `infra/demo/worker-loss.sh`
     and the `Makefile` worker targets).

3. **Lock:** `make registry-lock`. The lock records template hashes and the
   DSH runtime digest, not profiles, so a profile edit leaves it unchanged; it
   matters if a template changed too. CI fails on a stale lock.
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
minutes**, counted from the task's first turn; add the few seconds its first two
Activities take after submission.

Before stopping a harness's workers, check that no task resolved to its
template is still open, in the Temporal UI or with `make task-status ID=...`.
Stopping the DSH pairs early leaves those tasks waiting on `tpl.local-dsh`.
A waiting turn fails its task after `schedule_to_close` (6 × `turn_timeout`,
60 minutes for `local-dsh`) unless a pair returns first. Switching `default`
back does not move them: their template was fixed when they were submitted.

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
  Restart the DSH container (`dsh-a` or `dsh-b`). Its launcher removes leftover
  attempt trees, cgroups and processes when it starts. (The attempt volume is
  tmpfs, but restarting only the DSH container does not clear it, because its
  worker keeps it mounted.)
- **Unreachable launcher**: the DSH container is down or still starting. Start
  it; its worker recovers on the next restart.

A refusing pair takes no tasks, so the other pair carries the load. (`dsh-b`
depends on `dsh-a` only so that Compose builds the shared image first; a
running `dsh-b` does not need `dsh-a`.) With both
refusing, `default` and `dsh` tasks wait on the queue until a pair recovers, and
a waiting turn fails its task after `schedule_to_close` (60 minutes for
`local-dsh`). Switching `default` back helps only tasks submitted after the
switch.

## Agent events

Every harness attempt, on either runner, publishes its events to the event table
(migration 0005; [ADR-0009](../adr/0009-use-a-postgresql-event-table-for-agent-events.md),
[Phase 2 events plan](../plans/2026-11-18-phase-2-agent-events/plan.md)). Offsets are
per task (the workflow ID is the task ID), start at 1 and have no gaps.

```bash
./agentctl tail TASK_ID                 # follow live; stops once the Workflow has closed
./agentctl tail TASK_ID --after 120     # resume after offset 120
./agentctl tail TASK_ID --no-follow     # print what is stored and exit
./agentctl events prune --task TASK_ID --below 500       # delete offsets below 500
./agentctl events prune --task TASK_ID --older-than 7d   # delete the oldest events, up to the first newer than 7 days
./agentctl events prune --task TASK_ID --below 500 --dry-run  # print what would go
```

`agentctl` runs the CLI with `infra/.env` (`ENV_FILE=...` selects another file).
Each line is `offset<TAB>attempt<TAB>type<TAB>payload`. A line
`expired: events before N were pruned` means the reader asked for events that
`prune` removed; reading continues at N. Each attempt starts with a `reset`
naming the checkpoint it restored from, so the events after an earlier
attempt's last checkpoint are superseded by the new attempt's.

`events prune` is a removal like `gc` (see [Removing data](#removing-data)): it holds the
removal lock, prunes in batches of at most 500 events, each with a tombstone, and marks
the pruned events' blob references. `gc` prunes a task's events 30 days after it ended.
Deploy: `make migrate` (0005) before restarting the harness workers; running tasks need
no drain, because `TaskWorkflow` did not change.

If the database cannot store an attempt's last events, the attempt fails with
the retryable `EventsUnavailable` and writes no finish; Temporal retries the turn.

## Messaging between tasks

Tasks of one request can message and ask each other through the `comms` MCP server
([Phase 2 messaging plan](../plans/2026-11-18-phase-2-events-and-comms/plan.md)). The
templates `local-dsh` v2 and `local-default` v2 grant it.

**Setup.** The server connects as the `praxis_comms` role, which may write only
`task_messages` and `message_wakes`. Set `PRAXIS_COMMS_DB_PASSWORD` (and `PRAXIS_COMMS_DB_URL` for tests run on the
host) in `infra/.env` as in `infra/.env.example`. A fresh database volume creates the role
at init; on an existing volume, recreate the `db` container so it sees the password
(`make up`), then run `make db-roles` (safe to rerun) and `make migrate` (0006).
Without the password the role is skipped and comms tools fail.

**Joining a request.** `./agentctl task submit --join REQ ...` puts the new task in request
`REQ`, which must already have a task; its tasks can then message each other.

**Waiting tasks.** A task whose turn ends `waiting` stays open: its Workflow sleeps until a
message (an `inbox` Signal from the dispatcher in the orchestrator worker), a question's
deadline, its idle timeout (profile `idle_timeout`, default 10 min; only while it has no open
question) or its wall-time budget. After a Signal or a question's deadline it claims its
inbox again and runs a woken turn when the inbox has rows. At the idle timeout the task ends
`succeeded` without claiming; its unread messages then become `undelivered`, which their
senders see in `get_task_context`, and unanswered questions to it are cancelled, which wakes
their askers. At the wall-time deadline one last claim decides: no open
question ends it `succeeded`, an open one `failed`. Woken turns count against `max_wakes`
(default 50, capped by the template's `max_wakes_cap`). If the dispatcher is down, wake rows
wait in `message_wakes`; deadlines and timeouts still fire.

**Deploying the change.** Stop submitting and let running tasks finish, because workers
serve one template version and the v2 templates replace v1. Then `make db-roles` and
`make migrate`. Start the orchestrator worker first, so that a `waiting` turn always meets a
Workflow that accepts it: `docker compose -p praxismesh --env-file infra/.env -f
infra/docker-compose.yml --profile workers up -d --build --wait orchestrator` (use your
project name), then `make workers-up` for the rest. `make workers-up` alone starts every
worker at once.
To roll back, drain every task started on the new code first (cancel waiting ones with
`temporal workflow cancel`): the old code cannot replay their histories. Then delete
leftover `message_wakes` rows and redeploy the old workers.

## Removing data

Stored data has a retention class and a lifetime ([Phase 3A persistence
plan](../plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md), D3): `ephemeral`
1 day after it was written; from the task's end, `checkpoint` 7 days, `transcript` 30
days and `artifact` 90 days; `audit` (tasks, attempts, usage and the audit log) is kept.
Nothing is removed on its own: an operator runs the commands below. Each prints its plan
with `--dry-run`, which changes nothing. A dry run holds the locks of the rows it would
change until it ends, so uploads and checkpoints of the same tasks wait for it; its plan
leaves out the bucket deletes a real run first finishes for an earlier, stopped run.

```bash
./agentctl gc --dry-run                      # what has expired, by reason
./agentctl gc                                # remove it
./agentctl request delete REQ --dry-run      # what deleting request REQ would remove
./agentctl request delete REQ                # delete it
./agentctl request delete REQ --force        # also a task left running by a closed Workflow
```

**`gc`** removes expired rows (checkpoints, sessions, messages, events and the rest, by
their class), the blob references that expired with them, and every blob left with no
live reference. Uploads of a task that never got a row (no worker picked it up) go only
after 24 hours and only if Temporal reports its Workflow missing or closed, so a queued
task keeps its inputs. A bucket object with no reference at all goes once its last upload
is more than 24 hours old. A bucket object whose key is not a content key
(`sha256/<hex>`) is never removed; `gc` lists it as `unrecognised`. `gc` refuses while a
stored reference is not in the index; the message names the repair (`agentctl reconcile
--reindex`, added in phase 03).

**`request delete REQ`** removes what the request's tasks hold: checkpoints, events,
sample orders, inbox rows, and every blob nothing else still holds (identical bytes are
stored once, so a blob another task or a pending upload holds stays). It redacts content to `[deleted <date>]`: task
summaries, questions and failure reasons, message bodies, agent conversation items and
tool results; artifacts are emptied. Task IDs, statuses, attempts and usage stay. It works
on the tasks the request had when it started; a task that joins meanwhile waits and is
untouched. A delete that stopped partway is finished by running it again, with its own task
list; only once it has completed does a new delete pick up tasks that joined since. It
refuses while a task has not ended. `--force` treats such a task as ended, setting it
`failed`, but only if Temporal reports its Workflow closed (terminated, cancelled, timed
out) or no longer knows it; a running Workflow is always refused. The plan (`--dry-run`),
the report and the first tombstone list each forced task as `closed` or `missing`: if a
task you believe is running shows `missing`, check that `agentctl` points at the right
Temporal (`TEMPORAL_PORT`, `TEMPORAL_NAMESPACE`) before going on. After a delete, no attempt
of its tasks writes anything: checkpoints, events, messages, conversation items and tool
results are refused (each task gets a `deleted` attempt row), and an upload revives nothing. Temporal keeps each
turn's summary, questions and outcome in its histories for `TEMPORAL_RETENTION` (72 hours)
and in backups taken before; that is not rewritten (threat model).

**The lock.** `gc`, `request delete` and `events prune` hold one lock for their whole
run. A second one started meanwhile fails at once with "another gc, request delete, events
prune or backup is running"; run it again later. If an agent is writing a message for a
task of the request, the delete waits briefly and retries; if it keeps writing, the delete
stops having changed nothing and says to try again.

**What an expired read means.** A blob that was removed reads as expired, with the date:
`agentctl task output` prints `error: blob sha256/... expired: removed on <date> UTC`
instead of "not found". After a delete, `task output` reports the task has no outputs.

**Tombstones.** Every batch a removal commits (at most 500 rows) writes a row to
`audit_log` in the same transaction: the action (`gc`, `request.delete`, `events.prune`),
the subject (`task:...`, `request:...`, `orphans`), the operation ID shared by the run, and
counts of rows, references and blobs removed, never content. The app role cannot change or
delete these rows.

**A run that stopped partway** (killed, or the bucket unreachable) is safe to run again:
removals commit before the bucket is touched, and the next run first deletes the objects an
earlier run marked (reported as `finished_from_earlier_runs`), then carries on. Nothing is
counted twice.

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

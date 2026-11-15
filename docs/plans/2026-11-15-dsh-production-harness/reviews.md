# Reviews · Run production agents on DSH

## 2026-11-15 · design-review · plan · round 1 · changes-requested

Reviewers: fresh reader completed · codebase fit completed · zoom out completed · structure 0 errors, 0 warnings.

| ID | Sev | Reviewer | Place | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| F1 | Blocker | fresh reader | Decisions › D6 | The barrier's three parts (held request, session marker, pause) are named but never explained, so R3 and the top risk can't be judged. | open |
| F2 | Blocker | fresh reader | Decisions › D2 | What is ported ("ordered ownership", "`task_policy.py` classification") lives only in notes.md#d2; the plan doesn't state it. | open |
| F3 | Major | codebase fit, zoom out | R1, Impact, phase 01 › 2.1 | `dsh` must be added to the `Harness` Literal (`common/schemas/base.py:10`) and to `schemas.md`, and logged in the decision log. Profiles also carry `harness` and `resolve` requires it to match the template, which contradicts R1. Where the DSH image or release is pinned is undefined. | open |
| F4 | Major | codebase fit, zoom out | phases 02–03, Impact | No task selects the runner by harness (`workers/main.py:84` always builds `OpenAIAgentsRunner`) or adds a `tpl.local-dsh` worker, Docker access or an image build to Compose. | open |
| F5 | Major | codebase fit, zoom out | D3, Assumptions, Risks | Compose workers keep scratch on a private tmpfs (`infra/docker-compose.yml:129`), so a sibling container can't bind-mount the attempt tree or the gateway's Unix socket. Where they live is undecided. | open |
| F6 | Major | zoom out, codebase fit | Risks › Docker access; phase 02 › 1.1 | "Scope it to one image" can't be enforced on a raw Docker socket, and a preflight digest check doesn't limit the socket. The plan doesn't adopt the socket-proxy or other option from notes.md#d3. | open |
| F7 | Major | zoom out, codebase fit | R3, R4, Risks; phase 02 › 2.3 | When a real worker dies, the daemon-owned DSH container survives. No requirement or task covers orphan removal. | open |
| F8 | Major | codebase fit, fresh reader | R5, Impact | Usage is a non-null `int` default 0 everywhere (`task.py:77-78`, `0003_phase1_tables.py:68`), so "unknown" can't be represented without a schema change or migration. This contradicts "attempt rows unchanged". | open |
| F9 | Major | zoom out | R3 vs R5 | Worker loss mid-generation leaves usage unknown. The spike fails closed, while R3 expects the turn to resume. The production behaviour (retry vs fail, and how the budget counts it) is undecided. | open |
| F10 | Major | codebase fit, zoom out | D1, Impact › Data; phase 01 › 1.1 | Where DSH session state lives in a checkpoint (workspace tarball vs new column) and what `session_position` means for DSH are undecided. The seam omits checkpoint capture/ack, `HarnessRunner.run` takes an Agents SDK `Session`, and the conformance suite is hardwired to `OpenAIAgentsRunner`. | open |
| F11 | Major | codebase fit | Assumptions; phase 03 › 1.1 | The benchmark and test helpers hardcode `local-default`/`default` (`tests/benchmarks/run.py:47,58`; `tests/support/workers.py:20`). No task adds a DSH profile or a `--template`/`--profile` option. | open |
| F12 | Major | zoom out, fresh reader | Rollout & rollback; phase 03 › 2.2 | The plan omits deploy order, draining in-flight `tpl.local-dsh` tasks, and the fact that `openai_agents` can't resume DSH checkpoints. Rollback means two fields (`harness` and `allowed_templates`), not one line. | open |
| F13 | Major | fresh reader | Summary | The Summary omits R8, the R9 and owner gate on the default switch, and the Docker-access dependency and privilege risk. | open |
| F14 | Major | fresh reader | Why, R2, R3, R9 | Undefined: the "five adoption conditions", "stale attempt", "lost" task, and the "baseline rule" (which baseline R9 compares against). | open |
| F15 | Major | fresh reader, codebase fit, zoom out | R8, phases | The event interface has no decision on shape or location and no clear owning phase. It should reuse `AgentEvent` (`schemas.md:15`) and stay a minimal sink for Phase 2. | open |
| F16 | Major | fresh reader, codebase fit | R7 | Pass criteria are "matches the spike's expected result", but those results aren't in the plan. Name the case IDs in `dsh-phase02-r2-evidence.json`. | open |
| F17 | Major | fresh reader | R4 | The grace period's length is undefined, and so is how the 5 s stop bound relates to the 10 s observation. | open |
| F18 | Major | fresh reader | Assumptions, Open questions | "Phase 02 is blocked" has no fallback, yet Open questions says "None". The owner's cost and latency call is also effectively open. Plan "phase 02" reads like roadmap "Phase 2". | open |
| F19 | Nit | zoom out | Risks › cost; phase 03 | `local-dsh@1` sets no timeouts despite about 1.9x wall time (`local-default`: `turn_timeout PT10M`, `max_wall_time_cap PT1H`). | open |
| F20 | Nit | zoom out | phase 03 › 2.1 | "Registry lock updated" is the wrong check: profiles aren't in the lock, and the lock changes in 1.1. | open |
| F21 | Nit | codebase fit | phase 03 › 2.2 | "The runbook" doesn't exist yet (`docs/operations/runbook.md` is planned for Phase 9). | open |
| F22 | Nit | codebase fit | phase 02 › 2.2 | The plan doesn't say whether the DSH conformance tests (which need Docker and the image) run in CI, are marked `integration`, or skip. | open |
| F23 | Nit | codebase fit | phase 01 › delivers | Phase 01 lists R2, but no task in it runs the benchmark, so R2 is really delivered in phase 03. | open |
| F24 | Nit | zoom out | D2 | Module placement for the gateway, executor and barrier is unstated (`harness_activity/` is implied). | open |
| F25 | Nit | zoom out | docs/adr/README.md | The ADR index lists 0001–0003 only. | open |
| F26 | Nit | fresh reader | R1, R3, R4, R5, R6 | Several requirements hold more than one rule. Split them. | open |
| F27 | Nit | fresh reader | Summary, Non-goals, D5, Rollout, Risks | Repeated facts (`openai_agents` stays selectable, the gated switch, the control-case rerun) and minor undefined terms (`finish_task`, profile, comms MCP, attempt tree, "the owner"). | open |

## 2026-11-15 · design-review · round 1 · resolutions

| ID | Resolution |
| --- | --- |
| F1 | fixed: D6 steps 1-5 |
| F2 | fixed: D2 lists the ported rules |
| F3 | fixed: R1, R2, Impact, phase 01 tasks 2.1-2.3 |
| F4 | fixed: phase 02 tasks 1.2, 1.3 |
| F5 | fixed: D3 shared attempt volume and sockets |
| F6 | fixed: D3 paired container, no Docker access (socket proxy rejected) |
| F7 | fixed: R7, D3 launcher reaping, phase 02 tasks 1.1, 2.3 |
| F8 | fixed: D7, R9, Impact, phase 02 task 2.1 |
| F9 | fixed: D9, R9 |
| F10 | fixed: D1 session blob and position, phase 01 task 1.1 |
| F11 | fixed: phase 03 task 1.1 |
| F12 | fixed: Rollout & rollback, phase 03 task 2.2 |
| F13 | fixed: Summary |
| F14 | fixed: Why table, Terms |
| F15 | fixed: D8, R11, phase 01 task 3.1 |
| F16 | fixed: R13 names the cases |
| F17 | fixed: R6 |
| F18 | fixed: Open questions; roadmap Phase 2 naming; Docker fallback moot under D3 |
| F19 | fixed: phase 03 task 1.1 |
| F20 | fixed: phase 03 task 2.1 |
| F21 | fixed: phase 03 task 2.2 |
| F22 | fixed: phase 02 task 2.2 |
| F23 | fixed: phase 01 delivers |
| F24 | fixed: D2 |
| F25 | fixed: docs/adr/README.md |
| F26 | fixed: R1-R14 split |
| F27 | fixed: Terms; repeats removed |

## 2026-11-15 · design-review · plan · round 2 · changes-requested

Reviewers: fresh reader completed · codebase fit completed · zoom out completed · structure 0 errors, 1 warning.

| ID | Sev | Reviewer | Place | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| F28 | Blocker | zoom out, fresh reader | D9, R8, R9, Impact › Data | The gateway ledger is in memory in the worker (`spikes/dsh-harness/usage_ledger.py:14`), so it dies with the worker. No durable store or writer exists for a lost attempt's `usage_known = false` row. The ported admission denial is fail-closed, which D9 rejects. | open |
| F29 | Blocker | codebase fit, zoom out | D3, Why table, Open questions | ADR-0005 condition 3 requires one container per attempt. D3 uses one container per worker and doesn't flag the departure. There is no superseding ADR, decision-log entry or open question, and `concurrency_per_pod` > 1 would share a filesystem across tasks. | open |
| F30 | Major | zoom out, codebase fit | D7, D9, R9 | The unknown flag and the estimate stop at the attempt row. `Progress`, `TurnOutcome`, `ExecutionAttempt` and `TaskResult` are non-null ints (`task.py:77,102,120,160`), so changing them is a `Strict` payload-contract change. No template has a context-window field. Code rollback below D7 reads NULL into ints. | open |
| F31 | Major | codebase fit, zoom out | D1, Impact › Data, phase 02 › 2.1 | `session_position` is `Integer NOT NULL` (`0003_phase1_tables.py:84`) and no column holds a session blob ref. No task changes `CheckpointRepository` or the restore path. | open |
| F32 | Major | zoom out, fresh reader, codebase fit | R5, D2, D6 step 4, Terms | The ownership fence has no storage or rule. Production checks and then writes (`activity.py:310-312`) and `_finish` doesn't fence. "Owner" collides with the repo owner. The plan doesn't say whether the fence replaces `newer_attempt_exists` or also covers `openai_agents`. | open |
| F33 | Major | zoom out, codebase fit, fresh reader | Assumptions, D3, D6 step 3, phase 02 › 1.2 | The cgroup freeze inside an unprivileged container is untested: the spike used `docker pause`, and Docker mounts cgroupfs read-only. It's checked late, there's no fallback, and the Kubernetes claim is unverified. "Verified in phase 02 task 1.2" reads as done. | open |
| F34 | Major | zoom out, codebase fit | D4, D1, R6, R7, R10 | Commands (`sh` is granted) may run outside the attempt cgroup, so background children escape the freeze and kill. They can read session files, sockets and other attempts' trees. | open |
| F35 | Major | zoom out | D3, R7 | The backing (tmpfs or persistent) and file cleanup of the shared attempt volume are unstated. The current `finally` cleanup (`activity.py:237`) never runs on SIGKILL. | open |
| F36 | Major | zoom out, fresh reader | Rollout & rollback | It omits the migration step and its order, the additive/no-backfill note, the drain bound (`max_wall_time`), and what happens to multi-turn DSH tasks with DSH checkpoints after rollback. | open |
| F37 | Major | codebase fit | phase 02 › 1.2-2.3, phase 03 › 1.1 | Phase 02 needs `local-dsh@1` and the `dsh` profile, which phase 03 › 1.1 creates (`workers/main.py:68`). | open |
| F38 | Major | codebase fit, zoom out, fresh reader | R11, D8, phase 01/02 delivers | R11 is listed in phase 01, which has no DSH turn, and is missing from phase 02. `token` events are undefined for non-streamed `Runner.run` (`runner.py:202`), and the DSH-side event source is unnamed. | open |
| F39 | Major | codebase fit | R2, phase 03 › 2.1 | `local-default@1` fails `Name` validation (`base.py:9`), so R2's test passes without the rule. The match check already exists at resolve time (`loader.py:101-105`). | open |
| F40 | Major | fresh reader | Summary | It says the worker executor runs every tool, while D4 runs commands in DSH. It omits the usage migration and the D9 policy reversal, and the cost and latency risk and open question. | open |
| F41 | Major | fresh reader, zoom out | D6 | No trigger, no failure path (what a failed barrier becomes), no first-request case. "Acknowledged" and DSH's checkpoint policy are undefined. | open |
| F42 | Major | fresh reader | Why table, R10 | Disabling DSH discovery, jobs and delegation has no mechanism. | open |
| F43 | Major | fresh reader | D1, Terms, R14 | Undefined: `session_position`, truncation, `SQLAlchemySession`, workspace tarball. "Task lost" (benchmark) collides with "Lost attempt". | open |
| F44 | Major | fresh reader | D2, D3 | Rejected alternatives and their reasons live only in notes.md and can't be judged from the plan. | open |
| F45 | Major | fresh reader | R6 scenario 2 | "fails even though the launcher kills it" reads as a contradiction. | open |
| F46 | Nit | codebase fit, zoom out | R12, phase 01 › 2.3 | Digests are pinned before the image exists, and the plan doesn't say how the launcher reads the worker's lock. ADR-0005 says "in the worker image". | open |
| F47 | Nit | codebase fit, fresh reader | Decision log; D3, D7 | D3 and D7 need decision-log entries; the plan's Decision log section is empty. | open |
| F48 | Nit | codebase fit | phase 03 › 1.1 | `running_workers` already takes `template` (`tests/support/workers.py:20`). | open |
| F49 | Nit | codebase fit | D4 | `build_tools` returns SDK `FunctionTool`s (`tools.py:70`), so a refactor is needed. The DSH image must ship the granted `cli_tools`. | open |
| F50 | Nit | fresh reader | Terms, R8, R12, R13, D2, D7 | Minor undefined terms: admission denials, settled tokens, F1/F2, blocked error, queue naming, conformance suite, R13 case names, phase numbering, Profile `harness` field. D3 also says "Kubernetes" although it is a non-goal. | open |
| F51 | Nit | fresh reader | Summary | It omits R12 pinning, the D1 seam, and why this comes before Phase 2. | open |
| F52 | Nit | fresh reader | Summary, D1, D3, R3, R5, R6, R9, R12, R13 | Long sentences, repeated facts (default-switch gate, R14 rule, disabled features), and multi-rule requirements. | open |
| F53 | Nit | structure | plan.md | 271 body lines (budget 250). Move evidence and mechanics to notes.md. | open |

## 2026-11-15 · design-review · round 2 · resolutions

| ID | Resolution |
| --- | --- |
| F28 | fixed: D9, notes.md#d9 usage_ledger, R12, R13 |
| F29 | fixed: ADR-0006 amends condition 3; D3; adr_review pending |
| F30 | fixed: D7, notes.md#d7, Rollout |
| F31 | fixed: D1, notes.md#d7, phase 02 task 2.1 |
| F32 | fixed: D10, R6, R7, Terms |
| F33 | fixed: phase 01 task 0.1, notes.md#d3 fallback, Assumptions |
| F34 | fixed: D4, R15, ADR-0006 |
| F35 | fixed: Terms (tmpfs), R10, phase 02 task 1.1 |
| F36 | fixed: Rollout & rollback |
| F37 | fixed: phase 01 task 2.3 |
| F38 | fixed: R16, phase 02 delivers |
| F39 | fixed: R2, phase 01 task 2.2 |
| F40 | fixed: Summary |
| F41 | fixed: D6, notes.md#d6, Terms, Assumptions |
| F42 | fixed: R14, notes.md#r14, phase 02 task 2.4 |
| F43 | fixed: Terms; "task failed" |
| F44 | fixed: D2, D3 inline reasons |
| F45 | fixed: R9 |
| F46 | fixed: R17, phase 02 task 1.1 |
| F47 | fixed: Decision log |
| F48 | fixed: phase 03 task 1.1 |
| F49 | fixed: D4, phase 02 task 2.3 |
| F50 | fixed: Terms |
| F51 | fixed: Summary |
| F52 | fixed: R3/R4, R6/R7, R8/R9, R12/R13 split |
| F53 | fixed: plan.md under 250 body lines; check 0 errors, 0 warnings |

## 2026-11-15 · waiver · design review

The owner waived a third design-review round. Overridden: design_review passed for
the plan and all phases. Rounds 1 and 2 ran with fresh reviewers; every finding is
resolved in the round resolution tables above. The open cost question moved to
the owner's approval in phase 03 task 2.1.

## 2026-11-15 · approved · plan and phases 01-03 (with the waiver above)

## 2026-11-15 · start · phase 01

Branch `feat/62-dsh-harness-seam` from 0f32d7dd3077fcc13d03f7b16e7de7481e34c954 (stacked on the plan branch while PR #64 is open).

## 2026-11-15 · impl-review · phase 01 · round 1 · changes-requested

- Diff base: 0f32d7dd3077fcc13d03f7b16e7de7481e34c954; frozen review commit: bc8e97b7f7126ea62dbc8ef11eb16ba9a75c8875.
- Reviewers: Contract completed; Failure and retry completed; Scope and composition completed (fresh `impl-reviewer` subagents, docs/reviews/README.md rule 1).
- Mechanical: plan-tool check 0 errors, 0 warnings; no unticked tasks; R1-R3 defined with scenarios.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | all three | Fenced checkpoint insert is an unlocked NOT EXISTS under READ COMMITTED; it races a concurrent `attempts.start` (D10). | fixed: per-task advisory lock in start and fenced writes; test_fenced_insert_waits_for_a_concurrent_start (mutation-checked) |
| F2 | Major | all three | Probe moves only the parent PID into the cgroup; freeze/kill and SIGSTOP checks cannot fail for the tree (task 0.1). | fixed: probe starts the tree inside the cgroup and checks members, freeze, kill and SIGSTOP per process; rerun recorded in notes.md#d3 |
| F3 | Major | all three | Session store has no load/capture result a DSH store can use; checkpoint assembly stays in the Activity (D1, task 1.1). | fixed: SessionStore.load(checkpoint) and capture() -> SessionSnapshot (position, session_ref); the Activity commits the snapshot through the fence |
| F4 | Major | failure, scope | Conformance suite never exercises the session store or `run_harness_turn` (R3). | fixed: conformance suite takes sessions from a store (MemorySessionStore); store_contract runs on it and on SQLAlchemySessionStore (Postgres) |
| F5 | Major | scope, contract | No test reaches the Activity's fenced paths; reverting the fence leaves all tests green (D10). | fixed: test_newer_attempt_mid_run_fences_the_finish (mutation-checked) |
| F6 | Major | contract | Artifact blobs are published before the fenced finish (D10). | fixed: assert_current before artifact puts; test_newer_attempt_before_publication_blocks_artifacts. Residual: a start between that check and the fenced finish can leave an unreferenced blob, never an artifact |
| F7 | Nit | all three | Session items are shared across attempts and unfenced (D10 scope; pre-existing). | accepted: pre-existing openai_agents behaviour; DSH sessions are per-attempt blobs (D1), so it does not extend to DSH |
| F8 | Nit | all three | `AttemptEvents.emit` calls the sink outside the lock; delivery order can differ from seq (D8). | fixed: sink.emit inside the lock; test_concurrent_emitters_deliver_in_seq_order |
| F9 | Nit | all three | `dsh` profile resolves but no worker serves `tpl.local-dsh` until phase 02 (D5). | accepted: the dsh profile is not default; phase 02 task 1.3 adds the worker |
| F10 | Nit | all three | Resolve-time harness check duplicated rather than moved (task 2.2). | accepted: the resolve-time check stays as defence in depth |
| F11 | Nit | failure, contract | No test uses a harness outside the `Harness` Literal (R1). | fixed: test_unknown_harness_value_is_rejected |
| F12 | Nit | contract, scope | `SYS_ADMIN` grant recorded only in the plan, not the roadmap decision log or ADR-0006 (D3). | fixed: roadmap decision-log entry for SYS_ADMIN and command confinement |
| F13 | Nit | contract | `concurrency_per_pod: 1` not enforced for `dsh` templates (D3, ADR-0006). | fixed: loader requires concurrency_per_pod 1 for dsh; test_dsh_template_needs_one_attempt_and_a_context_window |
| F14 | Nit | contract | `context_window` optional for `dsh` templates (D7, D9). | fixed: loader requires context_window for dsh; same test |
| F15 | Nit | contract | `newer_attempt_exists` still in the seam as an early exit (D10). | accepted: early exit only; the fenced writes are authoritative |
| F16 | Nit | contract | `close_unfinished` is unfenced on a stale attempt's failure path (D10). | accepted: through_attempt bounds it to rows at or below the failing attempt |
| F17 | Nit | scope | Fence rejects writes when a higher turn exists, e.g. after a workflow reset (D10). | accepted: workflow resets to an earlier turn are not supported |
| F18 | Nit | failure | Fenced finish returns normally when the row was closed and nothing newer exists (D10). | accepted: pre-existing behaviour; the task already completed or was cancelled |
| F19 | Nit | all three | `AgentEvent.payload` does not enforce "no prompt text"; seq scope is per attempt (D8). | accepted: payload content is the emitter's responsibility; R16 tests in phase 02 assert no text; seq is per attempt by design |
| F20 | Nit | contract | Probe has a no-op line and no recorded run command (task 0.1). | fixed: no-op line removed; run command recorded in the probe header |
| F21 | Nit | contract | Worker refusal for non-`openai_agents` templates has no test. | accepted: covered when phase 02 task 1.3 replaces the guard with runner selection |
| F22 | Nit | contract | Stale checkpoint blob recorded before the fenced insert rejects (D10). | accepted: content-addressed task-retention blob without a checkpoint row |
| F23 | Nit | scope | User-namespace probe check still fails; deferred to phase 02 task 1.1 (D3). | accepted: phase 02 task 1.1 must make it pass |
| F24 | Nit | contract | `AgentEvent` lacks durability/retention metadata named in schemas.md (D8). | accepted: durability and retention metadata belong to roadmap Phase 2 |

## 2026-11-15 · impl-review · phase 01 · round 2 · changes-requested

- Diff base: 0f32d7dd3077fcc13d03f7b16e7de7481e34c954; frozen review commit: 9f9f1da0de895d3cec4145b4d727ddf91d3c967e.
- Reviewers: Contract completed; Failure and retry completed; Scope and composition completed (fresh subagents). Round-1 resolutions held; none reopened except F6 below.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F25 | Major | contract, scope | Artifact blobs are written after a separate currency check, which D10 rejects; a newer start in between leaves audit blobs (reopens F6, D10, R7). | fixed: plan D10 and R7 clarified (artifact refs only through the fenced finish; unreferenced blobs possible); design review due for the change |
| F26 | Major | contract | No test covers the lock in `attempts.start`; removing it re-opens the F1 race undetected (D10). | fixed: test_start_waits_for_the_task_lock (mutation-checked) |
| F27 | Major | scope | A template-version refusal writes no row, so a newer Temporal attempt is invisible to the fence (D10, R6). | fixed: AttemptRepository.record_refusal called on refusal; test_refusal_fences_older_attempts |
| F28 | Nit | failure | A stale attempt that starts late writes a row and truncates the shared session before the fence stops it (D10, D1). | fixed: start rejects a stale attempt before any write; test_late_stale_start_is_refused; Activity maps it to Superseded |
| F29 | Nit | contract, scope | Fenced finish has no Activity-level or newer-turn test; the UPDATE's fence clause is unobserved (D10). | fixed: test_fenced_finish_rejects_a_newer_turn |
| F30 | Nit | all three | Store has no commit step; conformance uses only `store.session`; contract uses one instance (D1, R3). | accepted: the Activity commits through the fence (D10); the DSH store and its multi-instance contract arrive in phase 02 task 2.1 |
| F31 | Nit | failure | The fence does not require the writer's own row to be `started`; a closed newest attempt can still checkpoint (D10). | accepted: a closed newest attempt only adds rows to a completed task; Temporal drops its result |
| F32 | Nit | scope | Unfenced `finish()`/`insert()` stay public; the fence is opt-in (D10). | accepted: production uses only fenced forms; phase 02 reviews DshRunner against D10 |
| F33 | Nit | failure, scope | `hashtext` gives a 32-bit lock key in the shared advisory space (D10). | accepted: throughput only; no other advisory-lock users |
| F34 | Nit | failure, scope | Event seq gaps after a failing sink; seq is per `AttemptEvents` instance (D8). | accepted: in-memory sinks never fail; roadmap Phase 2 owns transport semantics |
| F35 | Nit | contract | `docs/roadmap/schemas.md` lacks `context_window` (D7). | fixed: docs/roadmap/schemas.md lists context_window |
| F36 | Nit | failure | The `session_ref` stub fails retryably after the workspace upload (D1). | accepted: stub until phase 02 task 2.1 replaces it |
| F37 | Nit | scope | Early exit checks the same turn only, unlike the fence (D10). | accepted: early exit only; the fence covers newer turns |

## 2026-11-15 · design-review · round 3 · passed

Targeted follow-up (docs/reviews/README.md rule 6) on the D10 and R7 clarification, one fresh
`design-reviewer` subagent at 38e379c compared with 10ef351. ADR-0005 condition 2, R5, R12 and
phase 02 tasks: no findings.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F54 | Major | codebase fit | D10 implied a locked pre-check is a guarantee and did not name the unreferenced-blob residual. | fixed: D10 rejects a separate pre-check as the guarantee and names the residual; notes.md#d10 |
| F55 | Nit | codebase fit | "Referenced only through the fenced finish" is imprecise; references are in the returned `TurnOutcome`. | fixed: D10 and notes.md#d10 |
| F56 | Nit | codebase fit | R7 statement and scenario disagreed; place of observation unnamed. | fixed: R7 "returns no artifact reference or outcome"; Then names `TurnOutcome` and task-result outputs |
| F57 | Nit | codebase fit | `record_refusal` and `close_unfinished` write rows without the fence, against R6 as worded. | fixed: R6 scoped to checkpoints and attempt outcomes through the run path; notes.md#d10 |

## 2026-11-15 · verification · phase 01 · pass

code_sha 4969d4d, docs_sha 38e379c; fresh verifier subagents (acceptance, as-built, follow-up).
Report: docs/reviews/general-dsh-production-harness/verification-phase-01.md; demo:
docs/demos/general-dsh-production-harness-01.md; raw reports under that review folder.

## 2026-11-15 · done · phase 01

Shared done gate passed; all six tasks checked; design review passed (3 rounds), impl review
passed (2 rounds), verification and demo passed.

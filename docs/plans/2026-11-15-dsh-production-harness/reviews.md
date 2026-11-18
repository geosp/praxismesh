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

## 2026-11-15 · start · phase 02

Branch `feat/62-dsh-runner` from 562733a72b880d13576ced63e8b8ad09716094df (stacked on PR #66).

## 2026-11-16 · impl-review · phase 02 · round 1 · changes-requested

- Diff base: 562733a72b880d13576ced63e8b8ad09716094df; frozen review commit: 43798c76e42d04d205fbb8b9ba3b64916a8f4ab3.
- Reviewers: Contract completed; Failure and retry completed; Scope and composition completed (fresh `impl-reviewer` subagents, docs/reviews/README.md rule 1). Raw reports: docs/reviews/general-dsh-production-harness/raw/impl-review-phase-02-round-1-{contract,failure,scope}.md. An earlier attempt in another tool ended at its quota before any report was saved; this round replaces it.
- Mechanical: plan-tool check 0 errors, 0 warnings; no unticked tasks; R5-R18 defined with scenarios.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F58 | Major | all three | Workflow `ActivityError` branch drops `usage_known`; a turn that fails for good after a D9 charge reports `usage_known = true` (R12, D7). | fixed: failed_turn_usage carries usage_known; test_failed_turn_keeps_unknown_usage (tests/test_task_workflow.py, mutation-checked) |
| F59 | Major | all three | D9 charge and `usage_known = false` only applied when a later attempt opens; cancel, non-retryable stops and `AttemptsExhausted` leave unsettled requests uncharged (R12, R13, D9). | fixed: Activity charges its own unsettled rows on runner failure, cancel and AttemptsExhausted, NULL tokens on its row; tests/integration/test_dsh_usage.py (mutation-checked); cancel case in test_dsh_outcomes asserts (None, None, False) |
| F60 | Major | all three | Stop (deadline, cancel, thaw failure) while the barrier holds the freeze sends SIGTERM to a frozen runtime and becomes non-retryable `DshForcedStop` (R8, R9, D6). | fixed: launcher thaws before SIGTERM; runner ends an in-flight barrier before stop; a thaw that failed before the stop is DshCheckpointFailure (retryable); test_stop_while_frozen_is_cooperative, test_deadline_during_the_barrier_is_a_retryable_deadline, test_failed_thaw_is_a_retryable_checkpoint_failure (mutation-checked) |
| F61 | Major | scope, failure, contract | Ledger dispatch is unfenced and an attempt's first request has no barrier; a stale attempt's spend after the newer attempt's `close_unknown` escapes the turn total (R11, R13, D10). | fixed: UsageLedgerRepository.dispatch is fenced under the task lock; a refused dispatch is Superseded; test_stale_attempt_cannot_dispatch, test_stale_attempt_dispatches_nothing (mutation-checked) |
| F62 | Major | scope, failure, contract | R17 pin checked once at worker start; a recreated DSH container is served unchecked (R17). | fixed: the launcher reports a start-up runtime report; DshRunner re-verifies it at every open_attempt and raises RuntimePinMismatch (retryable); test_attempt_on_an_unpinned_runtime_is_refused (mutation-checked) |
| F63 | Major | failure | Commands share the container `/tmp` across attempts and tasks (R15). | fixed: commands bind a command-owned command-tmp/ and the runtime its tmp/ on /tmp; test_commands_get_their_own_tmp (mutation-checked) |
| F64 | Major | contract, scope | Step-limit/budget denial returns 429 only; no 5 s bound enforced or tested after a step limit (R8). | fixed: after a step-limit or budget denial the runtime gets 2 s, then a cooperative stop with the remaining 3 s; still a continue at the limit; test_step_limit_stops_a_runtime_that_does_not_exit |
| F65 | Major | contract, scope | R18 tests hard-code expectations that differ from `dsh-phase02-r2-evidence.json` (inner_turns, usage_known) with no recorded decision; cancel case has no TaskResult check (R18). | fixed: R18 tests read dsh-phase02-r2-evidence.json and apply only recorded differences (plan D11, decision log); workflow waits for a cancelled turn's Activity (WAIT_CANCELLATION_COMPLETED), cancel row asserted exactly |
| F66 | Major | contract | Stale-attempt test can pass vacuously (early exit or cancel); R7 "stale attempt that finished" not exercised on DSH (R6, R7). | fixed: test_stale_attempt_that_finished_is_fenced at checkpoint, publish and finish with the early exit stubbed (insert and assert_current mutations caught; the finish clause is also covered by the row no longer being started) |
| F67 | Major | contract | Failed freeze before the final checkpoint is ignored; a torn workspace can be checkpointed and published (R5, D6). | fixed: a failed final freeze is DshCheckpointFailure (retryable); test_failed_final_freeze_is_a_retryable_checkpoint_failure |
| F68 | Nit | all three | Lost attempt with only settled requests keeps `tokens_in = 0, usage_known = true` (R11, R12). | fixed: close_unknown sets a lost attempt's row to the ledger's usage through it (NULL if any request up to it is unknown); test_lost_attempt_with_settled_requests_records_them (mutation-checked) |
| F69 | Nit | scope, failure | Attempt rows write non-null tokens with `usage_known = false`, against the schema comment (D7). | fixed: one rule (attempt rows hold the turn's cumulative usage; NULL when an own request was unobserved; usage_known false when a D9 charge is included) in ExecutionAttempt and notes.md#d7 |
| F70 | Nit | scope, contract | `cooperative` covers only the runtime PID; commands killed by `cgroup.kill` still count as cooperative (R9). | accepted: commands killed with the cgroup are the R15 behaviour; R9 concerns the runtime ignoring SIGTERM |
| F71 | Nit | scope | Success-path cleanup report (`processes_left`, `tree_removed`) is ignored (R8, R10). | fixed: a dirty stop report marks the runner unhealthy; later attempts raise LauncherUnhealthy (retryable); test_failed_cleanup_after_success_stops_new_attempts (mutation-checked) |
| F72 | Nit | scope, failure | Attempt deadline built from per-turn `remaining_wall_time`; retries can exceed task wall time; step ceiling is per attempt. | accepted: pre-existing per-turn deadline and per-attempt step ceiling, as for openai_agents; bounded by schedule_to_close |
| F73 | Nit | scope, contract | Gateway does not clamp `max_tokens`; D9 assumes 2048 output tokens unchecked (D9). | fixed: to_model clamps max_tokens to DSH_MAX_OUTPUT_TOKENS; test_output_is_capped_at_the_charge_assumption |
| F74 | Nit | scope | Inner turns from the ledger count requests; live count uses logical steps. | accepted: the max() keeps the larger count; requests equal steps unless a body is re-sent, which maxRetries 0 prevents |
| F75 | Nit | scope | Activity heartbeat-base charge merge tested over two attempts only (D9). | fixed: test_retryable_failure_is_charged_once_across_attempts covers three attempts at Activity scope |
| F76 | Nit | scope | Tree created before launcher `open` is orphaned on worker death until launcher restart (R10). | accepted: narrow window; the launcher reaps the tree at its next start (test_restart_reaps_leftover_attempts) |
| F77 | Nit | scope, contract | `includeDefaultRoots: false` never set; live poison files only in workspace, not HOME (R14). | fixed: includeDefaultRoots belongs to the never-inserted dsh-skill-filesystem plugin (notes.md#r14); test_exactly_the_provider_and_tool_plugins_are_inserted; live test plants discovery files in the runtime HOME |
| F78 | Nit | scope | `context_window` default 32768 in composition vs `or 0` in `_open` (unreachable). | fixed: the Activity charges with composition.DEFAULT_CONTEXT_WINDOW as its fallback |
| F79 | Nit | failure | Cancellation outside the poll loop leaves the attempt row `started`. | accepted: a later start marks the row lost; only bare-runner use before the poll loop is affected |
| F80 | Nit | failure | Ledger request ids restart for a second `run` in one attempt; PK collision (Activity path unaffected). | accepted: the Activity makes one run per attempt; only bare HarnessRunner use repeats run() |
| F81 | Nit | failure | Tool body in a thread can recreate files after `destroy` (R10). | accepted: narrow window; the tree is removed again by DshAttempt.close and launcher reaping |
| F82 | Nit | failure, contract | Tool-call counts since the last heartbeat are lost with the worker (R11). | accepted: tool-call counts are informational; tokens are rebuilt from the ledger |
| F83 | Nit | failure | `checkpoints.session_ref` is `json`, D7 says `jsonb` (D7). | accepted: sa.JSON stores the same documents; no query depends on jsonb operators |
| F84 | Nit | failure | A transient barrier failure forces a retry of a run that later finished. | accepted: the retry is safe and rare |
| F85 | Nit | failure | Failed thaw is reported as barrier failure after the checkpoint committed (D6). | accepted: the checkpoint was captured while frozen, so it is consistent; the failed thaw is retryable |
| F86 | Nit | failure | Unproven race: `destroy` rmtree during barrier pack could commit an empty session (R5). | fixed: the runner closes the gateway server (cancelling an in-flight barrier, which thaws) before stopping; covered by test_deadline_during_the_barrier_is_a_retryable_deadline (no commit after the deadline) |
| F87 | Nit | contract | Plan D9 and decision log still say `context_window + max_tokens`; code uses the 2048 cap from notes.md#d9 (D9). | fixed: plan D9 and decision-log line corrected (2048-token cap, enforced by the gateway) |
| F88 | Nit | contract | `apparmor:unconfined` added without a decision-log entry (D3). | fixed: decision-log entry 2026-11-16 for apparmor:unconfined |
| F89 | Nit | contract | DSH image carries the full slim userland, not only granted `cli_tools` (D4). | accepted: D4 restated in plan and notes.md#d4 (boundary is UID, capabilities, seccomp and mount view; the base userland stays) |
| F90 | Nit | contract | Outcomes-level isolation test assertions cannot fail (R15; launcher test covers it). | fixed: labelled probes; exposing other attempts or the session makes the test fail (mutation-checked) |
| F91 | Nit | contract | Refused tool calls emit no event (gateway) or an unpaired `tool_result` (executor) (R16). | fixed: refused calls emit a paired tool_call and tool_result in the executor and gateway; unit tests updated |
| F92 | Nit | contract | Pin lock covers the DSH distribution only, not launcher/driver/bridge (R17). | fixed: the runtime digest covers pins.py, launcher.py, driver.py and mcp_bridge.py; test_control_files_are_part_of_the_pin (mutation-checked); lock regenerated |
| F93 | Nit | contract | Conformance `instructions_seen` now joins messages 0 and 1 for every runner, weakening the openai_agents check (task 2.3). | fixed: instructions_seen checks the system message for openai_agents and the first user message for dsh |
| F94 | Nit | contract | Reap-at-start test checks trees only, not processes or cgroups (task 1.1). | fixed: test_restart_reaps_leftover_attempts kills a live attempt's processes and cgroup through a real launcher restart (mutation-checked) |
| F95 | Nit | contract | Migration downgrade rewrites NULL tokens to 0 (D7). | accepted: rolling back below D7 is not supported (notes.md#d7) |

## 2026-11-16 · impl-review · phase 02 · round 2 · changes-requested

- Diff base: 562733a72b880d13576ced63e8b8ad09716094df; frozen review commit: e053d233cb39655e47ed0c22d1e37c1ed71fe14b.
- Reviewers: Contract completed; Failure and retry completed; Scope and composition completed (fresh `impl-reviewer` subagents). The briefs first carried a wrong full SHA; each reviewer got the correction and reviewed the stated range. Raw reports: docs/reviews/general-dsh-production-harness/raw/impl-review-phase-02-round-2-{contract,failure,scope}.md.
- Round-1 findings closed as accepted stay closed (F70, F72, F74, F76, F80, F82, F85, F95 raised again). Reopened: F59 (as F98), F63 (as F102), F64 (as F96), F68/F69 (as F101), F71 (as F100).

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F96 | Blocker | contract | A step-limit stop removes the attempt tree, then the Activity commits an empty finish checkpoint as a valid `continue` (R5, D6; reopens F64). | fixed: the launcher's stop takes keep_tree; a step-limit stop ends the processes and keeps the tree for the final checkpoint; test_step_limit_stop_keeps_the_workspace_for_the_checkpoint (through run_harness_turn) |
| F97 | Blocker | contract | A declared output symlinked by a command makes the worker publish its own files (e.g. `/proc/self/environ`) as an artifact; `inside()` and `share()` also check then follow (D4, R15). | fixed: outputs, read_file, write_file and list_files open each component with O_NOFOLLOW; share() uses fwalk and no-follow descriptors; test_symlinked_output_is_not_published (fails without the fix), test_file_bodies_never_follow_a_link |
| F98 | Major | all three | A cancelled turn, or one ended by schedule_to_close or a dead worker, never gets the D9 charge or `usage_known = false` into the TaskResult; the Workflow reads a pre-charge heartbeat or none (R12, R13, D9; reopens F59). | fixed: complete_task reconciles with the ledger (settled plus D9 charge, usage unknown); test_complete_task_charges_what_the_ledger_left_unobserved; the R18 cancel test checks the stored TaskResult |
| F99 | Major | scope, failure | A pin mismatch or unhealthy container refuses per attempt after `attempts.start`, so the worker keeps polling and each turn burns its five attempts (R17, R10). | fixed: a pre-flight check before attempts.start records an uncounted refusal (dsh_unserviceable) and shuts the worker down (exit 3); the launcher reports attempts it could not clean (dirty) until it restarts; test_unserviceable_worker_refuses_without_using_an_attempt, test_launcher_remembers_an_attempt_it_could_not_clean, test_local_dsh_refuses_a_container_left_dirty (all mutation-checked). The worker shutdown wiring in workers/main.py has no automated test |
| F100 | Major | scope, failure | A dirty stop inside `run()` (deadline, cancel, step limit), or a `LauncherError` from stop, never marks the runner unhealthy; an errored stop is classified clean (R10; reopens F71). | fixed: DshAttempt.stop checks its own report on every path, with a reply timeout; a refused stop reports nothing cleaned; test_dirty_stop_during_a_run_stops_new_attempts (both variants failed before) |
| F101 | Major | scope, failure | Rows closed by `close_unfinished` (failed, task_completed) keep their 0 tokens and `usage_known = true` (D7, R12; reopens F68, F69). | fixed: close_unfinished applies the ledger usage (settled through the attempt, or NULL) to the rows it closes; test_rows_closed_without_a_finish_hold_the_ledger_usage |
| F102 | Major | contract | Commands still share the container's `/run` and `/dev/shm` across attempts and tasks (R15, D4; reopens F63). | fixed: each attempt process gets a private tmpfs on /run and /dev/shm; test_commands_get_their_own_tmp covers /tmp, /run and /dev/shm |
| F103 | Nit | scope | An `unresolved usage` denial starts no exit timer; a retrying runtime runs to the deadline (R8). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F104 | Nit | scope | The charged-once test hands the next attempt the post-charge details, not the last heartbeat Temporal passes (D9 test scope). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F105 | Nit | scope | Worker-side tool bodies run outside the frozen cgroup; an abandoned call could write during a capture (D6). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F106 | Nit | contract | A stale attempt's `_charge` rewrites usage columns without the fence (R6). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F107 | Nit | contract | The output cap does not bound `n > 1` (D9). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F108 | Nit | contract | The R17 digest is self-reported by the launcher it vouches for (R17; inherent). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F109 | Nit | contract | The CLI attempt listing omits `usage_known` (D7). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F110 | Nit | failure | A dirty cleanup after a successful turn keeps the outcome, unlike the in-run path (R8, R10). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F111 | Nit | failure | No timeout on `poll` or the in-run `stop`; a stalled launcher skips the stop margin (R8). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |
| F112 | Nit | failure | Every `CancelledError` (heartbeat failure, timeout) is recorded as `DshCancelled` (R8, R18). | open: deferred by the engineer (round 2 fixes limited to Blockers and Majors) |

## 2026-11-16 · design-review · plan · round 4 · changes-requested

Targeted follow-up (docs/reviews/README.md rule 6) on the decision changes from the phase 02 impl review (D4, D9, D11, decision log 2026-11-16), at 98835319f201867887a5555e3651a2aa8eadd1e4. Reviewers: Fresh reader completed; Codebase fit completed; Zoom out completed (fresh subagents; codebase fit and zoom out stopped once on a usage limit and were resumed). Raw reports: docs/reviews/general-dsh-production-harness/raw/design-review-round-4-{fresh-reader,codebase-fit,zoom-out}.md. Structure check: 0 errors, 0 warnings.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F113 | Major | fresh reader | The 2026-11-16 decision changes did not reach the requirements: R13 (charge at the failure when no later attempt runs), R15 (per-attempt `/tmp`, `/run`, `/dev/shm`), R17 (control files, re-check at every attempt); D3's `SYS_ADMIN` grant lives only in the log. | fixed: R13 (charge at turn or task end), R15 (private /tmp, /run, /dev/shm, IPC), R17 (control files, before each attempt, refuse and stop polling), D3 (SYS_ADMIN for the launcher only) |
| F114 | Major | codebase fit | Phase 03 task 2.1 points `default` at DSH with no other profile allowing `local-default`, so `openai_agents` is no longer selectable (ADR-0005 condition 5) and CI checks that assume `default` = `local-default` break. | fixed: phase 03 task 2.1 adds an `openai` profile and repoints the tests and Make targets before the switch |
| F115 | Major | codebase fit, zoom out | Phase 03 task 1.1 omits the DSH container the benchmark needs and the hard-coded template, profile, harness label and output name in `tests/benchmarks/run.py`; its Verify cannot catch it. | fixed: phase 03 task 1.1 rewritten (template from the profile, results and label by profile, paired DSH container; Verify runs one real task per profile) |
| F116 | Major | codebase fit | ADR-0005 condition 1 also requires recording DSH's licence notices; no requirement or task does. | fixed: R20 and phase 03 task 1.3 (licence notices under docs/licences/dsh/ with a check) |
| F117 | Major | zoom out | The rollback drain bound is wrong (max wall time plus up to 6 x turn_timeout) and never says to keep the DSH pair up until no local-dsh task is open. | fixed: Rollout and notes.md#rollout state the drain bound (wall time plus 6 x turn_timeout) and keep the DSH pairs up; task 2.2 Verify includes an in-flight DSH task |
| F118 | Major | zoom out | Rollback is more than two field edits: registry lock, worker image rebuild, orchestrator restart. | fixed: Rollout lists edit, registry lock, image rebuild, orchestrator restart |
| F119 | Major | zoom out | Code rollback is ambiguous (roll back code on the 0004 schema, or roll forward only?) and contradicts the migration docstring; in-flight workflow behaviour on a revert is unstated. | fixed: code rolls forward only (Rollout, notes.md#rollout) |
| F120 | Major | zoom out | Switching `default` to one DSH pair cuts its capacity to about a quarter; the number of DSH pairs needed before the switch is not stated. | fixed: two DSH pairs before the switch (notes.md#rollout, task 2.1) |
| F121 | Major | fresh reader | Core terms undefined: task, turn, attempt and inner turn; settled and unsettled ledger rows. | fixed: Terms define task, turn, attempt, inner turn, settled and unsettled |
| F122 | Major | fresh reader | The Summary omits the event sink (D8/R16) that serves its stated reason, and the rollback limits. | fixed: Summary names the event sink, the openai profile and the rollback limits |
| F123 | Major | fresh reader, zoom out | Parts that don't connect: the transport between worker and DSH container, how worker death is detected (R10), why `session_position` 0 is safe (D1), whose row R12 means, and R18 vs D11 (exact match or recorded differences). | fixed: Terms (Unix sockets on the shared volume), R10 (control connection), D1 (blob replaces the home), R12 (the lost attempt's row), R18 (up to the D9 and D11 differences) |
| F124 | Major | fresh reader | D6 (what the flush check does on failure) and D10 (refusal rows) can only be paraphrased at headline level; the substance is in notes.md. | fixed: D6 (a missing ID fails the barrier), D10 (ledger dispatch and refusal rows) |
| F125 | Nit | codebase fit, zoom out | Phase 03 task 1.1's `turn_timeout`/`max_wall_time_cap` edit is a no-op; the values already match. | fixed: the no-op template edit is dropped from task 1.1 |
| F126 | Nit | codebase fit | notes.md#d3 says `cgroupns: private`; the Compose key is `cgroup: private`. | fixed: notes.md#d3 says `cgroup: private` |
| F127 | Nit | codebase fit | Phase 01 task 2.2 cites stale `registry/loader.py` line numbers. | fixed: phase 01 task 2.2 names Registry.resolve instead of line numbers |
| F128 | Nit | zoom out | Deferred F103, F106, F111 leave R8 and R6 short of their absolute wording, with no recorded deviation. | fixed: notes.md#rollout records F103, F106, F111 as known deviations |
| F129 | Nit | zoom out | Barrier cost grows with turn length times session and workspace size; not under Risks. | fixed: Risks line for barrier cost |
| F130 | Nit | zoom out | A worker that refuses (exit 3) restarts in a loop; R17 and Rollout don't say how an operator notices. | fixed: notes.md#rollout says how a refusing worker shows (log line, exit 3 restarts) |
| F131 | Nit | fresh reader | Readability: requirements holding two rules (R7, R8, R11, R12, R15, R16), repeated facts, a 60-word decision-log line, the commands sentence in the Summary, the SIGSTOP fallback, unmapped requirements in Why, the Phases table status. | accepted: the Summary's commands sentence and the decision log were rewritten; multi-rule requirements and repeated facts stay as approved |

## 2026-11-16 · impl-review · phase 02 · round 3 · changes-requested

- Targeted follow-up (docs/reviews/README.md rule 6), beyond the skill's two rounds at the engineer's request. Diff base: 562733a72b880d13576ced63e8b8ad09716094df; frozen review commit: 98835319f201867887a5555e3651a2aa8eadd1e4; focus 76dffd6..98835319.
- Reviewers: Contract completed; Failure and retry completed; Scope and composition completed (fresh `impl-reviewer` subagents; each stopped once on a usage limit and was resumed). Raw reports: docs/reviews/general-dsh-production-harness/raw/impl-review-phase-02-round-3-{contract,failure,scope}.md.
- Reopened: F102 (as F132), F99 (as F133), F101 (as F134). Deferred F103-F112 not re-raised.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F132 | Major | contract, scope | Commands of every attempt and task share one IPC namespace; SysV shared memory and message queues outlive an attempt and are readable by a later task (R15, D4; reopens F102). | fixed: unshare(CLONE_NEWNS | CLONE_NEWIPC); test_commands_get_their_own_tmp checks SysV shm and queues (failed before) |
| F133 | Major | contract, failure | A pre-flight that cannot reach the launcher (stopped or restarting container) raises `LauncherError`, not a refusal: no refused row, the attempt counts, the worker keeps polling, and the turn ends `AttemptsExhausted` (R17, R10; reopens F99). | fixed: DshRunner.check times out and raises LauncherUnreachable (Unserviceable); test_unreachable_launcher_is_a_refusal_every_time over seven attempts (failed before) |
| F134 | Major | failure, scope | Rows marked `lost` by `start` or `record_refusal` get the ledger's usage only if a later real attempt opens; `close_unfinished` touches `started` rows only, so a lost row can keep 0 (R12, D7; reopens F101). | fixed: close_unfinished applies the ledger usage to lost rows too; test_lost_rows_hold_the_ledger_usage_when_the_task_completes (failed before) |
| F135 | Nit | scope | Two rules for a row's usage: `_ledger_usage_sql` NULLs on any unknown up to the attempt, `_runner_failed` only on its own (D7). | accepted: a finished-and-failed row and a row closed without a finish follow the two rules notes.md#d7 states |
| F136 | Nit | scope, failure | `complete_task` reconciles tokens but not inner turns (D11). | fixed: complete_task takes inner turns from the ledger request count; F98 test asserts it |
| F137 | Nit | all three | `complete_task` looks the template up by name in the current registry: `KeyError` if it is gone, and the current version's `context_window` rather than the task's (R11, D9). | fixed: complete_task uses the task's template version or the default window; test_complete_task_survives_a_template_the_orchestrator_no_longer_has |
| F138 | Nit | scope | An `Unserviceable` raised in `open_attempt` after `attempts.start` still uses an attempt and does not stop polling (narrow window after the pre-flight). | accepted: narrow window after the pre-flight; the next turn's pre-flight refuses |
| F139 | Nit | all three | Worker shutdown: the task is not referenced, the wiring and the cross-attempt heartbeat hand-off are untested, and a refusing worker restart-loops until an operator acts. | accepted: the shutdown wiring and cross-attempt hand-off need a Temporal worker test; notes.md#rollout documents the restart loop |
| F140 | Nit | all three | `list_files` still checks then walks by name (names only could leak); the F97 resolution text overstates it. | fixed: list_files walks with fwalk from a no-follow descriptor; test_list_files_never_follows_a_link |
| F141 | Nit | contract | `read_file`/`write_file` now refuse in-workspace symlinks for `openai_agents` too, a behaviour change without a recorded decision (task 2.3). | accepted: recorded in notes.md#rollout (file tools refuse every link) |
| F142 | Nit | scope | The F98 reconciliation is tested on one turn only, and the cumulative ledger SQL on one attempt per turn. | accepted: the reconciliation takes a max per task and the SQL is per attempt; broader tests deferred |
| F143 | Nit | failure | An exception inside `destroy()` skips the dirty record, so the container can be served again (R10). | fixed: destroy marks the attempt dirty when cleanup raises; test_launcher_destroy_error_marks_the_attempt_dirty (failed before) |
| F144 | Nit | failure | A worker-side stop timeout is a non-retryable `DshCleanupFailure` even if the launcher cleans up later (R9). | accepted: conservative per R9 |
| F145 | Nit | failure | The final checkpoint after a step-limit stop skips the D6 tool-call check (the capture is at rest). | accepted: the capture is at rest after the processes were killed |
| F146 | Nit | failure | A cancel during the step-limit stop leaves the row for `complete_task` instead of `cancelled` (R18). | accepted: narrow window; F98 and F134 keep the usage right |
| F147 | Nit | failure | The refusal heartbeat is sent before `record_refusal`; a failed write leaves a counted refusal with no row. | fixed: record_refusal before the refusal heartbeat |
| F148 | Nit | failure | Review metadata disagreed (impl passed, design changes-requested, Phases table); resolved by recording design review round 4. | fixed: design review round 4 recorded |

## 2026-11-16 · impl-review · phase 02 · round 4 · passed

- Targeted follow-up (docs/reviews/README.md rule 6) on 11bb0d6ced126c12f03ea7dade4b7d1381d0c99c..3239e2a436e0911cd6b71ca8cfbcf875853e1e95; one fresh `impl-reviewer` subagent (contract lens), run alone per the engineer's sequential-review direction. Raw report: docs/reviews/general-dsh-production-harness/raw/impl-review-phase-02-round-4-contract.md.
- Reviewer: Contract completed. No Blocker or Major; F132, F133, F134, F136, F137, F140, F143, F147 confirmed enforced.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F149 | Nit | contract | The template-version refusal still heartbeats before `record_refusal` (F147 on one path only). | fixed: the version refusal records its row before the heartbeat |
| F150 | Nit | contract | A failed refusal write now counts the attempt and does not stop polling (F147 trade-off). | accepted: a failed refusal write counts the attempt; the trade-off keeps every subtracted refusal backed by a row |
| F151 | Nit | contract | The F137 test passes on the old code; with the version gone the charge falls back to 32768 even if that version's window was larger. | fixed: with the version gone, the charge uses the larger of the default and the current window; the test fails on the old code and covers a missing name |
| F152 | Nit | contract | `complete_task` counts ledger requests while the Activity counts logical steps (D11 unit). | accepted: requests equal logical steps unless DSH re-sends a body, which maxRetries 0 prevents (as F74) |
| F153 | Nit | contract | The pre-flight can take 20 s without a heartbeat, past a short `heartbeat_timeout`. | accepted: local-dsh's heartbeat_timeout is 30 s; a shorter one with a hung launcher is a deployment error |
| F154 | Nit | contract | The F133 test covers a missing socket only, not a hung or dropping launcher. | accepted: the timeout branches share the refusal path the missing-socket test covers |
| F155 | Nit | contract | The F140 test does not observe the race it fixes. | accepted: the no-follow walk is structural; the race is not reproduced in a test |
| F156 | Nit | contract | `list_files` changed for `openai_agents` too: a missing directory or a file path now errors, and a file deleted mid-walk raises. | accepted: errors are returned as tool text for both runners; recorded with F141 |
| F157 | Nit | contract | Worker start-up messages for an unreachable launcher lost the template ref. | fixed: start-up errors name the template again |
| F158 | Nit | contract | notes.md#d4 and phase 02 task 1.1 do not mention the IPC namespace, `/run` and `/dev/shm`. | fixed: notes.md#d4 and phase 02 task 1.1 name the IPC namespace, /run and /dev/shm |
| F159 | Nit | contract | F134 is tested on the task-completion path only. | accepted: the same SQL is tested on the task-completion path |

## 2026-11-16 · design-review · plan · round 5 · changes-requested

Targeted follow-up (docs/reviews/README.md rule 6) on 98835319..e51495c2bce9de2cfb1fada3505d518090f49626; one fresh `design-reviewer` subagent (codebase fit), run alone per the engineer's sequential-review direction. Reviewer: Codebase fit completed. Raw report: docs/reviews/general-dsh-production-harness/raw/design-review-round-5-codebase-fit.md. Round 4 fixes F113-F130 held.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F160 | Major | codebase fit | Phase 03 task 2.1's list of tests that assume `default` misses the R3 conformance suite (`tests/test_runner_conformance.py`) and `tests/integration/test_tracing.py`. | fixed: phase 03 task 2.1 lists test_runner_conformance.py (R3 through `openai`) and test_tracing.py |
| F161 | Nit | codebase fit | notes.md#rollout says a refusing worker exits 3; at start-up it exits 1 with a traceback. | fixed: notes.md#rollout gives both exits (3 during a turn, 1 at start-up) |
| F162 | Nit | codebase fit | A profile resolves in the submitting process and again in the orchestrator; between the registry edit and the restart, submissions can fail. | fixed: notes.md#rollout says to pause submissions until submitter and orchestrator have the new registry |
| F163 | Nit | codebase fit | Phase 03 task 1.1's Verify is weak (a one-task run fails the regression rule and writes into `docs/benchmarks/`; result files always differ). | fixed: task 1.1 Verify is a smoke run outside docs/benchmarks/, not judged against the baseline, checking names and label |
| F164 | Nit | codebase fit | The Phases table shows phase 03 at 0/4; it has 5 tasks. | fixed: Phases table shows 0/5 |
| F165 | Nit | codebase fit | R13's scenario covers only the retried case; R20 does not say the notices check runs in CI. | fixed: R13 adds the completion-time scenario; R20 and task 1.3 run the check in CI |

## 2026-11-16 · verification · phase 02 · pass

code_sha 86cfec8, docs_sha 7b06ce6; fresh verifier subagents run one at a time. First pass at 62ffc76
failed (four integration tests needed the developer's `VLLM_BASE_URL`); fixed in d170701 and
re-verified. Report: docs/reviews/general-dsh-production-harness/verification-phase-02.md; demo:
docs/demos/general-dsh-production-harness-02.md; raw reports under that review folder.

## 2026-11-16 · done · phase 02

Shared done gate passed; all eight tasks checked; design review passed (5 rounds), impl review
passed (4 rounds), verification and demo passed (code 86cfec8, docs 7b06ce6).

## 2026-11-17 · impl-review · phase 03 · round 1 · changes-requested

- Diff 285dd44034aef6c2bd4e40d6ae14811e546b7048..89ac455cf1474db179b04ff1b090b0447921fe4a (code_sha 89ac455). Three fresh `impl-reviewer` subagents, run one at a time; each report committed before the next. Raw reports: docs/reviews/general-dsh-production-harness/raw/impl-review-phase-03-round-1-{contract,failure,scope}.md.
- Before the round: unit and integration suites from a clean worktree with `infra/.env.example` (276 unit, 174 integration passed; 4 skipped, all `test_model_endpoints.py` for the unset `VLLM_BASE_URL`).
- Reviewers: contract ✅ · failure ✅ · scope ✅

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F166 | Major | contract, failure, scope | Tasks 1.1, 2.1, 2.2 ticked with no recorded verification (smoke runs, a `default` task on DSH, each pair serving, the revert walkthrough). | fixed: docs/demos/general-dsh-production-harness-03.md records the smoke runs, a `default` and an `openai` task, a task on each DSH pair, the CI path and the revert walkthrough |
| F167 | Major | contract, scope | D5 owner approval of the switch and its cost is not recorded in a decision log. | fixed: docs/roadmap/decision-log.md 2026-11-17 entry and the plan's Decision log record the owner's approval and the measured cost |
| F168 | Major | contract | Following the runbook's revert turns CI red: `test_default_profile_runs_on_dsh` and other "default is DSH" statements are not in the revert steps. | fixed: runbook step 2 lists the test, the profile comment, the runbook and overview rows and a decision-log line to change in the same PR |
| F169 | Major | contract, failure | `make demo-worker-loss` submits on `default`, so the Phase 1 demo now silently runs on DSH. | fixed: infra/demo/worker-loss.sh submits on `openai` by default (PROFILE overrides); rerun recorded in the demo record |
| F170 | Major | failure | A DSH worker that stops serving mid-benchmark leaves every remaining task waiting up to 60 min, then judged as a regression. | fixed: tests/benchmarks/run.py `await_result` terminates the task and stops the run, unjudged, when the worker stops serving; test_result_wait_stops_when_the_worker_stops_serving |
| F171 | Major | scope | `--only` subsets are judged against the 10-task baseline and can overwrite R19 evidence; an unknown `--only` ID (the docstring's `fizzbuzz`) runs nothing and exits 0. | fixed: unknown `--only` IDs are refused and a subset must use `--out`; test_unknown_task_id_is_refused, test_subset_is_not_written_to_docs; docstring example uses t01-order-total |
| F172 | Nit | contract, failure, scope | `--baseline` accepts any harness, so a DSH run can replace the openai-agents baseline. | fixed: `--baseline` takes an openai_agents profile only; test_baseline_only_from_openai_agents |
| F173 | Nit | contract, failure, scope | Results named `<date>-<profile>`: `default` files mix harnesses over time and a same-day run overwrites. | accepted: task 1.1 names results by profile; each file records its template and harness, and git keeps earlier runs |
| F174 | Nit | contract, scope | No test covers the results file name or `paired_dsh`. | fixed: test_paired_dsh_restores_dsh_control and test_results_are_written_as_tasks_finish (file name) |
| F175 | Nit | contract | Pass/fail comes from the last checkpoint's workspace, not task status (predates the phase). | accepted: predates the phase; all 20 recorded rows are `succeeded` |
| F176 | Nit | contract | `tool_calls` double-counts a retried turn (cumulative per turn, D11; predates the phase). | accepted: predates the phase; no recorded run retried a turn |
| F177 | Nit | contract | Benchmark rows omit `usage_known`. | fixed: rows and the report carry `usage_known`; test_results_are_written_as_tasks_finish |
| F178 | Nit | contract | `verdict_for` equals "at most one fails" only while the baseline is 10/10. | accepted: equivalent while the baseline is 10 of 10, as it is |
| F179 | Nit | contract | The licence check skips pins not written `name==version` (e.g. `pkg @ url`). | fixed: check_dsh_licences.py reports a requirement line that is not a `name==version` pin; test_a_pin_not_written_name_equals_version_fails |
| F180 | Nit | contract, scope | Any non-empty file satisfies a pin's notices. | accepted: the check proves presence; `export` copies the wheel's own licence files |
| F181 | Nit | contract, scope | The Compose pair test does not compare the pairs' security settings. | fixed: test_dsh_pairs_share_their_isolation_settings (fails when dsh-b's AppArmor setting is changed) |
| F182 | Nit | contract, failure, scope | `dsh-b` depends on `dsh-a`, coupling the pairs. | accepted: the dependency only orders the shared image build; runbook says a running dsh-b does not need dsh-a |
| F183 | Nit | contract | `make workers-up` does not enforce the notes' orchestrator-before-workers order. | accepted: the orchestrator and workers share one image and `make workers-up` starts them together after `make migrate` |
| F184 | Nit | contract | Prometheus does not scrape the DSH workers. | accepted: outside phase 03; observability of DSH workers belongs with Phase 2 event streaming |
| F185 | Nit | contract | No integration test submits on `default` and checks `local-dsh` end to end. | accepted: covered by the recorded live runs (F166); an end-to-end DSH task test needs the real model or the DSH outcome suite's fake-model stack |
| F186 | Nit | contract | The offline link check skips `docs/licences`. | accepted: intended; upstream notices stay verbatim |
| F187 | Nit | failure | Benchmark rows are written only at the end; an exception loses every finished row. | fixed: results are rewritten after each task; test_results_are_written_as_tasks_finish |
| F188 | Nit | failure | `start_container` leaks its temp directory if `docker run` fails; a killed benchmark leaves an unlabelled container. | fixed: tests/support/dsh_container.py removes its attempt directory when `docker run` fails and labels containers `praxismesh.dsh-test`; tests/test_dsh_container.py |
| F189 | Nit | failure | `paired_dsh` pops a pre-existing `DSH_CONTROL` instead of restoring it. | fixed: `paired_dsh` restores an earlier DSH_CONTROL; test_paired_dsh_restores_dsh_control |
| F190 | Nit | failure, scope | `check_dsh_licences.py export` deletes the notices before checking every pin has licences in the image. | fixed: `replace_notices` checks every pin before writing and swaps a staged tree in; test_export_keeps_notices_when_a_pin_has_none |
| F191 | Nit | failure | "Pause submissions" does not cover a workflow submitted but not yet resolved when the orchestrator restarts. | fixed: runbook step 1 waits for recent tasks' first attempt before the restart |
| F192 | Nit | failure | The runbook says a DSH container restart clears the tmpfs volume; the worker keeps it mounted (the launcher's start-up reap is what cleans). | fixed: runbook says the launcher's start-up reap cleans, not the tmpfs |
| F193 | Nit | failure, scope | `make workers-up` now fails on a host that cannot run the DSH container. | accepted: intended by task 2.1 (`make workers-up` starts the DSH pairs) |
| F194 | Nit | scope | R20 does not cover the image's Debian `git` package or base image. | accepted: R20 covers the pinned Python distributions; the image's Debian packages are outside it |
| F195 | Nit | scope | `check_dsh_licences.py` is not in mypy `files`. | fixed: pyproject.toml mypy files include check_dsh_licences.py |
| F196 | Nit | scope | The 90-minute drain bound starts after the first two workflow Activities, not at submission. | fixed: runbook states the bound is counted from the first turn |
| F197 | Nit | scope | The runbook's "about 1.9x the wall time" is the spike's figure; R19 measured about 1.3x. | fixed: runbook gives the measured 1.3x |
| F198 | Nit | scope | `adr_review` changed from `pending` to `null` outside any phase 03 task. | accepted: owner's instruction of 2026-11-17 (the `pending` marker was stale; set at close) |

## 2026-11-17 · impl-review · phase 03 · round 2 · passed

- Targeted follow-up (docs/reviews/README.md rule 6) on 89ac455cf1474db179b04ff1b090b0447921fe4a..d55f3ad (code_sha d55f3ad); one fresh `impl-reviewer` subagent (contract lens). Raw report: docs/reviews/general-dsh-production-harness/raw/impl-review-phase-03-round-2-contract.md.
- Before the round: full integration suite at d55f3ad, 178 passed.
- Reviewer: Contract completed. No Blocker or Major; every round 1 fix confirmed enforced (F166-F172, F174, F177, F179, F181, F187-F192, F195-F197).

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F199 | Nit | contract | The runbook's revert checklist misses comments in the Makefile, Compose, the demo script and the profiles that say `default` is DSH. | fixed: runbook step 2 names them and how to find them (docs only) |
| F200 | Nit | contract | Per-task writes let an interrupted same-day run replace committed results with an "Incomplete" file. | accepted: as F173; the partial file says "Incomplete" and git keeps the committed run |
| F201 | Nit | contract | No test drives `main`'s per-task write or its `WorkerStopped` path. | accepted: both are short and covered by `write_results`/`await_result` tests; `main` needs a model and a worker to drive |
| F202 | Nit | contract | No automated check keeps the Phase 1 demo on `openai`; its demo row has no commit. | accepted: a manual demo script; the rerun is recorded (at d55f3ad's script) |
| F203 | Nit | contract | "A few seconds" for the first two Activities is not a bound while the orchestrator is down. | accepted: the runbook counts the bound from the first turn, which is correct |
| F204 | Nit | contract | The plan's decision-log line for 2026-11-17 was out of date order. | fixed: moved to the end of the plan's Decision log (docs only) |

## 2026-11-17 · approved · phase 03 closure

Coordinator approval gate passed on PR #71 (merged as c015e0a): code_sha d55f3add6dcb9e2db2d4bf3047f3bb78be0cfdf7, docs_sha 06dd64737ee280d33574422982a2dcd37504ea31, head_sha 3598ab856d1330b809dc8c67b097727f63376af2 with `ci-ok` green; record: https://github.com/geosp/praxismesh/pull/71#issuecomment-6966523680.

## 2026-11-17 · ADR review

- In force, reviewed: ADR-0002, ADR-0003, ADR-0005, ADR-0006 (ADR-0001 and ADR-0004 are proposed).
- Covered already: D3 (ADR-0006); D1, D4, D5, D6 (ADR-0005 conditions 2-5). Tactical: D2, D8 (replaced by Phase 2's transport).
- Created, owner-confirmed: ADR-0007 (D10, the attempt fence) and ADR-0008 (D7, D9, D11, ledgered usage and conservative charging).
- Independent review by fresh `design-reviewer` subagents, one at a time (raw: docs/reviews/general-dsh-production-harness/raw/adr-review-*):
  - round 1 at 97578b7: both changes-requested (ADR-0007: stale failure path writes, orphaned blobs kept indefinitely; ADR-0008: rule stated for every runner, true for ledgered runners only); fixed in 03dd1b6;
  - round 2 at 03dd1b6: ADR-0008 pass; ADR-0007 changes-requested (incomplete list of writes skipping the newer-attempt check); fixed in 19fc4e2;
  - round 3 at 19fc4e2: ADR-0007 pass; its Nit (checkpoint blobs can be orphaned too) fixed.
- Both ADRs `accepted`.
- Verification Nit V1 (README `PRAXIS_SAMPLE_DB_URL`) fixed in the same change.

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

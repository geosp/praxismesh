# Reviews · Phase 2 - real-time events and the comms MCP

## 2026-11-18 · design-review · plan · round 1 · changes-requested
Reviewers: fresh reader ✅ (attempt 1 read only ~41 of 316 lines and was retried) · codebase fit ✅ · zoom out ✅ (plan at 3e9df4a; raw: docs/reviews/phase-2/raw/design-review-round-1-*.md)

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | codebase fit, zoom out | Message idempotency key includes the attempt (and an unknowable call number), so a retried attempt stores the message twice (R11) | fixed: D13, notes.md#d6 (key without attempt or call number) |
| F2 | Major | codebase fit, zoom out | Migration 0005 is split across phases 01 and 02 | fixed: migrations 0005 (phase 01) and 0006 (phase 02) |
| F3 | Major | codebase fit, fresh reader | `task submit --request` collides with the existing JSON-file flag; no task lets a task join a request | fixed: D5 `--join`, phase 02 task 2.3 |
| F4 | Major | codebase fit, zoom out | Wakes run turns, so `max_turns` (6, cap 10) ends tasks long before D11's 40 wakes; status when a budget runs out while waiting is unstated | fixed: D14 and R22 (owner: separate `max_wakes`); R21 (owner); test profile in phase 03 task 1.4 |
| F5 | Major | codebase fit, zoom out | The wait loop has no source for question deadlines, and a wake that lands during a turn or before Continue-As-New is lost | fixed: D7, R15, notes.md#d7 (claim before sleeping, `woken` flag in `TaskState`, deadlines from the claim) |
| F6 | Major | codebase fit, zoom out | The restore path replays a checkpoint's finish report across turns, so a woken turn would return `waiting` again; how claimed messages reach the turn input is unstated | fixed: phase 02 task 3.2, notes.md#d7 |
| F7 | Major | codebase fit | The fake model serves one script and cannot use a dynamic correlation ID, so it cannot script two agents | fixed: D16, phase 03 task 1.1 |
| F8 | Major | codebase fit, zoom out | The runner interface cannot take the Activity's per-attempt publisher; two producers per attempt give two `seq` counters and colliding batch IDs | fixed: D2 (Activity owns the publisher; `HarnessRunner.run` gains `events`), phase 01 task 2.2 |
| F9 | Major | codebase fit, zoom out, fresh reader | `post_status` has no defined target | fixed: D15 |
| F10 | Major | codebase fit, zoom out, fresh reader | Rollout: v2 workers refuse v1 turns; orchestrator must deploy before harness workers; rollback must drain every task started on new code | fixed: Rollout & rollback (drain, orchestrator first, rollback drains new-code tasks) |
| F11 | Major | zoom out, codebase fit | Sends to a finished task wait out the deadline; `cancel_for` writes no wake rows; no lock order for message writes | fixed: R24, R25, D10, notes.md#d6 |
| F12 | Major | zoom out | Message bodies in blobs add S3 access and orphan blobs for no requirement; how `comms_mcp` reaches the database is unstated | fixed: D6 (text column), D13 and notes.md#d6 (`praxis_comms` role) |
| F13 | Major | zoom out, fresh reader | "Asking ends the turn" depends on the model; the risk mitigation (deliver at next wait) fails when the turn ends `done` | fixed: R19 and D8 (owner: refuse `done` with open questions); Summary and Risks |
| F14 | Major | fresh reader | R6 (200 ms after the oldest unpublished event) and D2 ("every 200 ms") differ | fixed: D2 points to R7 |
| F15 | Major | fresh reader | R4 says the superseded attempt stops; D2 stops it only at the next model call | fixed: R5, D2 |
| F16 | Major | fresh reader | `get_task_context` is not specified, so how an agent learns whom it may message is unstated | fixed: D15 |
| F17 | Major | fresh reader | Summary omits how tasks share a request and the rollback constraint | fixed: Summary |
| F18 | Major | fresh reader | Terms used but not defined: checkpoint, `TaskState`, resolved task, `before_model_call`, §4.4 | fixed: Terms |
| F19 | Nit | zoom out | Risk "publish fewer, larger batches" contradicts R6 | fixed: Risks (returns to design review to change R7) |
| F20 | Nit | zoom out | `event_batches` grows until manual prune | fixed: D1, notes.md#d1 |
| F21 | Nit | codebase fit, zoom out | Request and task advisory locks share one `hashtext` key space | fixed: notes.md#d6 two-key request lock |
| F22 | Nit | zoom out | `expire_due` uses database time while the Workflow timer uses Temporal time | fixed: notes.md#d7 (`now` from the Workflow) |
| F23 | Nit | zoom out | DSH already emits one token event per response; D3 would double it | fixed: D3 |
| F24 | Nit | codebase fit, zoom out | No task writes `docs/demos/phase-2.md` | fixed: phase 03 task 2.1 |
| F25 | Nit | codebase fit, zoom out | Phase 03 task 1.2 cites R18 for cases that do not cancel | fixed: phase 03 task 1.3 |
| F26 | Nit | zoom out | Several orchestrator replicas would each run a dispatcher | fixed: notes.md#d6 (`SKIP LOCKED`) |
| F27 | Nit | codebase fit | notes.md says `workers/main.py` gives the DSH runner `NoOpSink`; the runner defaults to it | fixed: notes.md evidence |
| F28 | Nit | codebase fit | Reuse the existing `TaskWorkflow` replay test and Phase 1 fixture | fixed: D12, R29 |
| F29 | Nit | codebase fit | A continued run must skip `record_task` (it refuses a different run ID) | fixed: D11, notes.md#d7 |
| F30 | Nit | codebase fit | The port list omits the in-memory reference (`memory.py`) | fixed: phase 01 task 1.2 |
| F31 | Nit | codebase fit | `reply` must compare the deadline itself, not only the status | fixed: R18, notes.md#d7 |
| F32 | Nit | codebase fit | `AttemptOutcome` and `RunResult.status` also need `waiting` | fixed: phase 02 task 3.1 |
| F33 | Nit | fresh reader | R4, R9, R10, R11, R18, R19 each hold two rules | fixed: split into R4/R5, R10/R11, R12/R13, R26/R27; R24 and R28 kept as one rule each about one outcome |
| F34 | Nit | fresh reader | Smaller undefined terms and rereads (DSH, `Superseded`, `PRAXIS_*`, profile, owner, task numbering); facts repeated across D9, D13, R19 | fixed: Terms; D9, D13 and R26 now state identity once each with distinct points |
| F35 | Nit | fresh reader | Summary nits: R-number citations, wall-time trigger, idle completion status; R16 has no tolerance | fixed: Summary; R20 tolerance 60-65 s |

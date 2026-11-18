# Reviews · Phase 2 - real-time events and the comms MCP

## 2026-11-18 · design-review · plan · round 1 · changes-requested
Reviewers: fresh reader ✅ (attempt 1 read only ~41 of 316 lines and was retried) · codebase fit ✅ · zoom out ✅ (plan at 3e9df4a; raw: docs/reviews/phase-2/raw/design-review-round-1-*.md)

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | codebase fit, zoom out | Message idempotency key includes the attempt (and an unknowable call number), so a retried attempt stores the message twice (R11) | open |
| F2 | Major | codebase fit, zoom out | Migration 0005 is split across phases 01 and 02 | open |
| F3 | Major | codebase fit, fresh reader | `task submit --request` collides with the existing JSON-file flag; no task lets a task join a request | open |
| F4 | Major | codebase fit, zoom out | Wakes run turns, so `max_turns` (6, cap 10) ends tasks long before D11's 40 wakes; status when a budget runs out while waiting is unstated | open |
| F5 | Major | codebase fit, zoom out | The wait loop has no source for question deadlines, and a wake that lands during a turn or before Continue-As-New is lost | open |
| F6 | Major | codebase fit, zoom out | The restore path replays a checkpoint's finish report across turns, so a woken turn would return `waiting` again; how claimed messages reach the turn input is unstated | open |
| F7 | Major | codebase fit | The fake model serves one script and cannot use a dynamic correlation ID, so it cannot script two agents | open |
| F8 | Major | codebase fit, zoom out | The runner interface cannot take the Activity's per-attempt publisher; two producers per attempt give two `seq` counters and colliding batch IDs | open |
| F9 | Major | codebase fit, zoom out, fresh reader | `post_status` has no defined target | open |
| F10 | Major | codebase fit, zoom out, fresh reader | Rollout: v2 workers refuse v1 turns; orchestrator must deploy before harness workers; rollback must drain every task started on new code | open |
| F11 | Major | zoom out, codebase fit | Sends to a finished task wait out the deadline; `cancel_for` writes no wake rows; no lock order for message writes | open |
| F12 | Major | zoom out | Message bodies in blobs add S3 access and orphan blobs for no requirement; how `comms_mcp` reaches the database is unstated | open |
| F13 | Major | zoom out, fresh reader | "Asking ends the turn" depends on the model; the risk mitigation (deliver at next wait) fails when the turn ends `done` | open |
| F14 | Major | fresh reader | R6 (200 ms after the oldest unpublished event) and D2 ("every 200 ms") differ | open |
| F15 | Major | fresh reader | R4 says the superseded attempt stops; D2 stops it only at the next model call | open |
| F16 | Major | fresh reader | `get_task_context` is not specified, so how an agent learns whom it may message is unstated | open |
| F17 | Major | fresh reader | Summary omits how tasks share a request and the rollback constraint | open |
| F18 | Major | fresh reader | Terms used but not defined: checkpoint, `TaskState`, resolved task, `before_model_call`, §4.4 | open |
| F19 | Nit | zoom out | Risk "publish fewer, larger batches" contradicts R6 | open |
| F20 | Nit | zoom out | `event_batches` grows until manual prune | open |
| F21 | Nit | codebase fit, zoom out | Request and task advisory locks share one `hashtext` key space | open |
| F22 | Nit | zoom out | `expire_due` uses database time while the Workflow timer uses Temporal time | open |
| F23 | Nit | zoom out | DSH already emits one token event per response; D3 would double it | open |
| F24 | Nit | codebase fit, zoom out | No task writes `docs/demos/phase-2.md` | open |
| F25 | Nit | codebase fit, zoom out | Phase 03 task 1.2 cites R18 for cases that do not cancel | open |
| F26 | Nit | zoom out | Several orchestrator replicas would each run a dispatcher | open |
| F27 | Nit | codebase fit | notes.md says `workers/main.py` gives the DSH runner `NoOpSink`; the runner defaults to it | open |
| F28 | Nit | codebase fit | Reuse the existing `TaskWorkflow` replay test and Phase 1 fixture | open |
| F29 | Nit | codebase fit | A continued run must skip `record_task` (it refuses a different run ID) | open |
| F30 | Nit | codebase fit | The port list omits the in-memory reference (`memory.py`) | open |
| F31 | Nit | codebase fit | `reply` must compare the deadline itself, not only the status | open |
| F32 | Nit | codebase fit | `AttemptOutcome` and `RunResult.status` also need `waiting` | open |
| F33 | Nit | fresh reader | R4, R9, R10, R11, R18, R19 each hold two rules | open |
| F34 | Nit | fresh reader | Smaller undefined terms and rereads (DSH, `Superseded`, `PRAXIS_*`, profile, owner, task numbering); facts repeated across D9, D13, R19 | open |
| F35 | Nit | fresh reader | Summary nits: R-number citations, wall-time trigger, idle completion status; R16 has no tolerance | open |

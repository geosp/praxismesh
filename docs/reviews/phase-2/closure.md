# Phase 2 coordinator closure

Closed 2026-11-19 under the coordinator approval gate in
[the review protocol](../README.md) and plan sections 7.0 and 8. Issue #79 was
closed when PR #86 merged. This record brings together independent evidence that
already exists; it is not a new implementation review or verification.

Phase 2 was built as two implementation plans, each reviewed and verified on its own:

- **Events:** the event table and `agentctl tail`, in
  [docs/plans/2026-11-18-phase-2-agent-events](../../plans/2026-11-18-phase-2-agent-events/plan.md) (PR #85).
- **Messaging:** the inbox, the comms MCP server and waiting tasks, in
  [docs/plans/2026-11-18-phase-2-events-and-comms](../../plans/2026-11-18-phase-2-events-and-comms/plan.md),
  phases 02 and 03 (PR #86). The plan was closed with ADR-0010 and ADR-0011 (PR #87).

## Revisions and delivery

| Reference | Revision |
|---|---|
| Events: independently tested code | `499eb635d605826e912fb0fb4f52f02e63da99c5` |
| Events: assessed as-built docs | `965e8e83e9d24d5798d5dd367092c5d29953da34` |
| Events: final PR #85 head | `92403e8beba251f1ccc4ed2577b19aac1582b49f` |
| Events: delivery on main, PR #85 | `2f4b012a628f39a7c6af0c8d4c9b5d5e76ad89cd` |
| Messaging: independently tested code | `417c441c0f3c65ec637f873113a41d72aeda1e0e` |
| Messaging: assessed as-built docs | `8e9802ad67a36d28fbf8785cf4dd2ab58e65d051` |
| Messaging: final PR #86 head | `d0cc9f60ad00fc97c87dbbe5271bee0d1ca76c79` |
| Messaging: delivery on main, PR #86 | `95d75ab4ae3afdd7427431a529ab71905d3f59cf` |
| Plan close and ADRs: final PR #87 head | `0744002ad960525a1c0d0ef374726f11925eeefe` |
| Plan close and ADRs: delivery on main, PR #87 | `1b7b3d832a81f52bfbc1b3bec7bb9135ecbafa2f` |

The coordinator fetched merged main and compared it with each tested snapshot:

```sh
git diff --exit-code 499eb635d605826e912fb0fb4f52f02e63da99c5 2f4b012a628f39a7c6af0c8d4c9b5d5e76ad89cd -- . ':!docs'
git diff --stat 417c441c0f3c65ec637f873113a41d72aeda1e0e 95d75ab4ae3afdd7427431a529ab71905d3f59cf -- . ':!docs'
git diff --exit-code 417c441c0f3c65ec637f873113a41d72aeda1e0e 95d75ab4ae3afdd7427431a529ab71905d3f59cf -- . ':!docs' ':!*.md' ':!.github/workflows/ci.yml'
git diff --stat 95d75ab4ae3afdd7427431a529ab71905d3f59cf 1b7b3d832a81f52bfbc1b3bec7bb9135ecbafa2f -- . ':!docs'
```

- **Events:** exit 0, empty diff. The delivered source and tests match the verified snapshot.
- **Messaging:** the non-docs diff touches four files, none of them source or tests. Three are
  the status lines in `AGENTS.md`, `PROJECT_PLAN.md` and `README.md` (plan task 2.2, after
  verification). The fourth raises the CI `stack` job's `timeout-minutes` from 20 to 45, with a
  comment, because the new acceptance suites made the job run past 20 minutes. With those excluded,
  the third command exits 0: the delivered source and tests match the verified snapshot.
- **Plan close:** only the status lines in `AGENTS.md` and `PROJECT_PLAN.md` change outside `docs/`.

`ci-ok` and the `stack` job succeeded on all three final PR heads.

## Applicable independent evidence

Both plans ran at the light tier (Phases 0-2). The same coordinator ran the
implementation review and then the verification against the same code revision,
using fresh reviewer and verifier subagents one at a time; the reports state that
independence between the two was waived (`docs/reviews/README.md` rule 7). Raw
reports are in [raw/](raw/); the plans' `reviews.md` files hold every round.

| Gate | Events | Messaging |
|---|---|---|
| Design review | 2 rounds, passed | 3 rounds, passed |
| Implementation review | 1 round of three lenses, then a targeted follow-up: passed | phase 02: 2 rounds, passed; phase 03: 1 round, passed |
| Verification | [pass](verification-events.md) at `499eb63` (one acceptance failure on a test expectation, fixed and re-run) | [pass](verification-messaging.md) at `417c441` |
| Demo | [phase-2-events.md](../../demos/phase-2-events.md) | [phase-2.md](../../demos/phase-2.md), fake model by the verifier and the local model by the implementer |
| ADRs | ADR-0009 (from the issue #76 spike); ADR review: none needed | ADR-0010 and ADR-0011, accepted after fresh design-reviewer rounds |

## Acceptance and checklist basis

| Phase 2 deliverable (roadmap) | Evidence supporting completion |
|---|---|
| Event table behind the event-transport interface; the spike's shared suite and load runner ported | Events verification: `test_event_table.py` (shared suite, fence, lock order); `tests/benchmarks/event_load.py` fenced and unfenced: display p95 0.209 s, publish p95 10 ms |
| Batched deltas, monotonic `seq` and `attempt_id`, retention and reset semantics documented | Events plan R1-R9 tests; `schemas.md` and the runbook (tail, prune) |
| `comms_mcp` tools, worker-only and scoped | `test_comms_mcp.py`, `test_comms_role.py`, `test_messages.py`; ADR-0011 |
| Inbox and event migrations | `0005_agent_events`, `0006_task_messages`; at head in both verifications |
| Durable inbox: correlation, dedupe, deadlines, waking idle recipients, no circular waits, timeout and cancel propagation | `test_two_agents.py`, `test_messaging_failures.py` (R17 timeout, R10, R24, R13 worker kill), `test_messaging_endings.py`, `test_dispatcher.py`; ADR-0010 |
| `agentctl tail` with offset resume and gap detection | Events verification and demo; the messaging demo's observer reconnect showed every offset once |
| History stays bounded (R33) | `test_messaging_history.py`: 100 wakes in runs of 1,009, 1,013 and 443 events; 50 messages in one turn gave one run of 43 events and no `inbox` Signal |
| Demo evidence and reproduction steps | Both demo records: environment, commands, IDs, expected against observed, the failure and recovery case, cleanup |

The roadmap's wording asked for an outbox and blocking Update/Signal mechanics.
As built, a wake row committed with the message stands in for the outbox, and a
waiting task sleeps in its Workflow until a Signal wakes it, with no blocking
Update (ADR-0010). [The roadmap file](../../roadmap/phases/phase-2.md) records this.

## Agent benchmark

Phase 2 moved both templates to version 2: each grants the comms server and uses the
`local-comms.md` system prompt. The roadmap's benchmark rule requires a rerun after such a change,
so the coordinator ran `make benchmark` for both templates at merged main `1b7b3d8`, on a
throwaway Compose stack, against the local model (the DGX Spark vLLM endpoint):

| Profile | Template | Passed | Baseline | Record |
|---|---|---|---|---|
| `openai` | `local-default@2` (`openai_agents`) | 10 of 10 | 10 | [2026-11-19-openai.md](../../benchmarks/2026-11-19-openai.md) |
| `dsh` | `local-dsh@2` (DSH; also the `default` profile's template) | 10 of 10 | 10 | [2026-11-19-dsh.md](../../benchmarks/2026-11-19-dsh.md) |

Both are within the regression limit (closure is blocked at 8 or fewer). The recorded baseline is unchanged.

## Open items carried forward

These do not block closure; each is tracked:

- #88: add the comms server's database boundary and the `praxis_comms` role to the threat model (ADR-0011 follow-up).
- #89: the registry loader should refuse `PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT` in an MCP server's `env` and `secret_env`.
- Threat model R1, accepted until Phase 5: on `openai_agents`, `run_command` with `sh` can read the worker's environment, including the comms URL (ADR-0011).
- ADR-0010: a terminated (not cancelled) Workflow never runs `complete_task`; scheduled retention of messages and events belongs to Phase 3A.

## Next phase

Phase 3 is next. The final head of this closure PR is recorded in its PR
description, not in this file. Latest-head CI is still required before the owner merges.

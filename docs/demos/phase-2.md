# Demo: Phase 2, two agents communicating while an observer watches

Plan: [docs/plans/2026-11-18-phase-2-events-and-comms](../plans/2026-11-18-phase-2-events-and-comms/plan.md), phase 03 task 2.1 (R10, R14, R16, R17, R33). Roadmap: [Phase 2 demo checklist](../roadmap/phases/phase-2.md). Issue #79. The event table half of the checklist (live tail, reconnect, batching) was first recorded in [phase-2-events.md](phase-2-events.md); this run shows it again on a conversation between two agents.

- Recorded 2026-11-19 by the implementer at `90ad371` (branch `feat/79-agent-messaging`), on the
  owner's local stack (`COMPOSE_PROJECT_NAME=praxismesh`), with the owner's approval:
  `PRAXIS_COMMS_DB_PASSWORD` and `PRAXIS_COMMS_DB_URL` added to `infra/.env`, the `db` container
  recreated (`make up`), then `make db-roles`, `make migrate` (to `0006`) and `make workers-up`;
  profile `default` (`local-dsh` v2, DSH) on the local model endpoint. Python 3.11.17,
  `temporalio` 1.36.0, SQLAlchemy 2.1.8, `asyncpg` 0.32.0.
- Reproduce: `sh infra/demo/phase-2-messaging.sh [OUT_DIR]` (needs the setup above, a model
  endpoint, and `python3`, `uv` and `timeout` on the host). Each step's instructions carry a
  `[script:NAME]` marker, so the same script runs on the fake model.
- Dry run: from a clean worktree at `a0faad5` whose `infra/.env` is `infra/.env.example` with only
  the project name and ports changed (a separate project beside the owner's), on the fake model
  (`VLLM_BASE_URL=http://fake-model:8765 make workers-check`, then `make workers-up` with the same
  variable). It found that the probe could not import the repository's packages, fixed in
  `5b68eb6`; the rerun at `5b68eb6` passed every step.

| Step | Command or action | Expected | Observed | Result |
|---|---|---|---|---|
| Idle B | `./agentctl task submit --profile default --instructions "[script:demo-answerer] You are the price desk of this request. First call finish_task with status \"waiting\" ..."` | B's first turn ends `waiting`; its Workflow sleeps | request `req-8ad4ccbb-8745-4b01-8dc5-b7503d617ae6`, B `task-fb1a3baf-f5a0-4ae1-8cbe-1eab920d60e8`; probe `sleeping`: yes | pass |
| A asks B | `./agentctl task submit --profile default --join req-8ad4ccbb-... --instructions "[script:demo-asker] Please ask task task-fb1a3baf-... the question \"What is the price of SKU-4?\" with ask_agent, within 600 s ..."` | A asks and waits | A `task-0932bde5-292f-486e-9032-b1f669ab9a27`; tail: `3 ... tool_call {"call": 1, "tool": "ask_agent"}` ... `8 ... status {"status": "waiting"}` | pass |
| Observer live | `./agentctl tail task-0932bde5-...` (background) | one line per event as it happens | offsets 1-8 of turn 1 (above) | pass |
| B woken, answers; A resumes (R14, R16) | the question wakes B; B's reply wakes A | a correlated answer reaches A | messages: `ask A -> B answered "What is the price of SKU-4?"`, `reply B -> A read "The price of SKU-4 is 4.1 USD."`; A `succeeded`, summary "I asked task-fb1a3baf-... the question \"What is the price of SKU-4?\" and received the answer: The price of SKU-4 is 4.1 USD."; B `succeeded` | pass |
| Disconnect and reconnect | stop the first tail; `./agentctl tail task-0932bde5-... --after 8` | resumes after the last offset; no duplicate | first tail stopped after offset 8; the second printed `9 ... :2:1 reset {"restored_from": "task-0932bde5-...:1:1:1"}` to `13 ... status {"status": "done"}` and stopped when the Workflow closed; across both: 13 lines, offsets 1-13 once each, in order | pass |
| Unanswered question (R17) | D waits and never answers; C asks D `within 20 s (deadline_seconds 20)` | C is woken and told; no hang | D `task-9a6316fb-3af8-4762-8984-ff79a442fcd8`, C `task-39be2bc7-aafe-4af8-8f43-c6283e526fe0`; message `ask C -> D expired`; C `succeeded` 45 s after submit: "... I was woken with the notification that no answer came by the deadline ..." | pass |
| Unauthorized message (R10) | E, in a new request, is told to message B | the send is rejected | E `task-1d94486c-26f2-4d64-99d1-33f082a3f97a` in `req-b16ef9aa-4e01-4f3c-80a1-b440f791261c`; message `send E -> B rejected`, reason "task-fb1a3baf-... is not a task of this request"; B received nothing | pass |
| Batching and history (R33) | `messaging_probe.py batches` and `history` | events stored in batches; each Workflow's history bounded | A: 13 events in 7 batches; one run each: A 55 events (14,518 bytes), B 55 (14,566), C 54 (14,909), D 55 (12,276) | pass |
| Cleanup | `messaging_probe.py cancel task-9a6316fb-...` | D ends through `complete_task` | D `failed` ("cancelled"), Workflow `COMPLETED` | pass |

The bounds under load are tested, not demonstrated: `tests/integration/test_messaging_history.py`
woke one task 100 times back to back (three runs of 1,009, 1,013 and 443 events) and sent 50
messages during one turn (one run of 43 events, no `inbox` Signal).

Found while recording: in the first run on the owner's stack (`req-79a8ab8b-...`), the local
model did not follow D's instructions (it looked for an order to process and ended
`needs_input`), so the demo waited 300 s for D to sleep and stopped. The steps before it had
passed. `90ad371` makes D's instructions plain and stops the demo at once if a task ends instead
of waiting; the run above is the rerun.

After the demo the owner's stack runs this branch's workers and migration `0006`. To return to
`main` before this branch merges, first run `uv run --env-file infra/.env alembic -c
common/persistence/alembic.ini downgrade 0005` from this branch (`main` does not know `0006`),
then check out `main` and run `make workers-up`. No task of this demo is left waiting.

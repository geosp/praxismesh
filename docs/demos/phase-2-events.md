# Demo: Phase 2 events, the event table and `agentctl tail`

Plan: [docs/plans/2026-11-18-phase-2-agent-events](../plans/2026-11-18-phase-2-agent-events/plan.md), task 4.1 (R2, R3, R6, R9). Issue #79.

- Recorded 2026-11-18 by the implementer at `acd713e` (branch `feat/79-agent-events`), on the
  owner's local stack (`COMPOSE_PROJECT_NAME=praxismesh`): migration `0005` applied with
  `make migrate`, workers rebuilt with `make workers-up`; profile `default` (`local-dsh`, DSH)
  on the local model endpoint. Python 3.11, `temporalio` 1.36.0, SQLAlchemy 2.1.8, `asyncpg`
  0.32.0.
- Reproduce: `sh infra/demo/phase-2-events.sh [OUT_DIR]` (needs `make workers-up`, a model
  endpoint, and `python3`, GNU `grep` (`-P`) and `timeout` on the host). The phase verification
  reruns it from a clean worktree.

| Step | Command or action | Expected | Observed | Result |
|---|---|---|---|---|
| Submit | `./agentctl task submit --profile default --output order-summary.md --instructions "Use the order-desk skill. Order 2 units of SKU-4, ..."` | a DSH task | `task-f2492737-97a7-49b5-9c18-fbb7f072b951` | pass |
| Tail live | `./agentctl tail task-f2492737-...` (background) | one line per event: offset, attempt, type, payload | `1  task-f2492737-...:1:1  reset  {"restored_from": null}`, `2 ... token {"input_tokens": 1490, "output_tokens": 48, "request_id": "req-0001"}`, `3 ... tool_call {"call": 1, "tool": "read_file"}` ... | pass |
| Kill the worker mid-turn | after the task's second checkpoint, `docker kill` the container holding the attempt | the turn is retried on the other worker | latest checkpoint `...:1:1:1`; killed `praxismesh-worker-dsh-a-1`; attempts: `(1, 1, lost)` on `0877e4299f1f`, `(1, 2, done)` on `cbce89aa580f` | pass |
| Retried attempt opens with reset (R9) | the tail's lines for attempt 2 | its first event is a `reset` naming the restored checkpoint | `22  task-f2492737-...:1:2  reset  {"restored_from": "task-f2492737-...:1:1:1"}` | pass |
| Stop and resume (R2) | stop the first tail 15 s after the kill; `./agentctl tail task-f2492737-... --after 21` | resumes at 22; together the two tails show every offset once | first tail stopped after offset 21; second tail printed 22..41 and stopped when the Workflow closed (`status {"status": "done"}` at 41); offsets across both: 1..41, each once | pass |
| Task outcome | `./agentctl task status ...` | the task completes despite the lost worker | `succeeded`, Workflow `COMPLETED` | pass |
| No model text (R6) | the payload keys in both tails | counts, names, IDs and statuses only | keys: `call`, `input_tokens`, `output_tokens`, `request_id`, `restored_from`, `status`, `tool`; 41 events: 2 reset, 6 token, 16 tool_call, 16 tool_result, 1 status | pass |
| Prune and expiry (R3) | `./agentctl events prune --task task-f2492737-... --below 10`; `./agentctl tail task-f2492737-... --after 3 --no-follow` | the retained base is 10; the tail reports the expiry first, then 10 onwards | `{"task_id": "task-f2492737-97a7-49b5-9c18-fbb7f072b951", "retained_base": 10}`; `expired: events before 10 were pruned`, then `10 ... tool_call {"call": 4, "tool": "lookup_price"}` ... | pass |
| Cleanup | `docker start praxismesh-worker-dsh-a-1` | the killed worker serves again | restarted | pass |

Found while recording: `tail` printed through Python's block buffer, so a tail stopped early
lost lines it had already read. Fixed in `acd713e` (each line is flushed); the first run's task
(`task-c9f3acdb-...`) also completed, with its events stored.

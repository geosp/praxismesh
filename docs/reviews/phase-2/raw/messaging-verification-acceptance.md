<!-- Provenance: verbatim copy of .verify/report-acceptance.md, written by a fresh verifier subagent (verify-phase gate mode, brief "Acceptance and demo") for Phase 2 messaging (phases 02 and 03) at code_sha 417c441c0f3c65ec637f873113a41d72aeda1e0e. Copied with cp; not edited. -->

# Verification report: Phase 2 messaging (plan phases 02 and 03)

- Checkout: `/tmp/claude-1000/-home-geo-develop-praxismesh/599639d3-a59f-4a32-945c-fd5372c3c537/scratchpad/verify-phase2-messaging`, `git rev-parse HEAD` = `417c441c0f3c65ec637f873113a41d72aeda1e0e`; the only change in the tree is the untracked `.verify/` directory (`git status --short` -> `?? .verify/`) plus the git-ignored `infra/.env`.
- Compose project `pmphase2` only. I did not touch the owner's `praxismesh` project.
- Model: no real endpoint was available. Everything that needs a model ran on the documented fake model (`http://fake-model:8765`).
- Logs are under `.verify/` in the checkout. Each one is named below.

**Verdict: PASS.** Every acceptance test and every messaging demo-checklist item I could run passed on the fake model, with quoted output. The recorded run in `docs/demos/phase-2.md` used the owner's local model, so I could not reproduce it and it is **blocked (not verified)**. The findings below are minor and documentation-only.

## 1. Prerequisites (documented steps, in order)

| # | Step (source) | Command | Exit | Observed |
|---|---|---|---|---|
| 1 | README "Local stack": `cp infra/.env.example infra/.env` | `cp infra/.env.example infra/.env`, then a sed that changes only `COMPOSE_PROJECT_NAME=pmphase2`, `DB_PORT=45432`, `TEMPORAL_PORT=47233`, `TEMPORAL_UI_PORT=48080`, `S3_PORT=48333`, and port `45432` in `PRAXIS_SAMPLE_DB_URL` and `PRAXIS_COMMS_DB_URL` | 0 | `diff infra/.env.example infra/.env` shows exactly those 7 lines. `PRAXIS_COMMS_DB_PASSWORD=change-me-comms` is kept from the example. |
| 2 | README set-up | `uv sync --locked` | 0 | `Resolved 90 packages ... Checked 86 packages` (`uv-sync2.log`) |
| 3 | Runbook "Messaging between tasks" -> Setup: "recreate the db container ... (`make up`)" | `make up` | 0 | `Container pmphase2-db-1 Recreate ... Healthy`, `stack is up; run 'make status' for addresses and health` (`make-up.log`) |
| 4 | README | `make status` | 0 | `addresses: Temporal 127.0.0.1:47233, UI http://127.0.0.1:48080, S3 http://127.0.0.1:48333, DB 127.0.0.1:45432` / `model endpoint: not configured (VLLM_BASE_URL is empty)` / `all services healthy` |
| 5 | Runbook: `make db-roles` (safe to rerun) | `make db-roles` | 0 | `ALTER ROLE` `GRANT` `GRANT` `DO` `praxis_comms role ready` |
| 6 | Runbook: `make migrate` (0006) | `make migrate`, then `alembic ... current` | 0 | `0006 (head)` |
| 7 | Demo doc, dry-run line | `VLLM_BASE_URL=http://fake-model:8765 make workers-check` | 0 | The scripted task returned `"summary": "Ordered 3 x SKU-1."`, `"template": "local-default"`, `"template_version": 2` (`workers-check.log`) |
| 8 | Demo doc, dry-run line ("then `make workers-up` with the same variable") | `VLLM_BASE_URL=http://fake-model:8765 make workers-up` | 0 | orchestrator, worker-a/b, dsh-a/b and worker-dsh-a/b were all `Healthy`. `printenv VLLM_BASE_URL` in orchestrator and worker-dsh-a -> `http://fake-model:8765` |

I started the workers (steps 7 and 8) only after the integration suite had finished, and removed them again afterwards (section 4).

## 2. Acceptance tests

| Command | Exit | Summary line |
|---|---|---|
| `uv run ruff check .` | 0 | `All checks passed!` |
| `uv run ruff format --check .` | 0 | `461 files already formatted` |
| `uv run mypy` | 0 | `Success: no issues found in 154 source files` |
| `uv run pytest` | 0 | `340 passed, 251 deselected in 59.05s` |
| `uv run .agents/sync_agents.py --check` | 0 | `ok: 3 generated agent file(s) up to date` |
| `uv run .github/scripts/check_plans.py` | 0 | `Validated 7 implementation plan(s); 0 error(s)` |
| `uv run .github/scripts/check_dsh_licences.py` | 0 | `licence notices present for 7 pinned DSH distributions` |
| `uv run pytest -v tests/test_task_workflow_waiting.py` | 0 | `15 passed in 10.96s`. All 15 pass, including `test_a_cancel_during_the_wait_still_completes_the_task`, `test_a_claim_that_keeps_failing_ends_the_task_through_complete_task`, `test_back_to_back_wakes_continue_as_new_and_stay_bounded` and `test_out_of_wall_time_ends_by_open_questions` (`pytest-waiting.log`) |
| `uv run --env-file infra/.env pytest -q -m integration -rs -s` (no pmphase2 worker containers running; checked with `docker ps` first) | 0 | `247 passed, 4 skipped, 340 deselected in 852.43s (0:14:12)` (`integration.log`) |

**The 4 skips** are all `tests/integration/test_model_endpoints.py`, with the reason `VLLM_BASE_URL is unset or empty; model endpoint not configured`. These model-endpoint tests are blocked (no real model). They are not messaging tests.

**Named messaging suites.** The full run had no failures, and the only skips are the 4 above, so every collected test in these files passed. Per-file counts come from `pytest --co` (`integration-collect.log`):

| File | Tests | Result |
|---|---|---|
| tests/integration/test_messages.py | 15 | passed |
| tests/integration/test_comms_mcp.py | 4 | passed |
| tests/integration/test_comms_role.py | 2 | passed |
| tests/integration/test_dispatcher.py | 3 | passed |
| tests/integration/test_harness_activity.py | 32 | passed |
| tests/integration/test_two_agents.py | 1 (`test_a_asks_b_and_resumes_with_the_answer`) | passed |
| tests/integration/test_messaging_failures.py | 4 (`test_an_unanswered_question_times_out`, `test_a_cross_request_message_is_refused`, `test_a_cancelled_recipient_tells_the_waiting_asker`, `test_a_send_before_a_killed_worker_is_delivered_once`) | passed |
| tests/integration/test_messaging_endings.py | 2 (`test_done_with_an_open_question_is_refused_and_the_task_waits`, `test_an_unread_message_to_an_ended_task_is_listed_as_undelivered`) | passed |
| tests/integration/test_messaging_history.py | 2 | passed |
| tests/test_task_workflow_waiting.py (unit) | 15 | passed |

**R33 lines printed by test_messaging_history.py**, captured with `-s`:

```
R33 runs (run id, events, inbox signals): [('01a1f42a-0c57-7134-bf29-bd10c0586bda', 1009, 41), ('1c6afd06-0c32-4173-afce-76dd98ed3902', 1013, 42), ('28e3cab6-9075-4240-867a-2fa86e3bd9f9', 443, 18)]
R33 runs (run id, events, inbox signals): [('01a1f42e-2489-7f3e-9f15-71c369ffe595', 43, 0)]
```

- First test (100 back-to-back wakes): 3 runs of 1,009, 1,013 and 443 events. All are under the 2,000-event bound, and Continue-As-New took place.
- Second test (50 messages in one turn): 1 run of 43 events with 0 `inbox` Signals, within "at most one".

The integration log also shows the expected refusal diagnostics, for example `Tool 'send_to_agent' failed: 'Error executing tool send_to_agent: refused: task-mcp-3356b51cfe44 is not a task of this request'`.

**Roadmap "Accept" line, messaging parts:**
- Two agents exchange an answer: test_two_agents, plus the demo.
- An idle recipient is woken: test_dispatcher, test_two_agents, plus the demo.
- An unanswered request times out: test_an_unanswered_question_times_out, plus the demo.
- A worker crash or Continue-As-New does not drop accepted messages: test_a_send_before_a_killed_worker_is_delivered_once, plus the 100-wake test, which receives a reply after a new run starts.
- Unauthorized messaging is rejected: test_a_cross_request_message_is_refused, plus the demo.

All passed. The events-half Accept items (reconnect without gaps, high token volume) were verified separately (`docs/reviews/phase-2/verification-events.md`). I did not re-verify them beyond the demo items below.

## 3. Demo: `sh infra/demo/phase-2-messaging.sh .verify/demo`

- Command: `timeout 1700 sh infra/demo/phase-2-messaging.sh .verify/demo`, run with the workers on the fake model, profile `default` (`local-dsh` v2, DSH).
- Result: exit 0 (`demo-run.log`). Output files are in `.verify/demo/` (`demo.txt`, `tail-1.log`, `tail-2.log`, `tail-all.log`, `messages.txt`, `history.txt`).
- Request `req-c498cf90-4955-4a01-9863-e15c71f6192e`.

| Checklist item | Expected (roadmap / docs/demos/phase-2.md) | Observed (quoted) | Result |
|---|---|---|---|
| Idle B | "B's first turn ends `waiting`; its Workflow sleeps" | `B (price desk): task-3b8cee3f-e2ab-48be-9bad-51dec5919d19` / `B is waiting (idle, its Workflow asleep)` (the `probe sleeping` check returned yes). B's tail: `5 ...:1:1 status {"status": "waiting"}` | pass |
| `agentctl tail` live; A asks B; correlated answer; idle B woken | "Open `agentctl tail` on a workflow; demonstrate Agent A asking Agent B a question and receiving a correlated answer, including waking an idle Agent B" | A `task-26e03b28-d870-4039-a27d-c7fd891cfbdc`. Live tail-1: `3 ...:1:1 tool_call {"call": 1, "tool": "ask_agent"}` ... `8 ...:1:1 status {"status": "waiting"}`. Messages: `ask task-26e03b28... -> task-3b8cee3f... answered - \| What is the price of SKU-4?` and `reply task-3b8cee3f... -> task-26e03b28... read - \| SKU-4 costs 12.50`. `A: succeeded, summary: SKU-4 costs 12.50` / `B: succeeded`. Histories: B `signals ['inbox']`, A `signals ['inbox']`, so each was woken by one dispatcher Signal. On correlation: the fake script takes B's `reply_to` from its woken input (`${input:Question (\S+) from}`) and A's summary from `Reply from ... to your question ...: (...)`, so the question ID and the reply both travelled through the woken turns' input. | pass |
| Disconnect and reconnect with last offset | "retained events resume in order without duplicate display" | `observer disconnected after offset 9`. tail-2 (`--after 9`) printed offsets 10-13, ending `13 ...:2:1 status {"status": "done"}`, and stopped when the Workflow closed. Both tails' `.err` files were empty. `observer saw 13 lines, 13 distinct offsets, highest 13 (each once and in order: yes)` | pass |
| Unanswered question -> bounded timeout (failure path) | "Send a deliberately unanswered question to show a bounded timeout rather than a hung agent"; doc: "C is woken and told; no hang" | D `task-62880ff7-...` (silent), C `task-da093bf9-...`. `ask task-da093bf9... -> task-62880ff7... expired`. `C: succeeded after 27 s, summary: no answer came by the deadline.` That summary is regex-extracted from C's woken input (`Your question \S+ to \S+: ([^\n]*)`), so the diagnostic came from the platform, not from the fake script. C's history: `signals [] timers fired 1`, so the deadline timer woke it. | pass |
| Unauthorized message rejected (failure path) | "demonstrate one unauthorized message is rejected"; doc: "the send is rejected" | E `task-7541c9b9-...` in `req-ae27a75a-f03d-4bfe-a9a8-c101c9895042`. Row `send task-7541c9b9... -> task-3b8cee3f... rejected task-3b8cee3f-e2ab-48be-9bad-51dec5919d19 is not a task of this request \| hi`. E's event `4 ... tool_result {"call": 1, "status": "error", "tool": "send_to_agent"}`. worker-dsh-b log: `Tool 'send_to_agent' failed: 'Error executing tool send_to_agent: refused: task-3b8cee3f-e2ab-48be-9bad-51dec5919d19 is not a task of this request'`. B received nothing. (E itself ends `succeeded` because the fake script calls `finish_task("done")` after the error. The refusal is still reported to the agent as a tool error and stored as `rejected`; it is not a silent success.) | pass |
| Event batching and bounded history (report count/size) | "Show event batching under a busy response and a bounded Temporal history (report event count/size)" | `task-26e03b28...: 13 events stored in 6 batches`. History: A `55 events, 13769 bytes`, B `55 events, 13684 bytes`, C `54 events, 13608 bytes`, D `55 events, 12296 bytes`, one run each. | pass for the bounded history and batching on this conversation. A 13-event task is not a "busy response"; the busy-response batching belongs to the events half (see F3). |
| Cleanup | doc: "D ends through `complete_task`" | `cancelled task-62880ff7-...`. Task status `failed cancelled`, Workflow `COMPLETED`. All five Workflows `COMPLETED`; `message_wakes rows left [(0,)]` | pass |
| Save evidence in docs/demos/phase-2.md | the doc exists with environment, commands, IDs, expected vs observed, cleanup, pass/fail | The doc is present and has all of those parts. My fake-model dry run matches the doc's dry-run statement ("C told after 26 s; A's 13 events in 6 batches"): I observed C after 27 s and 13 events in 6 batches. | pass (the doc exists). The recorded run itself is **blocked**: it used the owner's local model (`COMPOSE_PROJECT_NAME=praxismesh`), which I cannot reach, so I neither reproduced nor verified it. |

## 4. Afterwards

- `make workers-down` exited 0. The remaining pmphase2 containers are `db`, `temporal` and `temporal-ui` (all healthy), `s3` (healthy), and the exited one-shot jobs `temporal-schema` and `temporal-namespace`. No worker or fake-model containers remain.
- `infra/.env` is left in the checkout.

## Findings (all minor, documentation)

- **F1. Demo script header.** The header says the demo "needs `make workers-up` and a model endpoint ... (`make workers-check` points the workers at it)". But `make workers-check` starts only `orchestrator worker-a worker-b`. Profile `default` (DSH) also needs the DSH pairs on the fake model, which means `VLLM_BASE_URL=http://fake-model:8765 make workers-up`. The README also says to run plain `make workers-up` after workers-check, which would point the workers back at an empty `VLLM_BASE_URL`. The correct two-step sequence is written down only in the "Dry run" bullet of docs/demos/phase-2.md. Suggest putting it in the script header or the runbook.
- **F2. Stale README status.** README still says "Status: Phase 1 complete ... Phase 2 is next and has not started". The plan's phase 03 task 2.2 (still open) says status lines are updated after verification, so this is expected for now, not a defect.
- **F3. "Busy response" batching not exercised by this demo.** The messaging demo shows batching only for a 13-event task (6 batches), which is not a busy response. The busy-response part of that checklist item is covered by the events-half demo (`docs/demos/phase-2-events.md`, verified separately), which I did not re-run.
- **F4. Environment note (not a finding).** `make up` recreated the existing pmphase2 `db`, `temporal` and `temporal-schema` containers, because their Compose config differed from this checkout's. The volumes were kept, and `make db-roles` reported `ALTER ROLE` on the existing role. No undocumented step was needed: every step I ran is in the README, the runbook or docs/demos/phase-2.md.
- **Not run:** `gitleaks`, which the README marks optional ("if gitleaks is installed") and which is not in the AGENTS.md check list.

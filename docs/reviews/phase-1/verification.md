---
review: verification
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: [docs/adr/0001-keep-default-openspec-schema.md, docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 593acd4a467a10763a117b6577ef90b3cd8c05ab
docs_sha: 593acd4a467a10763a117b6577ef90b3cd8c05ab
diff_base: n/a
session: fresh            # light tier: shared with the implementation review, independence between them waived per §7.0
date: 2026-11-12
verdict: fail
reviewers:
  - { lens: acceptance and demo (verifier), status: completed }
  - { lens: as-built claims (verifier), status: completed }
---

# Verification: Phase 1 harness-in-Activity, single agent

Gate mode, light tier. This fresh session first ran `review-implementation` (`docs/reviews/phase-1/implementation-review.md`) and then this verification against the same `code_sha`; independence between the two is knowingly waived (§7.0). Neither verifier was given the implementation review's findings or verdict.

`docs_sha` equals `code_sha`: the as-built documentation (overview, threat model, benchmark records, demo record, RFC as-built notes) was merged in PR #49 with the code.

## Inputs

- Phase file `docs/plan/phases/phase-1.md` (tasks, "Accept:" line, demo checklist); RFC `docs/rfcs/phase-1-single-agent.md` (Testing and demo section, as-built notes); OpenSpec change `openspec/changes/phase-1-single-agent`.
- Setup and demo instructions: `README.md` ("Getting started", "Local stack", "Running an agent task"), `AGENTS.md` (Checks), `docs/demos/phase-1.md`.
- As-built documentation: `docs/architecture/overview.md` (Phase 1 section), `docs/benchmarks/`, `docs/security/threat-model.md`.
- Owner decisions of 2026-11-11 and 2026-11-12 in `docs/plan/decision-log.md`, accepted as given.

## Environment

- Disposable worktree of `593acd4` (detached), committed 2026-11-12T11:55:49-05:00, removed afterwards.
- Docker 29.9.3, Compose v5.7.1, Python 3.11 (uv), Node v26.13.0 (fnm), OpenSpec 1.17.0.
- `infra/.env` copied from `infra/.env.example`, with `COMPOSE_PROJECT_NAME=praxisverify1`, host ports 15432 / 17233 / 18088 / 18333 (`PRAXIS_SAMPLE_DB_URL` on 15432), and `VLLM_BASE_URL` set to the DGX Spark endpoint (`VLLM_MODEL=spark`, no key). The endpoint address appears in no evidence file.
- The main checkout's stack (Compose project `praxismesh`) was running and was not touched.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Revision | `git cat-file -t 593acd4`; `git branch -r --contains 593acd4` | commit, on remote | `commit`; `origin/main` | pass |
| Docs describe this code | `docs_sha == code_sha` | empty diff | identical revisions | pass |
| CI at `code_sha` (informational) | `gh api .../commits/593acd4.../check-runs` | green | `ci-ok`, `lint`, `types`, `tests`, `stack`, `openspec`, `agents-sync`, `secrets`, `links`, `workflows` success; `licenses` skipped | pass |
| Secrets | `git grep -nIE '<token patterns>' 593acd4` | none | only the pattern itself in `.agents/skills/verify-phase/SKILL.md` | pass |
| Transcripts | `git ls-tree -r --name-only 593acd4 \| grep -iE '\.jsonl$\|transcript'` | none | three `spikes/harness-vllm/results/*.jsonl` per-task spike result records (pre-existing, `13841d7`), not session transcripts | pass |
| Prerequisites | `uv sync --locked`; `make up`; `make status`; `make migrate` | documented steps suffice | all exit 0; `make status`: "all services healthy", model endpoint answers `/v1/models`; migrate "0002 -> 0003" | pass |
| Lint and format | `uv run ruff check . && uv run ruff format --check .` | clean | "All checks passed!", "189 files already formatted" | pass |
| Types | `uv run mypy` | clean | "Success: no issues found in 85 source files" | pass |
| Unit tests | `uv run pytest` | pass | "141 passed, 85 deselected in 16.77s" | pass |
| Agent sync | `uv run .agents/sync_agents.py --check` | up to date | "ok: 12 generated agent file(s) up to date" | pass |
| OpenSpec | `openspec validate --all`; `openspec update --dry-run` | pass; no changes | "5 passed, 0 failed"; "No changes" | pass |
| Stack and model tests | `make smoke` (stack up, model configured) | pass, no skips | "80 passed in 39.80s", no skips (includes model endpoints, scripted e2e task, harness Activity, tracing) | pass |
| Recovery | `make recovery-check` | pass | "5 passed in 58.85s" (`test_recovery_after_workspace_edits`, `test_side_effect_not_repeated_after_crash`, `test_checkpoint_matches_session_position`, `test_superseded_attempt_comes_back_and_writes_nothing`, `test_recovery_in_a_later_turn_with_edit_and_effect`) | pass |
| Phase 0 regressions | `make restart-check`; `make unhealthy-check` | PASS | both PASS (revision 0003 survives restart) | pass |
| Worker containers, fake model | `make workers-check` | succeeded | `task-5005182f-...`: `"status": "succeeded"`, artifact `order-summary.md` | pass |
| gitleaks (local) | - | - | not installed locally; README marks it optional; CI `secrets` passed | not run |
| Benchmark | `make benchmark` (no `--baseline`), workers on the DGX Spark endpoint | at most 1 of 10 lost against the 10/10 baseline | exit 0 in 3m28s: "passed 10 of 10. Within the regression limit (baseline 10)." | pass |

### Benchmark against the baseline (`docs/benchmarks/2026-11-12-local-default.json`)

| Task | Pass (base/run) | Tokens in | Tokens out | Seconds |
|---|---|---|---|---|
| t01-order-total | pass/pass | 19717 -> 18746 | 2242 -> 1376 | 48.4 -> 32.3 |
| t02-restock | pass/pass | 14672 -> 18350 | 1335 -> 1529 | 30.6 -> 34.5 |
| t03-fix-discount | pass/pass | 9437 -> 10820 | 749 -> 587 | 18.0 -> 14.4 |
| t04-config-port | pass/pass | 11291 -> 11195 | 659 -> 645 | 16.9 -> 15.3 |
| t05-sort-expensive | pass/pass | 10958 -> 10351 | 1275 -> 1159 | 27.7 -> 24.2 |
| t06-git-commit | pass/pass | 14549 -> 10170 | 674 -> 634 | 18.2 -> 15.2 |
| t07-log-status | pass/pass | 6811 -> 6588 | 497 -> 407 | 12.2 -> 9.9 |
| t08-fill-prices | pass/pass | 15269 -> 17535 | 883 -> 1016 | 21.9 -> 24.4 |
| t09-report-table | pass/pass | 12450 -> 13203 | 914 -> 1089 | 21.3 -> 23.7 |
| t10-fix-script | pass/pass | 8690 -> 8522 | 558 -> 461 | 14.3 -> 12.2 |
| **Total** | **10 -> 10** | 123844 -> 125480 (+1.3%) | 9786 -> 8903 (-9.0%) | 229.5 -> 206.1 (-10.2%) |

Every task passed in 1 turn and 1 attempt. The run overwrote the tracked `docs/benchmarks/2026-11-12-local-default.{md,json}` in the worktree (same date); they were restored with `git checkout` and nothing from this run was committed (finding V12).

## Demo evidence

Recorded here rather than in `docs/demos/phase-1.md`: the owner's instruction for this gate limits the commit to the two reports. The committed demo record is from the implementer's run; this is an independent re-run.

| # | Demo item (phase-1.md) | Command / action | Expected | Observed | Result |
|---|---|---|---|---|---|
| 0 | Setup | `make workers-up` | orchestrator and two template workers on the model | exit 0; `praxisverify1-orchestrator-1`, `-worker-a-1`, `-worker-b-1` healthy | pass |
| 1 | One local-model task uses the template's skill and MCP tool | `make task PROMPT="We need to order 3 units of SKU-1 and 2 units of SKU-2. Use the order-desk skill: ..." OUTPUT=order-summary.md` | succeeded, skill and MCP used | `task-7b89e933-a1de-4c4e-a2af-3b4eda34bfde` (run `01a1d172-9b18-7e0b-b874-360ba5495aa8`): `"status": "succeeded"`, 1 turn, 1 attempt, 13092/1299 tokens. Session: `read_file .skills/order-desk/SKILL.md`, `lookup_price`/`lookup_stock`, `record_order` SKU-1 x3 and SKU-2 x2, `write_file`, `finish_task`. `make task-output`: table and "Total: 52.00". Temporal: `TaskWorkflow WORKFLOW_EXECUTION_STATUS_COMPLETED` on `orchestration` | pass |
| 2 | Worker terminated after an acknowledged checkpoint **that contains a workspace edit**; a replacement resumes without losing edits or context | Submit a four-SKU task; poll `checkpoints`/`agent_messages` until a checkpoint covers the `notes.md` write; `docker kill` the container named by `task_attempts.worker_identity` | attempt lost on one worker, resumed and finished on the other; edit kept; conversation continued | `task-e3a41564-8624-4f5c-9c4f-314b21751bb2` (run `01a1d174-e1fb-795b-aa53-3396b0f9b425`). Trigger: checkpoint at session position 7 covers the `notes.md` write. `docker kill praxisverify1-worker-b-1` at 20:31:04 UTC. Attempts: `1/1 ... lost lost_or_timed_out` (worker-b), `1/2 ... done` (worker-a). Result `succeeded`, 2 attempts. `notes.md` (`step 1: started`) present before the kill and at the end; the write appears once in the session. Attempt 2's first checkpoint is at position 8; the session grew 7 -> 47 items | pass (see V3: the procedure is not reproducible from the docs; the driver was written by the verifier) |
| 3 | No duplicated external side effects; forbidden MCP/skill overrides fail | Count `sample_orders` for task 2; submit `--request` files naming `mcp_servers`/`skills` and `tools` | one row per order; explicit rejection, no task started | task 2: rows 12-15, one per SKU (SKU-1, SKU-2, SKU-4, SKU-5). Rejections: "error: a task request may not set mcp_servers, skills: capabilities come only from the worker template" and "... may not set tools ...", exit 2; `tasks` rows 25 before and after. A retried effect after a crash is covered by `test_side_effect_not_repeated_after_crash` (passed in `make recovery-check`); in this live run the kill came before any `record_order` | pass |
| 4 | Completed output and the same task reference before and after replacement | `make task-status ID=task-e3a41564-...`; `make task-output ID=... FILE=order-summary.md` | same ID, output | `COMPLETED task-e3a41564-... succeeded`; four SKU lines, "Total: 64.85" | pass |
| 5 | One trace follows a task from submission to result | `make observability-up`; workers recreated with `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318` in the shell; one task | one trace, CLI to model and tool calls | `task-fca87d3f-a297-48b4-a26d-68e00c4b6141` succeeded. Jaeger v3: 1 trace, 22 spans, services `praxis-cli`, `praxis-orchestrator`, `praxis-template`, root `praxis.task.submit`, 4 model-call and 6 tool-call spans. Prometheus targets orchestrator, worker-a, worker-b `up`; `praxis_tokens_total` in 7262, out 505 | pass |
| 6 | Benchmark runs; baseline recorded | `make benchmark`; `docs/benchmarks/baseline.json` | runs; baseline present | 10 of 10, within limit (table above); baseline file present and consistent | pass |

**Cleanup.** `make workers-down`, `make observability-down`, `make reset` in the worktree (project `praxisverify1` only; its volumes and network removed), then `git worktree remove --force` and `git worktree prune`. No `praxisverify1` container, volume or network remains. The `praxismesh` stack's four containers stayed up and healthy throughout. Side effect: the image tag `praxismesh-worker:dev` is shared across Compose projects (V14), so it now points at the image built from `593acd4` in the worktree (the same source as `main`).

## As-built claims

| Claim (quoted) | Location | Status | Evidence |
|---|---|---|---|
| Registry: profile `default`, template `local-default@1`, MCP `sample-shop`, skill `order-desk`, lock | overview, Phase 1 | confirmed | `registry/*`; lock hash matches |
| CLI `submit`/`status`/`output`, `praxis.task.submit` span, `REJECT_DUPLICATE`, capability fields rejected by name | overview | confirmed | `orchestrator/cli.py:71, 129-142`; `submit.py:62`; `requests.py:17-40`; live rejection (demo 3) |
| `TaskWorkflow` on `orchestration`, harness turns on the template queue | overview | confirmed | `workflow.py:64-154`; Temporal: `orchestration` polled by the orchestrator, `tpl.local-default` by two workers |
| Template refusal, newest-checkpoint restore with truncation, outputs as `audit` | overview | confirmed | `activity.py:166-175, 217-243, 331` |
| Heartbeat every timeout/3, 5 real attempts, `schedule_to_close = 6 x turn_timeout`, fence before each model call | overview, durability | confirmed | `activity.py:65, 136, 177-180, 270-272`; `workflow.py:42, 114` |
| Recovery on another worker, no repeated side effect | overview, demo | confirmed | demo 2 and 3; `make recovery-check` 5 passed |
| Workers non-root, metrics on 9100, worker without model URL refuses to start | overview | confirmed | uid 10001 in all three containers; Prometheus targets up; `workers/main.py:71-76` (code) |
| Worker metrics: Activity duration, heartbeat lag, tokens, tool calls and errors, checkpoint size and time | phase-1.md task; RFC; observability spec | contradicted | three of the metrics are never recorded (V1) |
| JSON logs with `request_id`, `task_id`, `workflow_id`, `turn`, `attempt`, `worker` | RFC (Logs) | contradicted | worker lines lack `request_id`; orchestrator emitted 0 JSON lines (V2) |
| `make task-status` shows "status, turns, attempts and the latest checkpoint"; demo waits for an acknowledged checkpoint "in `make task-status`" | RFC (targets; demo step 2) | contradicted | `cli.py:108-123` prints only the `tasks` row and Workflow status (V3) |
| "The script submits a task that orders four SKUs ... stops it abruptly with `docker kill`" | `docs/demos/phase-1.md` step 2 | contradicted | no such script is committed (V3) |
| C5: "`run_command` runs only programs in the template's `cli_tools`" | threat model | contradicted | only the first word is checked, then `sh -c` runs the string; `cli_tools` includes `sh`; probe `wc -c /dev/null; uname -s` ran `uname`; `sh -c 'cat /etc/hostname'` read outside the workspace (V4). R1 in the same document accepts "any binary through a pipe" |
| C6: "File tools cannot leave the workspace" (named tests) | threat model | contradicted (test mapping) | named tests cover skills and symlinks only; disabling `inside()` left 141 tests green (V5) |
| C7: MCP servers get only their literal `env`, `PRAXIS_TASK_ID` and granted secrets (named test) | threat model | contradicted (test mapping) | the named test checks load-time grants only; adding `**os.environ` to the runtime env left tests green (V6) |
| C4: a refused call "is logged" | threat model | contradicted for `run_command`; untested | see implementation review F4 (V7) |
| C9: "A superseded attempt writes nothing" | threat model | overstated | final checkpoint at `activity.py:300` has no fence; restore ordering keeps it harmless (V8) |
| C11: SDK tracing off, test `test_no_sdk_trace_export` | threat model | confirmed (behavior); test does not pin the worker | removing the worker's call left tests green; `RunConfig(tracing_disabled=True)` still applies (V9) |
| C1-C3, C8, C9 fence, C12 | threat model | confirmed | tests target the controls; fixed test identities |
| Deviation "Up to 5 Temporal attempts per turn -> unlimited within `schedule_to_close`" cited to "informal durability review, F7" | overview, deviations | unverifiable source | no such record in the repository; no decision-log row (V10) |
| Benchmark baseline: template hash, prompt hash, `openai-agents` 0.24.0, 10 tasks, regression rule | `docs/benchmarks/` | confirmed | hashes match the lock and `registry/prompts/local-default.md`; `uv.lock`; `run.py:46, 153` |
| Benchmark per-task rows (tokens, seconds, pass) | `docs/benchmarks/2026-11-12-local-default.*` | unverifiable | task IDs are from another stack; md and json agree; this run reproduced 10/10 at similar cost |
| Benchmark method | `docs/benchmarks/` | incomplete | no note that workers run in-process (`run.py:170`) or that the "the DGX Spark endpoint" line is a fixed string (`run.py:131`) (V11) |
| Sparks demo figures ("4 session items at the stop, 40 at the end") | overview; demo record | unverifiable | another stack; this run observed the same pattern (7 -> 47) |
| "about 940 MiB in total" | overview, resource use | point-in-time | sampled about 1067 MiB; per-worker 170-180 MiB fits the stated range (V15) |
| Each worker has "its own scratch volume" | RFC, Workers | contradicted | tmpfs (`docker-compose.yml:174-175, 185-186`) (V16) |
| Scope lines "branch `feat/44-evidence`", "at the merge of issue #44's last PR" | overview; threat model | stale | now on `main` at `593acd4` (V17) |

## Findings

| ID | Severity | Location | Expected | Observed | Resolution |
|---|---|---|---|---|---|
| V1 | Major | `common/observability/metrics.py:7-15` | phase-1.md: worker metrics for "Activity duration, heartbeat lag, tokens, tool-call counts and errors, checkpoint size and time" | `praxis_activity_seconds`, `praxis_heartbeat_lag_seconds`, `praxis_tool_errors_total` never recorded; no samples after a task; tool calls only as `tool="any"` (implementation review F3) | open |
| V2 | Major | `harness_activity/activity.py:181`; orchestrator | RFC: logs carry `request_id` with the task IDs; phase-1.md: request, workflow, task and attempt IDs | worker-b: 5 JSON lines, all with `task_id`, none with `request_id`; orchestrator: 0 JSON lines (implementation review F8) | open |
| V3 | Major | `docs/demos/phase-1.md` step 2; RFC demo step 2 and targets | demo runnable from documented instructions; `make task-status` shows the latest checkpoint | "The script" is not committed; `make task-status` shows no checkpoint, so the documented wait cannot be done; the verifier wrote its own driver querying `checkpoints` and `task_attempts` | open |
| V4 | Major | `docs/security/threat-model.md` C5; `harness_activity/tools.py:116-130` | `run_command` runs only `cli_tools` programs, in the workspace | any command after an allowed first word runs through `sh -c`; `sh` is allowed; a probe read outside the workspace. Removing the timeout or output cap, or setting `cwd="/"`, left tests green | open |
| V5 | Major | threat model C6 | a named test fails if file tools can leave the workspace | none does (implementation review F9) | open |
| V6 | Major | threat model C7 | a named test fails if MCP servers get more than their granted env | none does (implementation review F9) | open |
| V7 | Nit | threat model C4 | refusals logged and tested | removing the refusal log line left tests green; `run_command` refusals are not logged (Major in the implementation review, F4) | open |
| V8 | Nit | threat model C9 | "writes nothing" | final checkpoint unfenced (implementation review N20) | open |
| V9 | Nit | threat model C11 | test pins the worker's tracing setup | test calls the helper itself | open |
| V10 | Nit | overview, deviations table | deviation traceable to a record | "informal durability review, F7" is not in the repository; no decision-log row for the attempts/`schedule_to_close` change | open |
| V11 | Nit | `docs/benchmarks/` | records say how they were produced | no method note (in-process workers, `--baseline`); endpoint line is a fixed string | open |
| V12 | Nit | `tests/benchmarks/run.py` | a re-run does not touch the baseline evidence | a same-day run overwrites the files `baseline.json` points to | open |
| V13 | Nit | `infra/docker-compose.yml`; `.env.example`; `check-prereqs.sh` | a second checkout can move every host port | `PROMETHEUS_PORT`, `JAEGER_UI_PORT`, `OTLP_HTTP_PORT` are not documented or accepted keys | open |
| V14 | Nit | Compose worker image | per-project images | `praxismesh-worker:dev` is shared by every project; a build in one checkout retags it for all | open |
| V15 | Nit | overview, resource use | stated total | about 1067 MiB observed against "about 940 MiB" (point-in-time) | open |
| V16 | Nit | RFC, Workers | as-built note for scratch storage | tmpfs, not a volume; no as-built note. RFC test traceability table names four tests that do not exist (`test_blob_contract`, `test_migration_0003`, `test_every_row_and_blob_has_retention`, `test_harness_turn_scripted`); equivalents exist and pass | open |
| V17 | Nit | overview; threat model; README; AGENTS.md | current status | scope lines name the pre-merge branch; README says "Phase 1 in progress"; AGENTS.md says "No product code yet" | open |
| V18 | Nit | demo record; Compose | demo says how to restore the killed worker | a killed worker stays `Exited (137)` (`restart: unless-stopped`); the doc does not say to run `make workers-up`; `fake-model` from `workers-check` stays up after `make workers-up` | open |
| V19 | Nit | `orchestrator/cli.py` | the task ID is readable while `make task` waits | stdout is block-buffered when not a terminal, so scripts see the ID only at exit | open |
| V20 | Nit | worker logging | the model endpoint stays out of logs | httpx INFO lines print the full endpoint URL into `docker logs` (filtered out of all evidence here) | open |

## Verdict

**fail.** Under the verify-phase verdict rules, as-built claims are contradicted: threat-model C5 (V4), the RFC's `make task-status` and logging claims (V2, V3), the demo record's committed script (V3), and the metrics the phase promises (V1). Every acceptance suite and every demo item passed with observed output, including recovery after a workspace edit with `docker kill` and the benchmark (10 of 10 against the 10 of 10 baseline). The evidence checks were clean.

## Open items

- V1-V6 (Major) go back to the implementer; V1, V2, V5 and V6 overlap implementation review F3, F8 and F9.
- 14 Nits (V7-V20).
- A re-check runs in a new session (rule 6).

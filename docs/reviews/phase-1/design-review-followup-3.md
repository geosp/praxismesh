---
review: design
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: []
commit_sha: c4e7590613d91a3db7f50eaac0ee22f5347a4fee
docs_sha: n/a
diff_base: e1380632c5709f3fcda1248d34e010778ea4480a
session: fresh (third targeted follow-up, docs/reviews/README.md rule 6)
date: 2026-11-11
verdict: PASS
reviewers:
  - { lens: fresh reader (design-reader), status: completed }
  - { lens: codebase fit (design-reviewer), status: completed }
  - { lens: zoom out (design-reviewer), status: completed }
---

# Design review, third targeted follow-up: Phase 1 harness-in-Activity, single agent

## Inputs

Revision `c4e7590613d91a3db7f50eaac0ee22f5347a4fee` (branch `docs/44-phase-1-design`, draft PR #45, issue #44). The working tree was clean (`git status --porcelain` empty). This is a **targeted follow-up** under rule 6. All paths are under `/home/geo/develop/praxismesh`. Neither the coordinator nor any reviewer read a session transcript.

- **Correction list:** [design-review-followup-2.md](design-review-followup-2.md) (verdict FAIL at `e138063`: Majors H1-H3, Nits H4-H15, H16 contested).
- **Revision diff:** `e138063..c4e7590 -- docs/rfcs openspec`. It changes the RFC (revision 4), the durability and harness-turn specs and `tasks.md`.
- **Fresh reader** (`design-reader`, Claude Code, project instructions omitted): `openspec/changes/phase-1-single-agent/proposal.md`, `design.md` and `docs/rfcs/phase-1-single-agent.md`, with its standard brief. It did not get the correction list.
- **Codebase fit** (`design-reviewer`):
  - the change: proposal, design, tasks and all `specs/**/spec.md`;
  - the RFC and `AGENTS.md`;
  - `PROJECT_PLAN.md` (§2, §6, §8);
  - `docs/plan/phases/phase-1.md` and §4.1, §4.2, §4.10 and §4.13 of `docs/plan/design-decisions.md`;
  - `docs/plan/schemas.md` and the newest rows of `docs/plan/decision-log.md`;
  - the correction list and the revision diff.
- **Zoom out** (`design-reviewer`):
  - the change and the RFC;
  - `PROJECT_PLAN.md`, `docs/plan/phases/phase-1.md`, `docs/plan/design-decisions.md`, `docs/plan/schemas.md` and `docs/plan/decision-log.md`;
  - the correction list and the revision diff.

Both `design-reviewer` briefs also carried:
- where the SDKs are installed;
- the owner's deferral of the Claude runner, accepted as given;
- the H3 endpoint observation, to be treated as recorded evidence: with tools, `output_type` finished 0 of 3 runs, and `finish_task` with `stop_at_tool_names` finished 3 of 3;
- the owner's scope rule. Blockers and Majors are only for problems that would:
  - fail a phase-1.md acceptance criterion;
  - contradict plan §2;
  - mis-state verified SDK or API behavior;
  - leave a requirement without a test path.
- the instruction to look for new Blockers and Majors only in changed text.

The coordinator applied the same rule when merging. Fresh-reader Majors outside it are marked "(FR: Major)".

**Coordinator checks against `openai-agents` 0.24.0.** Each was run against a stubbed Chat Completions client, with `SQLiteSession`, not just read.
- **No `response_format`:** with no `output_type`, the request's `response_format` is `omit`, so nothing is sent (`chatcmpl_converter.py:107-111`).
- **`stop_at_tool_names`:** the run ends after the named tool's call. `final_output` is the tool's **return value** (`run_internal/turn_resolution.py:789-796`), not its arguments.
- **Session at the first model call:** at the first `on_llm_start` the session already holds the run input (1 item). The `seq` 0 checkpoint of H1 therefore includes the instructions.
- **Invalid arguments:** a `finish_task` call whose arguments fail validation (`status: "bogus"`) **still ends the run**. `final_output` is then the generic string "An error occurred while running the tool. Please try again." The model gets no second try within the turn (see J11).

The zoom-out reviewer also ran `finish_task` and `write_file` in one response: both tools ran, then the run stopped (J12).

## Fresh reader paraphrase

> ## What this proposes
>
> Phase 1 adds the first product code on top of the Phase 0 stack. A single agent, running on the local model through the `openai_agents` SDK, does a task as a durable Temporal workflow (`TaskWorkflow`). Each bounded run of the agent ("harness turn") is a Temporal Activity (`run_harness_turn`). Inside a turn, the session and a workspace snapshot are saved before every model call, so if a worker container is lost, a second worker can pick the task up and continue the same conversation. Calls that change things (`record_order`) carry idempotency keys, so they are not repeated after a crash. Around this it adds:
> - a capability model where only templates grant tools, skills and MCP servers;
> - a `BlobStore` contract with a SeaweedFS adapter;
> - migration `0003`, with a retention class on every row;
> - logs, traces and metrics;
> - a 10-task benchmark with a regression limit;
> - a first threat model.
>
> The goal is a base that later phases build on, and evidence that the agent survives losing its worker.
>
> ## How the existing system works, per this document
>
> Phase 0 runs a local stack under Docker Compose: Temporal, ParadeDB, SeaweedFS, and an external vLLM endpoint on the "Sparks". It has no product code yet. What already exists:
> - a CI `stack` job that runs integration tests against the Compose stack;
> - test helpers (`tests/support/stack.py` with a path-style S3 client config, and `tests/test_hello_replay.py` for replay tests);
> - an `infra/.env` file checked by `check-prereqs.sh`, and `settings.app_database_url`;
> - earlier migrations (since this one is `0003`), and a uv project with `package = false`;
> - a CI license job, a mypy `files` list, and `make reset`.
>
> The Temporal namespace keeps closed runs for 72h. A Pre-0 spike already ran both harnesses against the local model with 10 tasks.

The reader could paraphrase every section, so it raised no Blockers. Its paraphrase matches the revised design, including "saved before every model call" (H1).

## Status of the earlier Majors

| ID | Status | Evidence |
|---|---|---|
| H1 | **resolved** | Step 4 now checkpoints "at every `on_llm_start`, including the first". The `seq` 0 checkpoint holds the instructions: the coordinator and both reviewers confirmed that the session already holds the input at that hook. Step 2 defines the case with no checkpoint: clear the session, download the input files and read `instructions_ref`. The input to `Runner.run` is the instructions when starting fresh. The durability spec adds "Lost before the first checkpoint" and now says "At the start of every inner turn, including the first". The test path is `test_restore_without_checkpoint` (task 3.1, the trace table, the unit-test list). A `ModelBehaviorError` in inner turn 1 is covered, because `seq` 0 always exists. Residue: J14, J15. |
| H2 | **resolved** | Task 3.1 now reads "restore ordered by turn, attempt and seq (or a fresh start when none exists)". `test_restore_prefers_latest_turn` is named in task 3.1, the trace table and the unit-test list. |
| H3 | **resolved** | The design drops `output_type` and ends a turn through a `finish_task` tool with `tool_use_behavior={"stop_at_tool_names": ["finish_task"]}`. Task 2.1, the harness-turn spec ("ending through `finish_task`") and the "APIs checked" table all agree. SDK behavior was verified in source and by running it: no `response_format` is sent, and the run ends at the named tool. The endpoint result (0 of 3 against 3 of 3) is taken as recorded evidence. The Activity was renamed `complete_task`, so the names no longer collide. Residue: J10-J13, J18. |

## Status of the earlier Nits

- **Fixed:** H9, H10, H13.
- **Partly fixed, with the residue carried into J1-J9:** H4, H5, H6, H7, H8, H11, H12, H14, H15.
- **H16:** stays contested. The fresh reader's note on how stray items from an old attempt shift the session's item count belongs to the same accepted risk ("Remaining window").

## Findings in the changed text

Reviewers: FR = fresh reader, CF = codebase fit, ZO = zoom out. Duplicates are merged. No Blocker or Major was raised by either `design-reviewer`. Each of the fresh reader's three Majors is a residue of an earlier Nit, with a local fix and a test path, so the coordinator classed them as Nits under the scope rule.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| J1 | Nit | CF, ZO | RFC "Starting a task"; "Outcomes and budgets" (new "A turn that fails for good") | H4 residue. The new rule says that on "a non-retryable error … the Workflow still runs `complete_task`. The task ends `failed`". The RFC also lists `TaskAlreadyExists` as non-retryable, so applying the rule broadly would overwrite the original task's `audit` row as `failed`. Still unstated: how the test simulates "after retention". | Fix: limit the rule to harness-turn failures. State that a `TaskAlreadyExists` run ends without `complete_task` and leaves the row untouched. Name the retention simulation (for example, insert a `tasks` row with another `run_id` before starting). | open |
| J2 | Nit | CF, ZO | RFC `test_side_effect_not_repeated_after_crash` | H5 residue. "The test template sets the sample server's `client_session_timeout_seconds`", but neither `McpServer` nor `WorkerTemplate` has such a field, and unknown fields are forbidden. It is still unstated which catalog entry carries `SAMPLE_MCP_PAUSE_AFTER_EFFECT`. | Fix: add the field to `McpServer` (or a test catalog entry) and name the entry that carries the flag. | open |
| J3 | Nit | CF, ZO, FR (FR: Major) | RFC `run_harness_turn` step 1 against "Versions" | H6 residue. Versions says "The hash check runs before the attempt row is written", but step 1 (unchanged) still lists the upsert first. A retryable refusal is also capped by the 5 attempts, which run out before `schedule_to_close`. | Fix: reorder step 1, and say "fails once its retries or `schedule_to_close` run out". | open |
| J4 | Nit | CF, ZO | harness-turn spec Purpose | H7 residue: "for both runners". | Fix: drop it. | open |
| J5 | Nit | CF, ZO | RFC front matter `pre0_inputs` | H8 residue: "model per tier (spark: …)". | Fix: align with the Terms gloss. | open |
| J6 | Nit | CF, ZO, FR (FR: Major) | harness-turn spec `TurnOutcome` fields; sequence diagram; Demo; step 5 | H11 residue. Step 5 adds output refs, summary and questions to `TurnOutcome`, but the spec's field list and the diagram omit them, and demo step 1 does not name `make task-output`. The fresh reader adds that `outputs[]` reaches the Activity through neither `tasks` nor `TurnInput`, and that `make task PROMPT=…` cannot pass it. | Fix: align the field lists, and state where `outputs[]` is stored and how the demo passes it. | open |
| J7 | Nit | CF, ZO, FR (FR: Major) | RFC step 2 (fresh start); `tasks` table; `TurnInput` | H12 residue. The fresh start downloads "the input files from the `tasks` row's blob refs", but `tasks` has only `instructions_ref`, and `TurnInput` carries no input refs. The refs exist as Workflow inputs, so the data is there; only where the Activity reads it is missing. | Fix: add an `input_refs` column to `tasks`, or put the refs in `TurnInput`. | open |
| J8 | Nit | CF, ZO | RFC Recovery check, Components; proposal "What Changes" | H14 residue: the `worker_identity` format, the purpose of `comms_mcp`, and `sample_orders` in the proposal's migration list. | Fix: one line each. | open |
| J9 | Nit | CF, ZO, FR | RFC throughout; `design.md` | H15 residue. The new Terms paragraph glosses the § numbers, `tier`, `size`, `pre0_inputs` and "phase closure". Still unglossed: "Pre-0" and "the Sparks", ADR-0001, "the as-built section", Claim Check, the "praxis CLI" against `python -m orchestrator.cli`, the open licensing decision, and ParadeDB against "praxismesh DB". | Fix: one-line glosses. | open |
| J10 | Nit | CF, ZO | harness-turn spec scenario "Scripted harness turn"; RFC `HarnessRunner` contract ("structured final output"); fake model ("a final answer"); task 2.1a | Unchanged text now contradicts "A run that ends without calling it counts as `continue`". The scenario expects `done` after a plain answer. Task 2.1a does not say the fake model ends by calling `finish_task`. Without that, the scripted end-to-end test, `make recovery-check` and the conformance case cannot reach `done`. They fail loudly, so the test path exists. | Fix: reword the three passages to "calls `finish_task`", and add that to task 2.1a. | open |
| J11 | Nit | ZO (coordinator-checked) | RFC step 4 "Done or needs input" | "Its arguments decide the turn's status", but the SDK returns the tool's **output**, as a `str`. A call whose arguments fail validation still ends the run, with a generic error string as `final_output`. The model never gets to correct it in that turn. | Fix: state that the runner records the validated arguments itself (for example in the run context) and maps "stopped without valid arguments" to `continue`. Or use a `ToolsToFinalOutputFunction` that stops only after a successful `finish_task` (`turn_resolution.py:797-807`). | open |
| J12 | Nit | ZO | RFC step 4 | When `finish_task` comes with other tool calls in one response, every call runs, then the run stops. The model never sees the other results, so a failed sibling call (for example `record_order`) can still end the turn `done`. | Fix: state it, or downgrade to `continue` when a sibling call in the same step failed. | open |
| J13 | Nit | ZO | RFC step 4 (final checkpoint) and step 5 | A worker lost after `Runner.run` returns, during uploads or the attempt-row update, leaves a final checkpoint that ends with the `finish_task` call. The retry sends "Continue the task …" and asks the model again, which may answer with a different status. | Fix: record the finish arguments with the final checkpoint, and have restore go straight to step 5 when they are present. | open |
| J14 | Nit | ZO | RFC step 2 parenthetical; durability scenario "Lost before the first checkpoint" | The rule says "No checkpoint exists **for the task**", which is correct. But "or an attempt lost before its first checkpoint" can be read as covering a turn-2 attempt, which would discard turn 1's work. | Fix: "an attempt of turn 1 lost before its first checkpoint". | open |
| J15 | Nit | CF, ZO | RFC test plan for H1 | No test pins down that the `seq` 0 position includes the instructions, or that a fresh or restored attempt sends them to the model, as seen in the fake model's request log. The fake model ignores instructions, so an SDK upgrade that changed the save order would pass every listed test. The `0.24.0` pin covers it for now. | Fix: add an assertion to `test_checkpoint_matches_session_position`, or a step-0 variant of the recovery check. | open |
| J16 | Nit | CF | RFC step 4 input | Each resumed attempt or later turn saves one more "Continue the task from where it stopped." message before its `seq` 0. This is harmless but unstated. | Fix: one line. | open |
| J17 | Nit | CF | RFC `WorkerTemplate` (`concurrency_per_pod` "used") | It is now "the worker's maximum concurrent harness turns", but no task maps it to the worker setting (for example `max_concurrent_activities`), and no test covers it. | Fix: add it to task 2.5 with a unit check. | open |
| J18 | Nit | CF, ZO | RFC "APIs checked" (endpoint observation); Risks | The 0 of 3 against 3 of 3 result has no script, log, vLLM flags or decision-log row. AGENTS.md asks for API and architecture changes to be recorded in `decision-log.md`. A model that keeps answering in plain text loops as `continue` until the budget runs out, and no Risks row covers it. The benchmark would catch that. | Fix: point to the run, add a decision-log row, and add a Risks row with a measurable signal. | open |
| J19 | Nit | FR | unchanged RFC text (not re-reviewed) | The fresh reader also noted, in unchanged text:<br>• the heartbeat timer during long model calls;<br>• SIGTERM graceful shutdown in the recovery check;<br>• where `model_override` is applied;<br>• the source of `BlobUnauthorized`;<br>• the set of `failure_category` values;<br>• `tasks.status` values, and what `InvalidTaskInput` raises. | Fix: optional, at the author's discretion. | open |

## Verdict

**PASS.**

The verdict follows `docs/reviews/README.md` rule 5: no Blocker is open, every Major is fixed, and all three reviewers completed.
- **Earlier Majors:** H1, H2 and H3 are resolved. H3 was checked in the SDK source and by running it. The endpoint observation is recorded evidence that this session could not reproduce.
- **New Blockers and Majors in the changed text:** none.
- **Nits:** 19 open (J1-J19). They do not block. H16 stays contested.

This verdict does not authorize a merge. Required CI checks on the latest head still apply, and the coordinator approval gate follows later in the phase.

## Open items

- **Nits for the author:** J1-J19. The most useful before implementation:
  - J10 and J11: they shape how the fake model and `OpenAIAgentsRunner` handle `finish_task`;
  - J1: the scope of the new failure rule;
  - J3 and J7: the step 1 order, and where the input refs live.
- **Not exercised here:**
  - the vLLM endpoint itself (H3 evidence taken as recorded);
  - Temporal's carrying of heartbeat details across attempts (documented, and read in the `temporalio` source).

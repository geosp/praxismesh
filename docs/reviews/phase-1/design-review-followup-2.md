---
review: design
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: []
commit_sha: e1380632c5709f3fcda1248d34e010778ea4480a
docs_sha: n/a
diff_base: 17b3d6770f964adf4a48dd6c53742057f620855f
session: fresh (second targeted follow-up, docs/reviews/README.md rule 6)
date: 2026-11-11
verdict: FAIL
reviewers:
  - { lens: fresh reader (design-reader), status: completed }
  - { lens: codebase fit (design-reviewer), status: completed }
  - { lens: zoom out (design-reviewer), status: completed }
---

# Design review, second targeted follow-up: Phase 1 harness-in-Activity, single agent

## Inputs

Revision `e1380632c5709f3fcda1248d34e010778ea4480a` (branch `docs/44-phase-1-design`, draft PR #45, issue #44). The working tree was clean (`git status --porcelain` empty). This is a **targeted follow-up** under rule 6. The two `design-reviewer` sessions received the correction list ([design-review-followup.md](design-review-followup.md), verdict FAIL at `17b3d67`) and the revision diff `17b3d67..e138063`. The fresh reader did not receive the correction list. Neither the coordinator nor any reviewer read a session transcript. All paths are under `/home/geo/develop/praxismesh`.

- **Fresh reader** (`design-reader`, Claude Code, project instructions omitted): `openspec/changes/phase-1-single-agent/proposal.md`, `design.md` and `docs/rfcs/phase-1-single-agent.md`, with its standard brief.
- **Codebase fit** (`design-reviewer`): the change (proposal, design, tasks and all nine `specs/**/spec.md`), the RFC, `AGENTS.md`, `PROJECT_PLAN.md` (§2, §6, §8), `docs/plan/phases/phase-1.md` and its *Read first* sections (§4.1, §4.2, §4.10, §4.13 of `docs/plan/design-decisions.md`), `docs/plan/schemas.md`, the newest rows of `docs/plan/decision-log.md`, the correction list and the revision diff.
- **Zoom out** (`design-reviewer`): the change, the RFC, `PROJECT_PLAN.md`, `docs/plan/phases/phase-1.md`, `docs/plan/design-decisions.md`, `docs/plan/schemas.md`, `docs/plan/decision-log.md`, the correction list and the revision diff.

The briefs of both `design-reviewer` sessions also carried four things:
- where the SDKs are installed: `openai-agents` 0.24.0 in `spikes/harness-vllm`, `temporalio` 1.36.0 in the root environment;
- the owner's decision, accepted as given: the Claude Agent SDK runner is deferred out of Phase 1, so G4, G6, G7, G8, G18 and G20 are closed. Reviewers checked only that no Phase 1 requirement, test or acceptance path still depends on it;
- the owner's scope rule. Blockers and Majors are only for problems that would:
  - fail a phase-1.md acceptance criterion;
  - contradict a §2 hard constraint;
  - mis-state verified SDK or API behavior;
  - leave a requirement without a test path.

  Developer-tooling edge cases are Nits at most;
- the instruction to look for new Blockers and Majors only in changed text.

The coordinator applied the same rule when merging. Fresh-reader Majors outside it are marked "(FR: Major)".

**Coordinator checks against the installed packages.** Each was run, not just read.
- **Tracing (G5):** `agents` 0.24.0: after `set_tracing_disabled(True)`, the `DefaultTraceProvider` is disabled but still holds `(BatchTraceProcessor,)`. After `set_trace_processors([])` it holds `()`.
- **Structured output (H3):** `agents/models/openai_chatcompletions.py:643,694-701`. With an `output_type`, every Chat Completions request carries `response_format` (`json_schema`, `chatcmpl_converter.py:107-120`) next to `tools` and `tool_choice`. The Pre-0 spike ran without `output_type` (`spikes/harness-vllm/run_openai.py:80-90`). Its vLLM uses `--tool-call-parser qwen3_coder` (`docs/spikes/harness-vllm.md:21`). Whether that server still emits tool calls under a JSON-schema `response_format` was **not** exercised (no access to the Sparks from this session).
- **Session input (H1):** `agents/run.py:1005-1020`. The `Runner.run` input is saved to the session before the first model call.
- **MCP timeout (H5):** `MCPServerStdio.__init__` defaults `client_session_timeout_seconds=5`.
- **Self-fencing (H9):** `temporalio` 1.36.0: `activity.heartbeat(*details) -> None`. `ActivityCancellationDetails` has `timed_out`, `cancel_requested`, `worker_shutdown` and other fields.

## Fresh reader paraphrase

> ## What this proposes
>
> This is the first product code for the project. One AI agent runs on a self-hosted model as a long-running Temporal workflow (`TaskWorkflow`). Each step is a time-limited "harness turn" (`run_harness_turn`) that the workflow sends to worker containers. Each step saves progress partway through: the conversation, a snapshot of the working files, and keys that stop side-effecting tool calls from running twice. So if a worker dies mid-task, a second worker picks the task up without redoing or duplicating work. Every capability (model, MCP servers, skills, tools, limits) comes from versioned worker templates; any profile or request that tries to grant capabilities is rejected. The change also adds a minimal blob-storage interface on SeaweedFS, new database tables where every row and blob has a retention class, logs/traces/metrics, a 10-task benchmark with a regression limit, and a first threat model. The reason given is that later phases build on these pieces. The Claude Agent SDK runner is deferred until its licensing is decided.
>
> ## How the existing system works, per this document
>
> Phase 0 left a local stack with no product code: Temporal, a ParadeDB database, SeaweedFS object storage, and an external vLLM endpoint on a pair of DGX Spark machines, serving a model named `spark`. CI has a `stack` job that brings up the Docker Compose stack and runs integration tests. A few Phase 0 pieces are named:
> - `tests/support/stack.py`, a path-style S3 client setup;
> - a hello-workflow replay test, `tests/test_hello_replay.py`;
> - a `settings.app_database_url` setting;
> - `infra/.env` with `check-prereqs.sh`;
> - `make reset`;
> - a CI license job;
> - a uv project with `package = false`, so no script entry points;
> - a Temporal namespace that keeps closed runs for 72h.
>
> An earlier spike ran both agent harnesses against the local model on 10 tasks. The document says little else about current behaviour.

The reader could paraphrase every section, so it raised no Blockers.

## Status of the earlier Majors

| ID | Status | Evidence |
|---|---|---|
| G1 | **resolved** | RFC "Starting a task" limits the Temporal guarantee to the 72h retention. It makes `tasks` the lasting authority: `record_task` is insert-only on `task_id`, and a row from another run fails with the non-retryable `TaskAlreadyExists` before any harness turn. A resubmitted ID therefore never reaches the old idempotency keys. `test_duplicate_task_id_rejected` (task 2.5) covers both Temporal and `tasks`. Residue (no `run_id` column, ordering against the diagram): Nit H4. |
| G2 | **resolved** | `SAMPLE_MCP_PAUSE_AFTER_EFFECT=1` commits the order and its key, then holds the tool response. The SDK saves a turn's items only after its tool calls finish (`run.py:2060-2097`). The newest checkpoint therefore ends before the call, and the fake model issues `record_order` again. Without idempotency keys a second `sample_orders` row appears and the test fails, so the test now proves the property. Residue (the 5 s MCP timeout, how the flag reaches the server): Nit H5. |
| G3 | **partly resolved** | Fixed in RFC step 2 ("order by `turn`, then `attempt`, then `seq`, all descending") and in the durability spec (new scenario "Latest turn wins"). Not fixed: task 3.1 still says "restore preferring the highest attempt", and the new scenario has no test. See Major H2. |
| G5 | **resolved** | RFC step 3 adds `set_trace_processors([])`. The coordinator ran it: the processor tuple is empty afterwards, so the observability scenario "no `openai-agents` trace processor or exporter is registered" can pass. |

**Claude runner deferral:**
- **No dependency remains.** No Phase 1 requirement, test, demo step or acceptance path depends on the Claude runner (both `design-reviewer` sessions agree):
  - `test_claude_runner_isolation` is replaced by `test_runner_conformance`;
  - the Claude session store, the Anthropic endpoint of the fake model and the `claude` extra are removed;
  - phase-1.md never names a second harness.
- **Leftovers are text only:** Nit H7.

## Status of the earlier non-Claude Nits

- **Fixed:** G9, G10, G12, G13, G14, G15, G16, G17, G19, G21, G22.
- **Partly fixed, with the residue carried into the list below:**
  - G11: H6;
  - G23: H15;
  - G24: the durability spec still carries the old condition (H8).
- **Fixed, but the new text opens a Major:**
  - G12's new input rule: H1;
  - G19's `output_type` mechanism: H3.

## Findings in the changed text

Reviewers: FR = fresh reader, CF = codebase fit, ZO = zoom out. Duplicates are merged. Where reviewers disagreed on severity, the coordinator applied the owner's scope rule.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| H1 | Major | ZO (CF: Nit) | RFC `run_harness_turn` step 2 (Restore), step 4 "Input to `Runner.run`" and "Checkpoint after every inner turn … the next `on_llm_start`"; RFC "Model mistakes" (`ModelBehaviorError` ends the turn with `continue`) | **Restore with no checkpoint is undefined, and no test can catch it.** The first checkpoint of an attempt comes at its *second* `on_llm_start`. An attempt can be lost during its first model call or first tool calls, which is the longest window with a local model. A `ModelBehaviorError` can also end inner turn 1. Either way, the next attempt or turn finds no checkpoint. Step 2 defines session restore only as "truncate to the checkpoint's `session_position`", and the new input rule then sends only "Continue the task from where it stopped." The instructions live only in the session (`run.py:1005-1020`). Either reading of the design fails the acceptance criterion "without losing edits or conversation context":<br>• truncating to 0 removes the task;<br>• not truncating can keep inner-turn items whose workspace edits were reset to the input files.<br>The fake model ignores instructions, and both crash tests stop after a checkpoint, so every test passes either way. | Fix: take a checkpoint at the first `on_llm_start` of every attempt (its position then includes the saved input). Or state the rule for no checkpoint: start from the input files, clear the session and send the instructions. Add a test that stops the worker while the fake holds step 0 and checks, from the request log, that worker B's request contains the instructions. | open |
| H2 | Major | CF (ZO: Nit) | tasks.md 3.1 ("restore preferring the highest attempt"); RFC test trace row "Durable session … recovery on another worker"; durability spec scenario "Latest turn wins" | **G3 residue: the stale task and the missing test.** Task 3.1 still tells the implementer the old, wrong rule, which contradicts RFC step 2 and the spec. The new scenario "Latest turn wins" has no test path. The trace table lists only `make recovery-check` (one turn, one stop) and `test_checkpoint_matches_session_position`. | Fix: change task 3.1 to "order by turn, attempt, seq (descending)". Add a named unit or time-skipping test (for example `test_restore_prefers_latest_turn`, with turn 1 on three attempts and turn 2 with one checkpoint) to task 3.1 and to the trace table. | open |
| H3 | Major | CF (ZO: Nit) | RFC step 4 "Done or needs input" (`Agent(output_type=FinalReport)`); RFC "APIs checked" (`Agent(output_type=)`); task 2.1 | **The design relies on an untested capability of the local model** (§2 and §9.3: verify, and never claim an untested capability works). With `output_type` set, the SDK sends a JSON-schema `response_format` on *every* request, including those that carry `tools` (coordinator-checked, see Inputs). The spike never used it, and the fake model ignores it. It is unverified whether vLLM with `qwen3_coder` tool parsing still emits tool calls under schema-constrained decoding. If it does not, every real-model task fails, and so do the sample-task, benchmark and demo acceptance criteria. Real-model runs come only in PR 4. | Fix: either add a check against the Sparks in PR 2, with a recorded fallback (for example a `finish(status, summary, questions)` function tool with `tool_use_behavior=StopAtTools`) and a Risks row; or switch to the tool-based finish now. Or contest the finding with a recorded run on the Sparks. | open |
| H4 | Nit | CF, ZO, FR (FR: Major) | RFC "Starting a task"; migration `0003` `tasks` row; sequence diagram | `record_task` compares "a different Workflow run ID", but `tasks` stores only `workflow_id` (always equal to `task_id`), not a run ID. "`record_task` is the Workflow's first Activity" contradicts the diagram, where `resolve_capabilities` runs first. That is harmless, because it only reads. Three things are not stated:<br>• how the test simulates "after retention";<br>• that a run rejected with `TaskAlreadyExists` leaves the existing `audit` row untouched;<br>• that it does not run `finish_task` over that row. | Fix: add a `run_id` column; align the diagram; state both points. | open |
| H5 | Nit | CF, ZO | RFC `test_side_effect_not_repeated_after_crash`; RFC step 3 (MCP environment) | The test has three loose details:<br>• **Timeout:** `MCPServerStdio` defaults `client_session_timeout_seconds=5` (coordinator-checked). A graceful stop slower than 5 s returns an error result that gets checkpointed, so worker B never repeats the call. The test then fails loudly; it never passes falsely.<br>• **The flag:** it reaches the server only through a catalog entry's literal `env`, since the MCP environment is `env` + `PRAXIS_TASK_ID` + `secret_env` only. The RFC does not say which entry carries it, and adding it changes the registry hash.<br>• **One-shot:** this cannot rely on process memory, because worker B spawns a fresh server. | Fix: state SIGKILL (`docker kill`) or a test-mode timeout, and the catalog entry or template used. Say the pause applies only on the first-commit path. | open |
| H6 | Nit | ZO, FR (FR: Major) | RFC "Versions" (retryable `TemplateVersionUnavailable`); `run_harness_turn` step 1 | G11 residue. With "one version at a time" deployed, no old-version worker exists after a deploy, so the retry cannot succeed: it uses up 5 attempts or `schedule_to_close`, and "preserves in-flight work (§4.10)" is overstated. Step 1 also upserts the attempt row before the hash check, so each refused attempt is later marked `lost`/`worker_lost`. | Fix: qualify the §4.10 claim, and check the hash before the upsert (or label refusals separately). | open |
| H7 | Nit | CF, ZO, FR | RFC capability model (`api_style` `anthropic`); capability-model spec negative scenario (`harness: claude_sdk`); harness-turn spec Purpose ("for both runners") | Text left over from the deferral. If the `harness` enum drops `claude_sdk`, the negative scenario fails schema validation instead of producing the stated `CapabilityError`. | Fix: use a valid mismatching value, or document that `claude_sdk` is accepted by the schema and rejected in Phase 1. Drop `anthropic` and "both runners". | open |
| H8 | Nit | CF, ZO | durability spec "Mid-turn checkpoints"; task 1.8; RFC front matter | Three small inconsistencies:<br>• the durability spec still says "After each inner turn that changed the workspace or the session" (G24 residue);<br>• task 1.8 does not repeat that `OTEL_EXPORTER_OTLP_ENDPOINT` is optional;<br>• the front matter's "model per tier (spark: …)" disagrees with the new gloss (`spark` is the served model name; the tier is `local`). | Fix: align the text. | open |
| H9 | Nit | CF | RFC "Overlapping attempts", Self-fencing ("its heartbeat call reports the attempt cancelled or timed out") | `activity.heartbeat()` returns `None`. A timeout arrives as cancellation, with `activity.cancellation_details().timed_out` (coordinator-checked). The behavior works; only the wording is off. | Fix: reword. | open |
| H10 | Nit | FR (FR: Major) | RFC "Outcomes and budgets"; "Each harness turn" (Retries, `schedule_to_close`) | The RFC does not say what the task does when a harness turn fails for good: retries exhausted, `schedule_to_close` passed, or no worker. The open points are the task status, whether `finish_task` runs, whether the checkpoint is kept, and whether lost-attempt usage is recorded. | Fix: state it (presumably `failed`, with the reason, the checkpoint kept and `finish_task` run). | open |
| H11 | Nit | FR (FR: Major) | RFC step 5 (outputs uploaded as `audit` blobs) against `TurnOutcome` and `finish_task`; Demo | `TurnOutcome` carries no output refs and no `FinalReport.questions[]`, so how `finish_task` builds `TaskResult` is unstated. The demo shows `order-summary.md` but gives no way to fetch an output blob. | Fix: add output refs and questions to `TurnOutcome` (or have `finish_task` read them), and name the fetch command. | open |
| H12 | Nit | FR | RFC `TurnInput`; step 2 | The RFC does not say where turn 1 gets its instructions and input files (`TurnInput` or the `tasks` row's `instructions_ref`), or where input files land in the workspace. | Fix: state it. | open |
| H13 | Nit | FR | RFC "Outcomes and budgets" (usage of lost attempts) | Usage after a lost attempt's last heartbeat, at most `heartbeat_timeout / 3`, is not counted, so "budgets count work done by a worker that was later lost" is approximate. | Fix: state the bound. | open |
| H14 | Nit | FR | RFC Versions, Capability model, `checkpoints`, Recovery check step 2, Components; proposal "What Changes" | Six small gaps:<br>• who updates `registry.lock`, and how a version bump is told apart from an unlisted file;<br>• whether `concurrency_per_pod` is one of the stored-but-unused fields;<br>• what `checkpoints.session_id` is for, when the session is keyed by `task_id`;<br>• the `worker_identity` format the recovery check maps to a container;<br>• what the `comms_mcp` stub is for;<br>• the proposal's migration list leaves out `sample_orders`. | Fix: one line each. | open |
| H15 | Nit | FR | RFC throughout (G23 residue) | Still unexplained for a reader outside the project:<br>• the plan § references (§4.1, §4.2, §4.3, §4.4, §4.10, §4.13, §7.1);<br>• the front matter's `tier`, `size` and `pre0_inputs`, and "Pre-0";<br>• ADR-0001, "phase closure" and "the as-built section";<br>• Claim Check, and the link between "praxis CLI" and `python -m orchestrator.cli`;<br>• what the open licensing decision is. | Fix: one-line glosses, or a pointer to the plan's glossary. | open |
| H16 | Nit | FR | RFC "Overlapping attempts" | An old attempt can append to the shared session after the new attempt has truncated it, and the reader says the accepted-risk wording does not cover this. | Contest: the "Remaining window" bullet already says the old attempt's in-flight call "can still reach the shared session", and the threat model lists it as an accepted risk. | contested: covered by the "Remaining window" text |

## Verdict

**FAIL.**

The verdict follows `docs/reviews/README.md` rule 5: every Major must be fixed or contested with evidence before a PASS.
- **Earlier Majors:** G1, G2 and G5 are resolved. G3 is partly resolved, and its residue is H2.
- **New Majors in the changed text:** H1 and H3.
- **Closed by the owner's deferral of the Claude runner:** G4.
- **Totals:** three Majors are open (H1, H2, H3) and no Blockers. All three reviewers completed.

Each open Major has a small, local fix: one restore rule and a test (H1), one task line and a named test (H2), and one verification with a fallback (H3).

## Open items

- **Majors:** H1, H2 and H3 must be fixed or contested by the author. A re-check then runs in a new session (rule 6).
- **Nits:** H4-H15 (12 open) do not block. H16 is contested.
- **Not exercised here:**
  - vLLM's behavior with `response_format` plus `tools` (H3);
  - Temporal's carrying of heartbeat details across attempts (documented, and read in the `temporalio` source).

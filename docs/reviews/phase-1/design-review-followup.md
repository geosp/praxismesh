---
review: design
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: []
commit_sha: 17b3d6770f964adf4a48dd6c53742057f620855f
docs_sha: n/a
diff_base: e437d0fa87919680fd156488e91f16ef213e09f0
session: fresh (targeted follow-up, docs/reviews/README.md rule 6)
date: 2026-11-11
verdict: FAIL
reviewers:
  - { lens: fresh reader (design-reader), status: completed }
  - { lens: codebase fit (design-reviewer), status: completed }
  - { lens: zoom out (design-reviewer), status: completed }
---

# Design review, targeted follow-up: Phase 1 harness-in-Activity, single agent

## Inputs

Revision `17b3d6770f964adf4a48dd6c53742057f620855f` (branch `docs/44-phase-1-design`, draft PR #45, issue #44). The working tree was clean (`git status --porcelain` empty). This is a **targeted follow-up** under rule 6: the two `design-reviewer` sessions received the correction list ([design-review.md](design-review.md), verdict FAIL at `e437d0f`) and the revision diff `e437d0f..17b3d67`. The fresh reader did not receive the correction list. No session transcript was read by the coordinator or any reviewer. All paths are under `/home/geo/develop/praxismesh`.

- **Fresh reader** (`design-reader`, Claude Code, project instructions omitted): `openspec/changes/phase-1-single-agent/proposal.md`, `design.md`, and `docs/rfcs/phase-1-single-agent.md`. Its standard brief, unchanged.
- **Codebase fit** (`design-reviewer`): the change (proposal, design, tasks, all nine `specs/**/spec.md`), the RFC, `AGENTS.md`, `PROJECT_PLAN.md` (§2, §6, §8), `docs/plan/phases/phase-1.md` and its *Read first* sections, `docs/plan/schemas.md`, `docs/plan/decision-log.md` (newest rows), the correction list and the revision diff. Asked to rule on F1-F31 and to look for new Blockers and Majors only in changed text.
- **Zoom out** (`design-reviewer`): the change, the RFC, `PROJECT_PLAN.md`, `docs/plan/phases/phase-1.md`, `docs/plan/design-decisions.md`, `docs/plan/schemas.md`, `docs/plan/decision-log.md`, the correction list and the revision diff. Asked to rule on F1-F9 end to end and to look for new Blockers and Majors only in changed text.

Both `design-reviewer` briefs also carried the location of the installed SDKs (`openai-agents` 0.24.0 and `claude-agent-sdk` 0.2.180 in `spikes/harness-vllm`; `temporalio` 1.36.0 in the root environment) and the owner's scope rule: Blockers and Majors only for problems that would fail a phase-1.md acceptance criterion, contradict a §2 hard constraint, mis-state verified SDK or API behavior, or leave a requirement without a test path; developer-tooling edge cases are Nits at most; the owner's Phase 1 decisions in the decision log are accepted as given. The coordinator applied the same rule when merging; fresh-reader Majors outside it are marked "(FR: Major)".

The fresh reader's findings are limited to text that changed: the RFC was largely rewritten in this revision (549 lines changed), so nearly all of its findings fall in changed text.

**Coordinator spot checks against the installed packages** (the evidence for G1-G5):
- `agents`: after `set_tracing_disabled(True)`, `get_trace_provider()` is a disabled `DefaultTraceProvider` that still holds `[BatchTraceProcessor(BackendSpanExporter)]` (run, not just read).
- `agents/run_internal/run_loop.py:2967-2979`: `hooks.on_llm_start` is awaited before the model request; `agents/run.py:2060-2097` saves a turn's items to the session before the loop reaches the next model call.
- `claude_agent_sdk/_internal/session_resume.py:150`: `project_key = project_key_for_directory(options.cwd)`; lines 82-93: resume works by setting `CLAUDE_CONFIG_DIR` in `options.env`; lines 115-119: the mirror's `projects_dir` comes from that directory or the default config directory.
- `claude_agent_sdk/_internal/transport/subprocess_cli.py:819-868`: the SDK adds `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_AGENT_SDK_VERSION`, the session-state variable, `TRACEPARENT` and `PWD` to the CLI's environment.
- `infra/docker-compose.yml:83`, `infra/.env.example:31`: Temporal namespace retention is 72h. That `REJECT_DUPLICATE` applies only to closed runs still inside retention is Temporal's documented behavior; it was not exercised here.

## Fresh reader paraphrase

> ## What this proposes
>
> Phase 0 built the platform stack. Phase 1 adds the first product code: one agent, running on the local model, carries out a task as a durable Temporal workflow and survives losing its worker partway through. Each step of the agent is a bounded "harness turn" Activity. The Activity takes its capabilities only from a versioned worker template, saves checkpoints of the session and workspace during the turn, and makes side-effecting tools idempotent, so another worker can pick the task up and continue without repeating effects. The change also adds the things later phases build on: a `BlobStore` contract with an S3 adapter, migration 0003 with retention classes on every row, baseline logs, traces and metrics, a benchmark suite with a regression limit, and a first threat model.
>
> ## How the existing system works, per this document
>
> According to the document, the existing system is only the Phase 0 local stack: Temporal, a ParadeDB database, SeaweedFS object storage and an external vLLM endpoint, run under Compose. A CI job called `stack` runs integration tests against that stack. It has at least migrations 0001 and 0002 (implied, because this change adds 0003), a hello-workflow replay test (`tests/test_hello_replay.py`), a stack helper with an S3 client (`tests/support/stack.py`), `infra/.env` with `check-prereqs.sh`, and existing `storage/blob-store` and `persistence/app-database` capabilities that this change modifies. It has no agent, worker or product code. A Pre-0 spike ran both harnesses against the local model on 10 tasks.

The reader could paraphrase every section, so it raised no Blockers.

## Status of the earlier Majors

| ID | Status | Evidence |
|---|---|---|
| F1 | **partly resolved** | Fixed: the CLI mints `task-<UUIDv4>`, the start uses `REJECT_DUPLICATE` and `id_conflict_policy=FAIL` (both exist in temporalio 1.36.0), and `test_duplicate_task_id_rejected` is in task 1.7. Remaining: the claim "rejected, whether the first run is still running or has finished" holds only inside namespace retention, and requests may supply `task_id`. See G1. |
| F2 | **resolved** | `tools`, exact `allowed_tools`, `permission_mode="dontAsk"`, `strict_mcp_config`, `setting_sources=[]`, `plugins`, `effort`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` and a clean-environment `cli_path` wrapper (RFC "The Claude runner"; harness-turn spec "Claude runner isolation"). The SDK runs `cli_path` as the command (`subprocess_cli.py:574`), so the wrapper does control the environment. `test_claude_runner_isolation` gives a test path against the fake Anthropic endpoint. The wrapper itself introduces G4 and Nits G6-G8. |
| F3 | **resolved** | Attempt row upserted at start on (`task_id`, `turn`, `attempt`); lost-attempt usage carried in heartbeat details (task-workflow spec "Lost attempts count against the budget"); template caps named (`max_turns_cap`, `max_tokens_cap`, `max_wall_time_cap`). Residual: G9. |
| F4 | **resolved** | `tests/support/fake_model/` answers from the message history, with a pause point and request log (RFC "Deterministic fake model"; task 2.1a). `on_llm_start` runs before the paused request, so "wait for the checkpoint, then stop the worker" holds for the workspace-edit check. The effect-then-crash variant does not work: G2. |
| F5 | **partly resolved** | `RunConfig(tracing_disabled=True)` plus `set_tracing_disabled(True)` stop export, so §2 is met. The new test cannot pass as specified: G5. |
| F6 | **resolved** | `retention_class NOT NULL` on every table, `DEFAULT 'task'` on the session-store tables and `sample_orders`, tables created only by the migration (RFC migration `0003`; app-database spec). |
| F7 | **resolved** | Hook point named (next `on_llm_start`, plus a final checkpoint after the run); save timing corrected; confirmed against `run.py:2060-2097` and `run_loop.py:2967-2979`; `test_checkpoint_matches_session_position` added. Residual: G12. |
| F8 | **resolved** | `tool_not_found_behavior="return_error_to_model"` returns a tool-result error instead of raising (`turn_resolution.py:3836-3843`); `ModelBehaviorError` classed non-retryable; `test_prohibited_tool_returns_error` added. Residual: G10. |
| F9 | **resolved** | `sample_orders` in `0003` with a unique `idempotency_key` and a retention class; credentials through `secret_env` (the MCP stdio client passes only a minimal env plus the configured one, `mcp/client/stdio.py`); `PRAXIS_TASK_ID` supplied, key computed by the server, both rows written in one transaction; identical-call collapse stated as intended (durability spec). The end-to-end crash test has no working pause point: G2. |

## Status of the earlier Nits

Fixed: F10, F12, F13, F14, F15, F16, F17, F18, F21, F22, F23, F24, F25, F27, F28, F29, F30.
Partly fixed, residue carried into the new list: F11 (G13), F20 (G15), F26 (G23), F31 (G24).
Changed, but the new text mis-states the SDK: F19 (G4).

## Findings in the changed text

Reviewers: FR = fresh reader, CF = codebase fit, ZO = zoom out. Duplicates are merged; where reviewers disagreed on severity, the coordinator applied the owner scope rule.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| G1 | Major | CF, ZO | RFC "Starting a task" ("whether the first run is still running or has finished"); RFC `TaskRequest` (`task_id?`); task-workflow spec "One run per task ID" | **F1 residue; mis-stated API behavior.** `REJECT_DUPLICATE` applies only to closed runs still inside namespace retention (72h, `infra/docker-compose.yml:83`). A request that supplies its own `task_id` after that starts a new run, and `idempotency_keys` (keyed on `task_id` + tool + arguments, `audit` class) silently returns the first run's `record_order` results. `test_duplicate_task_id_rejected` runs inside retention and cannot catch it. | Fix: make `record_task` insert-only on `task_id` and record the Workflow run ID; a row from a different run fails non-retryably (a retry of the same run is accepted). Or drop client-supplied `task_id`. Qualify the claim with the retention limit either way. | open |
| G2 | Major | CF, ZO | RFC "Recovery check" (`test_side_effect_not_repeated_after_crash` "with the pause placed between `record_order` and the next checkpoint"); durability spec "Crash between effect and checkpoint"; task 3.3 | **No working end-to-end test for "no duplicated external side effects".** The only pause point is a held model response. After `record_order` the order is: effect, turn items saved (`run.py:2060-2097`), `on_llm_start` checkpoint, then the request that the fake holds (`run_loop.py:2967-2979`). No pause can fall between the effect and the next checkpoint, so the resumed attempt never calls `record_order` again, and the test passes even without idempotency keys. The recovery check's "`sample_orders` has one row" has the same weakness. | Fix: add a test-only pause in the effect path (for example a `sample_mcp` flag that blocks after its commit and before returning, released through a control file or socket), or have the fake return `record_order` together with a slow second tool and stop the worker during that tool. Assert that the resumed attempt calls `record_order` again and gets the recorded result. | open |
| G3 | Major | CF, ZO, FR | RFC `run_harness_turn` step 2 ("newest checkpoint for the task …, preferring the highest attempt and then the highest `seq`"); RFC migration `0003` (`checkpoints` key (`task_id`, `turn`, `attempt`, `seq`)); RFC "Overlapping attempts" | **Restore order ignores the turn.** Temporal attempt numbers restart at 1 for each Activity, so for each harness turn. If turn 1 needed three attempts and turn 2 attempt 1 is lost, the stated order restores turn 1 attempt 3: the workspace rolls back and `pop_item` truncates turn 2's conversation. That fails the acceptance criterion "without losing edits or conversation context". The recovery check uses one turn and one stop, so no test covers it. | Fix: order by (`turn` desc, `attempt` desc, `seq` desc), and add a time-skipping or unit test with a multi-turn task whose earlier turn had retries. | open |
| G4 | Major | CF (FR in part) | RFC "Sessions" (`claude_sdk`: "`SessionKey.project_key = task_id`"); RFC "The Claude runner", Environment (the `env -i` wrapper with an explicit list) | **F19 changed, but the new text mis-states the SDK.** The caller cannot set `project_key`: the SDK derives it from `cwd` (`session_resume.py:150`) and the mirror from the transcript path. Store-backed resume works by setting `CLAUDE_CONFIG_DIR` in `options.env` (`session_resume.py:82-93`), which the wrapper's explicit list drops, along with the SDK's own `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_AGENT_SDK_VERSION`, session-state variable and `TRACEPARENT` (`subprocess_cli.py:819-868`). With `HOME` changed only inside the wrapper, the CLI writes transcripts outside the mirror's `projects_dir`, so they are not mirrored. The PR 3 verification would fail because of the design, and the §7.1 fallback would be recorded for the wrong reason. Impact is limited to the optional, non-default runner. | Fix: set `CLAUDE_CONFIG_DIR` (or `HOME`) in `options.env`, have the wrapper pass it and the SDK's `CLAUDE_*` and `TRACEPARENT` variables through, and either run every attempt in a stable per-task `cwd` or have the adapter key on `session_id` and ignore `project_key`. | open |
| G5 | Major | CF, ZO | observability spec "SDK tracing off" ("no `openai-agents` trace processor or exporter is registered"); task 1.6 `test_no_sdk_trace_export` | **F5 residue; the spec's only test cannot pass with the configured mechanism.** `set_tracing_disabled(True)` calls `get_trace_provider()`, which registers the default processor (`agents/tracing/setup.py:53-59`). Coordinator ran it: the disabled provider still holds `[BatchTraceProcessor(BackendSpanExporter)]`. Nothing is exported, so §2 is met, but the scenario fails as written (same class as F6). | Fix: also call `set_trace_processors([])` (or install the OpenTelemetry bridge processor), or change the scenario to "provider disabled and no export attempted". | open |
| G6 | Nit | CF | RFC "The Claude runner" (`tools`, `allowed_tools`, `plugins`) | Plugin skills are invoked through the `Skill` tool, granted by `Skill(name)` entries in `allowed_tools` (`subprocess_cli.py:527-568`). Neither list contains it, so under `dontAsk` the plugin route is closed (the bundle is still readable at `.skills/`). | Fix: add `Skill` and `Skill(<name>)`, or drop the plugin. | open |
| G7 | Nit | CF, ZO | RFC "The Claude runner" (bare `Bash`); capability-model spec "Prohibited tool call" | The Claude runner grants `Bash` without a program restriction, so the `cli_tools` allow-list the spec requires is not enforced for that runner. | Fix: use `Bash(<prog>:*)` rules and add the case to `test_claude_runner_isolation`, or state the exemption. | open |
| G8 | Nit | CF, ZO | RFC "The Claude runner" ("Neither the CLI nor its `Bash` tool sees the worker's credentials"); RFC `run_command` | Overstated: commands run as the worker's UID and can read `/proc/1/environ`; the SDK passes the MCP config, including the `secret_env` value, on the CLI command line (`--mcp-config`, `subprocess_cli.py:684-689`). The canary test checks only `env`. | Fix: qualify the claim and list it as an accepted Phase 1 risk in the threat model, or run commands under a separate UID. | open |
| G9 | Nit | CF, ZO, FR | RFC "Outcomes and budgets" ("read from their last heartbeat details"); RFC step 4 Heartbeat | Only the previous attempt's heartbeat details are visible, so counts must be cumulative (each attempt seeds from the previous details) or a second lost attempt drops the first one's usage. Nothing writes `outcome`/`failure_category` on a lost attempt's row. | Fix: state cumulative counts, and have the next attempt mark the previous row `lost`. | open |
| G10 | Nit | CF, ZO | RFC "Each harness turn" (non-retryable `HarnessProtocolError` "for example a `ModelBehaviorError`"); capability-model spec "Prohibited tool call" | Every `ModelBehaviorError` (malformed tool JSON from the local model, among others) now fails the whole task. The not-found case is already handled by `return_error_to_model`. No hook fires for a tool that was not found, so the refusal log has no stated detection point. | Fix: narrow the non-retryable class, and name where the refusal is logged (for example `on_llm_end` checking requested tool names). | open |
| G11 | Nit | CF | RFC `run_harness_turn` step 1; RFC Capability model (hash mismatch is a non-retryable `CapabilityError`) | A template version bump during a rollout permanently fails in-flight tasks, against §4.10 "preserve in-flight work". | Fix: use a retryable error, or per-version queues. | open |
| G12 | Nit | CF, ZO | RFC step 4 ("A final checkpoint is also taken after `Runner.run` returns") | `Runner.run` raises `MaxTurnsExceeded` at the inner-turn limit (`run.py:1598-1621`), so the final checkpoint and the `continue` mapping must run on that path too. The input given to `Runner.run` on a resumed attempt or later turn is not stated; re-sending instructions duplicates a user message. | Fix: state both. | open |
| G13 | Nit | CF, ZO, FR | RFC "Overlapping attempts" (F11 residue) | Keying checkpoints by attempt does not fence the session: a zombie attempt still appends to the same `SQLAlchemySession` (keyed by `task_id`) and can call `record_order` after its replacement has restored and truncated. | Fix: fence session writes by attempt, or state the accepted risk. | open |
| G14 | Nit | ZO | RFC "Deterministic fake model" (pause point) | Worker B resends the same history and reaches the same `pause` step again. | Fix: make the pause one-shot. | open |
| G15 | Nit | ZO | task 1.8; `infra/check-prereqs.sh:20-24` (F20 residue) | Every known key except the vLLM ones is required, so adding the optional `OTEL_EXPORTER_OTLP_ENDPOINT` would make it mandatory. | Fix: mark it optional. | open |
| G16 | Nit | ZO | tasks 1.7 vs 2.4 | `test_duplicate_task_id_rejected` is in PR 1, before `TaskWorkflow` exists. | Fix: use a stub Workflow or move the test. | open |
| G17 | Nit | ZO | capability-model spec "Capabilities come from templates only" | Still says "a request carries only a profile name, instructions and input files"; `TaskRequest` now also has `task_id`, `template` and `outputs`. | Fix: align the spec. | open |
| G18 | Nit | FR (FR: Major) | RFC step 4 Checkpoint; RFC "The Claude runner" | The mid-turn checkpoint hook and the consistent read of the entry count are given only for `openai_agents`. The Claude runner is optional and has a stated fallback. | Fix: name the Claude hook point (for example `PreToolUse`/result messages), or state that the fallback applies. | open |
| G19 | Nit | FR (FR: Major) | RFC "Outcomes and budgets" | How the harness tells `done` from `needs_input` (structured output, a tool, or the final message) is not stated. | Fix: state the mechanism. | open |
| G20 | Nit | FR (FR: Major) | RFC "The Claude runner", Environment | `ANTHROPIC_AUTH_TOKEN` comes "from the template", but the template has only `base_url_env` and MCP `secret_refs`. | Fix: name the template field or secret that supplies it. | open |
| G21 | Nit | FR | RFC TaskWorkflow sequence vs step 2; "Outcomes and budgets" | `TurnInput` carries the latest checkpoint, yet restore reads `checkpoints`; which wins is unstated. `TurnInput`'s remaining budget is never used inside a turn, so tokens can overrun within one turn (only wall time is acknowledged). | Fix: drop the field or say it is advisory; state the in-turn token overrun bound. | open |
| G22 | Nit | FR | RFC Sample skill (profile `default`); Retention classes; Workers and Compose | The profile's `max_tokens` and `max_wall_time` are not given; the retention table gives no class for `tasks`, `checkpoints` and `blob_objects` rows; `PRAXIS_SAMPLE_DB_URL` is not clearly in the worker's environment. | Fix: state each. | open |
| G23 | Nit | FR, ZO | RFC throughout (F26 residue) | Still unexplained: `tier` and how `spark` relates to the served model name, `allowed_model_overrides`/`model_override` handling, `ExecutionAttempt` vs `task_attempts`, `sample-shop` vs `sample_mcp`, `request_id`'s source, who owns the system prompt, Claim Check, "the installer's machine", `comms_mcp`. | Fix: one-line glosses. | open |
| G24 | Nit | ZO | RFC step 4 ("when an inner turn has changed the workspace or added session items") (F31 residue) | Every inner turn adds session items, so the condition is always true. | Fix: drop the condition or make it meaningful. | open |

## Verdict

**FAIL.**

Under `docs/reviews/README.md` rule 5, every Major must be fixed or contested with evidence before a PASS. Of the earlier Majors, seven are resolved (F2, F3, F4, F6, F7, F8, F9) and two are partly resolved (F1, F5); their residues are G1 and G5. The changed text adds three new Majors (G2, G3, G4). Five Majors are open. No Blockers were raised and all three reviewers completed.

The revision is a substantial improvement: the SDK settings it now names (`REJECT_DUPLICATE`, `tool_not_found_behavior`, `tracing_disabled`, the Claude `tools`/`dontAsk`/`plugins`/`effort`/`cli_path` options, `on_llm_start` ordering) exist and behave as described, apart from the points above. Each open Major has a small, local fix.

## Open items

- G1-G5 (Major) must be fixed or contested by the author. A re-check then runs in a new session (rule 6).
- G6-G24 (Nit, 19) do not block.
- Not re-checked: whether the Claude CLI loads `--plugin-dir` plugins with empty setting sources, and Temporal's carrying of heartbeat details across attempts (documented, not exercised). The RFC already defers Claude verification to the implementation PRs.

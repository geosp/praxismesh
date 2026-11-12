---
review: design
phase: 1
change: openspec/changes/phase-1-single-agent
rfc: docs/rfcs/phase-1-single-agent.md
adrs: []
commit_sha: e437d0fa87919680fd156488e91f16ef213e09f0
docs_sha: n/a
diff_base: n/a
session: fresh
date: 2026-11-11
verdict: FAIL
reviewers:
  - { lens: fresh reader (design-reader), status: completed }
  - { lens: codebase fit (design-reviewer), status: completed }
  - { lens: zoom out (design-reviewer), status: completed }
---

# Design review: Phase 1 harness-in-Activity, single agent

## Inputs

Revision `e437d0fa87919680fd156488e91f16ef213e09f0` (branch `docs/44-phase-1-design`, draft PR #45, issue #44). The working tree was clean (`git status --porcelain` empty). All paths below are under `/home/geo/develop/praxismesh`. Each reviewer received only its brief from the `review-design` skill, with these paths filled in.

- **Fresh reader** (`design-reader`, Claude Code, project instructions omitted):
  - `openspec/changes/phase-1-single-agent/proposal.md`
  - `openspec/changes/phase-1-single-agent/design.md`
  - `docs/rfcs/phase-1-single-agent.md`
- **Codebase fit** (`design-reviewer`):
  - change files: `proposal.md`, `design.md`, `tasks.md` and the nine specs: `specs/agents/capability-model`, `specs/execution/task-workflow`, `specs/execution/harness-turn`, `specs/execution/durability`, `specs/storage/blob-store`, `specs/persistence/app-database`, `specs/observability/baseline`, `specs/quality/agent-benchmarks`, `specs/security/threat-model` (each `spec.md`)
  - design docs: the RFC (no ADRs are linked to this change)
  - guidance and plan files: `AGENTS.md`, `PROJECT_PLAN.md` (§2, §6, §8), `docs/plan/phases/phase-1.md`, `docs/plan/design-decisions.md` (§4.1, §4.2, §4.10, §4.13), `docs/plan/schemas.md`, `docs/plan/decision-log.md` (newest rows)
- **Zoom out** (`design-reviewer`):
  - the change directory (proposal, design, tasks) and the RFC
  - plan files: `PROJECT_PLAN.md`, `docs/plan/phases/phase-1.md`, `docs/plan/design-decisions.md`, `docs/plan/schemas.md`, `docs/plan/decision-log.md`
  - any code it chose to read

Notes on the inputs:
- `design.md` only links to the RFC, by design (ADR-0001).
- No ADR has `openspec_change` set to this change, and `grep` finds none that names it.
- Both `design-reviewer` briefs added two pieces of environment information and nothing else: where the installed SDKs live (`openai-agents` 0.24.0 and `claude-agent-sdk` 0.2.180 in `spikes/harness-vllm`, `temporalio` 1.36.0 in the root environment), and the owner's scope rule for severities (below).
- **Owner scope rule.** Blockers and Majors are raised only when a problem would:
  - make the design fail a phase-1.md acceptance criterion;
  - contradict a §2 hard constraint;
  - mis-state a verified SDK or API behavior;
  - or leave a requirement without a test path.

  Developer-tooling edge cases are Nits at most. The owner's decision-log entries of 2026-11-12 are accepted as given. Following this rule, the coordinator downgraded to Nits those of the fresh reader's Majors that fall outside it. Each one is marked "(FR: Major)" below.
- There is no Phase 1 code yet. The codebase-fit reviewer checked the code claims against the plan, `schemas.md`, the Phase 0 code (`common/persistence/`, `infra/`, `Makefile`, CI) and the installed SDK packages, and it reported that it did.
- **Coordinator spot checks** against the installed packages, which confirm the reviewers' SDK evidence:
  - `temporalio` `Client.start_workflow` defaults to `id_reuse_policy=ALLOW_DUPLICATE` (enum value 1).
  - `agents.RunConfig.tool_not_found_behavior` defaults to `"raise_error"`.
  - `agents/tracing/processors.py` contains the OpenAI traces ingest endpoint.
  - The `claude_agent_sdk/types.py` docstrings say "To restrict which tools are available at all, use `tools`" (line 2357) and that `env` is "Merged over the parent process's environment" (line 2495).

## Fresh reader paraphrase

> ## What this proposes
>
> Phase 1 adds the first product code: one AI agent on a locally hosted model that does a task as a durable Temporal workflow. If the worker container running the task is killed partway through, the task continues on a second worker. The work is split into bounded "harness turns". Each turn is one Temporal Activity that runs an agent SDK (OpenAI Agents by default, Claude Agent SDK optional) for a limited number of model calls. After each model call that changes anything, the Activity saves a checkpoint of the conversation and a snapshot of the workspace, so a replacement worker can pick up from there. Around this it adds:
> - a capability model where only versioned templates decide which tools, MCP servers, skills and model an agent gets, and requests or profiles that try to name them are rejected;
> - a content-addressed `BlobStore`;
> - new database tables, each with a retention class;
> - idempotency keys so side-effecting tools don't run twice after a crash;
> - logs, traces and metrics;
> - a 10-task benchmark with a regression rule;
> - a first threat model.
>
> The reason given: later phases build on these foundations, and the plan requires crash recovery mid-task.
>
> ## How the existing system works, per this document
>
> Phase 0 provides only a local infrastructure stack: Temporal, ParadeDB/PostgreSQL, SeaweedFS (S3-compatible object storage) and an external vLLM model endpoint on two DGX Spark machines. There is no product code yet. There are no agents, workflows, schemas or workers. The documents imply some existing pieces: earlier migrations (this change adds `0003`), an `infra/docker-compose.yml` with an `infra/.env`, a CI `stack` job, a license check, and a `make reset` target. They don't describe any of these. A spike was run earlier: it had 10 tasks, compared the two harnesses, and found Claude used about 14 times the input tokens.

The reader could paraphrase every section, so it raised no Blockers.

## Findings

Reviewers: FR = fresh reader, CF = codebase fit, ZO = zoom out. Duplicates across reviewers are merged. Where reviewers gave the same issue different severities, the higher one is used, subject to the owner scope rule.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| F1 | Major | CF, ZO | RFC TaskWorkflow ("Starting the same task ID twice is rejected by Temporal, which makes submission idempotent") | **Mis-stated API behavior.** In temporalio 1.36.0, `Client.start_workflow` defaults to `id_reuse_policy=ALLOW_DUPLICATE` (coordinator confirmed). A start is rejected only while a run with that ID is still open, so a closed `task_id` starts a new run. That run re-runs `record_task`. Because `idempotency_keys` is keyed by `task_id` + tool + arguments, its `record_order` calls silently return the first run's results. The RFC also never says who mints `task_id`. | Fix: start with `id_reuse_policy=REJECT_DUPLICATE` (and state the conflict policy), say who mints `task_id`, and add a test that a second start with the same ID is rejected after the first run completes. | open |
| F2 | Major | CF, ZO | RFC `run_harness_turn` step 2 (Claude runner settings); harness-turn spec:21, 25; capability-model spec:32 | **The Claude runner settings don't do what the design says.** **Tools:** `allowed_tools` only auto-approves tools ("To restrict which tools are available at all, use `tools`", `claude_agent_sdk/types.py:2357`). Built-in Bash, Write, WebFetch and Task stay available. The spike used `permission_mode="dontAsk"` plus `disallowed_tools` (`spikes/harness-vllm/run_claude.py:62-66`); the RFC lists neither. **Credentials:** `env` is "Merged over the parent process's environment" (`types.py:2495`; `subprocess_cli.py:819` copies `os.environ`), so the CLI and its Bash see the worker's database, S3 and model credentials. The credential-free environment and the command allow-list exist only for `run_command`. **Skills:** with `setting_sources=[]`, the CLI discovers no skills (`subprocess_cli.py:527-568`), and the `.skills/` mount is not a Claude Skill location, so "`skills` limited to the bundle" loads nothing. **Missing settings:** the per-model `effort` pin (decision log 2026-11-11) and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` (§4.1). **No test path:** the scenario "Claude runner discovers nothing implicitly" has none, because CI doesn't install the extra and the CLI can't use `ScriptedModel`. | Fix: set `permission_mode="dontAsk"`, `tools=[...]` (the base set) and `allowed_tools` to the exact `mcp__server__tool` names. Start the CLI from an explicitly minimal environment. Name how the bundle is loaded (for example `plugins`). Add `effort` to `WorkerTemplate` and set the non-essential-traffic variable. Give the Claude scenarios a test path, or mark them verified-by-demo with a stated reason. | open |
| F3 | Major | ZO, CF, FR | RFC `run_harness_turn` step 4 ("write the `task_attempts` row"); RFC Terms (Budget); task-workflow spec:10, 16-18 | **Lost attempts are not accounted for.** The `task_attempts` row and the token usage are recorded only at Finish, from a returned `TurnOutcome`. An attempt killed with its worker, or timed out, therefore leaves no `ExecutionAttempt` row and no `failure_category`, yet those are the infrastructure failures the table exists for. Its tokens never reach the budget either, so `max_tokens` can be overrun by up to 5 attempts per turn. The plan task asks for "clear turn/budget accounting". Also, the "capped by the template" budget has no template fields (FR). | Fix: insert the attempt row at attempt start and update it at the end, with stable upsert keys. Carry the previous attempt's last heartbeat details (tokens, tool calls) into the next attempt's outcome. Name the template cap fields, or drop "capped by the template". | open |
| F4 | Major | ZO, CF | RFC Testing ("`make recovery-check` in the `stack` job with a scripted model"); tasks 3.4 | **The core acceptance test has no defined mechanism.** "Deleting a pod after workspace edits still restores" depends on this CI test. `agents.testing.ScriptedModel` is an in-process list of steps (`agents/testing/model.py:249-279`), and the design doesn't say how a container worker selects it. Worker B's copy would restart at step 0 whatever session it restored, so the test can't show that the conversation continued. Nothing holds a turn open long enough to stop worker A after an acknowledged checkpoint. | Fix: specify a test-only fake OpenAI-compatible endpoint, reached through the template's `base_url_env`. It should choose its reply from the request's message history and pause deterministically after a checkpoint. Add it to tasks.md and the RFC test list. | open |
| F5 | Major | ZO, CF | RFC Observability; observability spec:17 ("Export SHALL be OTLP when configured and off otherwise") | **Prompts can leave the machine (§2 local, self-hosted; §9.5).** openai-agents registers a `BackendSpanExporter` that posts to `https://api.openai.com/v1/traces/ingest` whenever `OPENAI_API_KEY` is set (`agents/tracing/processors.py:46,113`). It stays on unless disabled. The spike disabled it (`spikes/harness-vllm/run_openai.py:118`, `set_tracing_disabled(True)`); the RFC and tasks do not. | Fix: disable SDK tracing (or replace its processors with an OpenTelemetry bridge), add it to tasks, and add a test that no backend exporter is registered. | open |
| F6 | Major | CF, FR | RFC migration `0003` (`agent_sessions`/`agent_messages` "as the SDK defines them"; `claude_session_entries` columns); app-database spec:10, 17-21 | **The spec's retention test cannot pass.** The spec requires a non-null `retention_class` on every row in the Phase 1 tables, including the session-store tables. The SDK's tables have no such column (`agents/extensions/memory/sqlalchemy_session.py:206-247`), and `claude_session_entries` doesn't list one. So `test_every_row_and_blob_has_retention` fails as designed. This is the phase item "retention class on every blob and stored record from the first write". | Fix: have migration `0003` add `retention_class NOT NULL DEFAULT 'task'` to all three tables, so SDK inserts that omit it take the server default. State this in the RFC. | open |
| F7 | Major | CF, ZO | RFC Sessions ("Every item is committed as the run adds it"); RFC step 3 (checkpoints "after each inner turn" via hooks); durability spec | **The session save timing is mis-stated, and no checkpoint hook point is named.** openai-agents saves the input at run start, then each turn's items after that turn's tools finish, and the final output separately (`agents/run.py:2060-2097`). `RunHooks` has no after-turn or after-save hook (`agents/lifecycle.py:18-98`). A checkpoint taken in `on_tool_end` records an item count that lacks the current turn, while the workspace already holds its edit. On restore, `pop_item` then truncates to a count that doesn't match the snapshot, which breaks "without losing edits or conversation context". | Fix: name the hook point (for example the next `on_llm_start`, plus a final checkpoint after `Runner.run` returns), correct the commit-timing sentence, and add a test of the ordering. | open |
| F8 | Major | CF | capability-model spec:35-36 ("refused with an explicit error in the tool result"); RFC non-retryable list | **The SDK's behavior differs from the spec.** With `tool_filter`, a prohibited tool doesn't exist for the model. `RunConfig.tool_not_found_behavior` defaults to `"raise_error"` (coordinator confirmed), which raises `ModelBehaviorError` (`agents/run_internal/turn_resolution.py:3740`). That error is not in the non-retryable list, so Temporal would retry it up to 5 times as an infrastructure failure, instead of returning an explicit refusal. | Fix: set `RunConfig(tool_not_found_behavior="return_error_to_model")`, log the refusal, and classify `ModelBehaviorError` explicitly. Test that a prohibited call yields an error tool result and no retry. | open |
| F9 | Major | CF, FR, ZO | RFC "Side effects and idempotency"; migration `0003` table list; tasks 1.5, 3.3 | **The side-effect test (the "no duplicated external side effects" criterion) has nothing concrete to implement.** **Table:** `sample_orders` is not in migration `0003` or the tasks, and it has no retention class. **Credentials:** the stdio MCP subprocess has no stated way to get database credentials, since `McpServer.env` is "non-secret". **Key:** nothing says how `task_id` reaches `record_order(sku, qty)` to build the key, whether through the spawn environment, `_meta` or a harness wrapper. **Identical calls:** two intentional identical orders in one task collapse into one, and the threat model notes only the "different arguments" limit. | Fix: add `sample_orders` (with `retention_class`) to `0003` and the tasks. State how the server gets its credentials and the `task_id`, and say who computes the key. Record the identical-call collapse as intended, or add a sequence component to the key. | open |
| F10 | Nit | FR, ZO, CF | RFC Terms ("acknowledged … and its ID is sent in a heartbeat") vs durability spec:10 and RFC Risks | "Acknowledged" is defined two ways. Restore reads `checkpoints` directly, so the row commit alone is what works. | Fix: align the RFC and demo wording with the spec. | open |
| F11 | Nit | ZO | RFC Recovery on another worker | Overlapping attempts are not fenced. An attempt that outlives its heartbeat timeout and its replacement both write the same session and `checkpoints`. | Fix: pack and upload snapshots off the event loop, and prefer checkpoints from the highest attempt on restore. | open |
| F12 | Nit | ZO, CF, FR | capability-model spec:16-18 (hash mismatch "against the recorded version") | No recorded hash source is named. Nothing says what happens on a mismatch, or whether `run_harness_turn` rejects a `TurnInput` whose template version or hash differs. | Fix: name the record (for example a committed lock file) and the action. | open |
| F13 | Nit | ZO | RFC TaskWorkflow timeouts | There is no `schedule_to_close`, and wall time is checked only between turns. A task on a queue with no worker waits forever, and one turn can overrun by up to 5 × `turn_timeout`. | Fix: state that this is accepted (§4.3 scale-to-zero), or add the bounds. | open |
| F14 | Nit | ZO, CF, FR | RFC Retention classes vs step 3; BlobStore dedup | Intermediate snapshots are called `ephemeral` in one place and `put` as `task` in another. A content-addressed dedup `put` keeps the first write's class. | Fix: pick a rule (for example, the stronger class wins). | open |
| F15 | Nit | CF | RFC TaskWorkflow input (inline `instructions`) vs task-workflow spec:28 | The instructions travel inline, but the spec allows only IDs and `BlobRef`s. | Fix: cap the size, or store the instructions as a blob. | open |
| F16 | Nit | CF | RFC step 3 ("an unchanged workspace adds nothing") | Content addressing needs a deterministic tar and gzip: sorted entries, normalized mtimes and owners, gzip `mtime=0`. | Fix: state it. | open |
| F17 | Nit | CF | RFC migration `0003`; §2 stable operation IDs | The unique or upsert keys for `record_task`, `finish_task`, `task_attempts` and `checkpoints` are unstated. | Fix: state them. | open |
| F18 | Nit | CF | RFC Agent benchmark suite ("checks unchanged in substance"); `spikes/harness-vllm/shop_server.py:30-38` | Four spike tasks (`fix_discount`, `config_port`, `log_status`, `fix_script`) need `get_discount`/`get_setting`, which `sample_mcp` doesn't offer. | Fix: add the tools to `sample_mcp`, or adapt the tasks and say so. | open |
| F19 | Nit | CF | RFC Sessions (`claude_sdk`) | `SessionKey.project_key` defaults to the sanitized cwd, which changes when a turn is restored into a fresh directory on another worker. | Fix: use a per-task path or an explicit key. | open |
| F20 | Nit | CF | `infra/check-prereqs.sh:20-22`; `pyproject.toml` | **Tooling.** New `.env` keys need adding to the allowed list and `.env.example`. `[tool.uv] package = false` blocks a `[project.scripts]` entry, and the mypy `files` list lacks the new packages. | Fix: add these to tasks. | open |
| F21 | Nit | CF | RFC "APIs checked" table | `opentelemetry-sdk` 1.45.2 is said to be checked against the installed packages, but neither environment has it installed (only `opentelemetry-api`). | Fix: verify it, or reword. | open |
| F22 | Nit | CF | observability spec; phase-1.md:12 | Conversation IDs are omitted from the log fields without saying so. | Fix: state that they are deferred to Phase 2. | open |
| F23 | Nit | CF | agent-benchmarks spec (Purpose only) | The re-run trigger ("any change to a model, template, harness version or system prompt") has no SHALL. | Fix: make it a requirement. | open |
| F24 | Nit | CF, FR | proposal Impact vs RFC "New targets"; tasks 1.2 vs RFC `common/schemas/`; profile vs template `harness` | **Inconsistencies.** `task-status`/`recovery-check` are missing from the RFC targets, and `task-status` is never specified. `TaskRequest` is missing from the schema list. There is no precedence rule between the two `harness` fields, and no rule for choosing the template from `allowed_templates[]` (FR: Major). | Fix: align the files, and state the selection and precedence rules. | open |
| F25 | Nit | CF | Reuse | Existing helpers are not named. | Fix: reuse `common/persistence/settings.py:app_database_url`, the path-style S3 config in `tests/support/stack.py:85-93`, and the replay-fixture pattern in `tests/test_hello_replay.py`. | open |
| F26 | Nit | FR (FR: Major) | Throughout; front matter | **Undefined references and terms.** "The plan" and its § numbers, and "the spike", are never linked or located. Terms used without explanation: `tier`, `pre0_inputs`, the `stack` job, how `spark` resolves to an endpoint, the template fields (`api_style`, `base_url_env`, `allowed_model_overrides`, `secret_refs`, `concurrency_per_pod`, `capabilities[]`), MCP capability tags, status and outcome values, the §5 schema fields, process vocabulary, `sample-shop` vs `sample_mcp`, Claim Check, `request_id`, `make reset`, "the installer's machine". | Fix: link `PROJECT_PLAN.md` and `docs/spikes/harness-vllm.md`, and add one-line glosses. | open |
| F27 | Nit | FR (FR: Major) | RFC Sessions (`claude_sdk`) | Nothing says what `session_position` means for the Claude runner, or how entries after a checkpoint are discarded on restore. The runner is optional and has a stated §7.1 fallback. | Fix: define the position and the truncation, or state that the fallback applies. | open |
| F28 | Nit | FR (FR: Major) | RFC TaskWorkflow; step 1 | No mechanism or retention class is given for uploading input files to the `BlobStore` before the Workflow starts. | Fix: state that the CLI uploads them, and with which class. | open |
| F29 | Nit | FR (FR: Major) | RFC step 4 ("declared output files") | No schema or template field declares output files, so it is unclear how `order-summary.md` becomes a `TaskResult` artifact. | Fix: name the declaration (for example a template or request `outputs` field, or the whole workspace diff). | open |
| F30 | Nit | FR (FR: Major) | RFC Turn outcomes (`needs_input`) | `needs_input` has no resulting task status or resume path. Live input is Phase 2. | Fix: state the Phase 1 terminal status. | open |
| F31 | Nit | FR | RFC Capability model; Observability; Risks | **Smaller gaps.** "Inner turn that changed the session" is always true. Derived `capabilities[]` has no consumer. The Claude runner's equivalent of `RunHooks` is unnamed. Where request rejection runs is unclear. The §7.1 triggers name no action. The design is dated 2026-11-12, one day after the review date. | Fix: clarify each. | open |

## Verdict

**FAIL.**

Under `docs/reviews/README.md` rule 5, "every Major must be fixed or contested with evidence before a PASS". Nine Majors (F1-F9) are open, and none has been fixed or contested. No Blockers were raised, and all three reviewers completed, so neither of the rule's automatic-FAIL conditions applies.

The design's overall approach holds up. Durable state outside the worker fixes the root cause. Placement follows plan §6. The §7.1 rethink triggers are named with measurable signals. Migration `0003` is additive on the Phase 0 Alembic chain. The `openai-agents`, `claude-agent-sdk` and `temporalio` APIs the RFC names exist as described. The Majors concern how those APIs are used and how the tests reach the acceptance criteria.

## Open items

- F1-F9 (Major) must be fixed or contested by the author. A re-check then runs in a new session (rule 6).
- F10-F31 (Nit) do not block.
- F2's skill-loading claim comes from the SDK source and was not confirmed by running the CLI. It should be verified in the first implementation PR, along with the Claude session restore the RFC already defers there.

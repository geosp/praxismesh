# PraxisMesh threat model

A living document (plan Phase 1 task 6, rev 2.10). It covers what exists today. Every later phase that adds a trust boundary extends it. Each control names the test that checks it; each accepted risk names the phase that closes it.

**Covers:** Phase 1 at the merge of issue #44's last PR: the local Compose stack, `TaskWorkflow`, the template workers with the `openai_agents` harness, the sample MCP server and the CLI. **Deployment assumption:** single organization, single machine, ports bound to `127.0.0.1` (plan §2, tenancy default).

## Assets

| Asset | Where it lives |
|---|---|
| Workspace contents and task outputs | Worker scratch (tmpfs), checkpoint snapshots and artifacts in SeaweedFS |
| Conversation sessions | `agent_sessions`, `agent_messages` in the `praxismesh` database |
| Task, attempt, checkpoint and idempotency records | `praxismesh` database |
| Model access | The model endpoint (`VLLM_BASE_URL`, `VLLM_API_KEY`) |
| Credentials | `infra/.env`: database passwords, S3 keys, the sample server's database URL |
| Capability definitions | `registry/` (templates, profiles, MCP catalog, skills), pinned by `registry/registry.lock` |

## Trust boundaries

| # | Boundary | Crossed by |
|---|---|---|
| B1 | Client to platform | A task request through the CLI |
| B2 | Workflow to worker | `TurnInput` on `tpl.{template}` |
| B3 | Model output to tools | Tool calls the model requests |
| B4 | Worker to command execution | `run_command` |
| B5 | Worker to MCP servers | MCP tool calls, and the environment the server gets |
| B6 | Worker to database and object storage | Repositories, `BlobStore` |
| B7 | Platform to third-party services | Trace export (closed), model endpoint |

## Actors

- **Hostile prompt:** a task request, or text inside one, that tries to make the agent exceed its template's capabilities.
- **Hostile file content:** an input file or tool output carrying instructions (prompt injection).
- **Compromised or misbehaving worker:** a worker that was lost and comes back, or runs another template version.
- **Over-privileged profile:** a profile file that tries to grant capabilities.

## Controls

| # | Control | Boundary | Test |
|---|---|---|---|
| C1 | Capabilities (model, MCP servers, skills, commands) come only from the template; requests carrying capability fields are rejected by name before any Workflow starts | B1 | `tests/test_registry.py::test_request_rejects_capability_fields`, `tests/test_submit.py::test_forbidden_skill_or_tool_rejected_before_start` |
| C2 | Profiles have no capability fields; unknown fields are rejected | B1 | `tests/test_registry.py::test_profile_rejects_capability_fields` |
| C3 | Template content is pinned by `registry.lock`; a changed file without a new version fails to load; a worker refuses a turn for another template hash | B2 | `test_changed_template_without_version_bump`, `test_changed_prompt_without_version_bump`, `tests/integration/test_harness_activity.py::test_template_refusals_are_not_attempts` |
| C4 | Only the template's tools are exposed; a call to anything else returns an error to the model and is logged, without failing the turn | B3 | `tests/test_runner_conformance.py::test_runner_conformance`, `::test_prohibited_tool_returns_error` |
| C5 | `run_command` runs only programs in the template's `cli_tools`, in the workspace, with a minimal environment (no credentials), a timeout and capped output | B4 | `test_prohibited_tool_returns_error`, `test_command_env_has_no_credentials` |
| C6 | File tools cannot leave the workspace; skills are read-only; symlinks are never archived | B3, B4 | `tests/test_workspace.py::test_skills_are_excluded_and_read_only`, `::test_symlinks_are_not_archived` |
| C7 | MCP servers get only their literal `env`, `PRAXIS_TASK_ID` and the secrets the template grants them | B5 | `tests/test_registry.py::test_mcp_secret_must_be_granted_by_template` |
| C8 | Side-effecting MCP tools are idempotent per task; a reused task ID is rejected permanently | B5, B1 | `tests/integration/test_recovery.py::test_side_effect_not_repeated_after_crash`, `tests/integration/test_task_e2e.py::test_duplicate_task_id_rejected` |
| C9 | A superseded attempt writes nothing; restore uses the newest checkpoint | B2 | `test_harness_activity.py::test_superseded_attempt_writes_nothing`, `test_recovery.py::test_superseded_attempt_comes_back_and_writes_nothing` |
| C10 | No secrets in Temporal history: Workflow inputs carry IDs and `BlobRef`s; instructions and inputs are stored as blobs | B2 | `tests/test_submit.py::test_prepare_task`; replay fixture `tests/fixtures/task_workflow_history.json` |
| C11 | The harness SDK's tracing to a third-party backend is off; traces go only to the configured OTLP endpoint | B7 | `tests/test_observability.py::test_no_sdk_trace_export` |
| C12 | Recorded test fixtures carry no workstation hostname | — | Fixed worker and client identities in `tests/test_task_workflow.py` and `tests/support/stack.py` |
| C13 | Containers run as a non-root user; ports bind to `127.0.0.1`; no image is published | B6 | `workers/Dockerfile`, `infra/docker-compose.yml` (reviewed, not tested) |

## Accepted risks

| Risk | Why accepted now | Closed by |
|---|---|---|
| R1 | No sandbox for untrusted code: `run_command` can run any binary through a pipe, and runs as the worker's user, which can read the worker's own process environment (for example `/proc/1/environ`) | The sample tasks need a shell; single-user local deployment | Phase 5 sandbox ADR (plan §2) |
| R2 | No network egress control for commands, MCP servers or the model client | Same | Phase 5 |
| R3 | Prompt injection from file contents or tool output can steer the agent within its template's capabilities | Capabilities are bounded by the template (C1-C7) | Partly Phase 5 (sandbox), partly later review stages |
| R4 | Identical side-effect calls in one task collapse into one (by design of the idempotency key) | Matches the sample skill; real tools add a sequence argument | Per tool, when real tools arrive |
| R5 | An attempt that outlives its heartbeat can finish one in-flight model call and its tool calls before it is cancelled or fences itself; late session writes can land in the shared session | Idempotency keys cover side effects; restore truncates to the checkpoint | Revisit if recovery tests show drift |
| R6 | `run_command` effects outside the workspace (for example `git` against a remote) are not idempotent | No remote or credentials reach commands (C5) | Phase 5 |
| R7 | No authentication on Temporal, the UI, S3 or the database beyond passwords in `infra/.env`; no TLS | Local, single-user, `127.0.0.1` only | Phase 7 (deployment) and Phase 9 (security hardening) |

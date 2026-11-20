# PraxisMesh threat model

A living document (plan Phase 1 task 6, rev 2.10). It covers what exists today. Every later phase that adds a trust boundary extends it. Each control names the test that checks it; each accepted risk names the phase that closes it.

**Covers:** Phase 1 at the merge of issue #44's last PR: the local Compose stack, `TaskWorkflow`, the template workers with the `openai_agents` harness, the sample MCP server and the CLI. Phase 2 (issue #79) adds the comms MCP server, its database role `praxis_comms` and messages between tasks (B8, B9, C14-C17, R8). **Deployment assumption:** single organization, single machine, ports bound to `127.0.0.1` (plan §2, tenancy default).

## Assets

| Asset | Where it lives |
|---|---|
| Workspace contents and task outputs | Worker scratch (tmpfs), checkpoint snapshots and artifacts in SeaweedFS |
| Conversation sessions | `agent_sessions`, `agent_messages` in the `praxismesh` database |
| Task, attempt, checkpoint and idempotency records | `praxismesh` database |
| Messages between tasks, wake rows and the inbox state | `task_messages`, `message_wakes`, `task_inbox` in the `praxismesh` database |
| Model access | The model endpoint (`VLLM_BASE_URL`, `VLLM_API_KEY`) |
| Credentials | `infra/.env`: database passwords, S3 keys, the sample server's database URL, the comms server's database URL (`PRAXIS_COMMS_DB_URL`, role `praxis_comms`) |
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
| B8 | Comms MCP server to database | `comms_mcp` writes and reads the message tables as `praxis_comms`. It runs as a stdio child of the worker, as the same user in the same container, so the separate process is not a credential boundary |
| B9 | Task to task | A message body one task sends, which another task's woken turn reads |

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
| C4 | Only the template's tools are exposed, and MCP tools only as far as the catalog entry's `tools_allowed`; a call to anything else returns an error to the model and is logged with the task and attempt IDs, without failing the turn | B3 | `tests/test_runner_conformance.py::test_runner_conformance`, `::test_prohibited_tool_returns_error`, `::test_mcp_tools_allowed_filter`, `::test_refusals_are_logged_with_ids` |
| C5 | `run_command` checks **only the first word** of a command against the template's `cli_tools`, then runs the whole string with `sh -c` in the workspace, with a minimal environment (no credentials), a 60 s timeout and capped output. It does **not** confine what the command does: anything after an allowed first word runs (pipes, `;`, and `sh -c …` itself while `sh` is listed), including reading files outside the workspace. That is accepted risk R1 | B4 | `test_prohibited_tool_returns_error` (first word), `test_command_env_has_no_credentials` (environment), `test_command_runs_in_workspace`, `test_command_timeout_is_enforced`, `test_command_output_is_capped` |
| C6 | The file tools (`read_file`, `write_file`, `list_files`) cannot leave the workspace: `..`, absolute paths and symlinks pointing outside are refused; skills are read-only; snapshots never archive symlinks | B3 | `tests/test_runner_conformance.py::test_file_tools_stay_in_the_workspace`, `tests/test_workspace.py::test_skills_are_excluded_and_read_only`, `::test_symlinks_are_not_archived` |
| C7 | Praxis grants an MCP server `PATH`, `LANG`, its literal `env`, only the secrets its template names, and the worker-set `PRAXIS_TASK_ID`, `PRAXIS_TURN`, `PRAXIS_ATTEMPT` and `PRAXIS_MAX_ASK_WAIT`. The worker-set variables are applied last, and the loader refuses a catalog entry that names one in `env` or `secret_env`, so no entry can replace the attempt's identity. The MCP SDK also inherits its platform allow-list; on the Phase 1 POSIX workers that is `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM` and `USER` when set. No other worker variables are inherited | B5 | `tests/test_runner_conformance.py::test_mcp_server_env_is_exactly_what_is_granted`, `::test_mcp_subprocess_env_is_granted_plus_sdk_defaults`, `::test_worker_set_variables_win_over_a_catalog_entry`, `tests/test_registry.py::test_mcp_secret_must_be_granted_by_template`, `::test_mcp_server_may_not_set_the_worker_set_variables` |
| C8 | Side-effecting MCP tools are idempotent per task; a reused task ID is rejected permanently | B5, B1 | `tests/integration/test_recovery.py::test_side_effect_not_repeated_after_crash`, `tests/integration/test_task_e2e.py::test_duplicate_task_id_rejected` |
| C9 | A superseded attempt writes nothing; restore uses the newest checkpoint | B2 | `test_harness_activity.py::test_superseded_attempt_writes_nothing`, `test_recovery.py::test_superseded_attempt_comes_back_and_writes_nothing` |
| C10 | No secrets in Temporal history: Workflow inputs carry IDs and `BlobRef`s; instructions and inputs are stored as blobs | B2 | `tests/test_submit.py::test_prepare_task`; replay fixture `tests/fixtures/task_workflow_history.json` |
| C11 | The harness SDK's tracing to a third-party backend is off; traces go only to the configured OTLP endpoint | B7 | `tests/test_observability.py::test_no_sdk_trace_export` |
| C12 | Recorded test fixtures carry no workstation hostname | — | Fixed worker and client identities in `tests/test_task_workflow.py` and `tests/support/stack.py` |
| C13 | Containers run as a non-root user; ports bind to `127.0.0.1`; no image is published | B6 | `workers/Dockerfile`, `infra/docker-compose.yml` (reviewed, not tested) |
| C14 | `praxis_comms` may write only `task_messages` (`SELECT, INSERT, UPDATE`) and `message_wakes` (`SELECT, INSERT`), and read `tasks`, `task_attempts` and `task_inbox`; it has no other table grant of its own (`CONNECT`, `USAGE` on `public` and what `PUBLIC` may read). Granted by migration 0006 and `infra/db/roles.sh` | B8 | `tests/integration/test_comms_role.py::test_the_comms_role_writes_messages_and_reads_tasks`, `::test_the_comms_role_cannot_write_tasks` (checks `tasks` and `checkpoints`, not the full grant set) |
| C15 | A message reaches only tasks of the sender's request. A send to another request or an ended task, from an ended task, over 16,384 characters, a reply that is late, misaddressed or not to the asker, or a question that would close a wait cycle is refused, stored as a `rejected` row with its reason and returned to the model as a tool error (`MessageRepository`, ADR-0011) | B9 | `tests/integration/test_messages.py::test_messages_stay_inside_their_request_and_refusals_are_recorded`, `::test_an_ended_task_closes_its_messages_and_is_refused`, `::test_questions_never_wait_in_a_cycle`, `::test_a_reply_must_go_to_the_asker`, `tests/integration/test_comms_mcp.py::test_a_cross_request_send_is_refused`, `tests/integration/test_messaging_failures.py::test_a_cross_request_message_is_refused` |
| C16 | The sender is the calling attempt: `comms_mcp` takes the task, turn and attempt only from the worker-set variables (C7); no tool argument names the sender | B5, B9 | `tests/integration/test_comms_mcp.py::test_the_sender_is_always_the_calling_task` |
| C17 | Every message write from an attempt takes ADR-0007's fence with the request lock, so a superseded attempt cannot send; message bodies never enter a Temporal history (a claim returns IDs and counts) | B8, B2 | `tests/integration/test_messages.py::test_a_stale_attempt_cannot_send`, `::test_the_claim_inbox_activity` |

## Accepted risks

| Risk | Why accepted now | Closed by |
|---|---|---|
| R1 | No sandbox for untrusted code: `run_command` only checks a command's first word (C5), so with `sh` allowed, any command runs; it runs as the worker's user and can read files outside the workspace, including the worker's own process environment (for example `/proc/1/environ`) | The sample tasks need a shell; single-user local deployment | Phase 5 sandbox ADR (plan §2) |
| R2 | No network egress control for commands, MCP servers or the model client | Same | Phase 5 |
| R3 | Prompt injection from file contents, tool output or a message from another task of the request can steer the agent within its template's capabilities | Capabilities are bounded by the template (C1-C7) | Partly Phase 5 (sandbox), partly later review stages |
| R4 | Identical side-effect calls in one task collapse into one (by design of the idempotency key) | Matches the sample skill; real tools add a sequence argument | Per tool, when real tools arrive |
| R5 | An attempt that outlives its heartbeat can finish one in-flight model call and its tool calls before it is cancelled or fences itself; late session writes can land in the shared session | Idempotency keys cover side effects; restore truncates to the checkpoint | Revisit if recovery tests show drift |
| R6 | `run_command` effects outside the workspace (for example `git` against a remote) are not idempotent | No remote or credentials reach commands (C5) | Phase 5 |
| R7 | No authentication on Temporal, the UI, S3 or the database beyond passwords in `infra/.env`; no TLS | Local, single-user, `127.0.0.1` only | Phase 7 (deployment) and Phase 9 (security hardening) |
| R8 | Request scope, sender identity and the fence (C15-C17) are enforced by the comms server's code, not by the database: `praxis_comms` may insert or update any message row. They hold only while the comms URL stays out of an agent's reach. On `openai_agents` it does not: `run_command` with `sh` or `python3` runs in the worker container and can read the worker's environment, which holds the comms URL and the application role's credentials (R1), so an agent can bypass all three there, and more. DSH runs commands in its isolated container. Every task of a request can message every other | Single-user local deployment; C14 still confines the role's writes to the message tables | Phase 5 sandbox (R1), or earlier row-level security on the message tables; finer scope and tenants by a new ADR (Phase 4) |

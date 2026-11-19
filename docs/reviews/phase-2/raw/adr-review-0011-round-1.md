Review of ADR-0011 at 34a29791335435fda86d205fedec273a8f0b0455. File: /home/geo/develop/praxismesh/docs/adr/0011-scope-agent-messaging-to-the-request.md. I made no changes.

## What checks out

These statements match the code:

- **Refusals.** `MessageRepository._refusal`, `_question_for_reply` and the cycle check in `ask` store a `rejected` row with its reason (`_reject`). See /home/geo/develop/praxismesh/common/persistence/messages.py:110-180 and :377-436. The server turns a refusal into an MCP tool error (`raise ToolError(f"refused: ...")`), at /home/geo/develop/praxismesh/comms_mcp/server.py:64-66.
- **Identity.** `comms_mcp` reads `PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT` from its environment (server.py:49-57), and no tool takes a sender argument. `build_config` sets these after `**server.env`, so a registry entry cannot override them (/home/geo/develop/praxismesh/harness_activity/config.py:61-70). The attempt is Temporal's attempt number (`info.attempt`, activity.py:255, passed at :486-492). Both runners start servers from the same `config.mcp`: runner.py:278-289 and dsh/executor.py:79-87.
- **Fence.** `_enter` takes the task lock, then `NO_NEWER_ATTEMPT`, then the request lock (messages.py:357-365; fence.py:20-26).
- **Grants.** The ADR's list matches migration 0006 `GRANTS` (0006_task_messages.py:34-40) and /home/geo/develop/praxismesh/infra/db/roles.sh:21-31 exactly.
- **Registry entry.** /home/geo/develop/praxismesh/registry/mcp/comms.yaml matches, and both v2 templates grant `comms`.
- **Tests.** Every test named under Confirmation exists and checks roughly what is claimed (test_messages.py:71, 157, 173, 196; test_comms_mcp.py:109, 117; test_comms_role.py:29, 50; test_messaging_failures.py:112).
- **Links.** Both anchors resolve (notes.md:33, overview.md:241). Status is `proposed`, and the ADR is listed in docs/adr/README.md.
- **Design §4.4.** No contradiction ("a scoped service/client").

## Findings

**F1 · Major · Decision outcome › Consequences, first "Good" bullet, and the `sh` "Bad" bullet: the guarantees are overstated.**

The bullet says a prompt-injected agent "can reach only the tasks of its own request, cannot forge a sender, and cannot write any other table, whatever the server's code does." Only the last of the three is enforced by PostgreSQL. Request scope and sender identity are enforced in `MessageRepository` code (messages.py:357-392). The role has a plain `INSERT, UPDATE` on `task_messages` (0006:35) with no row-level restriction. Anyone holding the comms URL can therefore insert a row with any `sender_task` and `request_id`, or update any message, which skips scope, identity and the fence.

On `openai_agents` that URL is within reach:

- The `local-default` template grants `sh` (registry/templates/local-default.yaml:13).
- The worker container's environment holds `PRAXIS_COMMS_DB_URL`. It also holds `APP_DB_PASSWORD` and `PRAXIS_SAMPLE_DB_URL`, which is the app role (infra/docker-compose.yml:145, :152-153).
- Threat model R1 records that `sh` can read the worker's environment through `/proc/1/environ` (docs/security/threat-model.md:59).

So on `openai_agents` all three guarantees fail, and the "Bad" bullet's "The role's grants bound what that URL allows" is misleading: the same environment also exposes the full-access app credentials.

Suggested fix:
- Scope "whatever the server's code does" to table writes only.
- State that scope and identity depend on the server's code and on the URL staying secret.
- Say the guarantees hold on DSH only, until the Phase 5 sandbox (threat-model R1).

**F2 · Major · Considered options / Decision outcome: it bundles decisions.**

The title joins three choices with "and": request scope, identity from the worker, and a least-privilege role. The last option bullet itself combines two unrelated alternatives ("The server connects as the application role, or each runner builds the tools in-process"), and the ADR then rejects them separately. Each rejected option answers a different question, so "Chosen option" is not one choice among real alternatives. That breaks the rule "One decision per ADR. If several decisions are bundled, split them" (.agents/skills/docs-design/SKILL.md:35).

Fix: either split the ADR (scope and identity in one, the server and role in another), or recast it as a single decision about how the comms tools are confined, with each option a complete alternative.

**F3 · Major · Decision outcome › Rejected, "Tools built into each runner": the code contradicts the reason given.**

The ADR rejects this option "because the two runners would carry two copies of the same tools and checks, which could drift apart." The repository already shares tool bodies across runners: "Tool bodies, shared by every runner (DSH migration plan D4). The openai_agents wrappers below and the DSH executor call these" (harness_activity/tools.py:157-159). The checks would sit in the shared `MessageRepository` either way.

Plan D13 gives the same reason ("two copies"), so the plan supports it, but the code does not. Give the reasons that actually separate the options, for example:
- a separate process can hold the `praxis_comms` credentials apart from the worker's app-role engine;
- templates grant it through the registry like any MCP server;
- or say plainly that the cost is only per-runner wrappers.

## Nits

- **N1 · Confirmation.** test_comms_role.py checks two denials only (`UPDATE tasks`, `SELECT checkpoints`). A future grant on another table would pass unnoticed; asserting the role's full grant set (e.g. `information_schema.role_table_grants`) would actually confirm "no other table grant".
- **N2 · Confirmation.** The claim "set by the worker for each attempt" on both runners has a test the ADR does not cite: tests/test_runner_conformance.py:496-522 (and :525-567).
- **N3 · As built, first bullet.** The list of refusals is incomplete against the code and R11/R25: a send from an ended sender (messages.py:387-388), a reply to a closed or expired question (:409-414), and an oversized body (:380-381) are also refused and stored as `rejected`.
- **N4 · As built, second bullet.** "The attempt is ADR-0007's fence key" is imprecise: the fence key is (turn, attempt) (fence.py:23-26).

Verdict: changes-requested

Review of ADR-0011 (docs/adr/0011-scope-agent-messaging-to-the-request.md) at d395bbd15ff72d83b5bc551d8eadf378f1fc1cf7. Read-only; no files changed.

Most of the ADR matches the code. I found one Major and five Nits.

**What I checked and found accurate**
- **Refusals.** Every refusal listed under "As built" exists. Each is stored through `_reject` as a `rejected` row with its reason and returned to the model as `ToolError("refused: ...")`.
  - Evidence: `common/persistence/messages.py:377-393` (body over 16,384 characters, sender ended, other request, recipient ended), `:395-416` (question closed or not addressed to the replier, reply not sent to the asker), `:163-167` (cycle), `:484-501` (`_reject`); `comms_mcp/server.py:64-66`.
  - A superseded attempt raises `FenceRejected` and nothing is stored (`messages.py:357-365`, `server.py:88-89`).
- **Identity.** `comms_mcp` reads only `PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT` (`server.py:49-57`), and no tool takes a sender.
  - They are set in `harness_activity/config.py:62-71` after `**server.env`, with the Temporal attempt number (`harness_activity/activity.py:486-492`).
  - Both runners pass this env to their stdio servers (`harness_activity/runner.py:281`, `harness_activity/dsh/executor.py:82`).
  - The fence key is ADR-0007's (turn, attempt) (`common/persistence/fence.py:23-26`).
- **Role and grants.** They match exactly: `common/persistence/migrations/versions/0006_task_messages.py:34-40` and `infra/db/roles.sh:21-31`.
- **Registry and templates.**
  - `registry/mcp/comms.yaml` has `secret_env: [PRAXIS_COMMS_DB_URL]`.
  - Both templates list `comms` and `PRAXIS_COMMS_DB_URL` (`registry/templates/local-default.yaml:11,21`, `local-dsh.yaml:11,21`).
- **Reach.** The worker env holds `PRAXIS_COMMS_DB_URL` and the app-role credentials (`infra/docker-compose.yml:143,151-153`). DSH containers have `network_mode: none` (`:191`). Threat model R1 (`docs/security/threat-model.md:59`) covers `/proc/1/environ`.
- **Provisioning.** `PRAXIS_COMMS_DB_PASSWORD` and `make db-roles` exist (`Makefile:105`, `infra/.env.example:56-57`).
- **Confirmation.** All five test files exist and mostly check what the ADR says:
  - `test_messages.py:71,157,173,196`
  - `test_comms_mcp.py:109,117`
  - `test_comms_role.py:29,50`
  - `test_messaging_failures.py:112`
- **Links.** All resolve, including the anchors `notes.md#d6--messages-wake-rows-and-the-comms-role` and `overview.md#phase-2-messaging-...`.
- **Front matter.** Status is `proposed`, the date is an ISO date, and `supersedes` is null.
- **Consistency.** I found no contradiction with design §4.4 (`docs/roadmap/design-decisions.md:34`), ADR-0007, ADR-0010 or threat model R1.

**Findings**

1. **Major. Decision outcome, the reason for the choice and "Rejected: Tools built into each runner".** The rationale for a separate process doesn't hold up, and the strongest alternative is missing.
   - **The claim.** The ADR says the chosen option wins because "a separate process can hold a database role that PostgreSQL limits to the message tables". It rejects built-in tools "because they would write with the worker's application role".
   - **Why that's not a reason.** Writing with the app role is how the option was defined (Considered options: "writing through the worker's own (application-role) database connection"). A role is tied to a connection, not a process. Built-in tools could open their own `praxis_comms` engine inside the worker and get exactly the same PostgreSQL confinement.
   - **The process boundary adds no credential isolation here.** `comms_mcp` runs as a stdio child of the worker, with the same UID in the same container (`runner.py:281`, `dsh/executor.py:82`). So code execution in it can read the worker's `/proc/1/environ` (app role, S3 keys), just as threat model R1 says commands can.
   - **The app role already handles messages.** The worker already runs `MessageRepository` paths with the app role: `blocking_finish` and `read_claimed` (`harness_activity/activity.py:586,626`), and `claim` and `end_task` (`orchestrator/activities.py:117,150`).
   - **What's missing.** The one option that would test the decision, built-in tools with a `praxis_comms` connection, isn't considered. The decisive reason given doesn't separate the chosen option from it.
   - **Fix.** Add that option and say why it lost. The facts the ADR already states would serve: registry grants per template like any MCP server, and one implementation reached by both runners through MCP without changes to either runner. Alternatively, reword the rationale so the credential argument is "the tools' own connection uses a confined role" rather than "a separate process".

2. **Nit. "As built", second bullet.** "so a registry entry cannot override them" is not strictly true. `config.py:72-73` applies `secret_env` after the identity keys, so an entry that lists `PRAXIS_TASK_ID` in `secret_env` (with a matching template `secret_refs`) overwrites it from the worker env. The loader does not restrict these names (`registry/loader.py:178`).

3. **Nit. Confirmation.** The `test_runner_conformance.py` claim is overstated.
   - The per-runner subprocess test (`tests/test_runner_conformance.py:525-569`) starts a hand-built test server with only `PRAXIS_TASK_ID`, not the template's servers. It doesn't check turn or attempt.
   - Turn and attempt are checked only in `build_config` (`:495-523`), which is runner-independent.

4. **Nit. Consequences, fourth bullet ("the `sh` tool").** `sh` is not a tool. The tool is `run_command` with `sh` and `python3` allowed (`registry/templates/local-default.yaml:13`), and either one can read the worker env.

5. **Nit. Decision outcome, "Rejected".** The ADR drops plan D13's stated reason, "built-in tools in each runner (two copies)" (`plan.md` D13), without saying the plan's reason is superseded. The plan still records "two copies".

6. **Nit. Consequences, Follow-up.** The threat model has no entry for the new `comms_mcp` → database boundary or the `praxis_comms` role (`docs/security/threat-model.md` has no "comms" anywhere), and the ADR doesn't list updating it as follow-up.

Verdict: changes-requested

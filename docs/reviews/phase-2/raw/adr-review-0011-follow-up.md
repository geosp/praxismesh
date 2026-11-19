Targeted follow-up review of ADR-0011 at 95758e9 (`/home/geo/develop/praxismesh/docs/adr/0011-scope-agent-messaging-to-the-request.md`). This was a read-only review and I changed no files. All six items from round 2 are resolved, and only two small nits are new.

**1. (Major) Rationale and the missing option: resolved.**
- **The missing option is now listed.** The fifth Considered option, at lines 40-41, is "The tools built into each runner, each with its own `praxis_comms` connection…".
- **The reason for the choice is restated.** It now says "the tools' own database connection uses a role that PostgreSQL limits" (line 47). That replaces the claim about a separate process.
- **The new option's rejection admits the confinement would be equal.** Lines 57-60 say it "would confine their writes just as well (a role belongs to a connection, not a process)". They then separate the two options on registry grant and on whether the runners need changes.
- **The text on the process is accurate.** Lines 64-65 say the separate process "is not a credential boundary".
- **The stated reasons are true:**
  - Templates grant MCP servers through `mcp_servers`, which the loader checks along with their `secret_refs` (`registry/loader.py:175-181`). `local-default.yaml` lists `mcp_servers: [sample-shop, comms]`, and `registry/mcp/comms.yaml` declares the server.
  - Both runners loop over `config.mcp` in the same way, with no per-server code (`harness_activity/runner.py:275-295`, `harness_activity/dsh/executor.py:79`). `config.py:58-80` builds every stdio server the same way.
  - These facts do separate the chosen option from the built-in-tools-with-own-role alternative.

**2. `secret_env` wording: resolved.**
- Lines 72-74 say an entry "that named them in `secret_env` could [override them], and the loader does not forbid it."
- This matches the code. `config.py` sets the identity keys after `**server.env` and then applies `secret_env` after them. `loader.py:178` only checks `secret_env` against `secret_refs` and has no deny-list.

**3. Confirmation, `tests/test_runner_conformance.py`: resolved.**
- **The ADR now splits the two claims.** The config gives task, turn and attempt, and the runners start an MCP server with the task ID.
- **The config claim matches the test.** `build_config` asserts turn and attempt ("3", "2"), and the comms-versus-shop grant split, at `tests/test_runner_conformance.py:495-523`.
- **The runner claim matches the test.** The subprocess test checks only `PRAXIS_TASK_ID` (`:525-569`). It runs under the autouse runner fixture at `:72`, which covers both runners, with DSH only in the integration run.

**4. `run_command` wording: resolved.**
- Lines 90-91 now say "`run_command` (with `sh` or `python3` allowed by the `local-default` template)".
- This matches `cli_tools: [python3, wc, git, sh]` in `registry/templates/local-default.yaml`.

**5. D13 "two copies": resolved.**
- Lines 60-62 say that reason does not hold and that this ADR replaces it. The plan still reads "Rejected: built-in tools in each runner (two copies)" at `plan.md:293`.
- The supporting claim is true. Both runners use `build_tools` from `harness_activity/tools.py` (`runner.py:40`, `dsh/executor.py:33`), and `dsh/runner.py:43` imports `tools as tool_bodies`.

**6. Follow-up items: resolved.**
- Lines 102-104 add a threat-model entry for the comms server's database boundary and the `praxis_comms` role.
- They also add an optional loader refusal of `PRAXIS_TASK_ID`, `PRAXIS_TURN` and `PRAXIS_ATTEMPT` in `secret_env`.

**New issues in the changed text**
- **Nit, Decision outcome › Rejected, built-in tools on their own `praxis_comms` connection (line 59).** "granted outside the registry" is imprecise. Built-in tools could be gated by a template field, the way `cli_tools` already gates `run_command`. The accurate difference is that they would need a new template field, while an MCP server uses the existing `mcp_servers` grant.
- **Nit, Confirmation (line 111).** "gives every MCP server the attempt's task, turn and attempt" claims more than the test asserts. The test checks those values only on `sample-shop`; for `comms` it checks only the database URL grant. The code does give them to every server (`config.py:62-71`), so the statement about behaviour is true. Only the claim about what the test proves is stretched.

Verdict: accept

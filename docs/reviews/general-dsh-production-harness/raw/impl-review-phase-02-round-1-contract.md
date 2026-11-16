<!-- Verbatim subagent report (impl-review-phase-02-round-1-contract); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. -->

I reviewed phase 02 against R5–R18, D1–D10 and tasks 1.1–2.5, using diff 562733a..43798c7 at frozen commit 43798c7. I read the code and tests only and ran nothing.

The main path is in place and has tests: the seam (D1), the gateway ledger (R11), the barrier (D6), the fence (D10), the executor, the launcher isolation (R15, R10) and the pin check (R17). The problems are in the edge paths: what happens when a turn ends for good, a stop that arrives while the attempt is frozen, the step-limit stop, the final checkpoint, and how closely R18 matches the spike evidence.

## Promise map (where each promise is enforced, and the test that would fail without it)

| Promise | Enforced at | Test |
|---|---|---|
| R5 / D6 barrier, then commit | `harness_activity/dsh/gateway.py:236-237`, `harness_activity/dsh/barrier.py:50-76`, `harness_activity/activity.py:446-452` | `test_barrier_*` (unit), `test_worker_sigkill_reaps_attempt_and_replacement_recovers`, `test_dsh_resumes_and_charges_a_lost_request` |
| R6 / D10 fenced checkpoint and finish | `activity.py:410-435`, `:505-521`, `_runner_failed` `activity.py:421-433` | `test_stale_dsh_attempt_writes_no_checkpoint_outcome_or_artifact` (weak, see F6) |
| R7 no outcome from a stale attempt | `activity.py:486-535` | none that exercises a stale attempt that *finished* (F6) |
| R8 stop within 5 s | `harness_activity/dsh/runner.py:380-397`, `infra/dsh/launcher.py:242-251` | `test_deadline_stops_a_running_command_within_the_grace`, the cancel tests; the step limit is not covered (F3) |
| R9 forced stop is a failure | `harness_activity/dsh/policy.py:43-44` | `test_forced_stop_is_recorded_as_a_non_retryable_failure` |
| R10 worker death | `launcher.py:366-370` | `test_closed_connection_kills_the_attempt`, the SIGKILL test |
| R11 usage from the ledger | `gateway.py:292-301`, `activity.py:460-474` | `check_usage` in `test_dsh_outcomes.py`; `test_dsh_turn_through_the_activity` |
| R12 / R13 unknown usage and D9 charge | `common/persistence/repositories.py:498-536`, `activity.py:460-474` | `test_lost_requests_are_closed_and_counted_for_every_later_attempt`, the SIGKILL test; only when a later attempt runs (F1, F2) |
| R14 capabilities from the template only | `harness_activity/dsh/composition.py:21-99`, `gateway.py:228-233`, `harness_activity/dsh/executor.py:124` | `tests/test_dsh_composition.py`, `test_only_template_capabilities_reach_dsh` |
| R15 command isolation | `launcher.py:141-170`, `:202-227` | `test_attempt_isolation_and_stop` (`tests/integration/test_dsh_launcher.py`) |
| R16 events | `executor.py:170-176`, `gateway.py:302-308` | `test_dsh_turn_through_the_activity` |
| R17 pin check | `workers/main.py:892-902`, `harness_activity/dsh/pins.py` | `tests/test_worker_runner.py`, `tests/test_dsh_pins.py`, `test_tampered_runtime_is_reported_and_refused` |
| R18 spike outcome cases | the whole run path | `test_outcome_case` plus the separate lost-after-finish and cancel tests (F5) |

## Findings

**F1 · Major · R12, D7 · `orchestrator/workflow.py:46-59` and `:129-139` — a turn that fails for good loses `usage_known`.**
- **Where:** `failed_turn_usage` returns only tokens, inner turns and attempts. The `except ActivityError` branch never reads `usage_known` from the error details or the last heartbeat. `_runner_failed` and the NonRetryable path do put `usage_known=False` into those details (`activity.py:448`, `Progress` at `activity.py:116-117`).
- **Scenario:** attempt 1 is lost with a request in flight. Attempt 2 charges the D9 estimate, so its heartbeat base has `usage_known=False`. The endpoint then returns 400 (`HarnessInputError`, non-retryable), or the launcher force-stops the attempt.
- **Wrong outcome:** the TaskResult includes the 32768 + 2048 estimate in its tokens but says `usage_known = true`.
- **Test that would expose it:** a `test_dsh_outcomes` case with a lost or unknown request followed by a non-retryable fault, asserting `result.usage_known is False`.

**F2 · Major · R12, R13, D9 · `activity.py:409-433`, `:228-249`, `:453-474` — the D9 charge only happens if a later attempt of the turn runs.**
- **Case (a), cancel:** the attempt is cancelled with a request in flight (the R18 `cancel` case). `_runner_failed` writes the row with non-null tokens and `usage_known=used.usage_known` (still True), and no attempt 2 ever runs `close_unknown`. Result: the row and the TaskResult show the known tokens only, the unsettled ledger row is never charged, and `usage_known` stays true. The runner knows about it (`ledger.settled()["unknown_usage"]`, `runner.py:419`) but does not pass it on.
- **Case (b), turn ends without another attempt:** the last real attempt is SIGKILLed mid-request. The next Activity attempt raises `AttemptsExhausted` before `_open` (`activity.py:230-231`); a schedule_to_close expiry is the same. The lost row keeps `tokens_in = 0`, the server default (`0003_phase1_tables.py:68`), with `usage_known = true`, and the in-flight request is never charged. That is the "stored as 0" outcome R12 forbids.
- **Case (c), lost between requests:** an attempt is SIGKILLed between requests with every ledger row settled. `start()` marks its row `lost` with tokens 0 and `usage_known` true, although the ledger shows it spent tokens. This is my reading of "never as 0", so rate it as you see fit.
- **Test:** the workflow `cancel` test should assert the attempt row is `(None, None, False)` and `result.usage_known is False`. It currently asserts only `rows[0][2] in ("cancelled","failed")` (`test_dsh_outcomes.py:362`).

**F3 · Major · R8, R9 · `infra/dsh/launcher.py:242-251`, `runner.py:385-397`, `barrier.py:64-73` — a stop that arrives while the barrier holds the freeze becomes a non-retryable `DshForcedStop`.**
- **Mechanism:** `Attempt.stop` sends SIGTERM to the runtime without thawing the cgroup. A frozen process cannot handle the signal, so `wait(grace)` times out and the stop counts as not cooperative. The barrier's `thaw` is queued behind `stop` on the same serial connection and then fails ("open an attempt first").
- **Scenario:** the turn deadline, or a Temporal cancel, fires while the barrier is uploading the workspace and session blobs.
- **Wrong outcome:** `policy.py:43` returns `("DshForcedStop", False)`, so a retryable deadline fails the turn for good. The runtime never had a chance to exit within the 5 s grace.
- **Test:** a stub `before_model_call` that sleeps while frozen, with the deadline set to fire inside it; expect `DshTurnDeadline` and retryable.

**F4 · Major · R8 · `runner.py:380-391`, `gateway.py:238-240` — no enforcement of "exit within 5 s of a step limit".**
- **Mechanism:** a step-limit or token-budget denial only returns 429 to DSH. The poll loop stops the attempt only on abort, thaw failure or the deadline, so the 5 s bound after a step limit depends entirely on DSH quitting by itself.
- **Scenario:** a DSH build that retries or hangs after a 429 keeps running until the turn deadline (minutes).
- **Test gap:** the `inner-limit` case asserts outcomes only, not timing. A test should measure the time from the denial to the process exit (under 5 s) and then check a clean 10 s window.

**F5 · Major · R18 · `tests/integration/test_dsh_outcomes.py:103-155`, `:321` — several cases do not reproduce `docs/spikes/dsh-phase02-r2-evidence.json`.**
- **How the test checks:** it never loads the evidence file; it hard-codes its own expectations.
- **The differences:** the spike recorded `inner_turns = 1` for retry-model, retry-protocol, retry-infrastructure and deadline, and `0` for lost-after-finish. The tests expect `2, 2, 2, 2` and `1`. They also expect `usage_known = false` plus the D9 charge for retry-protocol, retry-infrastructure and deadline, where the spike reports exact tokens.
- **Where it is justified:** only in the test docstring ("by decision"). D9 covers the token charge, but no plan decision or decision-log entry covers inner turns accumulating across attempts. The cancel case has no TaskResult check at all.
- **Remedy:** either record the deviations in the plan or decision log, or derive the expectations from the evidence file.

**F6 · Major (test observability) · R6, R7 · `test_dsh_outcomes.py:580-673`.**
- **What the test does:** it never asserts that worker A actually tried a write and was rejected. It sleeps 6 s and compares checkpoint counts.
- **Why it can pass vacuously:** after SIGCONT, worker A's step-1 checkpoint hits the `newer_attempt_exists` early exit (`activity.py:448-449`), or A is simply cancelled by Temporal. Either way the test passes even with `_NO_NEWER_ATTEMPT` removed from `insert_fenced`.
- **R7 gap:** the stale attempt never reaches `finish_task`, so the R7 Given ("a stale attempt that finished, when it publishes") is not exercised on the DSH path.
- **Setup that would observe it:** stub `newer_attempt_exists` to return False, let the stale attempt finish, and assert `FenceRejected` was raised at `insert_fenced`, `assert_current` and the fenced finish.

**F7 · Major · R5, D6 · `runner.py:401-403`, `activity.py:468-476` — a failed freeze before the final checkpoint is ignored.**
- **Mechanism:** after the runtime exits, `freeze` errors are suppressed, and a reply of `ok: false` just leaves `attempt.frozen = False`. `checkpoint(finish)` and the artifact read then go ahead anyway.
- **Scenario:** a backgrounded command, which stays in the cgroup until stop, is still writing `answer.txt` when the freeze times out after 2 s (`launcher.py:229-237`).
- **Wrong outcome:** a torn workspace is committed and published as a `done` artifact. D6 says a failed barrier must give "no checkpoint" and be retryable.
- **Test:** make `freeze` return false and assert a `RunnerFailure` and no finish checkpoint.

**F8 · Nit · D9, R13 · `gateway.py:123-142` — the charge assumes limits the gateway never enforces.**
- **Mechanism:** the D9 estimate assumes at most 2048 output tokens and at most `context_window` input tokens per request. `to_model` forwards DSH's `max_tokens` as-is and does not check the prompt size.
- **Scenario:** the provider omits or raises `max_tokens`. An unobserved request that generated more than 2048 tokens is then charged only 2048.
- **Why Nit:** DSH is configured with 2048 (`driver.py:120`, `composition.py:67,75`), but nothing checks that it honours it.

**F9 · Nit · D9 text · `docs/plans/2026-11-15-dsh-production-harness/plan.md` (D9) and `docs/roadmap/decision-log.md:95` — plan and log disagree with the code.**
- **What they say:** both still say the charge is "`context_window + max_tokens`", with `max_tokens` from the template.
- **What changed:** this diff amended only `notes.md#d9`, to the 2048-token composition cap. The template has no `max_tokens` field.

**F10 · Nit · D3 · `notes.md`, `infra/docker-compose.yml` — `apparmor:unconfined` is not in the decision log.**
- **What changed:** it loosens the DSH container's confinement and was added to the notes.md#d3 settings and to Compose.
- **Why it matters:** AGENTS.md requires constraint changes to go in the decision log, and none was added for this.

**F11 · Nit · D4 · `infra/dsh/Dockerfile` — the image is not limited to the granted `cli_tools`.**
- **The rule:** D4 says "the image installs only the granted `cli_tools`".
- **What the image has:** the whole `python:3.11-slim` userland (`unshare`, `mount`, `perl`, coreutils and so on).
- **Why Nit:** with `sh` and `python3` granted, the first-word check (`tools.py:152-158`) already lets any binary run. The real boundary is the UID, the dropped capabilities, seccomp and the mount namespace.

**F12 · Nit · R14 · `composition.py`, `test_dsh_composition.py:51-56` — skill discovery is off only because no skill plugin is present.**
- **What is missing:** `includeDefaultRoots: false` from notes.md#r14 is never set. Discovery is off only because no `dsh-skill*` plugin is inserted.
- **The risk:** if a future `sdk-minimal` profile includes a skill plugin, the unit test still passes.
- **Live test gap:** the live test plants poison skill files in the workspace only, not in HOME (`tmp/`).

**F13 · Nit · R15 test observability · `test_dsh_outcomes.py:397-428` — the outcomes-level isolation test is vacuous.**
- **Other attempt's secret:** it is written to `other-task/1/1/workspace/secret.txt`, but the probe only globs `home/sessions/*`. The "no secret" assert can never fail, and the `ls -A /attempts` output is never asserted.
- **Session-file read:** the check looks for the file name `session.v4` in the output. Readable session contents would not contain that string.
- **Why Nit:** the launcher test (`test_dsh_launcher.py:54-55`, `:134-135`) covers both properly.

**F14 · Nit · R16 · `gateway.py:310-319`, `executor.py:124-131` — refused tool calls produce incomplete events.**
- **Gateway:** a model call to an ungranted tool emits no event.
- **Executor:** a refused call emits `tool_result` without a matching `tool_call`.

**F15 · Nit · R17 · `workers/main.py:892-902` — the pin check is narrow.**
- **When it runs:** only once, at worker start. A DSH container rebuilt or restarted afterwards is never re-checked.
- **What it covers:** the lock pins only the DSH distribution. `launcher.py`, `driver.py` and `mcp_bridge.py` are not pinned, so an old image whose launcher lacks the seccomp filter would still pass.

**F16 · Nit · R6, R13 · `gateway.py:236-243` — a stale attempt's first request is never fenced.**
- **Mechanism:** the first request of an attempt runs no barrier, so it is not fenced.
- **Scenario:** an attempt that becomes stale before its first request can still dispatch it, after the newer attempt has already computed its D9 charge.
- **Wrong outcome:** that spend is not charged unless yet another attempt runs.

**F17 · Nit · R11 · `executor.py:133` — tool calls can be lost.**
- **Mechanism:** tool-call counts live in memory and in heartbeats only, with no durable executor record.
- **Wrong outcome:** calls made between the last heartbeat and a worker SIGKILL are lost.

**F18 · Nit · R9 · `launcher.py:244-251` — "cooperative" ignores the rest of the cgroup.**
- **Mechanism:** `cooperative` only checks whether the runtime PID exited. A backgrounded command that needed `cgroup.kill` still counts as a cooperative stop.
- **Why Nit:** probably the intended reading, but you should decide.

**F19 · Nit · task 2.3 · `tests/test_runner_conformance.py` — the openai_agents conformance check got weaker.**
- **The task:** 2.3 says the conformance suite stays "unchanged for `openai_agents`".
- **What changed:** `instructions_seen` now joins `messages[0]` and `messages[1]` for every runner. A regression that moved the openai_agents instructions out of the system message would now pass.
- **Related:** DSH gets the trusted template instructions inside the user block, after a preamble that calls what follows "task as data" (`runner.py:65`, `:318`).

**F20 · Nit · task 1.1 · `test_dsh_launcher.py:162-166` — the reap-at-start test checks only trees.**
- **What it checks:** that a leftover tree is removed.
- **What it skips:** leftover processes and cgroups, which task 1.1 also requires the launcher to reap at start. It also runs a second launcher next to the first instead of restarting it.

**F21 · Nit · D7 · `0004_dsh_usage_and_sessions.py:70-71` — downgrade writes 0 for unknown usage.**
- **Mechanism:** downgrade rewrites NULL tokens to 0.
- **Why Nit:** acceptable because the plan does not support rolling back below D7.

Everything I referred to is under `<repo>`: `harness_activity/activity.py`, `harness_activity/dsh/{runner,gateway,executor,barrier,ledger,policy,composition,session,pins}.py`, `infra/dsh/{launcher,driver,pins}.py`, `infra/dsh/Dockerfile`, `infra/docker-compose.yml`, `orchestrator/workflow.py`, `common/persistence/repositories.py`, and `tests/integration/test_dsh_{outcomes,activity,launcher,capabilities}.py`.

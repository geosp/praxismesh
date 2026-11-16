<!-- Verbatim subagent report (impl-review-phase-02-round-1-scope); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. -->

## Scope review: phase 02 (DSH runner and worker pair), diff 562733a7..43798c7

I read the plan, the phase file, notes.md, the guidance files and the code at 43798c7. I ran only read-only git commands. Each property below is judged at the scope the plan promises (per request, per attempt, per turn, per task, per worker lifetime). Line numbers refer to files at 43798c7.

There are five Majors and nine Nits. The largest gaps:
- Usage that was never observed is reported as known whenever no retry follows.
- A deadline or cancel that lands during the barrier freeze turns a retryable stop into a non-retryable failure.

---

### Major 1: Unknown usage is never charged or flagged when no retry follows (R12, R13, D9)

**Where:**
- `harness_activity/activity.py:273-286` (`_runner_failed`)
- `harness_activity/activity.py:233` (the `AttemptsExhausted` check)
- `harness_activity/activity.py:314-317` (`close_unknown`, which runs only in `_open`)

**Scope mismatch:**
- The D9 charge and `usage_known = false` are applied only when the *next* attempt opens.
- The runner knows its own unsettled count when it fails (`ledger.settled()["unknown_usage"]`, passed to `classify`), but `_runner_failed` records `used = heartbeat.current()`. That value has no charge for this attempt's own unsettled rows and `usage_known=True`.
- `AttemptsExhausted` is raised before `_attempt` and `_open`, so the last real attempt's unknown rows are never charged.

**Failure scenarios:**
- **Cancel (the R18 `cancel` case):** a model request is held, the workflow is cancelled, and the attempt row becomes `cancelled` with numeric tokens and `usage_known = true`. The ledger still has an unsettled row. No later attempt exists to fix it.
- **Non-retryable failure:** a forced stop (`DshForcedStop`), `DshBlocked` or `DshCleanupFailure` while a request is in flight. Same result.
- **Five lost real attempts:** attempt 5 ends with an unsettled row and attempt 6 raises `AttemptsExhausted`. The failure details and the TaskResult exclude `context_window + 2048` for that request.

**Outcome:** R12 says unobserved usage is "never 0", and the plan says "Each unsettled request is charged the D9 estimate". In these cases the unobserved request is counted as 0, as known usage.

**Test that would expose it:** the cancel test (`test_dsh_outcomes.py::test_cancel_...`) only checks the row outcome. Add an assertion that the cancelled row has `tokens_in IS NULL` and `usage_known = false`, and that a task whose last real attempt left an unsettled row reports `usage_known = false` and the charge.

### Major 2: The workflow drops `usage_known` from a turn that failed for good (R12, D7)

**Where:**
- `orchestrator/workflow.py:46-59` (`failed_turn_usage` returns only tokens, inner turns and attempts)
- `orchestrator/workflow.py` `except ActivityError` branch: `usage_known` is updated only on the success path (`usage_known = usage_known and outcome.usage_known`)

**Failure scenario:**
1. Attempt 1 is lost with an unsettled request.
2. Attempt 2 charges it; its heartbeat base has `usage_known=False` and tokens that include the charge.
3. Attempt 2 then hits a non-retryable failure (for example `HarnessInputError` or `DshForcedStop`).
4. The ApplicationError details carry `usage_known: false`, and the heartbeat-timeout path carries it in `last_heartbeat_details`.
5. The workflow adds the charged tokens but completes the task with `TaskResult.usage_known = True`.

**Outcome:** the task-scope result says usage is exact while it holds a conservative estimate. D7 puts `usage_known` on `TaskResult` for exactly this purpose.

**Test that would expose it:** a workflow test where turn 1 fails non-retryably after a charged unknown request; assert `TaskResult.usage_known is False`. No current case combines `unknown > 0` with a failed status (`bad-request` has `unknown=0`).

### Major 3: A deadline or cancel during the barrier freeze becomes a non-retryable `DshForcedStop` (R8, R9, D6; the two mechanisms combined)

**Where:**
- `harness_activity/dsh/runner.py:387-397`: the poll loop keeps running while the gateway task holds the barrier.
- `harness_activity/dsh/barrier.py` `run_barrier`: freeze, then `capture_and_commit` (workspace pack, blob put, session capture, DB insert), then thaw.
- `infra/dsh/launcher.py:246-250`: `terminate()` followed by `wait(grace)`.
- `harness_activity/dsh/policy.py`: `cooperative_stop is False` is checked before `cancelled` and before the deadline.

**Failure scenario:**
1. The turn deadline passes (or the Activity is cancelled) while the barrier has the cgroup frozen and is uploading the checkpoint. A large workspace makes this window seconds long.
2. The poll loop calls `attempt.stop()`. The launcher sends SIGTERM to a *frozen* runtime, which cannot act on it.
3. `wait(timeout=5)` expires, so `cooperative=False`, and `destroy` then thaws and kills.
4. `classify` returns `("DshForcedStop", False)`.

**Outcome:**
- A deadline that should be `DshTurnDeadline` (retryable) fails the whole task.
- A cancel is recorded as `failed` instead of `cancelled`.
- The barrier's later `thaw` hits a launcher with no attempt.

Each mechanism is correct alone; together they break R9's meaning (a forced stop should mean the runtime ignored SIGTERM).

**Test that would expose it:** fire the deadline or cancel while the barrier is inside `capture_and_commit`, for example by pausing in a monkeypatched `insert_fenced`. Assert `DshTurnDeadline` (retryable) or a `cancelled` row. The existing deadline and cancel tests pause on request 0, the first request, which never runs a barrier (`test_dsh_outcomes.py` `deadline`, `test_cancel_...`; `test_dsh_activity.py` cancels while request 3 is in flight, after its barrier finished).

### Major 4: The ledger dispatch is unfenced, so a stale attempt's first request escapes the turn total (R11, D10)

**Where:**
- `harness_activity/dsh/ledger.py:91` (`store.dispatch` has no fence)
- `harness_activity/dsh/gateway.py:237-238` (the barrier, which has the only `newer_attempt_exists` and fence check, runs only when `self.dispatched` is nonzero)
- `harness_activity/activity.py:314` (`close_unknown` reads the ledger once, when the attempt opens)

**Scope mismatch:** the ledger is per turn, but the newer attempt takes one snapshot of it when it opens.

**Failure scenario:**
1. Attempt 1 is alive but stale, for example paused or partitioned while restoring a checkpoint, and has not yet sent its first model request.
2. Attempt 2 starts, runs `close_unknown` (finds nothing from attempt 1) and finishes the turn.
3. Attempt 1 resumes. Its first request has no barrier, so it is admitted and dispatched, and the endpoint spends tokens.
4. A `usage_ledger` row (attempt 1, settled with real tokens) appears after attempt 2 computed its totals.

**Outcome:** `TaskResult` tokens are lower than the ledger's settled totals, which contradicts R11 ("usage ... equals the ledger's settled totals"). The task budget is also exceeded unseen.

**Test that would expose it:** a variant of the stale test that SIGSTOPs worker A before its first request, lets B finish, then resumes A. Assert that no ledger row exists for attempt 1 after B's start, or that `ledger_totals == result tokens`.

### Major 5: The R17 pin is verified only once per worker process, not for the container it actually serves (R17)

**Where:**
- `workers/main.py:100` (`verify_launcher_report` runs once in `build_harness`)
- `harness_activity/dsh/runner.py` `open_attempt` (no digest check for each attempt or connection)
- `infra/docker-compose.yml` (`dsh-a` is `restart: unless-stopped`; `worker-dsh-a` only `depends_on` it with `service_started`)

**Failure scenario:**
1. The operator rebuilds or recreates `dsh-a` with a different DSH image (`docker compose up -d dsh-a` after a pin bump or a local edit).
2. `worker-dsh-a` is not recreated and keeps connecting to the new launcher's socket.
3. It serves `tpl.local-dsh` turns on a runtime whose digest no longer matches the registry lock.

**Outcome:** R17 says workers "serve a DSH queue only when the launcher's digests match". The Given/When names worker start, and that case is covered. The serving-time scope is not.

Rated Major because the mechanism exists to stop exactly a changed runtime. Rate it down if you read R17 strictly as a start-time check.

**Test that would expose it:** restart the container with a launcher that reports a different digest, then run a turn on the existing worker. The turn should be refused.

---

### Nit 1: Lost-attempt rows with only settled requests stay 0 and known (R11, R12)

**Where:** `common/persistence/repositories.py` `close_unknown` NULLs only the rows of attempts with an unsettled ledger row. `AttemptRepository.start` marks earlier rows `lost` without writing tokens.

**Scenario:** attempt 1 settles two requests (200 tokens) and the worker is SIGKILLed between requests. Its row reads `tokens_in = 0, usage_known = true`, although the ledger observed 200.

This is not "unobserved", so R12 is arguably met. It is still a 0 that is not true, and it is pre-existing Phase 1 behaviour.

### Nit 2: Attempt rows and the schema comment disagree (D7)

**Where:**
- `common/schemas/task.py` `ExecutionAttempt`: `tokens_in: int | None = 0  # None when usage_known is false (D7)`
- `harness_activity/activity.py` `_finish`: writes numeric cumulative tokens with `usage_known=False`
- The worker-SIGKILL test asserts `(2, result.tokens_in, result.tokens_out, False)`

Either the comment or the write is wrong. The engineer should pick one rule.

### Nit 3: The step-limit stop is not bounded by the 5 s grace (R8)

**Where:** `harness_activity/dsh/gateway.py`: "model-step limit", "token budget" and "explicit completion" denials return 429 without setting `abort`. `runner.py:383-390` then waits until the runtime exits by itself or `context.deadline` passes.

R8 names the step limit next to deadline and cancel. Here it relies on DSH exiting after a 429 (`maxRetries: 0` makes that likely). The `inner-limit` case checks the outcome, not the time from the denial to the runtime's exit.

### Nit 4: `cooperative` covers only the runtime PID (R9)

**Where:** `infra/dsh/launcher.py:243-251`.

A command started through `exec`, still running in the attempt cgroup when the runtime exits on SIGTERM, is killed by `cgroup.kill`, yet the stop is reported `cooperative: true`. `test_deadline_stops_a_running_command_within_the_grace` expects exactly that (`DshTurnDeadline`).

This is consistent with R15's "dies with the attempt". Whether "needs the launcher's kill" in R9 covers commands is for the engineer to decide.

### Nit 5: The success-path cleanup is never checked (R8, R10)

**Where:** `runner.py` `DshAttempt.close` ignores the stop report (`processes_left`, `tree_removed`). `classify(cleanup_ok=...)` sees a report only when `stop_reason` was set.

A cleanup failure after a successful turn is only logged.

### Nit 6: Per-attempt windows computed from per-turn values

- **Wall time** (`activity.py:331`): `turn.remaining_wall_time` is fixed when the workflow schedules the turn and is reused for every Temporal retry. Each attempt gets up to `min(turn_timeout, remaining_wall_time) - 20 s`, so a retried turn can run past the task's `max_wall_time`. It is bounded only by `schedule_to_close = turn_timeout * 6`. This was largely pre-existing; it is now an attempt-scope deadline built from a value meant for the whole turn.
- **Step ceiling** (`UsageLedger(steps=config.inner_max_turns)`): this is per attempt, so a turn with retries can use up to 5 × `inner_max_turns`. It matches `openai_agents`; noted for scope.

### Nit 7: The D9 output cap is not enforced by the gateway (D9)

**Where:** `gateway.py:271` (`to_model` forwards DSH's `max_tokens` and `contextWindow` unchanged).

The D9 charge assumes at most 2048 output tokens and at most `context_window` input tokens per request. The gateway does not clamp `max_tokens`, and no test asserts what DSH actually sends. If DSH omits `max_tokens` or sends a larger value, the conservative charge undercounts. A test should assert `max_tokens <= DSH_MAX_OUTPUT_TOKENS` on requests the fake model receives.

### Nit 8: Inner turns are counted as requests from the ledger but as logical steps live

**Where:** `activity.py` `_open`: `inner_turns = max(base.inner_turns, settled_count + unknown)` counts *requests*, including 4xx known-zero ones. The gateway sets `usage.inner_turns` to distinct *logical steps* (`gateway.py`, keyed by body hash).

The two agree only when no identical body is re-sent. The `max()` hides the difference.

### Nit 9: Smaller scope gaps in tests and wiring

- **Activity charging past two attempts:** the D9 "same charge for every later attempt" property is tested at repository scope over three attempts (`test_persistence_phase1.py:392-394`). The Activity's heartbeat-base `max()` merge is tested only over two attempts (`test_dsh_activity.py::test_dsh_resumes_and_charges_a_lost_request`).
- **Cancel outcome:** the cancel test accepts `rows[0][2] in ("cancelled", "failed")`, which would also pass in the Major 3 failure. The R18 cases hard-code their expectations rather than reading `docs/spikes/dsh-phase02-r2-evidence.json`.
- **Tree orphaned before `open`:** if the worker dies after `mkdir` of the attempt tree but before the launcher processes `open`, the launcher has no attempt to destroy. The tree stays until the launcher restarts and reaps it. This is a narrow R10 window.
- **R14 discovery test:** `test_no_skill_discovery_roots` checks only that the patch text lacks `includeDefaultRoots: true`. It does not check the effective DSH composition (notes.md#r14 says `includeDefaultRoots: false`).
- **Default mismatch:** `composition.build` defaults `context_window` to 32768, while `_open` charges `context_window or 0`. This is unreachable because the loader requires `context_window` for `dsh` templates, but the two defaults differ.

### Checked and found consistent

- The D10 lock is taken by `close_unknown`; settle after close is a no-op, so the charge stays conservative.
- `AttemptEvents` sequence numbers are per attempt and shared by the gateway and executor.
- The barrier runs before each request after the first in an attempt; the resumed attempt's first request skips it.
- `maxParallelToolCalls: 1` keeps worker-side tool bodies from overlapping the freeze.
- The timeout chain is ordered: worker MCP call 120 s < bridge 150 s < DSH tool call 180 s.
- Unknown usage is scoped per turn, and a new turn starts clean.
- The token budget is scoped per attempt and seeded with the turn's cumulative usage.

### Files
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/dsh/runner.py
- <repo>/harness_activity/dsh/gateway.py
- <repo>/harness_activity/dsh/ledger.py
- <repo>/harness_activity/dsh/barrier.py
- <repo>/harness_activity/dsh/policy.py
- <repo>/infra/dsh/launcher.py
- <repo>/common/persistence/repositories.py
- <repo>/orchestrator/workflow.py
- <repo>/workers/main.py
- <repo>/infra/docker-compose.yml
- <repo>/tests/integration/test_dsh_outcomes.py
- <repo>/tests/integration/test_dsh_activity.py
- <repo>/tests/integration/test_persistence_phase1.py

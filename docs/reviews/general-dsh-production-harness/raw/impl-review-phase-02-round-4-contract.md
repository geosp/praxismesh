<!-- Verbatim subagent report (impl-review-phase-02-round-4-contract, targeted follow-up on 11bb0d6..3239e2a); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. -->

## Phase 02 implementation review, follow-up round (11bb0d6..3239e2a, frozen at 3239e2a)

I found no Blockers and no Majors. Each round-3 fix that was marked "fixed" has enforcing code at the frozen commit:

- **F132 (R15, D3):** the launcher now unshares an IPC namespace per attempt process.
- **F133 (R17, R10):** an unreachable launcher now raises `LauncherUnreachable`, which is an `Unserviceable`.
- **F134 (R12, D7):** `close_unfinished` now gives `lost` rows the ledger's usage.
- **F136 (D11):** `complete_task` now takes inner turns from the ledger.
- **F137 (R11, D9):** `complete_task` now checks the template version.
- **F140 (D4):** `list_files` now walks by descriptor with `fwalk`.
- **F143 (R10):** `destroy` now marks the attempt dirty when cleanup raises.
- **F147 (R17):** the preflight refusal now writes its row before the heartbeat.

The findings below are gaps in how widely these fixes apply, and tests that would not catch the bug they target. All are Nits; the most substantive are 3, 4 and 5.

### Promise map for the changed code

| Promise | Enforcing code | Test that would fail without it |
|---|---|---|
| R15 / D3: private IPC namespace | `infra/dsh/launcher.py:151` | `tests/integration/test_dsh_launcher.py` `test_commands_get_their_own_tmp` (checks `ipcs`; real container) |
| R17 / R10: unreachable launcher is a refusal, not an attempt, and the worker stops polling | `harness_activity/dsh/runner.py:279-292`, `harness_activity/activity.py:227-242` | `test_unreachable_launcher_is_a_refusal_every_time` (missing-socket path only, see finding 6) |
| R12 / D7: lost rows get null or ledger usage at task completion | `common/persistence/repositories.py:293-303` | `test_lost_rows_hold_the_ledger_usage_when_the_task_completes` |
| D11: inner turns from the ledger in `complete_task` | `orchestrator/activities.py:64` | `test_complete_task_charges_what_the_ledger_left_unobserved` (`inner_turns == 2`) |
| R11 / D9: template-version-safe window in `complete_task` | `orchestrator/activities.py:51-57` | **none discriminating** (finding 3) |
| R10: a failed cleanup is dirty | `infra/dsh/launcher.py:291-298` | `test_launcher_destroy_error_marks_the_attempt_dirty` |
| D4: `list_files` never follows a link | `harness_activity/tools.py:183-204` | **none discriminating** (finding 7) |
| D10 / R17: refusal row before the heartbeat | `harness_activity/activity.py:234-238` | none (the order can't be observed without a failing DB write) |

### Findings

**1. Nit: F147 was fixed on only one of the two refusal paths (R17, D10)**
- **Where:** `harness_activity/activity.py:219-222`. The template-version refusal still heartbeats `refusals += 1` before `record_refusal`.
- **Scenario:** a worker on the wrong template version takes a turn, and the `record_refusal` write fails (DB blip).
  - The heartbeat already counted the refusal, and no `refused` row exists.
  - The next attempt subtracts a refusal that D10 never recorded. That is exactly the hazard the F147 resolution names: "a refusal the next attempt subtracts must exist".
- **Evidence:** compare lines 219-222 with lines 233-238.
- **Test:** make `record_refusal` raise on a version mismatch, then assert the next attempt's `real_attempt` and rows.

**2. Nit: the new refusal order turns a failed refusal write into a counted attempt (R17)**
- **Where:** `activity.py:234-242`.
- **Scenario:** `record_refusal` raises.
  - Nothing is heartbeated, `on_unserviceable` is not called, and a generic retryable error propagates.
  - The Temporal attempt then counts as a real attempt with no row, and the worker keeps polling, which contradicts R17's "without using an attempt, and stops polling".
- **Assessment:** this is a deliberate trade-off against F147. I'm reporting it because the R17 promise no longer holds when the DB write fails.
- **Test:** inject a failure into `record_refusal` during preflight and assert `refusals` and the `stopped` callback.

**3. Nit: the F137 test passes on the old code, and the "template gone" case is untested (R11, D9, R13)**
- **Where:** `tests/integration/test_dsh_usage.py`, `test_complete_task_survives_a_template_the_orchestrator_no_longer_has`.
- **Why it doesn't discriminate:**
  - The test only changes `template_hash`; the name `local-dsh` stays in the registry.
  - The old code (`self.registry.templates[payload.resolved.template].template.context_window`) therefore raised no `KeyError`.
  - It used 32768, which equals `DEFAULT_CONTEXT_WINDOW` (`harness_activity/dsh/composition.py:41`, `registry/templates/local-dsh.yaml:22`).
  - So the assertion `tokens_in == DEFAULT_CONTEXT_WINDOW` holds before and after the fix.
- **What is untested:** the `KeyError` scenario the finding named (the name is absent).
- **Semantic gap:** when the task's version is gone, the charge falls back to 32768 even if that version had a larger `context_window`. That undercharges, against D9 ("charged `context_window`") and R13 ("conservatively").
- **Test:** use a registry without the template name, or with a current version whose window differs from 32768 (for example 65536), and assert `KeyError`-free completion plus the expected charge.

**4. Nit: `complete_task` and the Activity count inner turns in different units (D11, R18)**
- **Where:** `orchestrator/activities.py:64` sets `inner_turns = max(payload.inner_turns, count(*) of ledger rows)`.
- **The mismatch:**
  - The Activity reports distinct logical steps, where identical request bodies share a step (`harness_activity/dsh/gateway.py:244`, `:258`; `ledger.py:129`).
  - If DSH re-sends an identical body within an attempt, the ledger has 2 rows for 1 logical step.
  - `TaskResult.inner_turns` then exceeds the sum of the turns' `TurnOutcome.inner_turns`, and exceeds the spike evidence by more than D11 allows ("adds retried or lost attempts' steps").
- **Assessment:** the current R18 cases don't re-send bodies (`served == requests + faults`), so this is latent.
- **Note:** the plan's Terms define an inner turn as "one model request", the Activity counts logical steps, and the plan doesn't say which unit wins.
- **Test:** a unit test where the gateway dispatches the same body twice in one attempt, then run `complete_task` and compare against the Activity's count.

**5. Nit: the preflight can block for up to 20 s with no heartbeat (R17)**
- **Where:**
  - `harness_activity/dsh/runner.py:94` (`CHECK_TIMEOUT_SECONDS = 10.0`), applied separately to connect (line 280) and to `digests` (line 287).
  - `activity.py:229`: no heartbeat before or during preflight.
- **Scenario:** a hung launcher (it accepts but never replies) with a template whose `heartbeat_timeout` is under about 20 s. The R18 test registry uses PT5S; `local-dsh` uses PT30S.
  - Temporal times the attempt out before the refusal heartbeat.
  - The `refusals` increment is lost, so the refusal counts as a real attempt (R17 "without using an attempt").
  - Nothing in the registry loader ties `heartbeat_timeout` to the check timeout.
- **Test:** a launcher stub that accepts and never answers, with `heartbeat_timeout` PT5S, run under a real Temporal worker.

**6. Nit: the F133 test only covers a missing socket (R17, R10)**
- **Where:** `tests/integration/test_dsh_activity.py`, `test_unreachable_launcher_is_a_refusal_every_time`.
- **Coverage:** it uses a nonexistent socket path, so only the `FileNotFoundError`-at-connect branch runs.
- **Untested branches:** the timeout branches (hung launcher, `runner.py:283`, `:288`) and the `LauncherError` on a dropped connection mid-`digests`.
- **Also unobserved:** "stops polling" is checked through the `on_unserviceable` callback, not a real worker shutdown (F139 was accepted).
- **Test:** a listening socket that never replies, and one that closes after accepting.

**7. Nit: the F140 test passes on the old code; the race it fixes is not observed (D4)**
- **Where:** `tests/test_dsh_runner_parts.py`, `test_list_files_never_follows_a_link`.
- **Why it doesn't discriminate:** with no race, the old `inside()` check plus `os.walk(followlinks=False)` already produced `error` for `dir-link` and `["sub/kept.txt"]` for `.` and `sub`. The F140 issue was a check-then-walk TOCTOU, and this test doesn't swap anything in.
- **Test:** monkeypatch `os.fwalk` or `open_inside` to swap a directory for a link between the open and the walk. Alternatively, record that the check is structural and not tested.

**8. Nit: `list_files` changed behaviour for `openai_agents` too (task 2.3, "conformance suite unchanged")**
- **Where:** `harness_activity/tools.py:185-192`. These bodies are shared by both runners.
- **Changes:**
  - A missing directory now returns `error: [Errno 2] ...` instead of `[]`.
  - A path that is a regular file now returns `error: path outside the workspace: <file>`: ENOTDIR is mapped to `WorkspaceError` in `open_inside`, `tools.py:96-98`. The message misleads the model.
  - `os.stat(name, dir_fd=fd, follow_symlinks=False)` at line 198 is not guarded, so a file deleted mid-walk (for example by a backgrounded command, R15) raises out of the body. Before, `is_file()` swallowed it. The executor and the SDK turn the exception into text, so the impact is low.
- **Note:** notes.md#rollout (F141) records the symlink change but not these.
- **Test:** `list_files_body(ws, "missing")`, `list_files_body(ws, "a.txt")`, and a deletion during the walk.

**9. Nit: the dead startup branch loses the template ref in its message (R17)**
- **Where:** `workers/main.py:99-103`. `check()` now wraps every `LauncherError` from connect and `digests` as `LauncherUnreachable`.
- **Effect:** the `except LauncherError` branch, which adds `template {ref}` to the message, can no longer run for an unreachable launcher. Startup failures now report `CapabilityError(str(error))` without the template.
- **Test:** call `build_harness` with a missing control socket and assert the message.

**10. Nit: the docs lag the code on the IPC namespace (D4, R15)**
- **notes.md#d4** still describes the command boundary as UID, capabilities, seccomp, `/work` and a per-attempt `/tmp`. It does not mention `/run`, `/dev/shm` or the IPC namespace, although the decision log (2026-11-16) says D4 was restated with them.
- **Phase 02 task 1.1** (`phases/02-dsh-runner.md`) still says "cgroup, command UID and mount namespace".
- **Fix:** none needed in code; update those two docs.

**11. Nit: F134 is tested only on the task-completion path (R12, D7)**
- **Where:** `close_unfinished` with `turn` and `through_attempt` set (Activity non-retryable path, `activity.py:270`, `:332`) now also rewrites `lost` rows.
- **Coverage:** only `turn=None` is tested.
- **Test:** an AttemptsExhausted or non-retryable failure after a refusal-marked lost row with an unsettled ledger row.

### Observability notes (no separate finding)
- The F132 test runs in the real DSH container, so the IPC namespace is genuinely observed.
- The F134, F136 and F137 tests use real Postgres through `engine`, so the SQL is observed.
- The F143 test exercises `destroy` on a fake cgroup directory. It shows the dirty bookkeeping, not real cgroupfs failures; that is acceptable for this branch.

### Relevant files
- <repo>/harness_activity/activity.py
- <repo>/harness_activity/dsh/runner.py
- <repo>/harness_activity/tools.py
- <repo>/orchestrator/activities.py
- <repo>/common/persistence/repositories.py
- <repo>/infra/dsh/launcher.py
- <repo>/workers/main.py
- <repo>/tests/integration/test_dsh_usage.py
- <repo>/tests/integration/test_dsh_activity.py
- <repo>/tests/test_dsh_runner_parts.py
- <repo>/docs/plans/2026-11-15-dsh-production-harness/notes.md
- <repo>/docs/plans/2026-11-15-dsh-production-harness/phases/02-dsh-runner.md

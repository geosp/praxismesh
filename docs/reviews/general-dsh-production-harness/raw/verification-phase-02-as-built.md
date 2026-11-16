<!-- Verbatim subagent report (verification phase 02, as-built claims, fresh verifier at 62ffc7618a78fac516a9b745bf7140d3e92a9d7d); saved by the coordinator per docs/reviews/README.md rule 1; scratch paths replaced by <verify-checkout>. -->

## Verification report: docs/architecture/overview.md, sections "DSH migration phase 01" and "DSH migration phase 02" (commit 62ffc7618a78fac516a9b745bf7140d3e92a9d7d)

**Verdict:** Almost every claim matches the code and the running `pmverify02` stack. I found no Blockers. One Major: the phase 02 Tests section describes an integration command that fails as documented. Three Nits.

**Setup**
- Checkout: `git rev-parse HEAD` gives 62ffc761…; `git diff HEAD -- docs/` is empty.
- I wrote only `.verify/v-isolation-probe.log`. I did not edit or rebuild anything and did not touch the `praxismesh` stack.
- Read-only probes I ran:
  - `make status`
  - a Temporal poller query (`uv run --env-file infra/.env python .verify/pollers.py`)
  - `docker inspect` on the pair and the volume
  - `psql` SELECTs through `docker compose -p pmverify02 … exec -T db`
  - a `{"op":"digests"}` request on the launcher socket, sent from inside `worker-dsh-a`
  - the documented isolation probe, run once in the existing `praxismesh-dsh:dev` image
- I did not re-run the DSH integration tests: they build the DSH image (`tests/support/dsh.py:75`), and the brief says not to rebuild. For test results I cite the earlier logs in `<verify-checkout>/.verify/` (07, 08, 09, 10, 11, 22, 23, 27, 28, 30), which were produced from this same checkout.

### Contradicted

**1. Major: phase 02 › Tests**
- Claim: "Integration (stack up, Docker, `infra/.env`): `uv run --env-file infra/.env pytest -m integration tests/integration/test_dsh_launcher.py … test_dsh_usage.py …` … They build the DSH image and start their own DSH containers; the model is the deterministic fake."
- `infra/.env:42` ships `VLLM_BASE_URL=` (empty). With that file, the documented command gives `4 failed, 51 passed` (`.verify/07-dsh-integration.log`):
  - `test_dsh_activity.py::test_step_limit_stops_a_runtime_that_does_not_exit`
  - `test_dsh_usage.py::test_non_retryable_failure_charges_its_own_unknown_request`
  - `test_dsh_usage.py::test_cancelled_attempt_charges_its_own_unknown_request`
  - `test_dsh_usage.py::test_retryable_failure_is_charged_once_across_attempts`
- The error is `ApplicationError: CapabilityError: VLLM_BASE_URL is not set for template local-dsh@1`. The full integration run shows the same four failures (`.verify/11-integration-all.log`: `4 failed, 170 passed, 4 skipped`).
- `test_dsh_usage.py` contradicts the description directly. It uses a `StubRunner` (lines 155–215), has no fake-model references and does not set `VLLM_BASE_URL`, unlike `test_dsh_activity.py:171` and others, which use `monkeypatch.setenv("VLLM_BASE_URL", fake.base_url)`. So not every listed test "starts its own DSH containers" or uses the fake.
- With `VLLM_BASE_URL` set, `test_step_limit_stops_a_runtime_that_does_not_exit` still failed once (`08-dsh-rerun-with-url.log:299`, `RunnerFailure: DshUsageUnknown`; `1 failed, 3 passed`) and passed alone (`09-step-limit-diag.log`: `1 passed`). It looks flaky or order-dependent.

**2. Nit: phase 01 › Components › Isolation probe**
- Claim: "Per-attempt cgroup freeze/kill and mount namespaces need `SYS_ADMIN`; the user-namespace check still fails."
- Present tense, and now stale. Running the documented probe command in the DSH image gives all 13 checks `ok:true`, including `{"check":"command_userns_blocked","ok":true,"detail":""}` (`.verify/v-isolation-probe.log`).
- `notes.md` (D3, "Phase 02 task 1.1") records the same. The phase 01 intro only supersedes "statements … about what phase 02 would add", which does not clearly cover this sentence. The `SYS_ADMIN` part is confirmed by the D3 table in notes.md.

**3. Nit: phase 02 › Usage accounting**
- Claim: "Attempt rows never read 0 for unobserved usage (NULL instead)."
- Holds for closed rows: `_runner_failed` writes NULL (`activity.py:301–318`), as do `close_unknown` (`repositories.py:538–593`) and `close_unfinished` through `_ledger_usage_sql` (`repositories.py:290–300`).
- It does not hold for open rows. `start` inserts without tokens, so the server default `0` applies (`0003_phase1_tables.py:68`), and the row keeps `usage_known = true` until it is closed.
- Observed in the DB: `task-usage-13f471feb315 | turn 1 | attempt 2 | started | tokens_in 0 | usage_known t | ledger requests 1 | unobserved 1` (task status `running`; this is leftover integration-test data).

**4. Nit: phase 02 › Launcher**
- Claim: the op list is "`digests`, `open`, `start`, `exec`, `freeze`, `thaw`, `poll`, `stop`".
- `infra/dsh/launcher.py:417` also serves `members`. Observed: `{"op":"members"}` on a fresh connection replied `{"error": "ValueError", "detail": "open an attempt first"}`, which is the attempt check, not `unknown op`.

### Unverifiable / observations

- **Nit: phase 02 › Worker pair › Start command.** The command is correct Compose syntax (`.verify/16-dsh-up-doc.log` shows both containers created and started). But `workers/main.py:141–146` makes the worker exit with `CapabilityError` at start when `VLLM_BASE_URL` is empty, and `infra/.env` ships it empty. The doc does not mention this. The running pair works only because it was started with `VLLM_BASE_URL=http://fake-model:8765` (`docker exec … printenv` printed `/attempts/.control.sock` and `http://fake-model:8765`).
- **"exit 1, `CapabilityError`" at start.** Confirmed by code only: `build_harness` raises `CapabilityError` (`workers/main.py:99–101`) and nothing catches it in `main` (`sys.exit(asyncio.run(main(...)))`, line 192), which gives Python's default exit 1. Earlier logs 22 and 23 show the `CapabilityError` tracebacks, but no exit code was captured.

### Confirmed

**Phase 01**
- **Session store:**
  - The `SessionStore` protocol has `session`, `load`, `capture` (`harness_activity/session_store.py:35–46`).
  - `SQLAlchemySessionStore` clears or truncates in `load` (57–68) and captures the position (70–71).
  - `run_harness_turn` uses only the store (`activity.py:431–461`).
  - "Raises until phase 02" is historical; phase 02 added the columns (`0004_dsh_usage_and_sessions.py:55–56`) and `insert_fenced` writes `session_ref` (`repositories.py:399–417`).
- **Fence:**
  - `_TASK_LOCK = pg_advisory_xact_lock(hashtext(:t))` (`repositories.py:380`) is used in:
    - `start` (141)
    - the fenced `finish` (188)
    - `assert_current` (264)
    - `insert_fenced` (393)
    - `record_refusal` (233)
  - The newer-attempt check `_NO_NEWER_ATTEMPT` (381–384) raises `FenceRejected`.
  - The refusal inserts `'refused'` without the newer-attempt check (250–255).
  - The Activity maps the rejection to `Superseded` (`activity.py:400, 480, 546, 571`); `Superseded` is not a `NonRetryableError` (`runner.py:65`), so nothing more is written.
  - Artifacts are uploaded after `assert_current` (`activity.py:545–555`) and recorded through the fenced finish (557–571).
- **Registry:**
  - `Harness = Literal[…, "dsh"]` (`common/schemas/base.py:10`).
  - Profile and template harness must match (`registry/loader.py:133, 206`).
  - `dsh` templates need `concurrency_per_pod: 1` and `context_window` (165–170).
  - `local-dsh@1` is in `registry.lock:7`.
  - `schedule_to_close = turn_timeout * 6` (`orchestrator/workflow.py:127`) with `turn_timeout: PT10M` gives 1 h.
- **Events:** `AgentEvent` (`common/schemas/events.py:30`); `EventSink`, `NoOpSink`, `MemorySink`, `AttemptEvents` with `seq` assigned and emitted under a lock (`harness_activity/events.py:16–54`).
- **Isolation probe:** the file and its header run command exist.
- **Tests:** the phase 01 integration files have no failures in `.verify/11-integration-all.log`.
- **Links:** `plan.md`, `notes.md#d3` and `notes.md#rollout` exist.

**Phase 02**
- **Pair (observed):**
  - `dsh-a`: `net=none ro=true cgns=private capadd=[CAP_SYS_ADMIN] secopt=[no-new-privileges:true apparmor:unconfined]`; its environment has no credentials (only `DSH_SHARED_GID`, `DSH_WORKER_UID` and base-image variables).
  - The volume is `pmverify02_dsh-attempts-a`, mounted at `/attempts`, tmpfs (`o:size=2g,mode=1770,gid=4243`).
  - `worker-dsh-a`: `cmd=[template local-dsh]`, `DSH_CONTROL=/attempts/.control.sock`.
  - Pollers: `tpl.local-dsh ['bb87b880f041@1/local-dsh']`.
  - Compose definitions: `infra/docker-compose.yml:185–214, 259–261`.
- **Launcher:**
  - Runs as root (observed: `Uid: 0` in `dsh-a`).
  - One attempt per connection; a closed connection destroys it (`launcher.py:374–436`, `finally: destroy`).
  - Each attempt gets its own cgroup (196–201).
  - Runtime UID 1000 (46, 206–215) and command UID 4242 (47, 219–240) both run through `setpriv` with no capabilities and `--no-new-privs` (185–191), with seccomp blocking `CLONE_NEWUSER` (88–128).
  - Mount and IPC namespaces with private `/run`, `/dev/shm` and `/tmp`, and other attempt trees hidden (144–167).
  - `stop`: thaw, SIGTERM, then kill and `keep_tree` (259–278); `_destroy` removes the tree (301–321).
  - `reap` at start (329–340, 441); observed log `{"launcher": "ready", "reaped": []}`.
  - `DIRTY` set reported with `digests` (320, 402); observed `dirty= []`.
- **Runtime pin:**
  - `CONTROL_FILES = ("pins.py", "launcher.py", "driver.py", "mcp_bridge.py")` together with the requirements digest (`infra/dsh/pins.py:29, 53–58`).
  - The report is computed at start-up (`launcher.py:343–356, 442`).
  - Observed `runtime_digest: sha256:a842ed2e…` equals `registry.lock` `runtimes: dsh: sha256:a842ed2e…`, with `integrity: ok`.
  - The worker checks at start (`workers/main.py:99`) and before every attempt (`preflight=dsh.check`, `activity.py:228–243`; plus `_verify` in `open_attempt`, `runner.py:255`).
- **Runner:**
  - `DIRS = ("workspace", "home", "ipc", "config", "tmp")` (`runner.py:87`).
  - Starts the driver through the launcher (488–490).
  - Polls and stops on deadline, cancel, abort, or `LIMIT_EXIT_SECONDS = 2.0` after a step-limit or token-budget denial (90, 493–527).
  - Classifies the end with `policy.classify` (551) and raises `RunnerFailure` (582).
  - `check` raises `Unserviceable` subclasses when the container is unreachable, dirty or the pin differs (274–304).
- **Gateway and ledger:**
  - Unix socket at `ipc/gateway.sock` (`runner.py:424`, `gateway.py:68`).
  - Checks the attempt key, model and tool catalog (`gateway.py:223, 238`).
  - Barrier on every request after the first (246–247).
  - Fenced ledger row before dispatch (`repositories.py:495–510`) and settle (512–536).
  - `max_tokens` capped at `min(…, 2048)` (`gateway.py:132–134`, `ledger.py:17`).
  - `token` event (`gateway.py:319–320`).
  - The `usage_ledger` table exists with the expected columns.
- **Barrier:** checks the flush marker, then freezes, captures and commits, then thaws (`barrier.py:50–78`).
- **Executor and tools:**
  - The worker runs the tool bodies; `run_command` goes through launcher `exec` (`runner.py:370–381`).
  - `O_NOFOLLOW` on every path component (`tools.py:82–98`).
  - `tool_call` and `tool_result` events (`executor.py:130–177`).
  - The bridge only forwards calls (`mcp_bridge.py:1–20`).
- **Session store:**
  - `DshSessionStore` clears and replaces the home directory, checks the digest, and captures with `position=0` (`dsh/session.py:70–85`).
  - Observed: DSH checkpoints have `session_position 0`, with `session_ref` and `session_digest` set.
- **Usage accounting:**
  - `unknown_charge = requests*context_window, requests*2048` (`ledger.py:53–55`).
  - Charged when the next attempt opens (`activity.py:376–381`), on runner failure or cancel (301–304), on non-retryable failure (270–272), and in `complete_task` (`orchestrator/activities.py:42–67`).
  - Observed ledger rows with NULL tokens and `lost` rows with NULL tokens and `usage_known f`.
- **Worker start:**
  - The runner is chosen from `template.harness` (`workers/main.py:91–124`).
  - During a turn: a `dsh_unserviceable` refusal row (`activity.py:235–243`), then `EXIT_UNSERVICEABLE = 3` (`main.py:65, 188`).
  - Observed earlier: `status=exited exit=3` (`.verify/27`), the row `1 | 1 | refused | dsh_unserviceable` (`.verify/28`), then `done` on attempt 2 after restore (`.verify/30`).
- **Workflow:** `WAIT_CANCELLATION_COMPLETED` (`workflow.py:130`); `failed_turn_usage` carries `usage_known` (46–62, 142).
- **Header and known limits:**
  - `default.yaml` is `harness: openai_agents`.
  - The deferred items match notes.md Rollout (161–163): the "unresolved usage" denial is not in `STEP_DENIALS` (`policy.py:12`), so it starts no exit timer; launcher `request` awaits its reply with no timeout (`launcher_client.py:53–64`).

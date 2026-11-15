<!-- Verbatim subagent report (verification-phase-01-as-built); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## As-built doc check: DSH migration phase 01 (doc at 3e11afc, code at 4969d4d)

**Result:** 2 claims contradicted (both Nit), 2 unverifiable (both Nit), no Blockers, no Majors. All other claims confirmed in code and, where they describe runtime behaviour, by observation.

**Scope:** `docs/architecture/overview.md` at 3e11afc. I checked the section "DSH migration phase 01: harness seam and registry" (lines 122-139) and the Phase 1 "Fencing" bullet (line 86). The doc was extracted to `<verify-checkout>/.verify/overview-3e11afc.md`. The checkout HEAD is 4969d4dbeaddd6fd8f6af777a9b0fdbe50db0bb3, and `git status` shows only `?? .verify/`.

### How I ran things (deviations included)
- **Stack:** `make up` refused with "infra/.env is missing". I did not create `infra/.env`. Instead I used the Makefile's documented `ENV_FILE=` override with `<verify-checkout>/.verify/env`. It is a copy of `infra/.env.example` with project name `verifydsh01` and ports 15432, 17233, 18080 and 18333. The user's own `praxismesh` stack was running on the default ports and I left it alone.
- **Commands:** `make up`, `make migrate` (ran 0001 to 0003), `make recovery-check` and `make down`, each with `ENV_FILE=.verify/env`. The stack is stopped now; `docker ps | grep -c verifydsh01` gives 0.
- **Integration tests:** I ran the doc's command with `uv run --env-file .verify/env` added (see U2).
- **Isolation probe:** I ran the header command with the pinned image `python:3.11-slim-bookworm@sha256:a83ba18a...`. I added the SELinux `,z` mount option, because this host enforces SELinux.
- **Cleanup incident:** my `pkill -f "workers.main orchestrator"` stopped my own probe orchestrator (pid 316569, with its uv wrapper) and my own shell. The user's `praxismesh-orchestrator-1` container was not affected: it runs as UID 10001, `docker top` still showed it, and it reported "Up 15 hours (healthy)".
- **Writes:** only under `.verify/` (env file, probe output, registry copies under `.verify/reg/`) and probe scripts in the scratchpad. I wrote test rows only to my disposable `verifydsh01` database.

### Confirmed claims

**Fencing bullet (line 86)**
- "checks for a newer attempt before every model call and stops without writing anything". Code: `harness_activity/activity.py:318-322` runs the `newer_attempt_exists` check (`repositories.py:309-318`) before `checkpoint()`. Superseded is re-raised without writes at `activity.py:331-335`, and `Superseded(Exception)` (`runner.py:64`) is not a `NonRetryableError`, so `close_unfinished` is not reached. Observed: `test_superseded_attempt_writes_nothing PASSED`, `test_superseded_attempt_comes_back_and_writes_nothing PASSED`.
- "the writes themselves are fenced": see the Fence row below.

**Header (line 124)**
- "Production still runs only `openai_agents`; no DSH runner exists yet." `OpenAIAgentsRunner` is the only runner class (`harness_activity/runner.py:159`). `DshRunner` appears only in comments (`workers/main.py:72`, `tests/test_runner_conformance.py:35`).

**Session store row (line 130)**
- The protocol has `session`, `load` and `capture` (`session_store.py:35-46`). `SessionSnapshot` holds position and an optional `session_ref` (`:26-32`; it also has `session_digest`, which the doc does not mention).
- `load` clears when there is no checkpoint and pops items down to the checkpoint's position (`:57-68`). `SQLAlchemySessionStore` wraps `SQLAlchemySession` (`:49-55`).
- `run_harness_turn` uses only the store (`activity.py:161`, `:261-262`, `:269`, `:283`, `:291`); the Activity never imports `SQLAlchemySession` itself.
- "a snapshot with a session ref raises": `NotImplementedError` at `activity.py:292-294`. The checkpoints table has no session-ref column (psql listing: `checkpoint_id task_id turn attempt seq session_id session_position workspace_ref finish created_at retention_class`), and the only migrations are 0001 to 0003.
- Observed: `test_session_store_contract PASSED`, `test_restore_truncates_session PASSED`, `test_restore_without_checkpoint PASSED`.

**Fence row (line 131)**
- Every listed operation takes the task lock `_TASK_LOCK = pg_advisory_xact_lock(hashtext(:t))` (`repositories.py:329`). It is taken in `start` (:138), fenced `finish` (:186), `record_refusal` (:222), `assert_current` (:254) and `insert_fenced` (:345).
- The newer-row check `_NO_NEWER_ATTEMPT` (:330-333) runs in the same transaction in `start` (:139-144), `finish` (:196, :209-215), `assert_current` (:255-260) and `insert_fenced` (:351-366). Refusal records do not run it (see C1).
- `FenceRejected` becomes `Superseded` at `activity.py:240-241`, `:311-312`, `:377-378` and `:398-399`.
- Refusal rows: `outcome='refused'` is inserted (:236-245) and earlier open rows of the turn become lost. Observed: `test_refusal_fences_older_attempts PASSED`.
- Artifacts are uploaded after `assert_current` (`activity.py:375-384`) and returned only after the fenced finish succeeds (:386-399). Observed: `test_newer_attempt_before_publication_blocks_artifacts PASSED`.
- Concurrency tests passed: `test_fenced_insert_waits_for_a_concurrent_start`, `test_start_waits_for_the_task_lock`, `test_late_stale_start_is_refused`, `test_fenced_finish_rejects_a_newer_turn`.

**Registry row (line 132)**
- `dsh` is a `Harness` value (`common/schemas/base.py:10`; `loader.py:30`).
- Load-time checks: harness mismatch (`loader.py:172-179`) and the `dsh` requirements (`:134-140`). My probes on registry copies showed:
  - `profile_mismatch RegistryError profile 'dsh' harness 'openai_agents' does not match template 'local-dsh@1' harness 'dsh'`
  - `concurrency2` and `no_context_window` both give `RegistryError ... dsh templates need concurrency_per_pod: 1 and a context_window`
- `local-dsh@1` is locked (`registry/registry.lock`). The unmodified registry loads with `check_lock=True`, and an edited `local-dsh` gives "template local-dsh@1 changed but its version did not".
- Workers refuse `dsh`: `workers/main.py:71-77`. Observed on start: `CapabilityError: template local-dsh@1 uses harness 'dsh', which this worker cannot run yet`.
- A submitted `--profile dsh` task (`task-verifydsh0001`) showed `"workflow": "RUNNING"`. Its history showed `scheduled run_harness_turn tpl.local-dsh s2c 3600` and `pending run_harness_turn state 1 attempt 1`, so it is unserved (but see C2).

**Events row (line 133)**
- Schema at `common/schemas/events.py:30-40`. `NoOpSink`, `MemorySink` and `AttemptEvents` at `harness_activity/events.py:56-95`; `emit` holds the lock while delivering (:83-94).
- "No runner emits events yet": grep finds no use of these classes outside the events modules and `common/schemas/__init__.py`.

**Isolation probe row (line 134)**
- The script exists and its header holds the run command; results are in `notes.md` §D3.
- Observed with `SYS_ADMIN`: `cgroup_freeze ok:true`, `cgroup_kill ok:true "alive=0 of 3"`, `mount_namespace ok:true`, `command_userns_blocked ok:false "user namespace allowed"`.
- Observed with default caps: `cgroup_create ok:false`, `mount_namespace ok:false`.
- Output files: `<verify-checkout>/.verify/probe-sysadmin.txt` and `<verify-checkout>/.verify/probe-default.txt`.

**Tests (lines 136-139)**
- `uv run pytest`: `174 passed, 101 deselected`. It covers `tests/test_registry.py`, `tests/test_agent_events.py`, and `tests/test_runner_conformance.py`, which takes its session from `MemorySessionStore` via the `make_store` hook.
- Integration: `33 passed in 9.86s` (`<verify-checkout>/.verify/integration.txt`).
- `make recovery-check`: `5 passed in 58.09s`.

### Contradicted claims

**C1. Nit. Fence row, line 131**
- Claim: "Every `start`, fenced checkpoint insert, fenced finish, `assert_current` and refusal record takes `pg_advisory_xact_lock(hashtext(task_id))`, then checks in the same transaction that no newer (turn, attempt) row exists."
- What the code does: `record_refusal` (`common/persistence/repositories.py:217-246`) takes the lock but never runs `_NO_NEWER_ATTEMPT` and never raises `FenceRejected`. It just inserts, with `ON CONFLICT DO NOTHING`.
- Observed: after `start(t, 5, 3)`, `record_refusal(t, 5, 2)` printed `no FenceRejected`, and the rows were `5 2 refused template_version_unavailable` and `5 3 started None`.
- Why only a Nit: a stale refusal only marks rows with a lower attempt number as lost and never changes the newer row. Even so, the sentence states the check for all five operations, and that is false for one of them.

**C2. Nit. Registry row, line 132**
- Claim: "`dsh` tasks wait unserved until phase 02."
- What the code does: the turn Activity has `schedule_to_close_timeout = turn_timeout * 6` (`orchestrator/workflow.py:124`). Observed: `s2c 3600` for `tpl.local-dsh`.
- So a `dsh` task waits at most 1 h per turn and then fails with a harness-turn failure; it does not wait until phase 02. The `dsh` profile's `max_wall_time: PT30M` is not applied while the Activity is pending.

### Unverifiable claims

**U1. Nit. Fencing bullet, line 86**
- Claim: "Temporal also cancels a resumed attempt whose heartbeat timed out."
- The only end-to-end test, `test_superseded_attempt_comes_back_and_writes_nothing`, passed. Its own docstring says it "checks the property" without telling apart Temporal cancellation and the self-fence.
- I found no test or observation that shows the cancellation itself. The claim depends on Temporal SDK heartbeat behaviour, which I did not confirm against the docs.

**U2. Nit. Tests, line 139**
- The integration command is given as `uv run pytest -m integration ...` with no `--env-file`. The Makefile (`UV := uv run --env-file $(ENV_FILE)`) and the CLI docstring load the env file.
- I only ran it with `--env-file`, so I cannot confirm the command works as written. It probably needs `--env-file infra/.env`.

### Outside the requested scope
The Phase 1 Components "Registry" row (line 72) still lists only profile `default` and template `local-default@1`. That is accurate for the Phase 1 commit it describes, but someone reading the doc at 3e11afc might take it as the current registry.

### Key paths
- `<verify-checkout>/common/persistence/repositories.py` (`record_refusal`, lines 217-246)
- `<verify-checkout>/harness_activity/activity.py`
- `<verify-checkout>/harness_activity/session_store.py`
- `<verify-checkout>/workers/main.py`
- `<verify-checkout>/orchestrator/workflow.py`
- `<verify-checkout>/registry/loader.py`
- Evidence under `<verify-checkout>/.verify/`: `overview-3e11afc.md`, `integration.txt`, `probe-sysadmin.txt`, `probe-default.txt`, `env`, `reg/`, `orch.log`

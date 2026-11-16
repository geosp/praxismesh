<!-- Verbatim subagent report (verification-phase-01-as-built-follow-up); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

## Result: all three claims hold; two Nits

I checked the three claims from `docs/architecture/overview.md` at 38e379ce, section "DSH migration phase 01", against the code at 4969d4db in `<verify-checkout>`. I also ran them on a disposable stack: project `verifydsh01`, env file `.verify/env`, ports 15432, 17233, 18080 and 18333. I started it with `make up`, `make migrate` and `make workers-check`, then tore it down with `make workers-down` and `make reset`. Afterwards no `verifydsh01` containers or volumes were left. The user's `praxismesh` containers were not touched and stayed "Up 15 hours (healthy)". `git status` shows only `?? .verify/`. Logs are in `<verify-checkout>/.verify/followup/`.

### Claim 1, Fence row: confirmed, with one Nit

**Code (`common/persistence/repositories.py`):**
- **Lock:** `_TASK_LOCK = pg_advisory_xact_lock(hashtext(:t))` (329). Five methods take it: `start` (138), `finish` only when `fenced=True` (186-187), `record_refusal` (225), `assert_current` (254) and `insert_fenced` (343).
- **Newer-attempt check:** `_NO_NEWER_ATTEMPT` (330-333) runs in the same transaction in four of them: `start` (139-144), the fenced `finish` (198 and 209-215), `assert_current` (255-260) and `insert_fenced` (351 and 365-366).
- **Refusal:** `record_refusal` (217-246) has no such check. It marks earlier open rows lost and inserts `outcome='refused'`, `failure_category='template_version_unavailable'` with `ON CONFLICT DO NOTHING`.
- **Activity (`harness_activity/activity.py`):**
  - `FenceRejected` becomes `Superseded` at 240-241, 311-312, 377-378 and 398-399.
  - The refusal is recorded at 185, before `TemplateVersionUnavailable` is raised.
  - Artifacts are uploaded only after `assert_current` (376-383).

**Runtime (probe `.verify/followup/test_probe_fence.py`, log `05-probe-fence.log`):** while a separate transaction held the task's advisory lock, each operation waited.
```
start(t,1,1): BLOCKED then ok
assert_current(t,1,1): BLOCKED then ok
finish fenced(t,1,1): BLOCKED then ok
insert_fenced(t,1,1): BLOCKED then ok
record_refusal(t,1,3): BLOCKED then ok
record_refusal(t,1,2) with newer attempt 3 present: no exception
after refusal@2, assert_current(1): FenceRejected
after refusal@2, finish fenced(1): FenceRejected
after refusal@2, start(1) again: FenceRejected
rows2: [(1, 'lost', 'lost_or_timed_out'), (2, 'refused', 'template_version_unavailable')]
```
So all five operations take the lock, the refusal skips the newer-attempt check, and the refusal fences the older attempt, as the row says.

**Nit: "the Activity raises Superseded, writing nothing" is not literally true.**
- **Code:** in `checkpoint()` (activity.py:286-290), the workspace tarball goes through `self.blobs.put(...)` before `insert_fenced` runs. In production that is a `RecordingBlobStore`, which also inserts a `blob_objects` row (repositories.py:437-466). A superseded attempt can therefore leave an unreferenced blob and its `blob_objects` row.
- **Observed:** in the same probe, a newer attempt started between the pre-call check and the finish checkpoint. Output: `run raised: Superseded a newer attempt owns this task` / `blobs uploaded by the superseded attempt: 2` / `checkpoints rows: 1` / `checkpoint rows with finish: 0`. The second blob is the finish-checkpoint workspace, uploaded after the attempt was already superseded and then never referenced.
- **Scope:** no checkpoint row, attempt row or artifact is written, and the fenced writes are correct. The gap is only the wording; "writing no row" would be accurate.

### Claim 2, Registry row: confirmed (terminal failure confirmed in code only)

The claim: "Workers refuse non-`openai_agents` templates, so no worker serves `tpl.local-dsh` until phase 02: a `dsh` task's turn waits and then fails at `schedule_to_close` (6 x `turn_timeout`, 1 h)."

**Code:**
- `workers/main.py:71-77` raises `CapabilityError` at worker startup for any harness other than `openai_agents`.
- `infra/docker-compose.yml:172,183` runs both template workers on `local-default` only.
- `orchestrator/workflow.py:122-128` sets `schedule_to_close=turn_timeout*6` with unlimited attempts (`TURN_ATTEMPTS = 0`). Wall time is checked only between turns (101-103), so the dsh profile's `max_wall_time: PT30M` does not cut the wait short.
- `registry/templates/local-dsh.yaml` has `turn_timeout: PT10M`.
- When the timeout fires, the `ActivityError` handler (130-139) breaks the loop with `status="failed"`.

**Runtime:**
- `VLLM_BASE_URL=http://127.0.0.1:9 uv run --env-file .verify/env python -m workers.main template local-dsh` exited 1 with `CapabilityError: template local-dsh@1 uses harness 'dsh', which this worker cannot run yet` (`10-dsh-worker.log`).
- With the orchestrator and both `local-default` workers up, `make task PROFILE=dsh PROMPT=...` submitted `task-fa4a831c-...` with `"template": "local-dsh"`.
- `describe.py`, a read-only Temporal client script under `.verify/followup`, logged to `09-describe.log`: `scheduled run_harness_turn queue: tpl.local-dsh schedule_to_close: 3600 schedule_to_start: 3600 start_to_close: 600`.
- 85 s later (`11-describe-later.log`) the turn was still waiting: `status: RUNNING`, `pending: run_harness_turn state: 1 attempt: 1 ... expiration: 2026-11-15 21:55:52 last_worker: ''`.
- `make task-status` showed `"attempts": []`.

I did not wait the full hour to watch the failure itself. That part rests on the code above plus the observed 3600 s expiration.

### Claim 3, Tests list integration command: confirmed, with one Nit

**Runtime:**
- **As written, with no `infra/.env` in the checkout:** exit 2, `error: No environment file found at: infra/.env` (`03-as-written-no-infra-env.log`). That file is the documented setup (`cp infra/.env.example infra/.env`, Makefile header), so this is expected.
- **Same command with `--env-file .verify/env`, stack up:** I had already run `make migrate`. Result: `33 passed in 9.91s` (`04-integration.log`).
  - The test names cover what the doc lists: fence concurrency (`test_fenced_insert_waits_for_a_concurrent_start`, `test_start_waits_for_the_task_lock`) and refusal rows (`test_refusal_fences_older_attempts`).
  - Activity-level fencing: `test_newer_attempt_mid_run_fences_the_finish`, `test_newer_attempt_before_publication_blocks_artifacts`, `test_superseded_attempt_writes_nothing`.
  - Store contract: `test_session_store_contract`.

**Nit: the doc says only "stack up", but the tests expect migrations applied.**
- **Code:** neither test file applies migrations; `test_sdk_session_uses_migrated_tables` assumes the migrated schema. `make up` does not run `make migrate`.
- **Not tested:** I ran migrations first, so I did not watch the command fail on an unmigrated database.

### Severity summary
- **Contradicted:** none.
- **Nit:** claim 1, "the Activity raises `Superseded`, writing nothing". A superseded attempt can still upload an orphan checkpoint blob and its `blob_objects` row.
- **Nit:** claim 3, "Integration (Postgres, stack up)". It omits that `make migrate` is needed (inferred from code, not observed).
- **Unverifiable:** none. In claim 2, the failure after one hour is confirmed in code, not by waiting it out.

**Temporary changes:** none to source, tests or docs. I added only files under `<verify-checkout>/.verify/followup/`: `test_probe_fence.py`, `describe.py` and logs `01` to `12`.

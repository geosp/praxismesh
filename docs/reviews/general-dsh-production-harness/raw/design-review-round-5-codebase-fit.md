<!-- Verbatim subagent report (design-review round 5, codebase fit, targeted follow-up at e51495c); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>. -->

Targeted design review round 5 (follow-up under rule 6) of <repo>/docs/plans/2026-11-15-dsh-production-harness at e51495c. I covered the changes in 98835319..e51495c and judged the plan as a whole.

**Verdict: changes-requested.** There is 1 Major and 5 Nits. No Blockers.

**Checked and correct:**
- Terms › Attempt tree (Unix sockets): `launcher_client.py:32`, `gateway.py:68`, `infra/dsh/driver.py:34`.
- R15 and D3 (separate IPC namespace, private `/run` and `/dev/shm`): `infra/dsh/launcher.py:58,151,156`.
- D1 (a restore replaces the whole home): `harness_activity/dsh/session.py:6,50`.
- notes.md#rollout:
  - two `openai_agents` slots: `infra/docker-compose.yml:169,216`; `concurrency_per_pod: 1` in `registry/templates/local-default.yaml:21`.
  - the registry ships in the image: `workers/Dockerfile:21`.
  - drain bound of 30 min + 6 x 10 min: `orchestrator/workflow.py:90,105,125-127`, profile `PT30M`, `turn_timeout: PT10M`.
  - exit code 3: `workers/main.py:65,188`.
  - symlink refusal: `harness_activity/tools.py:95-98,197`.
- `cgroup: private` in `infra/docker-compose.yml:191`.
- Phase 01 task 2.2: the load-time check exists at `registry/loader.py:206`.
- Phase 03 task 1.1 helper: `tests/support/dsh.py` imports pytest, so the plan is right to ask for a non-pytest helper.
- `tests/support/workers.py:20`: `running_workers` takes a template.
- R20: the 7 pins in `infra/dsh/requirements.txt` exist and `docs/licences/` does not yet. Task 1.3 creates it.
- ADR-0005 condition 5 is now kept through the `openai` profile.
- The workflow edits since the plan's base add no new commands, so workflows already in flight still replay. This is consistent with "roll forward only".

## Findings

**F160 · Major · phases/03-acceptance.md › Task 2.1 (D5, R3)**
- **What is wrong:** The task lists the tests and Make targets that assume `default` is `local-default`. The list leaves out two places where tests resolve or run `default`:
  - The R3 conformance suite: `tests/test_runner_conformance.py:128`, `:419` and `:473` all call `registry.resolve("default")` and pass the result to the OpenAI runner.
  - `tests/integration/test_tracing.py:76` submits `{"profile": "default"}` to `running_workers`, whose template is `local-default` (`tests/support/workers.py:20`).
- **Effect:** After the switch, the suite that delivers R3 ("Given `local-default`, when the conformance suite runs on the seam") would resolve `local-dsh` instead. The tracing test would send a `local-dsh` task to a worker that serves only `local-default`. CI would expose this, but the task names files to change and gets the list wrong.
- **Fix:** Add both files to the list, and say that R3's suite resolves through the `openai` profile.

**F161 · Nit · notes.md › Rollout ("A refusing DSH worker … logs 'worker cannot serve its queue', exits 3"); feeds phase 03 task 2.2**
- **What is wrong:** This is true only for a refusal during a run (`harness_activity/activity.py:240`, then `workers/main.py:188`).
- **The start-up refusal behaves differently:**
  - `workers/main.py:100-101` raises `CapabilityError(f"template {...}: {error}")`, and nothing catches it in `main()` (`workers/main.py:173-188`). The process exits with code 1 and a traceback, and does not log "worker cannot serve its queue".
  - This is the usual case after an image rebuild with a pin mismatch.
- **Effect:** A runbook written from this note would have operators watching for exit 3 while the worker loops on exit 1.
- **Fix:** Either correct the note, or catch the start-up refusal and exit with code 3.

**F162 · Nit · notes.md › Rollout ("Profiles resolve once per task") and plan.md › Rollout & rollback**
- **What is wrong:** A profile is resolved twice, from two copies of the registry:
  - The submitting process resolves it from its own checkout (`orchestrator/submit.py:33`, called from `orchestrator/cli.py:78` and `tests/benchmarks/run.py:58`) and fixes `template` in `TaskStart` (`submit.py:47`).
  - The orchestrator container resolves it again from its image (`orchestrator/activities.py:75`).
- **Effect:** Between the registry edit and the orchestrator restart, a task submitted with `default` names `local-dsh`. The old orchestrator still allows only `[local-default]`, so `resolve_capabilities` fails with `CapabilityError` (`registry/loader.py:124-128`). The same happens in reverse on a revert.
- **Fix:** Say which side switches first, or that submissions pause during the switch.

**F163 · Nit · phases/03-acceptance.md › Task 1.1 Verify**
- **What is wrong:** The check "one benchmark task runs to completion on each profile, and the two result files differ" is weak:
  - A one-task run (`--only`) is still compared against the baseline of 10 passes (`tests/benchmarks/run.py:148-153`). It reports "Regression limit exceeded", exits 1 (`:206`) and writes its result into `docs/benchmarks/` (`:185-190`).
  - "the two result files differ" always holds, because the template field differs between profiles.
- **Fix:** Check that the file names and the `harness` label follow the profile, and keep this smoke run out of `docs/benchmarks/`.

**F164 · Nit · plan.md › Phases table**
- **What is wrong:** Phase 03 shows "0/4". Since task 1.3 was added, phases/03-acceptance.md has 5 tasks (1.1, 1.2, 1.3, 2.1, 2.2).
- **Why it was missed:** `check_plans.py` does not check task counts.

**F165 · Nit · plan.md › Requirements › R13 (and R20)**
- **R13:** The rule now covers charging "when the turn or task ends with no later attempt". The scenario still checks only "then it is charged the D9 estimate and the attempt is retried", and R12's "the task completes" case cannot be retried. The completion-time charge (F98 and F134 paths, `orchestrator/activities.py:42-67`) has no scenario of its own.
- **R20 and task 1.3:** These say "with a check" but not where the check runs (CI or `check_plans.py`). Unless it runs in CI, removing a notice will not be caught.

## Relevant paths
- <repo>/docs/plans/2026-11-15-dsh-production-harness/plan.md
- <repo>/docs/plans/2026-11-15-dsh-production-harness/notes.md
- <repo>/docs/plans/2026-11-15-dsh-production-harness/phases/03-acceptance.md
- <repo>/tests/test_runner_conformance.py
- <repo>/tests/integration/test_tracing.py
- <repo>/workers/main.py
- <repo>/harness_activity/activity.py
- <repo>/orchestrator/submit.py
- <repo>/orchestrator/activities.py
- <repo>/tests/benchmarks/run.py

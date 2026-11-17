<!-- Verbatim subagent report (impl-review-phase-03-round-1-scope, 285dd44..89ac455, frozen at 89ac455); reviewers: fresh-subagent; saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Impl review: DSH migration phase 03, round 1, scope lens

Range: `285dd44..89ac455` (frozen at 89ac455). Contract: plan.md (R4, R19, R20, D5, D6, notes.md#rollout), phases/03-acceptance.md tasks 1.1-2.2.

## Findings

### F1 · Major · Task 2.1 verify / D5: "a `default` task runs on DSH" is only tested at registry-resolution scope
- Location: `tests/test_registry.py:106-113` (`test_default_profile_runs_on_dsh`); no other test or recorded evidence in the range.
- Promise: phase 03 task 2.1, "Verify: CI passes; a `default` task runs on DSH and an `openai` task on `openai_agents`."
- What the test covers: `load_registry().resolve("default")` returns `local-dsh`. It does not submit a task through the Compose stack (orchestrator, `worker-dsh-a`/`worker-dsh-b`, `tpl.local-dsh`). CI's `make workers-check` only starts `$(WORKERS)` with `PROFILE=openai` (Makefile:133-136), so neither the new `dsh-b`/`worker-dsh-b` pair nor a `default` submission is ever exercised in CI. The commits and phase file record no manual run either.
- Failure scenario: `worker-dsh-b` refuses (for example a pin or volume-permission problem specific to the second pair). `default` tasks then run on one slot, or wait on `tpl.local-dsh` if `dsh-a` also refuses. Every unit test still passes, and task 2.1 is ticked.
- Test that would expose it: `make workers-up`, then `make task PROFILE=default ...` and `make task PROFILE=openai ...`, asserting `template` = `local-dsh` / `local-default`, with the output recorded in the phase file. Also start a task on each pair, for example by stopping `worker-dsh-a` for the second task.

### F2 · Major · Task 2.2 verify / D6, notes.md#rollout: the revert walkthrough (drain across the switch) is not recorded or tested
- Location: `docs/operations/runbook.md` ("Switch `default` ... and back", "Drain"); phase file task 2.2 ticked at `phases/03-acceptance.md`.
- Promise: "Verify: a walkthrough reverts the switch, a DSH task started before it finishes on DSH, and a new task runs on `openai_agents`."
- The property spans a second deployment: a task already running while the registry and images change. Nothing in the range shows this was done. The runbook's own step 4 says that it also restarts the DSH workers ("An attempt in flight is lost and retried"). So "finishes on DSH" depends on a lost-attempt retry after a worker restart in the middle of a revert, and the range shows no evidence of that run.
- Failure scenario: the owner reverts with `make workers-up` while a `default` (DSH) task is mid-turn. Both DSH workers are recreated; the attempt is lost and retried. Without a recorded walkthrough, nobody has checked that the task completes on DSH, as opposed to failing on `resolve`/template checks or stalling, or that its result carries `usage_known: false` as the runbook states.
- Test that would expose it: run the walkthrough as written (start a long `default` task, revert `default.yaml`, `make workers-up`, submit a new `default` task), then record both task results (template, status, `usage_known`) in the phase file or a review note.

### F3 · Major · Task 1.1 / R19, R4: a partial run's pass count is judged against the full-suite baseline, and an unknown `--only` ID runs nothing yet "completes"
- Location: `tests/benchmarks/run.py:219` (`tasks = [t for t in TASKS if not args.only or t.id in args.only]`), `run.py:189-200` (`verdict_for`), `run.py:238-239` (stem `<date>-<profile>` in `args.out`); docstring example `run.py:304` `--only fizzbuzz --out /tmp/smoke`.
- The counter has the wrong scope: `passed` is counted over the selected subset, while `baseline.json["passed"]` (10) is counted over all 10 tasks. The verdict compares the two directly.
- Failure scenarios:
  1. `make benchmark ARGS="--profile dsh --only t01-order-total"` (without `--out`) passes 1 of 1. The verdict is `10 - 1 = 9 >= 2`, giving "Regression limit exceeded", and it overwrites the day's full 10-task `docs/benchmarks/<date>-dsh.{md,json}` record, the R19 evidence, with this 1-task file.
  2. The documented smoke command `--only fizzbuzz --out /tmp/smoke` matches no task ID (IDs are `t01-order-total`... in `tests/benchmarks/agent_tasks/tasks.py:158-260`). It runs 0 tasks, writes "Passed 0 of 0. Not judged", and exits 0. A smoke run done as documented "completes" without any task running on the profile, so task 1.1's Verify ("a one-task smoke run per profile ... completes") passes vacuously.
- Test that would expose it: a unit test that `main(["--only", "nope", "--out", tmp])` errors on an unknown ID, and that a subset run into `docs/benchmarks` is refused or not judged.

### F4 · Major · D5 / plan "after the owner approves the cost": the switch has no recorded owner approval or decision-log entry
- Location: `registry/profiles/default.yaml` (commit 3295e5a); `docs/roadmap/decision-log.md` (unchanged in range); plan.md `## Decision log` (no 2026-11-17 entry).
- Promise: D5, "switch `default` only after R19 and owner approval"; task 2.1, "Then, after the owner approves the cost, point `default` at `dsh`/`local-dsh`"; AGENTS.md, "Record changes to ... architecture ... in docs/roadmap/decision-log.md."
- Failure scenario: a later reader or verifier cannot tell whether the gate was met. The commit message of 3295e5a mentions no approval, and the `default` profile change is a production-default architecture change with no decision-log row. (Outside the scope lens, but a contract mismatch.)
- Fix or evidence: a decision-log row (and a plan decision-log line) recording the owner's approval and the measured cost (1.27x input tokens, 1.31x wall time).

## Nits

- `tests/benchmarks/run.py:257-262`: `--baseline` is accepted for any profile, so `--profile dsh --baseline` (or plain `--baseline` now that `default` is DSH) overwrites the openai-agents `baseline.json`. The plan defines the baseline rule against "baseline.json (10/10, openai-agents)", and R4/R19 are judged against it. Accepted silently. Nit because it needs a deliberate flag.
- `tests/benchmarks/run.py:207,238`: results are named by profile, so `<date>-default.*` meant `local-default` (openai_agents) until 2026-11-17 and means `local-dsh` from then on. A plain `make benchmark` no longer measures R4. The JSON's `template`/`harness` fields disambiguate, and overview.md names `--profile openai`, hence Nit.
- `.github/scripts/check_dsh_licences.py:60`: any non-empty file satisfies a pin. Notice contents are never compared with the pinned wheel, so a stale or wrong file passes R20's check. Nit: the version-qualified directory name forces a re-export on a version bump.
- `.github/scripts/check_dsh_licences.py:82-91`: `export` deletes `docs/licences/dsh/` before checking that every pin has `dist-info/licenses`. If one is missing, the export aborts with a partial tree. Nit: git restores it.
- `.github/scripts/check_dsh_licences.py` / R20 scope: the DSH image also pins `git=1:2.39.5-0+deb12u3` and the base Python image (`infra/dsh/Dockerfile:4,14`), and neither has notices. Nit because R20 is scoped to `infra/dsh/requirements.txt`.
- `pyproject.toml:42`: the new `check_dsh_licences.py` is not in mypy `files`, although the other `.github/scripts` checks are. Nit: tests import it, so mypy may still follow it.
- `docs/operations/runbook.md` "Drain": the 90-minute bound starts at `workflow.now()` after `resolve_capabilities` and `record_task` (each up to 5 SHORT attempts, `orchestrator/workflow.py:72-90`), so the real bound from submission is slightly longer. Nit: small, and the runbook says to check open tasks anyway.
- `docs/operations/runbook.md` "What runs where": says DSH takes "about 1.9x the wall time", but R19 measured about 1.31x (commit b3c378e). Nit: stale figure from the spike.
- `infra/docker-compose.yml` `dsh-b`: `depends_on: dsh-a` (only so that dsh-a builds the image) couples the second pair's container to the first pair's service. Starting `dsh-b` alone also starts `dsh-a`, which slightly contradicts "a refusing pair ... the other pair carries the load". Nit: `service_started` only, no health gate.
- `tests/test_compose_dsh_pairs.py:34`: checks only `network_mode` and `read_only` of each DSH container. `dsh-b` duplicates `dsh-a`'s `cap_add`, `cgroup`, `security_opt`, `tmpfs` and env by copy rather than anchor, so drift between the pairs would go unnoticed. Nit: identical today.
- `Makefile:165-168`: `make workers-up` now always starts the DSH pairs (SYS_ADMIN, AppArmor unconfined, private cgroup) with `--wait`. A host that cannot run the DSH container can no longer bring up the `openai` workers through this target. Nit: matches task 2.1's intent that workers-up starts both.
- `tests/benchmarks/run.py:63-77` (`paired_dsh`): there is no automated test of the DSH branch (container start, `DSH_CONTROL` wiring, teardown). Only `profile_template`/`harness_label` are unit-tested (`tests/test_benchmark_report.py:66-76`). Nit: the 2026-11-17 dsh run exercised it once.
- `plan.md` frontmatter: `adr_review: pending` changed to `null` (commit ea3d733). Not part of any phase 03 task. Nit: bookkeeping.

## Checked and holding

- Benchmark DSH pairing: one in-process worker (`tests/support/workers.py`) plus one container per run, with `DSH_CONTROL` set before `build_worker` reads it (`workers/main.py:93`) and removed in `finally`. The queue prefix is unique per run, so Compose workers never take the benchmark's tasks.
- The licence check removed/empty/stale cases are tested (`tests/test_dsh_licences.py`) and run in CI `lint` (`.github/workflows/ci.yml:52`).
- Each DSH pair has its own attempt volume that no other service mounts (`tests/test_compose_dsh_pairs.py`).
- The drain arithmetic matches the code: `max_wall_time = min(PT30M, PT1H)` (`orchestrator/activities.py:86`) plus `schedule_to_close = 6 x PT10M` (`orchestrator/workflow.py:127`) = 90 min.
- A profile edit leaves `registry/registry.lock` unchanged (the lock holds templates and runtimes only), as the runbook says.
- R4 and R19 results were recorded on the same day (2026-11-17), each 10/10. The `default` run used `local-default@1` / `openai-agents 0.24.0`, before the switch.

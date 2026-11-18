<!-- Verbatim subagent report (impl-review-phase-03-round-1-contract, 285dd44..89ac455, frozen at 89ac455); reviewers: fresh-subagent; saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Impl review, phase 03 (Acceptance and default switch), round 1, contract lens

Range: `285dd44..89ac455` (frozen at 89ac455). Contract: plan.md R4, R19, R20, D1-D11, phases/03-acceptance.md tasks 1.1-2.2, notes.md#rollout.

## Promise map

| Promise | Enforcing code | Test that fails without it |
|---|---|---|
| R4: `local-default` meets the baseline rule | `tests/benchmarks/run.py:188-200` (`verdict_for`); artifact `docs/benchmarks/2026-11-17-default.{md,json}` (10/10, `local-default@1`, `openai-agents 0.24.0`) | None in CI (by design: needs the real model). Recorded artifact only |
| R19: `local-dsh` meets the baseline rule | same verdict; artifact `docs/benchmarks/2026-11-17-dsh.{md,json}` (10/10, `local-dsh@1`) | None in CI (by design). Recorded artifact only |
| R20: every pinned DSH distribution has notices; a CI check | `.github/scripts/check_dsh_licences.py:40-64`; `ci.yml` lint step; `docs/licences/dsh/*` (7 dirs = 7 pins) | `tests/test_dsh_licences.py` (removed, empty, stale, normalised) |
| D5: `default` switches only after R19 and owner approval | `registry/profiles/default.yaml:6-7`; commit order b3c378e (benchmarks) before 3295e5a (switch) | `tests/test_registry.py:106-112` (resolution only). No recorded approval (F2) |
| Task 1.1: `--profile`, template from profile, label/name by profile, paired DSH container, `DSH_CONTROL` | `run.py:348-379, 440-486`; `tests/support/dsh_container.py` | `tests/test_benchmark_report.py:927-941` (template/label/verdict). Nothing covers the file name or `paired_dsh` (Nit) |
| Task 2.1: `openai` profile; listed tests/targets repointed; second pair | `registry/profiles/openai.yaml`; `Makefile:135,167`; `infra/docker-compose.yml:216-247,296-298` | `test_registry.py`, `test_runner_conformance.py` (R3 via `openai`), `tests/test_compose_dsh_pairs.py` |
| Task 2.2: runbook from notes.md#rollout | `docs/operations/runbook.md` | Walkthrough: no recorded evidence (F1) |
| R2 still enforced for the new profile | loader (unchanged) | `test_registry.py:93-97` now edits `openai.yaml` |
| R3 through `openai` | `test_runner_conformance.py:128,419,473` | the conformance suite |

## Findings

### F1 · Major · tasks 1.1, 2.1, 2.2 ticked without recorded verification · phase 03 Tasks, D5, rollout
- **Where:** `docs/plans/2026-11-15-dsh-production-harness/phases/03-acceptance.md:25-32`. The tasks are all `[x]`, but the diff adds no demo or evidence file. Compare `docs/demos/general-dsh-production-harness-02.md` for phase 02.
- **Contract:** 1.1 says "Verify: a one-task smoke run per profile, written outside `docs/benchmarks/` ... completes; its file name and `harness` label follow the profile." 2.1 says "Verify: CI passes; a `default` task runs on DSH and an `openai` task on `openai_agents`." 2.2 says "Verify: a walkthrough reverts the switch, a DSH task started before it finishes on DSH, and a new task runs on `openai_agents`." AGENTS.md says "Check a task off only after its tests, acceptance criteria and phase demo pass."
- **Failure scenario:** the revert walkthrough is the only check of the rollback promise ("Tasks already running stay on their template ... a switch back drains running DSH tasks on DSH"). If it was never run, a broken revert path ships unnoticed. F3 shows one way it breaks: CI goes red when someone follows the runbook. Nothing in the repository shows the walkthrough happened, and no automated test covers it. `test_default_profile_runs_on_dsh` only checks registry resolution, not a task running on DSH.
- **Evidence needed:** a phase-03 demo record with the smoke-run file names and labels, the task IDs and templates of the `default` and `openai` tasks, and the revert walkthrough (a pre-revert DSH task finishing on `local-dsh`, then a new `default` task on `local-default`).

### F2 · Major · owner approval of the switch is not recorded · D5
- **Where:** `registry/profiles/default.yaml:6-7` switches `default` to `dsh`/`local-dsh` (commit 3295e5a).
- **Contract:** D5 says "switch `default` only after R19 and owner approval." The Open questions say "The owner judges the R19 cost when approving the switch in phase 03 task 2.1." AGENTS.md says to record changes to acceptance criteria and architecture in the decision log.
- **Failure scenario:** the diff records the R19 cost (about 1.27x input tokens and 1.31x wall time, commit b3c378e message) but no approval. Neither the plan's decision log (`plan.md` decision log, unchanged apart from the header) nor `docs/roadmap/decision-log.md` has an entry. A later reader cannot tell that the gate in D5 was met. I can't verify whether the approval was given out of band.
- **Fix/test:** add a decision-log entry, dated, that names the approved cost and the switch commit.

### F3 · Major · the revert procedure fails CI as written · rollout, task 2.2
- **Where:** `docs/operations/runbook.md:52-76` (the switch and revert steps) and `tests/test_registry.py:106-112`.
- **Scenario:** the operator follows the runbook to revert: edits `default.yaml` to `harness: openai_agents`, `allowed_templates: [local-default]`, runs `make registry-lock` and opens the PR the repository requires (AGENTS.md: "Changes reach `main` only through pull requests"). `test_default_profile_runs_on_dsh` asserts `("dsh", "local-dsh")` for `default` and fails, so `ci-ok` is red. The runbook names no test to update. It also omits the `default.yaml` header comment and the `docs/architecture/overview.md` profile row that now assert DSH. The plan's rollout calls a revert "an edit, `make registry-lock`, a worker image rebuild and an orchestrator restart". As built, it is more than that.
- **Test that would expose it:** the task 2.2 walkthrough done through a branch and CI. Alternatively, make the test read the expected harness from the profile file, or document the test edit in the runbook.

### F4 · Major · `make demo-worker-loss` still assumes `default` runs on openai_agents · task 2.1 (universal "repoint ... Make targets that assume `default` is `local-default`")
- **Where:** `infra/demo/worker-loss.sh:21` submits with no `--profile`, so it uses `default` and now runs on `local-dsh`. `Makefile` `demo-worker-loss` target. `docs/demos/phase-1.md:13-14,49` documents this command as reproducing `local-default@1` on `worker-a`/`worker-b`.
- **Scenario:** with the stack up, `make demo-worker-loss` now kills a `worker-dsh-*` container, not `worker-a`/`worker-b`. The Phase 1 demo's documented reproduction ("`worker-b` killed; ... attempt 2 `done` on the other container") silently exercises a different harness, and its checkpoint-count wait (`CHECKPOINTS=2`) depends on DSH barrier timing. The task list names `make workers-check` and `make workers-up` but not this target, which has the same assumption.
- **Fix/test:** pass `--profile openai` in the script (or make it a parameter). Re-running the Phase 1 demo would expose the change.

### Nits
- `tests/benchmarks/run.py:440,497-503`: `--baseline` now records whatever profile is chosen, and `make benchmark ARGS="--baseline"` defaults to `default`, which is now DSH. The plan's baseline is "baseline.json (10/10, openai-agents)", so a re-baseline silently moves the R4/R19 reference to DSH. Consider refusing `--baseline` for non-`openai_agents` templates.
- `docs/benchmarks/2026-11-17-default.*`: named by profile, but `default` meant `local-default` at the time and means `local-dsh` now. Future `<date>-default` files mix harnesses, and a same-day `make benchmark` overwrites this one. The template field disambiguates it, so this is cosmetic.
- `tests/benchmarks/run.py:486`: no test asserts that the results stem follows the profile, or that `paired_dsh` sets and clears `DSH_CONTROL` (task 1.1). Only the label and the template are unit-tested.
- `tests/benchmarks/run.py:126-137`: R19/R4 "at most one task fails" is judged from the last checkpoint's workspace, not from `status`, so a task with `status: failed` but correct files counts as passed. All 20 recorded rows have `succeeded`, so the recorded results are unaffected. The logic predates this phase.
- `tests/benchmarks/run.py:131-136`: `tool_calls` sums `task_attempts.tool_calls`, which is cumulative per turn (`harness_activity/activity.py:104-137`, D11). A retried turn is therefore over-counted in the R19 cost record. No recorded run has a retried turn (attempts equal turns), and the logic predates this phase.
- `tests/benchmarks/run.py:140-147`: rows omit `usage_known`, so a run that includes D9 charges shows estimated tokens as if they were measured (D7). The R19 cost comparison cannot tell them apart.
- `tests/benchmarks/run.py:188-200`: `verdict_for` judges "lost vs baseline < 2", not "at most one task failed". The two are the same only while the baseline is 10/10. It is equivalent today.
- `.github/scripts/check_dsh_licences.py:43-45`: lines that are not `name==version` (for example `pkg @ url`) are skipped without an error, so an unpinned distribution would escape R20. `--require-hashes` and uv export make that unlikely today.
- `.github/scripts/check_dsh_licences.py:60`: the check only tests for a non-empty file, so a placeholder file satisfies R20. It cannot tell whether the notices match the wheel. `export` is the only source of truth.
- `tests/test_compose_dsh_pairs.py:969-981`: checks volumes, network and read-only, but not parity of `cgroup: private`, `cap_add`, `no-new-privileges` or `apparmor:unconfined` between `dsh-a` and `dsh-b` (D3 Compose settings). They match today; a drift would go unnoticed.
- `infra/docker-compose.yml:212-213`: `dsh-b` `depends_on: dsh-a`, so the pairs are not independent. Starting or recreating `dsh-b` brings up `dsh-a`. This qualifies the runbook's "the other pair carries the load" when `dsh-a` is the broken one.
- `docs/operations/runbook.md:29-31`: notes.md says "Deploy order: migration, orchestrator, then workers", but the runbook's single `make workers-up` starts the orchestrator and the workers together. Compose has no `depends_on: orchestrator`, so the order is not enforced. With the shared image this is probably harmless.
- `infra/observability/prometheus.yml`: scrapes only `orchestrator`, `worker-a` and `worker-b`. After the switch, `default` traffic runs on `worker-dsh-a`/`-b`, which are not scraped. This is outside the phase's stated scope.
- No integration test submits on `default` and asserts `template == local-dsh` end to end. Task 2.1's "a `default` task runs on DSH" is covered only by registry resolution (`test_registry.py:106-112`) and the unrecorded live check (F1).
- `docs/licences` is excluded from the offline link check (`ci.yml` lychee args). This is intended, but broken links in notices are no longer caught.

## Verdict
R20 is enforced and tested. R4 and R19 are met by recorded same-day artifacts, which by design are not CI-observable. The open issues are F1 (unrecorded task verification, including the rollback walkthrough), F2 (no recorded owner approval for D5), F3 (the revert procedure breaks CI) and F4 (one Make target still assumes `default` is `local-default`).

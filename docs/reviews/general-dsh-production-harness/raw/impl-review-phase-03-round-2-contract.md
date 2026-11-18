<!-- Verbatim subagent report (impl-review-phase-03-round-2-contract, targeted follow-up on 89ac455..d55f3ad, frozen at d55f3ad); reviewers: fresh-subagent; saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# impl-review · phase 03 · round 2 · contract lens

Diff 89ac455cf1474db179b04ff1b090b0447921fe4a..d55f3ad (frozen at d55f3ad). This is a targeted follow-up to round 1 (docs/reviews/README.md rule 6). Contract: plan.md (R4, R19, R20, D5, D6) and phases/03-acceptance.md tasks 1.1-2.2.

**Verdict: approve.** No Blocker or Major findings. Every fix marked `fixed` is in place at d55f3ad. Six Nits follow.

## Fixed findings checked

| ID | Enforced at d55f3ad | Test that fails without the fix |
|---|---|---|
| F166 | docs/demos/general-dsh-production-harness-03.md has rows for the 1.1 smoke runs on each profile, the 1.2 benchmarks, the 1.3 check, the 2.1 `default`/`openai` tasks, a task on each pair, the CI path, the 2.2 revert walkthrough (old task finishes on DSH, new task on `local-default`) and the restore. The numbers match docs/benchmarks/2026-11-17-*.json. | documentation |
| F167 | docs/roadmap/decision-log.md 2026-11-17 row and plan.md:241. The ratios match the recorded JSON: tokens_in 161518/126942 = 1.27, seconds 278.5/211.8 = 1.31. | documentation |
| F168 | runbook.md step 2 lists `test_default_profile_runs_on_dsh` (the only test that pins `default` to DSH: tests/test_registry.py:106-112), the profile comment, the runbook and overview rows, and a decision-log line. | documentation (but see Nit 1) |
| F169 | infra/demo/worker-loss.sh:20,24 set `PROFILE=${PROFILE:-openai}` and pass `--profile "$PROFILE"`. The Makefile defines no default `PROFILE` that would override it. | none (see Nit 4) |
| F170 | run.py `await_result` polls `workers.main.UNSERVICEABLE` (set by `stop_polling`, workers/main.py:166), then terminates the workflow and raises `WorkerStopped`. `main` breaks out of the loop and writes a "Not judged" result. | test_result_wait_stops_when_the_worker_stops_serving (`await_result` did not exist before) |
| F171 | run.py:262-266 refuse unknown IDs and a subset written to docs. | test_unknown_task_id_is_refused, test_subset_is_not_written_to_docs (the old code returned 2 instead of raising SystemExit) |
| F172 | run.py:268-272 | test_baseline_only_from_openai_agents |
| F174 | `write_results` stem; `paired_dsh` | test_results_are_written_as_tasks_finish (file name), test_paired_dsh_restores_dsh_control |
| F177 | row key `usage_known` and a "Usage known" column | test_report_has_every_required_column, test_results_are_written_as_tasks_finish |
| F179 | `read_pins` reports any line that is not indented, not a comment and not a pin. The real requirements.txt has only `name==version \` lines at column 0. | test_a_pin_not_written_name_equals_version_fails |
| F181 | compares dsh-a and dsh-b on network_mode, read_only, cgroup, cap_add, security_opt, tmpfs and environment | test_dsh_pairs_share_their_isolation_settings |
| F187 | `write_results` runs after each row (run.py main loop) | partially: see Nit 3 |
| F188 | `start_container` removes the attempt directory on `BaseException` and passes `--label praxismesh.dsh-test` | tests/test_dsh_container.py |
| F189 | `paired_dsh` restores an earlier `DSH_CONTROL` | test_paired_dsh_restores_dsh_control (the old `pop` fails the `/earlier` assert) |
| F190 | `replace_notices` checks every pin first, then stages the tree and swaps it in | test_export_keeps_notices_when_a_pin_has_none |
| F191 | runbook step 1 waits for each recent task's first attempt before step 4 | documentation |
| F192 | runbook: the launcher's start-up reap (infra/dsh/launcher.py:329-340, 441) cleans; tmpfs is not cleared | documentation, matches code |
| F195 | pyproject.toml mypy `files` | n/a |
| F196 | runbook: the bound counts from the first turn. Matches orchestrator/workflow.py:90 (deadline set after `resolve_capabilities` and `record_task`). | documentation (see Nit 5) |
| F197 | runbook says 1.3x and cites the 2026-11-17 benchmarks; the JSON gives 1.27x and 1.31x | documentation |

## Findings

No Blocker or Major findings.

### Nits

1. **Runbook revert checklist is incomplete (F168, D5/D6).** docs/operations/runbook.md step 2 leaves out other places that also say `default` runs on DSH: Makefile:120-121, infra/demo/worker-loss.sh:17-18, infra/docker-compose.yml:216, registry/profiles/dsh.yaml:1, registry/profiles/openai.yaml:1-2 and docs/architecture/overview.md:174. After a revert these comments are wrong, but CI stays green. Nit because the CI-red scenario that F168 described is fixed.
2. **Incremental writes overwrite committed R19/R4 evidence with partial results (R19, F187 fix).** run.py main writes `docs/benchmarks/<date>-<profile>.{md,json}` after each task with the verdict "Incomplete: n of 10". So an interrupted same-day run of `make benchmark ARGS="--profile dsh"` replaces the committed 10-of-10 file with a partial one. The old code wrote only at the end, so an interrupted run left the file untouched. Nit because F173 (same-day overwrite; git keeps history) was accepted.
3. **No test guards the per-task write in `main` (F187).** test_results_are_written_as_tasks_finish calls `write_results` directly. Deleting the per-task `write_results(...)` call in `main`'s loop fails no test. Likewise no test covers `main` catching `WorkerStopped` and writing a "Not judged" result (F170). Nit because the code is right at d55f3ad.
4. **No automated check that the Phase 1 demo stays on `openai` (F169).** Only the recorded rerun in the demo record covers infra/demo/worker-loss.sh. The demo row also gives no commit, although the record's header says commits are "noted per row". Nit because the demo is a manual script.
5. **"A few seconds" is not a bound (F196).** The runbook adds "the few seconds its first two Activities take after submission". When the orchestrator is down or restarting, `resolve_capabilities` and `record_task` wait on its queue for as long as that lasts. The deadline (workflow.py:90) then starts later. Nit because counting from the first turn, as the runbook says, is correct.
6. **Plan decision log out of date order (D5 record).** plan.md:241 adds the 2026-11-17 line above the 2026-11-16 design-review round 4 line (plan.md:242). Nit, cosmetic.

Not raised again: F173, F175, F176, F178, F180, F182-F186, F193, F194 and F198 (accepted). The recorded 2026-11-17 JSON rows have no `usage_known` because they predate the F177 fix. Under the rule for accepted findings this is noted, not raised.

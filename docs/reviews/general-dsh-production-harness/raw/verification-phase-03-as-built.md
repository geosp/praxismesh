<!-- Verbatim verifier report (verification-phase-03-as-built, code_sha d55f3add6dcb9e2db2d4bf3047f3bb78be0cfdf7, docs_sha 0e35ec61a4c1fe829515d105f5e0ecc90588db5c); fresh verifier subagent; saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# As-built documentation check: DSH migration phase 03

- Code under check: d55f3add6dcb9e2db2d4bf3047f3bb78be0cfdf7 (checkout `verify-03`, clean except `.verify/`).
- Documents read at 0e35ec61a4c1fe829515d105f5e0ecc90588db5c (`git show <rev>:<path>`). Between d55f3ad and 0e35ec6 only docs changed (runbook +4 lines, plan/reviews files); no code differs.
- Runtime: Compose project `verify03acc` (DB 25432, Temporal 27233, UI 28080, S3 28333), read through documented commands only (`make status`, `make task-status`, `docker compose ... ps/logs/exec`, `make benchmark` refusal paths that exit before contacting anything). Project `praxismesh` was not touched.
- Raw probe output in `.verify/asbuilt-0*.log`.

## Verdict

1 Major, 5 Nit. Every other claim was confirmed against code, and against the running stack where it describes runtime behaviour. The sections checked contain no diagrams.

## Findings (contradicted or unverifiable)

| # | Severity | Location | Claim (quoted) | Class | Evidence |
|---|---|---|---|---|---|
| F1 | **Major** | runbook.md:112-113 (Drain) and :145-147 (A DSH worker that refuses) | "Stopping the DSH pairs early leaves those tasks waiting on `tpl.local-dsh` until the pairs return." / "With both refusing, `default` and `dsh` tasks wait on the queue until a pair recovers or `default` is switched back." | contradicted | A queued turn waits at most `schedule_to_close_timeout=resolved.turn_timeout * 6` (orchestrator/workflow.py:127; 60 min for `local-dsh`, registry/templates/local-dsh.yaml:15). It then raises `ActivityError`, and the workflow ends the task as failed: `reason = f"harness turn {turns} failed: ..."; break` (workflow.py:136-148). So tasks wait only until a pair returns **or** about 60 min have passed since the turn was scheduled. Switching `default` back does not release tasks already on the queue: their template is fixed at submission (orchestrator/submit.py:33,47 `template=loaded.template.name`), as runbook.md:17-18 itself says. Only new submissions move. An operator who reads this during an outage could expect queued tasks to survive any outage length, or expect a switch back to rescue them. |
| F2 | Nit | overview.md:180 (Profiles row); runbook.md:83-84 (Lock step) | "The registry lock pins templates only, so a profile switch leaves it unchanged." / "The lock records template hashes only, so a profile edit leaves it unchanged; it matters if a template changed too." | contradicted (wording) | registry/registry.lock:8-9 also pins `runtimes: dsh: sha256:a842...` (written by registry/lock.py:47-64). The point that profiles are not locked holds, and `make registry-lock` after a profile-only edit is a no-op (`python -m registry.lock --check` exit 0). The lock also matters when the DSH runtime changes, not only a template. |
| F3 | Nit | demo general-dsh-production-harness-03.md:3 | "Independent verification (`verify-phase`) reproduces these and adds its own section." | contradicted (future stated as current) | At 0e35ec6 the file has no verification section: it ends with the implementer's table (line 18). This describes a step that is still to come. |
| F4 | Nit | demo general-dsh-production-harness-03.md:4, rows 9-18 | Implementer runs on the local stack `praxismesh` (task IDs `task-568d0776-…`, `task-92d9c95a-…`, `task-93c77f00-…`, etc.; 276 unit / 174 integration at 89ac455) | unverifiable | These are historical observations on another Compose project, which I was told not to touch. The cited commits exist and are ancestors of HEAD (47dcfc0, 3812efb, 3295e5a, 89ac455, b3c378e). Equivalent behaviour was observed on `verify03acc` (see confirmed items C25-C29). The "both DSH pairs serve concurrently" row was not reproduced: that needs task submissions, which are not read-only. |
| F5 | Nit | decision-log.md:9 (2026-11-17) | "The owner stated \"The cost is acceptable.\" before the switch commit (3295e5a)." | unverifiable | No repository artefact records the statement other than this row and plan.md:242, which cites the decision log. 3295e5a exists ("Switch the default profile to DSH…"). The figures in the row are confirmed (C22). |
| F6 | Nit | demo row 2.2 "switch restored": "`/attempts` empty in `dsh-a` and `dsh-b`" | confirmed with caveat | `docker compose exec dsh-a ls -A /attempts` lists `.control.sock` only (same for `dsh-b`). There are no attempt trees, but the volume is not literally empty: the control socket is always there. |

Not counted as a finding: the phase 02 section of overview.md (:143, :168) still says "`default` still runs `openai_agents`; the switch, the `openai` profile and the second DSH pair are phase 03". The section's opening sentence explicitly supersedes this ("Phase 03 (below) switches `default` and supersedes the statements here about what phase 03 would add"), and phase 03 does cover all three items. The supersession sentence is confirmed. The bullet is still in the present tense, though, so a reader who jumps straight to "Known limits" sees a stale statement.

## Confirmed claims

### overview.md, phase 03 section

| # | Claim | Code evidence | Runtime evidence |
|---|---|---|---|
| C1 | `default` and `dsh` resolve to `local-dsh` (`harness: dsh`); `openai` resolves to `local-default` (`harness: openai_agents`) | registry/profiles/default.yaml:7-8, dsh.yaml:6-7, openai.yaml:6-7; registry/loader.py:123 (first allowed template); tests/test_registry.py:106-112 | `make task-status ID=task-9efe0581-…`: `"profile": "default", "template": "local-dsh"`; `task-47a34c54-…`: `"profile": "openai", "template": "local-default"` (asbuilt-03). In the running orchestrator image, `/app/registry/profiles/default.yaml` has `harness: dsh`, `allowed_templates: [local-dsh]` |
| C2 | Two pairs `dsh-a`/`worker-dsh-a`, `dsh-b`/`worker-dsh-b`, Compose profile `dsh` | infra/docker-compose.yml:185-248 | `make status`: `dsh-a Up`, `dsh-b Up`, `worker-dsh-a Up (healthy)`, `worker-dsh-b Up (healthy)` (asbuilt-01) |
| C3 | Each pair has its own attempt volume that no other service mounts | compose:195,207,227,241 | `docker inspect`: `dsh-a`/`worker-dsh-a` mount only `verify03acc_dsh-attempts-a:/attempts`, and `dsh-b`/`worker-dsh-b` only `…-b`. No other container mounts either volume. Both volumes are `{"type":"tmpfs","o":"size=2g,mode=1770,gid=4243"}` (asbuilt-02) |
| C4 | `make workers-up` builds and starts orchestrator, `worker-a`, `worker-b` and both pairs | Makefile:122-127 (`--profile workers --profile dsh up -d --build --wait … $(WORKERS) $(DSH_WORKERS)`) | All 7 services up (asbuilt-01) |
| C5 | `make workers-check` submits on `openai` against the fake model | Makefile:132-136 (`VLLM_BASE_URL=http://fake-model:8765`, `task PROFILE=openai`) | — |
| C6 | Benchmark `--profile` (default `default`) takes the template from the profile | tests/benchmarks/run.py:254, 61-63, 267 | Raw run output `.verify/bench-results/2026-11-18-default.md`: "default (local-dsh@1)" |
| C7 | For a `dsh` template the benchmark builds the DSH image and starts its own paired container | run.py:89-107; tests/support/dsh_container.py:59-67 | `bench-results/2026-11-18-dsh.md`: `harness \| deepseek-harness-sdk 0.2.2rc2` |
| C8 | Results go to `docs/benchmarks/<date>-<profile>.{md,json}`, rewritten as each task finishes | run.py:57, 241-246, 291-293 (`Incomplete: n of m`) | — |
| C9 | `--out` writes elsewhere and is not judged | run.py:259, 227-228 | `smoke-*/…md`: "Not judged against the baseline (written outside docs/benchmarks)." |
| C10 | Unknown `--only` ID refused; a subset must use `--out`; `--baseline` openai_agents only | run.py:260-272 | `make benchmark ARGS="--only nope --out …"` → "error: unknown task IDs: nope"; `ARGS="--only t01-order-total"` → "error: --only runs a subset, which is never judged: write it elsewhere with --out"; `ARGS="--baseline --profile dsh"` → "error: --baseline: the baseline is an openai_agents run; profile 'dsh' runs dsh"; each exit 2 (asbuilt-07) |
| C11 | If the worker stops serving, the run terminates the waiting task and stops, unjudged | run.py:74-86 (`handle.terminate`, `WorkerStopped`), 287-309 ("**Not judged:** …", exit 1); workers/main.py:161-167 (`UNSERVICEABLE`) | not exercised (it would need a refusing DSH container) |
| C12 | Containers it starts carry label `praxismesh.dsh-test` | dsh_container.py:35, 182, 48 (`--label`, LABEL) | `docker ps -a --filter label=praxismesh.dsh-test` → none left (asbuilt-04) |
| C13 | Same-day 2026-11-17: `dsh` and `default` (then `openai_agents`) each 10 of 10 | docs/benchmarks/2026-11-17-dsh.json (`local-dsh@1`, passed 10 of 10), 2026-11-17-default.json (`local-default@1`, `openai-agents 0.24.0`, 10 of 10); at 3812efb default.yaml had `harness: openai_agents` | — |
| C14 | Licence notices in `docs/licences/dsh/` for each pinned distribution | 7 directories match the 7 pins in infra/dsh/requirements.txt | `uv run .github/scripts/check_dsh_licences.py` → "licence notices present for 7 pinned DSH distributions" (asbuilt-05) |
| C15 | CI `lint` fails on a pin with no notices, an empty notice directory, or a stale notice directory; `export` refreshes from the DSH image | check_dsh_licences.py:66-74, 78-113; ci.yml:40-53 (`lint` job runs the script) | tests/test_dsh_licences.py passes (asbuilt-08) |
| C16 | The offline link check skips `docs/licences` | ci.yml:238 `--exclude-path 'docs/licences'` | — |
| C17 | Unit tests cover profiles, Compose pairs, the benchmark report and the licence check | tests/test_registry.py, test_compose_dsh_pairs.py, test_benchmark_report.py, test_dsh_licences.py | `uv run pytest` on these: "44 passed" (asbuilt-08) |
| C18 | `make demo-worker-loss` submits on `openai`, override with `PROFILE=` | infra/demo/worker-loss.sh:19,24 | A scratch Makefile check shows that a command-line `PROFILE=dsh` reaches the script's environment ("PROFILE=dsh"); with no override the script falls back to "PROFILE=openai" |
| C19 | Rebuilding the worker image restarts DSH workers; the in-flight attempt is lost and retried; the task reports `usage_known: false` | compose: `worker-dsh-*` use `praxismesh-worker:dev` | `make task-status ID=task-458373dd-…` (revert walkthrough on this stack): attempt 1 `73708d28104f@1/local-dsh lost lost_or_timed_out`, attempt 2 `de54591be9be@1/local-dsh done`, `usage_known False` (asbuilt-06). After the last `workers-up`, `worker-dsh-*` show "Up 3 minutes" and `dsh-a/b` "Up 9 minutes" |
| C20 | Phase 02 deferred items remain | ledger.py:80 ("unresolved usage" denial, no timer); runner.py:494 `request("poll")` with no `wait_for`; plan notes.md:161 | — |

### runbook.md

| # | Claim | Evidence |
|---|---|---|
| C21 | Profile table (:11-15) | as C1, C2; `worker-a`/`worker-b` run `["template","local-default"]` (asbuilt-02) |
| C22 | A pair runs one attempt at a time; DSH about 1.3x wall time and input tokens; two pairs as there were two openai workers (:20-24) | local-dsh.yaml:21 `concurrency_per_pod: 1` → workers/main.py:159 `max_concurrent_activities`. From the 2026-11-17 JSON: tokens_in 161518 / 126942 = 1.27, seconds 278.5 / 211.8 = 1.31 (also confirms decision-log.md:9) |
| C23 | Template fixed at submission; a profile change never moves a running task (:17-18) | submit.py:33,47; the workflow uses `resolved.task_queue`. Observed: task-458373dd, submitted on `default` before the revert, finished on `local-dsh` |
| C24 | Deploy: `make migrate`; migration 0004 needed by both harnesses (:30-31) | 0004_dsh_usage_and_sessions.py:34-56 adds `task_attempts.usage_known`, which the shared AttemptRepository writes (repositories.py:184-211). `alembic current` → "0004 (head)". (`make migrate` was run once: a no-op at head) |
| C25 | `make workers-up` also builds `praxismesh-dsh:dev` (:33-34) | compose:187-188 (`dsh-a` has `build`), Makefile:126 `--build`; `dsh-a image=praxismesh-dsh:dev` |
| C26 | Check: result `template` is `local-dsh` for `default` and `local-default` for `openai` (:35-43) | `.verify/45-task-default.log` result `"template": "local-dsh"`, `45-task-openai.log` `"template": "local-default"`; confirmed by task-status (asbuilt-03) |
| C27 | Profile resolves twice (submitter, orchestrator); a rejected template fails for good (:56-62) | submit.py:33; orchestrator/activities.py:75; `CapabilityError` is NonRetryable (common/errors.py:15; workflow.py:29-32) |
| C28 | Switch table and the files that state the harness (:63-81) | default.yaml header and values; `test_default_profile_runs_on_dsh` at tests/test_registry.py:106. `git grep -n default -- registry/profiles infra Makefile` hits the three profile files, docker-compose.yml:216, worker-loss.sh:17-18 and Makefile:121, plus unrelated `TEMPORAL_NAMESPACE=default` hits |
| C29 | Lock: `make registry-lock`; CI fails on a stale lock (:83-85) | Makefile:117-118; tests/test_registry.py:35 `test_registry_lock_is_current` (run by CI pytest); `python -m registry.lock --check` exit 0 (wording caveat: F2) |
| C30 | The registry ships in the worker image; `workers-up` restarts the orchestrator and the workers whose image changed (:86-88) | workers/Dockerfile:21 `COPY registry registry`; observed restart pattern under C19 |
| C31 | The lost attempt is retried with no repeated side effect; `usage_known: false` (:97-100) | task-458373dd: orders SKU-4×2, SKU-5×1, SKU-2×3, SKU-1×1, each once; `usage_known False` |
| C32 | Drain bound: wall time + 6 × `turn_timeout` = 30 + 60 = 90 min from the first turn, plus the first two Activities (:104-108) | workflow.py:74-90 (deadline set after `resolve_capabilities` and `record_task`), 105-108 (checked only before a turn), 127; activities.py:86 `min(profile PT30M, cap PT1H)`; local-dsh.yaml:15 `PT10M` |
| C33 | Refusal: exit 1 with `CapabilityError` at start-up; "worker cannot serve its queue" and exit 3 during a turn; no attempt spent; stops polling (:115-124) | workers/main.py:92-101, 161-167, 188 (`EXIT_UNSERVICEABLE = 3`); activity.py:228-243 (`record_refusal`, `refusals += 1`, log message); runner.py:274-301 |
| C34 | Compose restarts the worker (:126) | compose `restart: unless-stopped`; inspect: `restart=unless-stopped` on `worker-dsh-a/b` |
| C35 | Causes: pin mismatch, dirty container, unreachable launcher; the launcher reaps at start (:132-141) | runner.py:295-301 (dirty, pin), 279-290 (unreachable); launcher.py:18, 329 `reap()`. Runtime: `dsh-a`/`dsh-b` logs `{"launcher": "ready", "reaped": []}` |
| C36 | `dsh-b` depends on `dsh-a` only for the image build (:143-145) | compose:229-230. `dsh-b` shares no volume or network with `dsh-a` (`network_mode: none`, own volume) |
| C37 | Known deviations F103/F106/F111 (:151-155) | as C20 |
| C38 | Upstream barrier follow-up; R18 test file; licence export command (:157-172) | tests/integration/test_dsh_outcomes.py exists; export as C15 |

### tests/benchmarks/run.py module docstring

All confirmed: usage lines (Makefile:144-145; `--profile` default `default` at :254); "first allowed template" (loader.py:123); paired DSH container (:89-107); final workspace read from the last checkpoint and checked (:153-156); output path and rewriting (:241-293); `--out` not judged and `--only` requires `--out` (:259, :265-266; C10); regression limit of 2 or more fewer (:58, :233); baseline from openai_agents only (:268-272); stopped worker ends the run unjudged (:74-86, :302-309).

### decision-log.md 2026-11-17 row

`default` on DSH (`local-dsh@1`), new `openai` profile (`local-default@1`), two DSH pairs: confirmed (C1-C3). Both 10 of 10, 1.27x tokens, 1.31x wall time: confirmed (C13, C22). Switch commit 3295e5a exists. Owner quote: unverifiable (F5).

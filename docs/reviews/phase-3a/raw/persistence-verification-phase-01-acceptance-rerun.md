<!-- Verbatim verifier report (Phase 3A persistence plan, phase 01 gate verification, acceptance re-run after the F1 docs fix; code bbfe1ce, docs dc83f97); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-acceptance-rerun.md per docs/reviews/README.md rule 1. -->

# Phase 3A phase 01 acceptance re-run: integration suite, smoke, refusal-log test

- Checkout: verify-phase3a-01 at bbfe1ceb5cdc5e36138a4d9fbdbc10d117259844 (`git rev-parse HEAD` printed that SHA; `git status --short` showed only `?? .verify/`)
- Documentation: README.md at dc83f97669fa592cc4f80b9b49906a1e5ccf471a, section "Local stack" (read with `git show dc83f97...:README.md`)
- Stack: Compose project `pmverify3a` (from `COMPOSE_PROJECT_NAME=pmverify3a` in infra/.env; DB port 55432; VLLM_BASE_URL=http://spark-01:8000, VLLM_MODEL=spark). I did not touch any `praxismesh-*` container or volume.
- Environment: the calling shell had `VIRTUAL_ENV=/home/geo/develop/praxismesh/.venv` and that `.venv/bin` on PATH. I unset VIRTUAL_ENV and removed the PATH entry in every command below.
- Logs: <checkout>/.verify/rerun/ (make-*.log, integration.log, smoke.log, loop-int-N.log, loop-unit-N.log)

## 1. Preparing the stack and running the integration tests

### Steps run, with their source in the documentation

| # | Step | Source in README (dc83f97) "Local stack" | Exit | Observed |
|---|---|---|---|---|
| 0 | `cp infra/.env.example infra/.env`: **not run** | code block, line 1 | n/a | infra/.env was already in place, with its own `COMPOSE_PROJECT_NAME` and ports as the "Several checkouts" paragraph requires. Copying the example over it would have pointed the run at the owner's ports and project. |
| 1 | `make up` | code block, "start and wait until healthy (safe to repeat)" | 0 | `stack is up; run 'make status' for addresses and health` |
| 2 | `make status` | code block | 0 | `model endpoint: http://spark-01:8000 answers /v1/models` / `all services healthy` |
| 3 | `make migrate` | code block, "apply application database migrations" | 0 | `INFO  [alembic.runtime.migration] Will assume transactional DDL.` (already at head) |
| 4 | `make workers-down` | paragraph after the code block: "Run `make smoke`, or `uv run --env-file infra/.env pytest -m integration`, with the worker containers stopped (`make workers-down`)" | 0 | `Container pmverify3a-orchestrator-1 Removed` (all 7 worker/dsh/orchestrator containers removed). Afterwards `docker ps` listed only `pmverify3a-temporal-ui-1`, `pmverify3a-temporal-1`, `pmverify3a-s3-1`, `pmverify3a-db-1`. |
| 5a | `uv run --env-file infra/.env pytest -m integration -rs` | same paragraph | **1** | see below |
| 5b | `make smoke` | code block and same paragraph | 0 | see below |

Steps the run needed that the documentation does not mention: **none found**. The documented sequence (up, status, migrate, workers-down, then tests) was enough, and no undocumented action was needed. Unsetting VIRTUAL_ENV was a condition of this brief caused by the calling shell, not a step the stack needs, so I do not count it as a documentation finding.

### 1a. Full integration suite: FAIL (1 failure)

Command: `uv run --env-file infra/.env pytest -m integration -rs`. Expected: all pass, with no unexplained skips.

Observed: exit status `exit=1`. Summary line:

```
========== 1 failed, 278 passed, 372 deselected in 880.94s (0:14:40) ===========
```

Nothing was skipped: `-rs` printed no skip summary. The one failure:

```
____________________ test_refusals_are_logged_with_ids[dsh] ____________________
...
        refusals = {line["msg"]: line for line in lines if line["msg"].startswith("refused")}
>       assert refusals["refused tool call"]["tool"] == "delete_database"
E       KeyError: 'refused tool call'
tests/test_runner_conformance.py:422: KeyError
```

`tests/test_runner_conformance.py ..............F..........` was the last file in the run. Every file under tests/integration passed, including `test_recovery.py .....` and `test_persistence_phase1.py .................`.

### 1b. `make smoke`: PASS

Observed: exit status `exit=0`. Summary line:

```
======================= 249 passed in 763.05s (0:12:43) ========================
```

There were no FAILED or SKIPPED lines. `make smoke` runs `pytest -m integration tests/integration --ignore=tests/integration/test_recovery.py` (Makefile line 109). So it does not include tests/test_runner_conformance.py, and it cannot show the 1a failure.

## 2. `test_refusals_are_logged_with_ids`, 10 runs per parameter

Loop: for i in 1..10, run
- `uv run --env-file infra/.env pytest -m integration "tests/test_runner_conformance.py::test_refusals_are_logged_with_ids" -rs` (collects `[dsh]` only, confirmed with `--collect-only -q`: `tests/test_runner_conformance.py::test_refusals_are_logged_with_ids[dsh]`);
- `uv run --env-file infra/.env pytest "tests/test_runner_conformance.py::test_refusals_are_logged_with_ids"` (default addopts `-m 'not integration'`, so it collects `[openai_agents]` only: `tests/test_runner_conformance.py::test_refusals_are_logged_with_ids[openai_agents]`).

The workers were stopped throughout, as in step 1.

| Parameter | Passed | Evidence |
|---|---|---|
| `dsh` | **10/10** | every run: `exit=0 ======================= 1 passed, 1 deselected in 4.4xs ========================` (runs 1-10: 4.44s, 4.42s, 4.40s, 4.45s, 4.45s, 4.38s, 4.45s, 4.48s, 4.46s, 4.43s) |
| `openai_agents` | **10/10** | every run: `exit=0 ======================= 1 passed, 1 deselected in 2.2xs/2.3xs ========================` |

`grep -l KeyError loop-*.log` matched nothing.

Conclusion: run on its own, `test_refusals_are_logged_with_ids[dsh]` passes every time (10/10). In the full `-m integration` run it fails. So the failure depends on what runs before it in the same session: an earlier test changes some shared state, which makes the refused-tool-call WARNING missing from `caplog` for the `praxis.harness` logger. A likely cause is logging configuration (handlers or propagation) left behind by an earlier test. I have not verified this; it is a lead only. I did not isolate the earlier test that interferes.

## 3. Leaving the stack as found

- `make workers-up`: exit 0. The output includes `Container pmverify3a-orchestrator-1 Healthy`, `Container pmverify3a-worker-a-1 Healthy`, `Container pmverify3a-worker-b-1 Healthy` and `Container pmverify3a-worker-dsh-b-1 Healthy`.
- `make status`: exit 0. db, s3, temporal, temporal-ui, orchestrator, worker-a, worker-b, worker-dsh-a and worker-dsh-b are `(healthy)`; dsh-a and dsh-b are `Up`. The output ends with `all services healthy`. The stack is still running.

## Findings

1. **F1 (blocking for 1a):** the full integration suite as documented (`uv run --env-file infra/.env pytest -m integration -rs`, workers stopped) exits 1: `test_refusals_are_logged_with_ids[dsh]` fails with `KeyError: 'refused tool call'`. The test passes 10/10 on its own, so this is a test-isolation or order-dependence defect, not a lone flake. The suite cannot be counted as passing until it is fixed.
2. **F2 (coverage note):** `make smoke` excludes tests/test_runner_conformance.py and tests/integration/test_recovery.py. A green `make smoke` (as CI runs it) therefore does not catch F1.
3. No documentation gaps found: every step needed came from the README at dc83f97.

Verdict: FAIL. 1a: full integration suite 278 passed, 1 failed (test_refusals_are_logged_with_ids[dsh], order-dependent; it passes 10/10 on its own). 1b: make smoke passed (249 passed). No undocumented steps were needed. The stack was restored and is healthy.

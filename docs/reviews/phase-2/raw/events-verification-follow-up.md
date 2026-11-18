<!-- Verbatim verifier report (Phase 2 events, phase 01 gate verification, docs follow-up, code 499eb63, docs 965e8e8); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-follow-up.md per docs/reviews/README.md rule 1. -->

# Phase 2 events: targeted follow-up (docs at 965e8e8, code at 499eb63)

Read-only: code reads, `psql` SELECTs on `pmverify2-db-1` (db `praxismesh`), files already in `.verify/`. No tests run, nothing built, no `praxismesh-*` resource touched.

## 1. schemas.md, `reset` row: confirmed
- Code: `harness_activity/activity.py:429-430` emits `reset` with `restored_from=latest.checkpoint_id if latest else None` as the attempt's first event. `:449-450` emits `reset(restored_from=None)` when the attempt fails before that (`events.seq == 0`). If the fence refuses the attempt at start, `:410-412` raises `Superseded` before the publisher exists (`:414`), so nothing is stored. If the attempt limit is passed, `:269-270` raises `AttemptsExhausted` before `_attempt` is called.
- Probe: across the 48 real-task attempts (`task-<uuid>`, not counting the pruned `task-a70928e4`), 48 of 48 have exactly one `reset`, at seq 0. Observed payloads are `{"restored_from": null}` and `{"restored_from": "task-…:1:1:0"}`. The only logs without a `reset` are synthetic ones (`task-load-*`, `task-test-*`, `wf-test-*`, `task-spike76-capture`), whose events were not written by the Activity, plus one pruned log.

## 2. schemas.md, `status` row: confirmed
- Code: every success path emits `status=result.status` (the runner's result) at `activity.py:618` in `_finish`, before the flush, finish checkpoint and outcome write. A failure emits `_failure_status(e)` (`:452`, `:677-683`), which is `{"status": "failed"|"cancelled", "error": <class or category>}`. `Superseded` is excluded at `:451`. When `_finish` is superseded, `publisher.close()` returns `FenceRejected` (`:621-622`), so the `status` event is not stored. A killed worker reaches no emit.
- Probe: 42 of 48 attempts end with exactly one `status`, at max(seq). 6 have no `status`, 0 have more than one. Observed values: `done`, `continue`, `needs_input`, `failed/<error>` (for example `failed/DshUsageUnknown`), `cancelled/CancelledError`, `cancelled/DshCancelled`. Every failure value carries `error`.

## 3. phase-2-events.md, prune output: confirmed for the format, the specific run is unverifiable (low)
- Code: `orchestrator/cli.py:281` prints `json.dumps({"task_id": args.task, "retained_base": base})`, which matches the documented key order. `cli.py:193` prints `expired: events before N were pruned`. `cli.py:196` prints the payload with `sort_keys=True`, so `{"call": 4, "tool": "lookup_price"}` matches.
- Probe: the documented task `task-f2492737-…` was recorded on the `praxismesh-*` stack, which is off-limits. It has 0 rows in `pmverify2`, so that run cannot be re-observed. Equivalent run in this stack: `.verify/demo/prune.json` is `{"task_id": "task-a70928e4-430c-429c-8d15-f04b6e54505f", "retained_base": 10}`. `event_logs` has `retained_base=10` for that task, and offset 10 is `tool_call {"tool": "lookup_price", "call": 4}`.
- Severity: low. The output shape is proven, and only the literal task ID is untested here.

## 4. overview.md, Phase 2 events "Tests" bullet: confirmed
- `tests/test_event_publisher.py` and `tests/test_event_transport.py` exist. The CLI tail and prune tests are at `tests/test_cli.py:122,132,140,175`.
- Conformance: `tests/test_runner_conformance.py:71` parametrizes `[openai_agents, pytest.param("dsh", marks=pytest.mark.integration)]`, and the event test is at `:559`. `pyproject.toml:50` has `addopts = "-ra -m 'not integration'"`, so plain `uv run pytest` runs only `openai_agents`.
- CI stack job (`.github/workflows/ci.yml:103-121`) runs smoke, restart-check, unhealthy-check, workers-check and recovery-check. `make smoke` runs `pytest -m integration tests/integration` (Makefile:105). The conformance file is in `tests/`, not `tests/integration/`, and the Makefile never mentions "conformance" (count 0). So the stack job does not run the `dsh` case.

Result: 3 confirmed, 1 confirmed in format with the specific recorded run unverifiable (low). Nothing contradicted.

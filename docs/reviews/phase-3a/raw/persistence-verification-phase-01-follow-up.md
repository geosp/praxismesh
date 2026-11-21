<!-- Verbatim verifier report (Phase 3A persistence plan, phase 01 gate verification, as-built follow-up of the corrected statements; code and docs 56c0170); reviewers: fresh-subagent (verifier); copied unchanged by the coordinator from .verify/report-follow-up.md per docs/reviews/README.md rule 1. -->

# Phase 3A persistence phase 01: narrow follow-up verification (docs at 56c0170)

Checkout HEAD = 56c0170872fd14efa3f7902779284b9a32d382ba (`git rev-parse HEAD`), tree clean apart from `.verify/`.
Docs read with `git show 56c0170:<path>`. No tests run, no images built. The probes were read-only: `docker ps`/`inspect`, and `psql` SELECTs on `pmverify3a-db-1`, database `praxismesh`. No `praxismesh-*` container was touched.

## 1. README.md "Local stack": workers stopped for `make smoke` (README.md:93, :100). Confirmed
- Dispatcher in the orchestrator container: compose `orchestrator` uses `command: ["orchestrator"]` (infra/docker-compose.yml:139). The entrypoint is `python -m workers.main` (workers/Dockerfile:31). workers/main.py:197-199 starts `Dispatcher(...).run()` for role `orchestrator`. The dispatcher selects and `DELETE FROM message_wakes` rows (orchestrator/dispatcher.py:88, :97).
- Probe: `pg_stat_activity` shows `172.21.0.10|idle|LISTEN "message_wakes"`, and 172.21.0.10 is `pmverify3a-orchestrator-1`'s IP (`docker inspect`). `select count(*) from message_wakes` returns 0 with the workers up.
- Why tests fail otherwise: the messaging tests assert wake rows exist, e.g. tests/integration/test_messages.py:184, :210, :217. A live dispatcher would delete those rows.
- `make workers-down` removes `orchestrator worker-a worker-b` and the DSH workers (Makefile:126-127, :157-159). `make smoke` is `pytest -m integration tests/integration --ignore=...test_recovery.py` (Makefile:108-109), which is the same suite as the `pytest -m integration` alternative apart from recovery.
- CI order: `make up`, `make migrate`, `make smoke`, ..., `make workers-check` (.github/workflows/ci.yml:117-122). `make up` starts only `SERVICES := db temporal temporal-ui s3` (Makefile:30, :65-66), so no workers are running when smoke runs. Confirmed.

## 2. docs/roadmap/schemas.md:41-43: "All three carried retention class `task` until migration 0007, which moved ...". Confirmed
- Code: 0005_agent_events.py:11 and :35 give server_default `'task'` for all three tables. 0007_blob_refs_and_classes.py:60-62 gives event_logs/agent_events `transcript` and event_batches `ephemeral`, each with old default `task`, and OLD_CLASS (:77-79) is `task` for all three.
- Probe: alembic_version `0007`. Column defaults: `agent_events|'transcript'`, `event_batches|'ephemeral'`, `event_logs|'transcript'`. Row classes: `ev|transcript|10335`, `el|transcript|384`, `eb|ephemeral|5136`.

## 3. docs/architecture/overview.md:75, `run_harness_turn`: outputs are `artifact`-class (`audit` before 0007). Confirmed
- Code: harness_activity/activity.py:693 `self.blobs.put(data, retention="artifact", task_id=turn.task_id)`. Before b1c36a9 (#94) the parent had `retention="audit"` at line 691 (`git show b1c36a9^:harness_activity/activity.py`).
- Probe: `blob_refs` has `tasks|artifact|133` and `blob_objects` has `artifact|17`. This is consistent with the code, but it does not tie these rows to this activity specifically.

## 4. docs/architecture/overview.md:204, "Event tables": all listed in `APP_TABLES`; since 0007 transcript/ephemeral (`task` before). Confirmed
- Code: common/persistence/retention.py:53 `APP_TABLES = tuple(TABLE_CLASS)`. TABLE_CLASS lists `event_logs` and `agent_events` as `transcript` and `event_batches` as `ephemeral`. The "before" class is confirmed in item 2.
- Probe: the same defaults and row classes as item 2. The CHECK constraint on all three now allows `ephemeral, checkpoint, transcript, artifact, audit, task`.

## Result
All 4 statements are confirmed. None is contradicted or unverifiable.

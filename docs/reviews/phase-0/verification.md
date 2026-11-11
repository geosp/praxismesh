---
review: verification
phase: 0
change: openspec/changes/phase-0-local-infrastructure
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 075791ab7de4c39b7cd0d21f29fbd7dca7a1d597
docs_sha: 075791ab7de4c39b7cd0d21f29fbd7dca7a1d597
diff_base: n/a
session: fresh            # light tier: shared with the implementation review, independence between them waived per §7.0
date: 2026-11-11
verdict: fail
reviewers:
  - { lens: acceptance and demo (verifier), status: completed }
  - { lens: as-built claims (verifier), status: completed }
---

# Verification: Phase 0 local infrastructure

Gate mode, light tier. This fresh session first ran `review-implementation` (`docs/reviews/phase-0/implementation-review.md`) and then this verification against the same `code_sha`; independence between the two is knowingly waived (§7.0). Neither verifier was given the implementation review's findings or verdict.

The as-built documentation landed in the same commit as the code, so `docs_sha` = `code_sha` = `075791a` (phase file, light-tier application).

## Inputs

- **Checkout:** a disposable `git worktree` at `075791a` (detached), commit date 2026-11-11T12:30:06-05:00, removed after the run.
- **Requirements:** `docs/plan/phases/phase-0.md` (tasks, Accept, Demo checklist); `docs/rfcs/phase-0-local-infrastructure.md` ("Testing and demo", traceability table).
- **Setup and demo instructions:** README "Local stack"; `docs/demos/phase-0.md` (demo steps only); the RFC "Testing and demo" section.
- **As-built documentation:** `docs/architecture/overview.md` at `docs_sha`.
- **Environment:** x86_64 workstation, Docker 29.9.2, Compose v5.7.0, uv 0.13.5, Python 3.11.17. Model endpoint: the DGX Spark endpoint (vLLM, served names `qwen3.8-flash-next` and `spark`), set in the checkout's git-ignored `infra/.env` as the README instructs; its URL is not recorded here.
- **Isolation (coordinator deviation from the documented commands):** `infra/docker-compose.yml` fixes `name: praxismesh`, so `make reset` in a second checkout would delete the main checkout's volumes. Every `make` and `docker compose` command in the checkout ran with `COMPOSE_PROJECT_NAME=praxismesh-verify`. The main checkout's stack was stopped first with `make down` (data kept); its volumes `praxismesh_pgdata` and `praxismesh_seaweeddata` were still present after cleanup. See finding V7.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Prerequisites | `uv sync --locked`; `cp infra/.env.example infra/.env`; set `VLLM_BASE_URL`; `make reset` | Documented steps suffice | All exit 0; `infra/.env` is git-ignored (`.gitignore:2`). No undocumented step was needed for the stack | pass |
| Clean start | `make up` on a clean volume | All services healthy, jobs exit 0 | Exit 0 in 16.7 s: `stack is up: Temporal 127.0.0.1:7233, UI http://127.0.0.1:8080, S3 http://127.0.0.1:8333, DB 127.0.0.1:5432` | pass |
| Repeat start | `make up` again | Succeeds | Exit 0, same line | pass |
| Migrations | `make migrate` twice | Head on a clean volume; second run applies nothing | `Running upgrade  -> 0001, Baseline: empty application schema.`, `Running upgrade 0001 -> 0002, Require the pg_search extension (ADR-0002).`; second run printed no upgrade lines | pass |
| Integration suite | `make smoke` | All pass | Exit 0, `15 passed in 2.55s`, no skips (blob store 1, database 4, env check 4, model endpoints 5, temporal 1) | pass |
| Integration suite, CI path | `make smoke VLLM_BASE_URL=` | Model tests skipped | Exit 0, `12 passed, 3 skipped` (`VLLM_BASE_URL is unset or empty; model endpoint not configured`) | pass |
| Unit suite | `uv run pytest` | All pass, replay included | Exit 0, `84 passed, 15 deselected`; `test_hello_replay PASSED` | pass |
| Restart check | `make restart-check` | State survives `make down` / `make up` | Exit 0 in 32 s: `seeded Workflow phase0-restart-cb94960a1c9b and s3://phase0-restart-cb94960a1c9b/seed.txt` ... `restart-check: PASS (revision 0002, Workflow and object survived)` | pass |
| Demo 1: healthy services | `make status` | "healthy Temporal, PostgreSQL, SeaweedFS, and vLLM services (with no hidden manual setup)" | `db`, `s3`, `temporal`, `temporal-ui` `Up … (healthy)`; `temporal-namespace`, `temporal-schema` `Exited (0)`; `all services healthy`; `model endpoint: <DGX Spark endpoint> answers /v1/models` | pass |
| Demo 2: hello Workflow in the UI | `curl http://127.0.0.1:8080/`; UI API `GET /api/v1/namespaces/default/workflows?query=WorkflowType="HelloWorkflow"` | "show its completed status in Temporal UI" | UI root HTTP 200; `phase0-hello-910217e6b64c HelloWorkflow WORKFLOW_EXECUTION_STATUS_COMPLETED` (plus two more). Shown through the UI's HTTP API; a headless screenshot rendered blank (V6) | pass |
| Demo 2: real prompts | `curl` to `/v1/models`, `/v1/messages`, `/v1/chat/completions` on the DGX Spark endpoint, model `spark` | Both API styles answer | Models `['qwen3.8-flash-next', 'spark']`. Messages: `stop_reason end_turn`, "Temporal is an open-source workflow engine that enables developers to build reliable, scalable applications…". Chat: `finish_reason stop`, "SeaweedFS is an open-source distributed file storage system designed for high scalability…" | pass |
| Demo 3: object and state survive a restart | boto3 put `s3://verify-demo/demo.txt` (27 bytes); `make down`; `make up`; list, history, `make migrate`; get, delete | Object and Workflow history remain; download and delete | After restart: `list [('demo.txt', 27)]`; `phase0-hello-910217e6b64c` history `11 events … EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED`; `make migrate` applied nothing; `get … matches: True`, `after delete KeyCount: 0`, `bucket deleted; buckets now: []` | pass |
| Demo 4: missing `infra/.env` | `make up` with the file moved aside; `make up ENV_FILE=infra/.env.absent` | Names the missing file | `error: infra/.env is missing; create it with: cp infra/.env.example infra/.env` (make exit 2; see V3) | pass |
| Demo 4: unset variable | `make up` with `APP_DB_PASSWORD=` | Names the variable | `error: APP_DB_PASSWORD is not set in .verify/env.unset` | pass |
| Demo 4: `db` stopped | `docker compose stop db`; `make status`; `make smoke`; recovery `make up` | `make status` names `db`; `make smoke` names the database | `db Exited (0)`, `unhealthy or stopped: db`. `make smoke` exit 2, `5 failed, 10 passed`: `RuntimeError: database server (service db) at 127.0.0.1:5432 is unreachable; check make status: [Errno 111] Connect call failed ('127.0.0.1', 5432)`. Recovery: `make up` exit 0, `all services healthy`, `make smoke` `15 passed` | pass |
| Demo 4: model endpoint unreachable | `make smoke VLLM_BASE_URL=http://127.0.0.1:9` | Model tests fail naming it | Exit 2, `3 failed, 12 passed`: `EndpointUnreachableError: model endpoint http://127.0.0.1:9 is unreachable: ConnectError('[Errno 111] Connection refused')`; `make status`: `model endpoint: http://127.0.0.1:9 is unreachable` | pass |
| Demo: resources | `docker stats --no-stream` | Under 6 GB | `temporal-ui` 14.3 MiB, `temporal` 93.6 MiB, `s3` 163.8 MiB, `db` 96.8 MiB, about 368 MiB | pass |
| Revisions | `git cat-file -t 075791a`; `git branch -r --contains 075791a` | Commit on the remote | `commit`; `origin/main` | pass |
| Docs describe this code | `git diff --stat <code_sha> <docs_sha> -- . ':!docs'` | Empty | Empty (same commit) | pass |
| CI on `code_sha` (informational) | `gh api repos/{owner}/{repo}/commits/075791a/check-runs` | - | `ci-ok`, `stack`, `tests`, `lint`, `types`, `secrets`, `links`, `workflows`, `openspec`, `agents-sync` success; `licenses` skipped | pass |
| Secrets | `git grep -nIE '<token patterns>' 075791a`; grep for the DGX Spark endpoint host | No secrets; endpoint not committed | One hit: the pattern itself in `.agents/skills/verify-phase/SKILL.md:76` (false positive). The endpoint host does not occur in the tree | pass |
| Transcripts | `git ls-tree -r --name-only 075791a \| grep -iE '\.jsonl$\|transcript'` | None | Three `spikes/harness-vllm/results/*.jsonl` files, added in `13841d7` (Pre-0 spike, before this phase). They hold per-task harness metrics (task, tool counts, usage, final answer), not session transcripts | pass |
| Teardown | `make reset` in the checkout (`praxismesh-verify`); `git worktree remove --force`; `git worktree prune` | Clean | Verify volumes and network removed; worktree removed; main checkout's volumes intact | pass |

## As-built claims

Every claim in `docs/architecture/overview.md` § "Phase 0: local infrastructure" was checked against the code and, for runtime behavior, against the running stack. Confirmed claims are summarized by group; contradicted and unverifiable claims are listed one by one.

| Claim (quoted) | Location | Status | Evidence |
|---|---|---|---|
| "ParadeDB's own bootstrap installs eight extensions (including `pg_search`, `vector`, `postgis` and `pg_cron`) into `template1`" | overview.md line 29 (same wording in decision-log.md line 10) | contradicted | `template1` holds `fuzzystrmatch, pg_ivm, pg_search, pg_stat_statements, plpgsql, postgis, postgis_tiger_geocoder, postgis_topology, vector`: eight plus `plpgsql`, no `pg_cron`. The image's `10_bootstrap_paradedb.sh` installs `pg_cron` in `postgres` only. Re-checked by the coordinator with `psql -d template1`. The bootstrap also creates a `paradedb` database, which the document does not mention |
| "Observed idle memory after the smoke tests (`docker stats`): about 275 MB for the four long-running services" | overview.md line 49 | contradicted | Three samples on this run: about 368 MiB, about 400 MiB and about 408 MiB (`s3` alone 164-176 MiB). Far below the 6 GB budget; the recorded figure is a single implementer measurement |
| "from a clean volume it takes about 15 s once images are pulled" | overview.md line 36 | confirmed | Acceptance run: `make up` on a clean volume took 16.7 s |
| "when init failed partway, Docker restarted `db`, the entrypoint skipped init on the existing volume, and `db` stayed unhealthy" | overview.md line 30 | unverifiable | Labelled as observed during implementation; reproducing it needs a deliberately failing init on a fresh volume. Code is consistent: `init.sh` uses `set -euo pipefail` and writes the marker last; `healthcheck.sh` requires it; `restart: unless-stopped` |
| "**Describes:** `aa3889b` on branch `feat/34-local-stack`" | overview.md line 7 | unverifiable (traceability) | The merged commit is `075791a`. `git diff --stat aa3889b 075791a` shows no change under `infra/`, `common/`, `tests/`, `Makefile` or `pyproject.toml`, so the description holds for `075791a` |
| Components: project `praxismesh`; `db` ParadeDB `0.26.6-pg16` (PostgreSQL 16.15) with the marker health check; `temporal-schema` (admin-tools 1.32.2, `setup-schema -v 0.0` + `update-schema` for both databases, exits 0); `temporal` 1.32.2 single process with frontend, history, matching and worker, no `temporal` CLI, HTTP `cluster-info` health check; `temporal-namespace` (describe, create if absent, wait); `temporal-ui` 2.58.1 health check on `/`; `s3` SeaweedFS 4.53 single `weed` process with S3 on 8333 and `/healthz`; volumes `pgdata`, `seaweeddata`; `unless-stopped` for services and `no` for jobs; vLLM external | overview.md "Components" | confirmed | `infra/docker-compose.yml` (images pinned by digest, ports and policies), container logs, health endpoints (`cluster-info` reports `1.32.2`; UI and `/healthz` HTTP 200), `which temporal` absent in the server image |
| Ports bound to 127.0.0.1 only (5432, 7233, 8080, 8333) | overview.md "Components", "Known limitations" | confirmed | `compose ps` shows only `127.0.0.1:` bindings |
| Databases `temporal`, `temporal_visibility`, `praxismesh` from `template0`, CONNECT revoked from PUBLIC and held by the owner only; app role refused on the Temporal databases | overview.md "Data and isolation" | confirmed | `pg_database` ACLs `{=T/<owner>,<owner>=CTc/<owner>}`; `FATAL: permission denied for database "temporal"` (and `temporal_visibility`) |
| Extensions per database: `temporal` `plpgsql`; `temporal_visibility` `plpgsql`, `btree_gin`; `praxismesh` `plpgsql`, `vector`, `pg_search` (CASCADE) | overview.md line 29 | confirmed | `pg_extension` queries; `init.sh` `CASCADE` |
| Init marker; `PDB_TUNE=false` | overview.md "Data and isolation" | confirmed | `shobj_description` = `praxismesh-init-complete`; `shared_buffers` 128MB |
| Alembic with async env (SQLAlchemy 2.1.8, Alembic 1.20.1, asyncpg 0.32.0); revisions `0001` (empty) and `0002` (`pg_search` check); settings from the environment | overview.md "Data and isolation" | confirmed | `alembic history` `0001 -> 0002 (head)`, `alembic current` `0002 (head)`; `uv.lock` |
| `make up`, `make status`, `make smoke`, `make restart-check` behavior | overview.md "Commands" | confirmed | `Makefile` and runs above; `make status` "not configured" and "unreachable" branches exercised with temporary env copies |
| Tests: unit run with replay; integration content; CI `stack` job required by `ci-ok` | overview.md "Tests" | confirmed | `84 passed, 15 deselected`; `ci.yml` `stack` job, `ci-ok` `needs`, `ci_gate.py` `REQUIRED_JOBS` |
| Known limitations: placeholder passwords, no TLS or auth, init only on a fresh volume, retention not reapplied, GCS and Ceph documented only, model tests skipped in CI | overview.md "Known limitations" | confirmed | `.env.example`, `init.sh`, `namespace.sh`, README, `ci.yml` |

The section has no diagrams. Namespace retention was observed as 72h (`WorkflowExecutionRetentionTtl 72h0m0s`, UI API `259200s`), matching `TEMPORAL_RETENTION`.

## Findings

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| V1 | Nit | as-built | `docs/architecture/overview.md` line 29; `docs/plan/decision-log.md` line 10 | Contradicted claim: `pg_cron` is installed in `postgres`, not `template1`. Expected: the listed examples are in `template1`. Observed: no `pg_cron` in `template1` | Fix (docs) | open |
| V2 | Nit | as-built | `docs/architecture/overview.md` line 49 | Contradicted claim: "about 275 MB" idle memory. Observed about 368-408 MiB across three samples. Budget conclusion unaffected | Fix (docs: give a range or the measurement date) | open |
| V3 | Nit | acceptance | `docs/demos/phase-0.md` step 5 | The missing-`.env` case is recorded as "exit 1"; `make` exits 2 (the script exits 1, `make` reports `Error 1`) | Fix (docs) | open |
| V4 | Nit | acceptance | `docs/demos/phase-0.md` steps 3-4; README | No documented command for "send a real prompt to each endpoint" or "upload / download / delete an object"; the verifier wrote its own `curl` and boto3 calls, so these steps are not reproducible exactly from the docs | Fix (docs) | open |
| V5 | Nit | acceptance | RFC "Testing and demo" step 5; `docs/demos/phase-0.md` | `docker compose stop db` does not resolve the project from the repository root; it needs `-f infra/docker-compose.yml --env-file infra/.env` (the demo doc writes `docker compose ... stop db`) | Fix (docs) | open |
| V6 | Nit | acceptance | Demo checklist item 2 | "Completed status in Temporal UI" was shown through the UI's HTTP API, not a rendered page or screenshot (the checklist mentions screenshots or recording) | Accept or add a screenshot | open |
| V7 | Nit | coordinator | `infra/docker-compose.yml` line 9 (`name: praxismesh`) | Any second checkout (worktree, verification) shares the project name, so its documented `make reset` deletes the first checkout's volumes. This run avoided it with `COMPOSE_PROJECT_NAME`; nothing documents that | Fix (docs, or allow a project-name override in `infra/.env`) | open |
| V8 | Nit | acceptance | `Makefile` `status`; `tests/integration/test_temporal.py` | `make status` exits 0 when a service is unhealthy. With `db` stopped, `temporal` stays healthy and `test_hello_workflow` fails with `RPCError: Timeout expired` rather than naming the database (the database tests do, as the RFC requires) | Fix | open |
| V9 | Nit | as-built | `docs/architecture/overview.md` line 7 | "Describes" names the pre-merge commit `aa3889b`, not `075791a`; no source difference between them | Fix (traceability) | open |
| V10 | Nit | as-built | `docs/architecture/overview.md` line 30 | Partial-init recovery claim unverifiable without a deliberately failing init; code is consistent | Accept as unverifiable | open |

## Verdict

**fail.** Every acceptance test and every demo step passed with observed output against the live stack and the DGX Spark endpoint, and the evidence checks are clean. The verdict is decided by the `verify-phase` rule "fail if an as-built claim is contradicted": two claims in `docs/architecture/overview.md` are contradicted (V1, V2). Both are Nit-severity documentation errors with no effect on behavior; correcting them is a docs-only change, which under the coordinator approval gate needs only the affected doc checks (a re-verification of those claims in a new session) and latest-head CI, not a repeat of the code checks.

Demo evidence: this run's observed demo results are recorded in the Checks table above. `docs/demos/phase-0.md` (the implementer's run) was not rewritten, because this session does not edit the reviewed work; V3-V5 list its corrections.

## Open items

- V1, V2: correct the two contradicted as-built claims, then re-check them in a new session.
- V3-V10: Nits for the implementer.
- Unverifiable: V10 (partial-init recovery).
- The main checkout's stack was left stopped (`make down`, data kept); restart it with `make up` when needed.

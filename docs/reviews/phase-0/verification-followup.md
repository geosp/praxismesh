---
review: verification
phase: 0
change: openspec/changes/phase-0-local-infrastructure
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 61c40ef50b5b062527d953f70eed3689254723be
docs_sha: 61c40ef50b5b062527d953f70eed3689254723be
diff_base: n/a
session: fresh            # light tier: shared with the targeted implementation follow-up, independence between them waived per §7.0
date: 2026-11-11
verdict: fail
reviewers:
  - { lens: acceptance and demo (verifier), status: completed }
  - { lens: as-built claims (verifier), status: completed }
---

# Verification (targeted follow-up): Phase 0 local infrastructure

Gate mode, light tier, **targeted follow-up** under `docs/reviews/README.md` rule 6. This report is scoped to the changes in `075791a..61c40ef`:

- the as-built claims that changed in `docs/architecture/overview.md` (including V1 and V2), the top decision-log rows and the changed demo lines;
- `make up`, `make migrate`, `make smoke`, `make restart-check`, `make unhealthy-check`;
- the README's "Trying the services by hand" commands;
- probes of the behavior the fixes changed.

This fresh session ran the targeted implementation review (`implementation-review-followup.md`) first; independence between the two is waived (§7.0). Neither verifier was given the review's findings or verdict.

The fix landed docs and code in one commit, so `docs_sha` = `code_sha` = `61c40ef`.

## Inputs

- **Checkout:** a disposable `git worktree` at `61c40ef` (detached, commit date 2026-11-11T14:12:41-05:00), removed after the run.
- **Requirements:** `docs/plan/phases/phase-0.md`; RFC "Testing and demo"; `specs/dev-environment/local-stack/spec.md` at `61c40ef`.
- **Setup and demo instructions:** README "Local stack" (including "Several checkouts", "When things go wrong", "Trying the services by hand"); `docs/demos/phase-0.md`.
- **Environment:** x86_64 workstation, Docker 29.9, Compose v5.7. Model endpoint: the DGX Spark endpoint, set in the checkout's git-ignored `infra/.env`; its URL is not recorded here.
- **Isolation:**
  - The main checkout's stack (project `praxismesh`, default ports) stayed running throughout and was never touched.
  - Following README "Several checkouts", the checkout's `infra/.env` (copied from `infra/.env.example`) set `COMPOSE_PROJECT_NAME=praxismesh-verify` and ports DB 15432, Temporal 17233, UI 18080, S3 18333.
  - `make -n reset` was confirmed to resolve to `-p praxismesh-verify` before any destructive command.
  - Every probe whose project could resolve to `praxismesh` was run only as `make -n`.
- **Coordinator upgrade probe:** a second disposable worktree, project `praxismesh-upg`, ports 25432/27233/28080/28333. It started the stack at `075791a`, moved the checkout to `61c40ef`, then ran `make down` and `make up`. It was torn down and removed afterwards.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Prerequisites | `uv sync --locked`; `make -n reset`; `make reset` | Documented steps suffice | `Installed 42 packages`; `docker compose -p praxismesh-verify down --volumes --remove-orphans`; `No resource found to remove for project "praxismesh-verify"`. No undocumented step needed | pass |
| Clean start | `make up` | Healthy, jobs exit 0 | Exit 0, 17.2 s: `stack is up: Temporal 127.0.0.1:17233, UI http://127.0.0.1:18080, S3 http://127.0.0.1:18333, DB 127.0.0.1:15432` | pass |
| Repeat start | `make up` | Succeeds | Exit 0, 2.1 s | pass |
| Status | `make status` | All healthy | Four services `(healthy)`, both jobs `Exited (0)`, `model endpoint: <DGX Spark endpoint> answers /v1/models`, `all services healthy`, exit 0 | pass |
| Migrations | `make migrate` twice | Head, then no change | `-> 0001`, `0001 -> 0002`; second run no upgrade lines | pass |
| Integration suite | `make smoke` (endpoint set) | All pass, no skips | Exit 0, `27 passed in 3.17s` | pass |
| Restart check | `make restart-check` | PASS | Exit 0, 34.5 s: `restart-check: PASS (repeat start changed nothing; revision 0002; Workflow and object survived)`. temporal-schema log: `Current database schema version 1.19 is greater than initial schema version 0.0. Skip version upgrade`, `found zero updates` | pass |
| Unhealthy check | `make unhealthy-check` | PASS | Exit 0, 8.5 s: `unhealthy-check: PASS (make status and the smoke test named the stopped db)`; `make status` afterwards `all services healthy` | pass |
| Unit suite | `uv run pytest` | Pass, replay included | `84 passed, 27 deselected`; `tests/test_hello_replay.py .` | pass |
| README: Messages prompt | curl `/v1/messages` as written, after `set -a; . infra/.env; set +a` | Answers | `"stop_reason":"end_turn"`, "Hello! How can I help you today?" | pass |
| README: chat prompt | curl `/v1/chat/completions` as written | Answers | `"finish_reason":"stop"`, same greeting | pass |
| README: object put/get/delete | boto3 snippet as written | Round trip | `b'hello'`, exit 0 | pass |
| README: stop one service | `docker compose -p "$COMPOSE_PROJECT_NAME" --env-file infra/.env -f infra/docker-compose.yml stop db` | Stops this checkout's `db` | `Container praxismesh-verify-db-1 Stopped`; `praxismesh-db-1` stayed up. `make status`: `unhealthy or stopped: db` (make exit 2). `make smoke`: `database server (service db) at 127.0.0.1:15432 is unreachable`, `9 failed, 18 passed`. Recovery `make up` and `make status` healthy | pass |
| Changed retention | `make up TEMPORAL_RETENTION=96h`; then `make up` | Updated, then restored | Job log `default has retention 259200s; updating to 96h`, `Namespace default update succeeded.`. DescribeNamespace 4 days. Then `updating to 72h`, DescribeNamespace 3 days. Through an env-file copy with `5d`: 5 days, restored | pass |
| Retention rejected by server | `make up TEMPORAL_RETENTION=1s` | Non-zero, naming the failure | Exit 2: `error: job temporal-namespace exited with 1; see: make logs`. The cause is only in the job log (`namespace update failed: A valid retention period is not set on request.`). Retention unchanged | pass (Nit VF7) |
| `.env` syntax: quoted value | `make up ENV_FILE=<copy with APP_DB_PASSWORD="s3cr#t">` | Rejected, naming the line | `error: … line 42: use KEY=value with no quotes, …`, exit 2 | pass |
| `.env` syntax: line without `=` | `KEY http://x`; `KEY foo` | Rejected, naming the line | First: check-prereqs names line 42. Second: Make stops first with `…:42: *** missing separator.  Stop.` (also for `down`/`reset`) | pass (Nit VF8) |
| `.env` syntax: comment ending in `\` | `# …\` followed by `TEMPORAL_RETENTION=96h`; and by `COMPOSE_PROJECT_NAME=praxismesh-verify` | Rejected, or read identically by Make and Compose (spec) | `check-prereqs.sh` exit 0. Make sees `TEMPORAL_RETENTION` undefined while Compose applied 96h (`make up` exit 0, `updating to 96h`; restored). In front of the project name: `make -n reset` resolves to `-p praxismesh`, another checkout's project | **fail (VF1)** |
| Project-name resolution | `make -n reset` in four variants | Each checkout acts only on its own project | `make -n reset` gives `praxismesh-verify`. `COMPOSE_PROJECT_NAME=other make -n reset` gives `praxismesh-verify` (file wins over environment). `make -n reset COMPOSE_PROJECT_NAME=other` gives `other`. `make -n reset ENV_FILE=/nonexistent` gives **`praxismesh`**, no warning | **fail (VF2)** |
| CI log step | `bash -e -c '<ci.yml "Stack logs on failure" command>'`, healthy and with `db` stopped | Prints logs | Healthy: logs printed, project resolved from the env file (`praxismesh-verify`). `db` stopped: `make status` exits 2, **0 log lines** | fail (Nit VF3) |
| Upgrade of a `075791a` volume (coordinator) | Stack at `075791a`; checkout to `61c40ef`; `make down`; `make up` | Repeat start succeeds, or documented step | Before: marker on `praxismesh`, `postgres` uncommented. `make up` failed after the 180 s wait: `error: the stack did not become healthy … If database init failed or its passwords changed, run 'make reset'`; `make status`: `unhealthy or stopped: db temporal temporal-ui`. Without recreating the containers, `make up` passed: the bind-mounted health script kept its old inode | fail (Nit VF10) |
| Revisions | `git cat-file -t 61c40ef`; `git branch -r --contains 61c40ef` | Commit on the remote | `commit`; `origin/main` | pass |
| Docs describe this code | `git diff --stat <code_sha> <docs_sha> -- . ':!docs'` | Empty | Empty (same commit) | pass |
| CI on `code_sha` (informational) | `gh api repos/{owner}/{repo}/commits/61c40ef/check-runs` | - | `ci-ok`, `stack`, `tests`, `lint`, `types`, `secrets`, `links`, `workflows`, `openspec`, `agents-sync` success; `licenses` skipped | pass |
| Secrets | `git grep -nIE '<token patterns>' 61c40ef`; search for the endpoint host | None | Only the pattern itself in `.agents/skills/verify-phase/SKILL.md:76`. Endpoint host not in the tree | pass |
| Transcripts | `git ls-tree -r --name-only 61c40ef \| grep -iE '\.jsonl$\|transcript'` | None | The three Pre-0 spike metric files `spikes/harness-vllm/results/*.jsonl` (unchanged since the earlier verification; not transcripts) | pass |
| Teardown | `docker compose -p praxismesh-verify down --volumes`; same for `praxismesh-upg`; `git worktree remove --force`; `git worktree prune` | Clean; main stack untouched | Both projects' volumes and networks removed; worktrees removed. `praxismesh_pgdata` and `praxismesh_seaweeddata` present; main stack still `Up (healthy)`; main working copy clean | pass |

## As-built claims

Claims on lines changed in `075791a..61c40ef` in `docs/architecture/overview.md`, the top decision-log rows and the changed lines of `docs/demos/phase-0.md`.

| Claim (quoted) | Location | Status | Evidence |
|---|---|---|---|
| "ParadeDB's own bootstrap installs extensions (including `pg_search`, `vector` and `postgis`) into `template1`, and `pg_cron` into `postgres`" (V1) | overview "Data and isolation"; decision log row 3 | confirmed | `template1`: fuzzystrmatch, pg_ivm, pg_search 0.26.6, pg_stat_statements, plpgsql, postgis 3.6.4, postgis_tiger_geocoder, postgis_topology, vector 0.8.6. `postgres`: the same plus pg_cron 1.6. `paradedb`: same as `template1` |
| "275 MiB in the implementer's run, 368-408 MiB in the verification run, 349 MiB in three samples after the gate fixes … It varies with activity; all are far under the 6 GB budget" (V2) | overview "Resource use"; demo step 6 | unverifiable (historical figures), consistent | This run: 323.8 / 325.1 / 327.7 MiB over the four long-running services. Varies as stated; far under 6 GB |
| Marker is `COMMENT ON DATABASE postgres`; "Only the superuser can change it" | overview "Data and isolation"; overview `db` row | confirmed | `pg_database` comment on `postgres` = `praxismesh-init-complete`; `db` healthy. App role in a rolled-back transaction: `must be owner of database postgres` |
| "`CONNECT` on these three and on `postgres` is revoked from `PUBLIC` and granted only to the owning role"; the observed "permission denied" pairs | overview "Data and isolation" | confirmed | ACLs show no PUBLIC `c`. `praxismesh` denied on postgres, temporal, temporal_visibility; `temporal` denied on postgres, praxismesh. Not covered by the claim: the `paradedb` database keeps PUBLIC CONNECT, and both roles can connect (VF11) |
| "prefixed with the Compose project name … from `COMPOSE_PROJECT_NAME` (default `praxismesh`), so separate checkouts can run separate stacks" | overview "Components" | **contradicted** (partly) | Volumes `praxismesh-verify_pgdata` and `_seaweeddata` alongside `praxismesh_*`, so separate stacks do run. But a checkout whose `infra/.env` is absent, mistyped or carries a comment ending in `\` silently falls back to `praxismesh`, and an environment override is ignored (VF2, VF1) |
| "`make down` and `make reset` work by project name alone, so they run even when `infra/.env` is missing or invalid" | overview "Commands"; `Makefile:19-20` comment | **contradicted** | Missing: they run, but against the default `praxismesh` (`make -n reset ENV_FILE=infra/.env.absent` gives `-p praxismesh`), not the checkout's own project. Invalid: a line Make cannot parse stops both with `missing separator` |
| `check-prereqs.sh` rules: Docker running, Compose plugin, file present, plain `KEY=value` (no quotes, spaces, `#`, `$`, `\`, backticks), required variables non-empty, `VLLM_MODEL` without `/`, `TEMPORAL_RETENTION` as `<number><s\|m\|h\|d>` | overview "Commands" | confirmed, with one gap | Probes on env copies: each listed character, `export`, `KEY = v`, CR line ending and lowercase key rejected with the line number. Empty and missing variables named. `org/m` rejected. `72`, `3w`, `0h` rejected; `3d` accepted. Docker and Compose checks confirmed in code only. Gap: comment lines are not checked (VF1) |
| Jobs checked with `docker wait`, limited to 120 s | overview "Commands" | confirmed | `Makefile:25, 55` |
| "`make status` … names any unhealthy or stopped service with exit status 1"; decision log "(3) `make status` exits 1" | overview "Commands"; decision log row 1 | contradicted (Nit) | The recipe exits 1 (`Makefile:80`); `make status` returns **2** to the caller (observed). The demo record words the analogous case correctly (VF4) |
| `make status` sends `VLLM_API_KEY` when set | overview "Commands" | confirmed | `Makefile:71` |
| Namespace job: "creates … if absent, updates the retention if it differs, fails naming a failed create or update; exits once `namespace describe` shows the configured retention" | overview `temporal-namespace` row; decision log row 1 (1) | confirmed | `namespace.sh`; job logs for update, unchanged and failed-update paths (Checks above). The create path was exercised by the clean start |
| Restart check snapshots both Temporal databases' `schema_version` and `schema_update_history` and the namespace description around a repeat `make up`; "a repeated `setup-schema -v 0.0` logs 'Skip version upgrade' and changes no rows" | overview "Tests" | confirmed | `restart_check.py`; PASS; schema job log quoted above |
| Unhealthy check: stops `db`, `make status` non-zero naming `db`, database test names the server, then restarts | overview "Tests" | confirmed | `unhealthy_check.py`; PASS |
| Integration list: 30 s execution timeout, at most 3 Activity attempts, retention test, UI on host port, wrong S3 secret, role isolation both ways, migrate hint, rejected `.env` syntax, model tests | overview "Tests" | confirmed | `27 passed`. Code at `tests/support/stack.py:64`, `hello.py:28`, `test_temporal.py`, `test_blob_store.py`, `test_database.py`, `test_env_check.py` |
| Fixed identity `phase0-smoke-worker`, "recorded histories carry no hostname" | overview "Tests" | confirmed | `stack.py:23`; the fixture carries only that identity |
| CI `stack` job runs up, migrate, smoke, restart-check and unhealthy-check; required by `ci-ok` | overview "Tests" | confirmed | `ci.yml:102-124`; `ci_gate.py` |
| "**Describes:** `main` at `075791a` (PR #36), updated … by the branch `fix/34-phase-0-gate-findings` …; the commit that merges it is the one to verify" | overview line 7 | unverifiable (traceability), consistent | `61c40ef` is the single-parent squash of PR #38 on `main`, descending from `075791a`; the line names no commit itself (VF12) |
| Decision log row 1: three RFC behavior changes, marker move, configurable project name; `0002` stays on the main chain | decision log | confirmed for behavior | Retention applied (observed), syntax enforced (with the VF1 gap), `make status` fails when unhealthy, marker on `postgres`, project name configurable (with VF2), `0002` `down_revision = "0001"` |
| Demo: missing `.env` "the script exits 1 and `make` exits 2" (V3) | demo step 5 | confirmed | `make up ENV_FILE=infra/.env.absent`: `make: *** [Makefile:41: check] Error 1`, rc 2 |
| Demo: database-stopped command `docker compose -p praxismesh …` | demo step 5 | confirmed as a record; hazard | It names the implementer's project. Copied into another checkout, it stops that other stack's `db` (VF5) |

## Findings

| ID | Severity | Reviewer | Location | Expected / observed | Action | Resolution |
|---|---|---|---|---|---|---|
| VF1 | **Major** | acceptance | `infra/check-prereqs.sh:35`; `Makefile:9-12` | Spec: `infra/.env` is read identically by Make and Compose, and other syntax is rejected naming the line. Observed: a comment ending in `\` passes the check, and Make drops the next line while Compose reads it. Retention 96h was applied by Compose while Make saw it undefined. Before `COMPOSE_PROJECT_NAME`, `make reset` resolves to another checkout's project. Same as review R2 | Fix | open |
| VF2 | **Major** | acceptance, as-built | `Makefile:16-21, 61-65`; overview "Components" and "Commands" | Expected: each checkout's `make reset` acts on its own project only (V7, README "Several checkouts"). Observed: with `infra/.env` missing or `ENV_FILE` mistyped, `make -n reset` gives `-p praxismesh` with no warning. A `COMPOSE_PROJECT_NAME` in the environment is ignored in favor of the file. Two overview claims contradicted. Same as review R1 | Fix | open |
| VF3 | Nit | acceptance | `.github/workflows/ci.yml:121` | Expected: the failure step prints logs. Observed under `bash -e` with `db` stopped: `make status` exits 2, 0 log lines. Same as review R4 | Fix | open |
| VF4 | Nit | as-built | overview "Commands"; decision log row 1 | "exit status 1": `make status` returns 2 (the recipe's `exit 1` is wrapped by Make) | Fix (docs) | open |
| VF5 | Nit | as-built | `docs/demos/phase-0.md` step 5 | Hard-coded `-p praxismesh`; copying it into another checkout stops the other stack's `db`. The README form `-p "$COMPOSE_PROJECT_NAME"` is safe | Fix (docs) | open |
| VF6 | Nit | as-built | overview "Resource use" | Historical figures cannot be reproduced; this run 324-328 MiB, consistent with "varies" | Accept | open |
| VF7 | Nit | acceptance | `Makefile:57`; `infra/temporal/namespace.sh` | A failed namespace job shows only "exited with 1; see: make logs" (and `make logs` follows forever); the cause is in the job log. Same family as review R8 | Fix | open |
| VF8 | Nit | acceptance | `Makefile:10` | A line Make cannot parse stops `down` and `reset` too (contrary to the overview and Makefile comment). `KEY http://x` becomes a Make rule and the default goal. Same as review R10 | Fix | open |
| VF9 | Nit | acceptance | README "Trying the services by hand" | The curl commands send no key; they work only with an empty `VLLM_API_KEY` (true for the DGX Spark endpoint) | Fix | open |
| VF10 | Nit | coordinator | `infra/db/healthcheck.sh`; README "When things go wrong" | A volume created at `075791a` never becomes healthy after the containers are recreated at `61c40ef`, and the message advises `make reset` (data loss) for causes that do not apply. The owner's main volume already has the new marker (checked read-only). Same as review R5 | Fix (docs or legacy marker) | open |
| VF11 | Nit | as-built | `infra/db/init.sh` | The `paradedb` database keeps PUBLIC CONNECT; both application roles connect to it. Same as review R19 | Fix or document | open |
| VF12 | Nit | as-built | overview line 7 | "Describes" names a branch, not a commit | Fix (traceability) | open |

## Verdict

**fail.** All acceptance commands passed with observed output against the live stack and the DGX Spark endpoint:

- `make up` and its repeat, `make migrate`, `make smoke` (27 passed, no skips);
- `make restart-check` and `make unhealthy-check`;
- the unit suite;
- every README "Trying the services by hand" command, as written.

V1 and V2 are confirmed fixed, and the evidence checks are clean. The verdict is decided by the `verify-phase` rules "fail if an as-built claim is contradicted" and "an acceptance test … fails":

- The two overview claims on project-name isolation and on `down` and `reset` are contradicted (VF2).
- The spec's "read identically … reject any other syntax" fails on a comment ending in `\` (VF1).

Demo evidence: the observed results are in the Checks table. `docs/demos/phase-0.md` was not rewritten, because this session does not edit the reviewed work; VF5 lists its correction.

## Open items

- **Majors:** VF1 and VF2. Fix, then re-verify the affected claims and probes in a new session.
- **Nits:** VF3-VF12, 10 in all, for the implementer.
- **Main checkout's stack:** never stopped or modified by this run. It was left running and healthy under project `praxismesh`.

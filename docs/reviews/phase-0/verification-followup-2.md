---
review: verification
phase: 0
change: openspec/changes/phase-0-local-infrastructure 
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: f0337f1cdde68c104fecbf748739ca9b4cb72125
docs_sha: f0337f1cdde68c104fecbf748739ca9b4cb72125
diff_base: n/a
session: fresh            # light tier: shared with the final narrow implementation follow-up, independence between them waived per §7.0
date: 2026-11-11
verdict: fail
reviewers:
  - { lens: acceptance and demo (verifier), status: completed }
  - { lens: targeted probes R1-R5 (coordinator), status: completed }
---

# Verification (final narrow follow-up): Phase 0 local infrastructure

This is a gate-mode, light-tier verification, run as the **final narrow follow-up** under `docs/reviews/README.md` rule 6. The code is `f0337f1`, the squash merge of PR #40, and docs and code are the same commit. Tracking issue: #34.

The owner fixed the scope:

- **Reproduce R1 and R2 (VF2 and VF1)** to confirm they are closed.
- **Run** `make up`, `make migrate`, `make smoke`, `make restart-check` and `make unhealthy-check`.
- **Check** the CI failure step (R4) and a volume from before PR #38 (R5).

The rest of the demo checklist and the as-built claims outside these items were not re-checked.

This session ran the targeted implementation review (`implementation-review-followup-2.md`) first; independence between the two is waived (§7.0). The verifier agent was not given the review's findings.

## Inputs

- **Checkout:** a disposable `git worktree` at `f0337f1` (detached, commit date 2026-11-11T15:20:36-05:00), removed after the run.
- **Requirements:** `docs/plan/phases/phase-0.md`, the RFC "Testing and demo", and `specs/dev-environment/local-stack/spec.md`.
- **Instructions:** README "Local stack" and `docs/demos/phase-0.md`.
- **Environment:**
  - x86_64 workstation with Docker 29.9.2, Compose v5.7.0 and uv 0.13.5; Python 3.11.
  - Model endpoint: the DGX Spark endpoint, set in the checkout's git-ignored `infra/.env`. Its URL is not recorded here.
- **Isolation:**
  - The checkout's `infra/.env` was copied from `infra/.env.example`, following README "Several checkouts". It set `COMPOSE_PROJECT_NAME=praxismesh-v2` and ports DB 35432, Temporal 37233, UI 38080 and S3 38333.
  - `COMPOSE_PROJECT_NAME` was unset in the shell.
  - Before any target ran, `--project-only` printed `praxismesh-v2` and `make -n reset` resolved through it.
  - The main checkout's stack (project `praxismesh`, ports 5432, 7233, 8080 and 8333) was never touched.
- **Upgrade probe (R5):** a second disposable worktree with project `praxismesh-upg2` and ports 45432, 47233, 48080 and 48333.
  - At `075791a`, its `db` was started only with an explicit `docker compose -p praxismesh-upg2`, never through that revision's Makefile.
  - The worktree was then moved to `f0337f1`.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Prerequisites | `uv sync --locked` | Documented steps suffice | Exit 0. No undocumented step was needed | pass |
| Clean start | `make up` | Spec "Clean start": every service healthy | Exit 0 in 17.7 s. `Volume praxismesh-v2_pgdata Creating`, four services `Healthy`, then `stack is up; run 'make status' for addresses and health` | pass |
| Repeat start | `make up` | Succeeds | Exit 0 in 2.1 s | pass |
| Status | `make status` | All healthy | Four services `(healthy)` and both jobs `Exited (0)`. `addresses: Temporal 127.0.0.1:37233, …`, `model endpoint: <DGX Spark endpoint> answers /v1/models`, `all services healthy`, exit 0 | pass |
| Migrations | `make migrate`, twice | Head, then no change | First run `-> 0001` and `0001 -> 0002`; second run printed no upgrade lines | pass |
| Integration suite | `make smoke` (endpoint set) | All pass, no skips | Exit 0: `47 passed in 4.80s`, 0 skipped. The model tests ran against the DGX Spark endpoint | pass |
| Restart check (includes R3) | `make restart-check` | Spec: Repeat start, Changed retention, Restart keeps state | Exit 0 in 73.2 s. Sequence: `make up`, `make up`, `stopping the stack (containers kept)`, `make up`, `TEMPORAL_RETENTION=96h make up`, `make up`, seed, `make down`, `make up`, `make migrate`. Result: `restart-check: PASS (repeat starts changed nothing; retention change applied and restored; revision 0002; Workflow and object survived)`. Its `make down` acted only on `praxismesh-v2` | pass |
| Unhealthy check | `make unhealthy-check` | Spec "Unhealthy service": status names `db`, smoke names the database; recovery | Exit 0 in 68.4 s: `unhealthy-check: PASS (make status and the smoke test named the stopped db)`. The `db` container restarted. The diagnostics are captured, not shown (VG5) | pass |
| Status after | `make status` | All healthy | `all services healthy`, exit 0 | pass |
| Unit suite | `uv run pytest` | Pass | `84 passed, 47 deselected` | pass |
| **R1 / VF2: missing env file** | `sh infra/check-prereqs.sh --project-only /nonexistent.env`; `make reset ENV_FILE=/nonexistent.env`; `make down ENV_FILE=/nonexistent.env` | Refuse; never fall back to `praxismesh` | Each prints `error: COMPOSE_PROJECT_NAME is not set (in /nonexistent.env or the shell); refusing to guess which stack to act on`. `make` exits 2 and Docker is never called | pass (closed) |
| **R1 / VF2: shell override** | `COMPOSE_PROJECT_NAME=other` with `--project-only`, and with `docker compose … config` | Shell wins for both | Both resolve `other`. Without the shell variable, both resolve `praxismesh-v2` | pass (closed) |
| R1: invalid names | Env copies with `Upper`, `a;b` and an empty value | Rejected | Each rejected by name, exit 1 | pass |
| R1: stale shell name from another checkout | `COMPOSE_PROJECT_NAME=praxismesh` exported (as README's `set -a; . infra/.env` leaves it), then `--project-only` and the full check on this checkout's file | Act only on this checkout's project, or refuse | `--project-only` prints **`praxismesh`**, and the full check exits 0. `make reset` would delete the other checkout's volumes | **fail (VG2, Major)** |
| R1: empty but set shell name | `COMPOSE_PROJECT_NAME=` with `--project-only` and `docker compose config` | Same project for both | `--project-only` gives `praxismesh-v2`, but Compose gives **`infra`**. The full check exits 0 | fail (VG3, Nit) |
| **R2 / VF1: comment ending in `\`** | `make up ENV_FILE=<copy with "# note \" before TEMPORAL_RETENTION=96h>`; the same before `COMPOSE_PROJECT_NAME` | Rejected, naming the line | `… line 30: a line must not end with '\'`, exit 2. Before the project name: `line 17`, exit 2 | pass (closed) |
| R2: reserved keys | `MAKEFLAGS=x`, `SHELL=x`, `ENV_FILE=x` appended | Rejected | `line 44: expected KEY=value with a known KEY`, exit 1 for each | pass |
| R2: uv and Compose agree on single values; shell precedence | `uv run --env-file infra/.env` printing `DB_PORT`, `TEMPORAL_RETENTION` and `COMPOSE_PROJECT_NAME`; again with `TEMPORAL_RETENTION=96h` in the shell | Same as Compose; shell wins | `35432 72h praxismesh-v2`; with the shell value, `96h` | pass |
| R2: repeated key | Env copy plus `DB_PORT=45432` and `TEMPORAL_RETENTION=96h` appended; another copy plus `COMPOSE_PROJECT_NAME=praxismesh-dup` | Spec: every reader reads identically, else `make up` rejects naming the line | Check exits 0 for both. uv: `35432 72h`. Compose: `db` published on `45432`, namespace job `TEMPORAL_RETENTION: 96h`. Project: Compose and `--project-only` give `praxismesh-dup`; uv, and Compose run under uv, give `praxismesh-v2` | **fail (VG1, Major)** |
| **R4 / VF3: CI failure step** | Step text extracted from `ci.yml` and run with `bash -e` while `db` was stopped | Logs print | Step exit 0. `unhealthy or stopped: db`, then 676 log lines (db 125, temporal 200, temporal-ui 71, temporal-schema 76, temporal-namespace 4). Recovery `make up` succeeded and status was healthy | pass (closed) |
| **R5 / VF10: volume from `075791a`** | `db` up at `075791a` (project `praxismesh-upg2`); worktree to `f0337f1`; `make down`; `make up`; `make status`; `make migrate`; `make smoke` | Becomes healthy; README: "no reset is needed after updating" | Before: marker on `praxismesh` only, and `postgres`/`paradedb` with default ACLs. `make down` removed only `praxismesh-upg2`. `make up` exit 0 in 16.8 s; `all services healthy`; migrations applied. `make smoke`: **`2 failed, 41 passed, 4 skipped`**: `test_app_role_refused_elsewhere[postgres]`, `test_temporal_role_refused_elsewhere[postgres]` | health: pass (closed). README claim: contradicted (VG4, Nit) |
| Revisions | `git cat-file -t f0337f1`; `git branch -r --contains f0337f1` | Commit on the remote | `commit`; `origin/main` | pass |
| Docs describe this code | Same commit | Empty diff | `docs_sha` = `code_sha` | pass |
| CI on the tested code (informational) | `gh api …/commits/f0337f1/check-runs`; PR #40 checks | - | The `main` push run for `f0337f1` was still queued (0 check runs). PR #40's head `4ed5de4` has an identical tree (`git diff --stat 4ed5de4 f0337f1` empty), and all 11 checks there succeeded, including `stack` and `ci-ok` | pass |
| Secrets | `git grep -nIE '<token patterns>' f0337f1`; search for the endpoint host | None | Only the pattern itself, in `.agents/skills/verify-phase/SKILL.md:76`. Endpoint host: 0 files | pass |
| Transcripts | `git ls-tree -r --name-only f0337f1 \| grep -iE '\.jsonl$\|transcript'` | None | The three Pre-0 spike metric files `spikes/harness-vllm/results/*.jsonl`, unchanged and not transcripts | pass |
| Teardown | `make reset` in each disposable checkout, after confirming `--project-only`; `git worktree remove --force`; `git worktree prune` | Disposable projects gone; main stack untouched | `deleting the stack and data volumes of project praxismesh-upg2` and `… praxismesh-v2`; volumes removed; both worktrees removed. Remaining: `praxismesh_pgdata` and `praxismesh_seaweeddata`; the four `praxismesh-*` containers still `Up (healthy)`; main working copy clean | pass |

## As-built claims

Only the claims tied to R1-R5 were checked.

| Claim (quoted) | Location | Status | Evidence |
|---|---|---|---|
| "`make down` and `make reset` act only on the named project, and refuse when no name is set rather than fall back to a default" | README "Several checkouts" | confirmed as written | The refusal was observed. However, the "named project" can come from a stale shell variable (VG2) |
| "A variable set in your shell overrides the file" | README "Local stack" | confirmed, with a gap | Confirmed for Compose and uv. An empty but set `COMPOSE_PROJECT_NAME` is not honoured consistently (VG3) |
| "Make never reads it … Write it as plain `KEY=value` lines using the names in `infra/.env.example`; values may use only …" | README "Local stack" | confirmed, with a gap | The character, key and `\` rules are enforced, naming the line. Repeated keys are accepted and read differently (VG1) |
| "A database volume created before the gate fixes (PR #38) is still accepted as initialised; no reset is needed after updating." | README "When things go wrong" | **contradicted** (Nit) | It is accepted, but `make smoke` fails two isolation tests on such a volume (VG4) |

## Findings

| ID | Severity | Reviewer | Location | Expected / observed | Action | Resolution |
|---|---|---|---|---|---|---|
| VG1 | **Major** | coordinator probe | `infra/check-prereqs.sh`; `Makefile:11-12` | Spec: every reader reads `infra/.env` identically, otherwise `make up` rejects the file naming the line. Observed: a repeated key passes the check; Compose uses the last value and uv the first (port, retention and project name all diverge). Same as review N2 | Fix | open |
| VG2 | **Major** | coordinator probe | `infra/check-prereqs.sh:32`; README "Trying the services by hand" | Expected: each checkout's `make reset` acts on its own project. Observed: a `COMPOSE_PROJECT_NAME` exported by the README's `set -a; . infra/.env` snippet in another checkout wins, and the check passes, so `make reset` would delete that other checkout's data. Same as review N1 | Fix | open |
| VG3 | Nit | coordinator probe | `check-prereqs.sh:32-33` | An empty but set `COMPOSE_PROJECT_NAME` resolves to the file's name for `down`/`reset` but to `infra` for Compose (`up`, `status`, `logs`). Same as review N3 | Fix | open |
| VG4 | Nit | coordinator probe | README "When things go wrong"; `infra/db/healthcheck.sh` | A volume from `075791a` becomes healthy, but `make smoke` fails 2 role-isolation tests (no `REVOKE CONNECT` on `postgres`), so "no reset is needed" is wrong. Same as review N11 | Fix (document the one-time REVOKE, or narrow the claim) | open |
| VG5 | Nit | acceptance (verifier) | `tests/integration/unhealthy_check.py` | The check captures the output of `make status` and `make smoke` and prints only PASS or FAIL, so a run shows no diagnostic for the demo item "produces a clear diagnostic". It matches `database server (service db)`, not the spec's "unreachable" wording | Fix (echo the captured lines) | open |

## Verdict

**fail.** Every acceptance command in scope passed with observed output: `make up` and its repeat, `make status`, `make migrate`, `make smoke` (47 passed, no skips), `make restart-check` (now including the retention change), `make unhealthy-check` and the unit suite.

R1/VF2, R2/VF1 and R4/VF3 reproduce as closed. R5/VF10 is closed for health.

The verdict is decided by the `verify-phase` rule "fail if an acceptance test … fails". Two probes of the fixed behaviour fail:

- **VG1:** the spec's "every reader … reads identically" fails on a repeated key.
- **VG2:** a documented shell setup sends `make reset` to another checkout's project.

## Open items

- **Majors:** VG1 and VG2 (the same as review N2 and N1).
- **Nits:** VG3-VG5, 3 in all.
- **Not re-checked (out of scope):** the rest of the demo checklist and `docs/demos/phase-0.md`.
- **Main checkout's stack:** never stopped or modified. It was left running and healthy under project `praxismesh`.

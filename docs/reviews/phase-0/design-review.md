---
review: design
phase: 0
change: openspec/changes/phase-0-local-infrastructure
rfc: docs/rfcs/phase-0-local-infrastructure.md
adrs: [docs/adr/0002-paradedb-as-postgresql-server.md]
commit_sha: 83e0ae31439edcbacb13441f7603777f92ef3242
docs_sha: n/a
diff_base: n/a
session: fresh
date: 2026-11-11
verdict: FAIL
reviewers:
  - { lens: fresh reader (design-reader), status: completed }
  - { lens: codebase fit (design-reviewer), status: completed }
  - { lens: zoom out (design-reviewer), status: completed }
---

# Design review: Phase 0 local infrastructure

## Inputs

Revision `83e0ae31439edcbacb13441f7603777f92ef3242` (branch `docs/phase-0-design`). The working tree was clean (`git status --porcelain` empty). All paths below are under `/home/geo/develop/praxismesh`. Each reviewer received only its brief from the `review-design` skill, with these paths filled in.

- **Fresh reader** (`design-reader`, Claude Code, project instructions omitted):
  - `openspec/changes/phase-0-local-infrastructure/proposal.md`
  - `openspec/changes/phase-0-local-infrastructure/design.md`
  - `docs/rfcs/phase-0-local-infrastructure.md`
- **Codebase fit** (`design-reviewer`):
  - change files: `proposal.md`, `design.md`, `tasks.md`, `specs/dev-environment/local-stack/spec.md`, `specs/persistence/app-database/spec.md`, `specs/storage/blob-store/spec.md`, `specs/inference/model-endpoints/spec.md`
  - design docs: the RFC and `docs/adr/0002-paradedb-as-postgresql-server.md`
  - guidance and plan files: `AGENTS.md`, `PROJECT_PLAN.md` (§2, §6), `docs/plan/phases/phase-0.md`, `docs/plan/design-decisions.md` (§4.13, §4.16, §4.17), `docs/plan/schemas.md`
- **Zoom out** (`design-reviewer`):
  - the change directory (proposal, design, tasks) and the RFC
  - plan files: `PROJECT_PLAN.md`, `docs/plan/phases/phase-0.md`, `docs/plan/design-decisions.md`, `docs/plan/schemas.md`, ADR-0002
  - any code it chose to read

Notes on the inputs:
- ADR-0002 is linked from the RFC body and front matter (`plan_sections`), not through `openspec_change`.
- `design.md` only links to the RFC, by design (ADR-0001).
- The repository has no infrastructure code yet. The codebase-fit reviewer therefore checked the code claims against the plan, `schemas.md`, ADR-0002 and the spike write-up, and it reported that it did.

## Fresh reader paraphrase

> ## What this proposes
>
> Phase 0 builds a local Docker Compose stack that every later phase will run on. The stack has one ParadeDB (PostgreSQL 16) server holding Temporal's two databases and a separate application database, plus Temporal Server with its UI, SeaweedFS as an S3-compatible object store, and a vLLM model endpoint that runs outside Compose on the "DGX Spark pair". Make targets start, stop, reset and migrate the stack. Smoke tests check each part: a Temporal Workflow, an S3 round trip, Alembic migrations with `pg_search`, database role isolation, and both vLLM API styles. A scripted demo shows that state survives a restart and that failures produce clear diagnostics. The point is a stack that starts with one command, keeps its state across restarts and is known to work before any product code is written.
>
> ## How the existing system works, per this document
>
> The documents say almost nothing about a current system: there is no infrastructure and no product code, and "Modified Capabilities: None (no existing specs)". The relevant existing pieces are earlier decisions. ADR-0002 picked ParadeDB as the single PostgreSQL server. A "Pre-0 spike" said "go" on running the model path through vLLM on the DGX Sparks. The plan swapped MinIO for SeaweedFS. The project already uses `uv`/`uv.lock`, pytest unit tests, GitHub CI and Dependabot, and this change leaves those as they are.

The reader reported no sections it could not paraphrase, so it raised no Blockers.

## Findings

Reviewers: FR = fresh reader, CF = codebase fit, ZO = zoom out. Duplicates across reviewers are merged. Where reviewers gave the same issue different severities, the higher one is used.

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| F1 | Major | CF, ZO | RFC Topology table and "Data boundaries" (rfc:47-58); tasks 1.3, 4.1 | **No namespace.** The design drops `temporalio/auto-setup`, which also registered the `default` namespace, and keeps only the `temporal-sql-tool` schema job. On a clean volume, nothing creates a namespace or sets its retention (§4.13 "Align Temporal namespace retention…"). **Re-runs.** The one-shot jobs run on every `make up`, and the design does not say they are idempotent. | Fix: add a one-shot namespace step that runs after the server is healthy (`temporal operator namespace create`, with name and retention from `.env`, treating "already exists" as success). Add it to the topology table, task 1.3 and the `make up` wait logic. Require that `make up` succeeds twice in a row on the same volumes. Verify against current Temporal docs. | open |
| F2 | Major | CF, ZO, FR | RFC rfc:57-59 ("`make migrate` runs `alembic upgrade head` as role `praxismesh`"); task 3.1; app-database spec:27-32 | **Privileges.** `CREATE EXTENSION pg_search` needs superuser unless the extension is `trusted`. The design doesn't say which applies, and making `praxismesh` a superuser would void role isolation. **Template.** The ParadeDB image's bootstrap may already create the extension in `template1`. Then every database has it, Temporal's included, and the "pg_search installed" test (task 4.4) proves nothing. | Fix: inspect `paradedb/paradedb:0.26.6-pg16` and state in the RFC which component creates `pg_search` and as which role (for example, the init script as superuser, with the migration as an `IF NOT EXISTS` no-op). Say whether Temporal's databases get ParadeDB extensions and what the downgrade does. Make the test assert the intended mechanism. | open |
| F3 | Major | CF, ZO | local-stack spec:27-32 "Restart keeps state"; app-database spec:23-25 "After restart"; RFC Testing (rfc:92); tasks 3.2, 5.1 | No automated test performs a `down`/`up` cycle. CI runs only `make up`, `make migrate`, `make smoke`, so restart persistence and "migrate is a no-op after restart" are shown only in demo step 4. The plan requires otherwise: phase-0.md:15 accept line; §8 says "demonstration alone does not substitute for tests". | Fix: add an automated sequence (a make target used by the CI `stack` job): up → migrate → seed object and Workflow → down → up → migrate (assert the revision is unchanged) → assert the Workflow and object survived → reset. Add it to tasks and the RFC test list. | open |
| F4 | Major | ZO | RFC rfc:46 (`db` health check `pg_isready`), rfc:57 (init script on first start); task 1.2 | **Health-check race.** The postgres entrypoint runs init scripts against a temporary server on the Unix socket. A bare `pg_isready` can report healthy before the roles and databases exist, so `temporal-schema` can intermittently fail on a clean volume. **Init runs once.** Init runs only on an empty data directory. A half-failed init leaves a broken volume that later starts silently skip, and credential changes in `.env` after the first start have no effect. | Fix: make the health check prove the end state (for example `pg_isready -h 127.0.0.1`, or a `psql` query as each role). Make the init script fail fast (`set -e`, `ON_ERROR_STOP`). Document that a failed first init and any credential change both need `make reset`. | open |
| F5 | Major | ZO | task 4.3 ("skipped … when unset or unreachable"); model-endpoints spec:23-25; RFC Risks (rfc:84) | If `VLLM_BASE_URL` is set but the Sparks are down, `make smoke` exits 0 without touching a model. Phase evidence could then show a green suite for "both vLLM endpoints answer" (phase-0.md:15). §8 says: "A phase cannot close on stubbed results alone"; a missing dependency means the demo is recorded as blocked. | Fix: skip only when `VLLM_BASE_URL` is unset. When it is set and the endpoint is unreachable, fail and name the endpoint (or add a required-model mode for the gate run). State that phase closure needs a recorded, non-skipped model run. | open |
| F6 | Major | ZO, CF, FR | RFC demo step 5 (rfc:101); local-stack spec:23-25 "Unhealthy service" | "Run `make up` … with the database stopped" produces no failure, because `make up` restarts the database. The plan's demo item "failed health check or missing dependency produces a clear diagnostic" (phase-0.md:46) therefore has no working second case, and the unhealthy-service scenario has no test. | Fix: define a reproducible failure. Either `docker compose stop db`, then `make migrate`/`make smoke` showing the named error, or a forced health-check failure through an `.env` override that `make up` names. Add a test for the unhealthy-service scenario. | open |
| F7 | Major | CF, ZO, FR | model-endpoints spec:10 ("Model name, base URL and API style SHALL be configuration"); RFC rfc:51, rfc:61, rfc:65; task 1.6; phase-0.md:10 | `.env.example` lists only `VLLM_BASE_URL`: no model name, API key or API style, and the RFC names `spark` inline. The `vllm-local` profile is "vLLM image from the model registry": no image, model, flags or port, and "model registry" is never introduced. No machine in the stated environment can test the profile. Phase task 2 (`--served-model-name` without `/`, tool-choice/parser flags) has no recorded configuration. | Fix: add `VLLM_MODEL`, an optional `VLLM_API_KEY` and the API style to `.env.example`. Name where the external endpoint's launch flags are recorded (`docs/spikes/harness-vllm.md:21`). Either define the profile fully (image, served name, `--enable-auto-tool-choice --tool-call-parser …`) and label it "untested in Phase 0", or defer it. Remove or explain "model registry". | open |
| F8 | Major | CF, ZO | RFC rfc:69-71 (`smoke` marker); `pyproject.toml:24,28-29`; `.github/workflows/ci.yml:94`; proposal.md:39 | **Test isolation.** `testpaths = ["tests"]` with no marker deselection means the existing CI `tests` job (`uv run pytest`) would collect `tests/smoke/` and fail without a stack. **Typing.** mypy `strict` covers `tests`, so `boto3` needs stubs. **Dependencies.** No task adds `temporalio`, `alembic`, `boto3`, `httpx` etc. to `uv.lock`. The proposal calls them runtime dependencies, though `boto3`/`httpx` serve only the tests. | Fix: add a task before section 3 that adds the dependencies (stating the group for each), registers the `smoke` marker, excludes it from the default run (for example `-m "not smoke"`), and adds the mypy stubs or override. | open |
| F9 | Major | CF, ZO | proposal, RFC and tasks (absent); phase-0.md:30 | The phase file requires "a simple traceability list (requirement -> spec -> acceptance test)". The specs cite plan items, but nothing maps each requirement to its smoke test or demo step. | Fix: add a requirement → spec → acceptance test/demo step table to the RFC (or `tasks.md`). | open |
| F10 | Major | ZO | proposal.md:38; RFC rfc:59 (`migrations/` at the repo root); tasks section 4 (`tests/smoke/`) | Plan §6 puts SQL migrations under `common/persistence/` (PROJECT_PLAN.md:142, :157). Later phases add to this baseline, so its location is permanent, and the §4.16 precedence rule forbids silent departures. `tests/smoke/` is not one of the plan's test suites (unit, replay, integration, e2e, chaos). | Fix: place Alembic under `common/persistence/migrations/` (with `alembic.ini` where `make migrate` points), or record the deviation in the decision log. Consider `tests/integration/` with a `smoke` marker. | open |
| F11 | Major | FR | RFC Testing and demo, demo step 2; Topology | The hello Workflow needs a Temporal worker, but no worker is introduced: none is in Compose and none is described in the smoke tests. | Fix: state where the hello Workflow's worker runs (for example, in-process in the smoke test, with its task queue name) and how demo step 2 starts it. | open |
| F12 | Major | FR | proposal "Impact"; RFC Testing; task 5.1 | The CI `stack` job runs `make up`, which fails without `.env`, and `.env` is git-ignored. The design never says how CI gets its configuration and credentials. | Fix: state the mechanism (for example, CI copies `.env.example`, whose placeholder values work for a throwaway stack, or the job sets variables in the workflow) and confirm it commits no secrets. | open |
| F13 | Major | FR | proposal "Why"; RFC Background, front matter, "Models" | The RFC uses terms it never explains: the plan sections it cites (§4.16 is the stated reason for role isolation, but its content is never given), and the "DGX Spark pair / the Sparks" (how many hosts, how they are reached, one URL or two). | Fix: add one-line glosses in the RFC: what §4.16 requires here, and what the Spark endpoint is (hosts, single base URL, who runs it). | open |
| F14 | Nit | CF, ZO | RFC rfc:85 ("Dependabot proposes updates"); `.github/dependabot.yml` | Dependabot covers only `github-actions`, `uv` and `npm`, not images. | Fix: add a task for a `docker-compose`/`docker` ecosystem entry for `infra/`, or drop the claim. | open |
| F15 | Nit | CF, ZO | RFC rfc:57; tasks 1.2, 4.4 | PostgreSQL grants `CONNECT` to `PUBLIC` on new databases, so "each role can connect only to its own databases" needs `REVOKE CONNECT … FROM PUBLIC`. | Fix: name the revokes in task 1.2 and the RFC. | open |
| F16 | Nit | CF, ZO | app-database spec:28; ADR-0002 front matter (`status: proposed`) | The `pg_search` requirement traces only to an ADR. §4.16 says ADRs are not requirement sources. ADR-0002 is still `proposed`, yet the RFC depends on it. | Fix: also cite the 2026-11-11 decision-log entry. Have the owner accept ADR-0002 along with this design, or state that approval covers it. | open |
| F17 | Nit | CF | ADR-0002 ("The README and the release license check must say so"); task 6.1 | README has no AGPL note for ParadeDB, and task 6.1 doesn't add one (`docs/release.md:15` has it). | Fix: add the README AGPL note to task 6.1. | open |
| F18 | Nit | CF | RFC rfc:65-66 | With `-f infra/docker-compose.yml`, Compose reads `.env` from `infra/` by default. The Makefile and the Python smoke tests must agree on one path. | Fix: state the `.env` location (or the `--env-file` flag) in the RFC. | open |
| F19 | Nit | CF | RFC Testing; plan §8 ("Every Workflow: deterministic replay and time-skipping tests") | The hello Workflow's status under the §8 replay rule is unstated. | Fix: declare it a test-only fixture, exempt from §8 replay tests, or add a trivial replay test. | open |
| F20 | Nit | CF, ZO, FR | RFC Topology table (rfc:46-53), rfc:66 | **SeaweedFS image.** It is given only as "SeaweedFS 4.53 (`server -s3`)", with no image name. **Temporal health check.** `temporal operator cluster health` assumes the CLI ships in `temporalio/server`. **One-shot jobs.** `docker compose up --wait` with one-shot jobs may report exited containers as failures, and without `--wait-timeout` it has no timeout, which contradicts "On a timeout it exits non-zero". | Fix: name the SeaweedFS image. Verify where the health-check CLI lives (or run the check from admin-tools). Verify `--wait` behavior with one-shot jobs on the pinned Compose version, and add `--wait-timeout`. | open |
| F21 | Nit | CF | RFC front matter `issue: null`; branch `docs/phase-0-design`; AGENTS.md "All work is tracked in GitHub issues" | The design has no GitHub issue. | Fix: open an issue and link it in the RFC front matter. | open |
| F22 | Nit | ZO | RFC rfc:60 ("The smoke test creates its own bucket"); task 4.1 | Fixed bucket names and Workflow IDs collide when a run is interrupted or two runs overlap. | Fix: use unique per-run bucket/key and Workflow IDs, and create the bucket idempotently. | open |
| F23 | Nit | ZO, FR | RFC Risks (rfc:83) | The memory risk ("Phase 0 records actual use") has no threshold, no rethink trigger and no place where the figure is recorded. The §7.1 "review process costs more than it returns" trigger is not restated. | Fix: name a threshold and where it is recorded (for example, the demo file), and restate the applicable §7.1 trigger. | open |
| F24 | Nit | CF, ZO | task 5.1; `.github/scripts/ci_gate.py:22-32`; `.github/workflows/ci.yml:264`; `tests/test_ci_gate.py` | **Gate wiring.** "Included in `ci-ok`" requires editing `REQUIRED_JOBS` and the `needs:` list, which a test keeps in sync. **Cost.** A skipped job counts as a failure, so the `stack` job runs on every PR, docs-only PRs included, with image pulls exposed to Docker Hub rate limits. | Fix: name both edits in task 5.1. State the always-run choice and consider image caching or retries. | open |
| F25 | Nit | FR | RFC "Models" ("served name `spark`, no `/`"); RFC Commands; proposal "What Changes" | **Wording.** "no `/`" is ambiguous. **Make targets.** The proposal lists only `up`/`down`/`migrate`, while the RFC adds `reset`/`smoke`/`logs`. **Volumes.** "Named volumes" are never named per service. **Project terms.** The following are used without explanation: Pre-0 spike inputs, `tier`/`size`, `pg_search`, Phases 3A/7/9, the documentation skill, where the GCS/Ceph settings are documented, and how a user repoints to `vllm-local`. | Fix: write "served model name contains no `/`". Align the proposal's list of make targets with the RFC. List the volumes. Add brief glosses or links for the terms. | open |

## Verdict

**FAIL.**

Under `docs/reviews/README.md` rule 5, "every Major must be fixed or contested with evidence before a PASS". Thirteen Majors (F1-F13) are open, and none has been fixed or contested. No Blockers were raised, and all three reviewers completed, so neither of the rule's automatic-FAIL conditions applies. The design is otherwise consistent with the plan's main constraints, and `openspec validate --strict` passes.

## Open items

- F1-F13 (Major) must be fixed or contested by the author. A re-check then runs in a new session (rule 6).
- F14-F25 (Nit) do not block.
- Several points need verification against live images and docs at implementation time:
  - the namespace step (F1);
  - `pg_search` trust and template behavior (F2);
  - the health-check CLI and `--wait` behavior (F20);
  - the versions the RFC cites (`temporalio/auto-setup` stuck at 1.29; Temporal 1.32.2, UI 2.58.1, SeaweedFS 4.53, `temporalio` 1.36, `alembic` 1.20), which the reviewers could not confirm offline (plan §2).

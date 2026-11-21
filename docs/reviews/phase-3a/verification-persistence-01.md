---
review: verification
phase: Phase 3A persistence (plan docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle, phase 01)
change: docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle
rfc: n/a
adrs: []
commit_sha: 56c0170872fd14efa3f7902779284b9a32d382ba
docs_sha: 56c0170872fd14efa3f7902779284b9a32d382ba
diff_base: n/a
session: coordinator with fresh verifier subagents run one at a time (docs/reviews/README.md rules 1 and 8)
date: 2026-11-20
verdict: pass
reviewers:
  - { lens: acceptance (at bbfe1ce), status: completed, result: pass for the phase's deliverables; integration suite exit 1 (F1, F2) }
  - { lens: as-built claims (code and docs bbfe1ce), status: completed, result: pass with 3 nits }
  - { lens: acceptance re-run after the F1 docs fix (code bbfe1ce, docs dc83f97), status: completed, result: fail (F2) }
  - { lens: acceptance re-run at the F2 fix (56c0170), status: completed, result: pass }
  - { lens: as-built follow-up (docs 56c0170), status: completed, result: pass }
---

# Verification: Phase 3A persistence, phase 01 (reference index, classes, audit log and the payload guard; issue #92)

## Inputs

A disposable worktree of the pinned commit, with `infra/.env` from `infra/.env.example` changed
only as README "Several checkouts" and "Model endpoint" direct (Compose project `pmverify3a`, its
own ports, `VLLM_BASE_URL=http://spark-01:8000`); the owner's `praxismesh` stack was not touched.
The plan, the phase file and the notes it links, README, AGENTS.md, the Makefile, the runbook,
`schemas.md`, the threat model, the decision log and the overview. Raw reports:
[raw/persistence-verification-phase-01-*.md](raw/). This phase has no demo checklist: the plan's
demo is phase 03's (task 3.2). The observed behaviour is collected in the acceptance walkthrough
[docs/demos/phase-3a-persistence-01.md](../../demos/phase-3a-persistence-01.md).

## History

1. Acceptance at `bbfe1ce`: every task's Verify line and R1, R2, R4, R5, R14, R18, R19, R20
   passed, including a migration round trip by hand (0006, seed, 0007, down, up). The full
   integration suite exited 1 (`5 failed, 274 passed`): four messaging tests fail while the
   documented workers run (F1), and `test_refusals_are_logged_with_ids[dsh]` failed (F2).
2. As-built claims at `bbfe1ce`: no Blocker or Major; three Nits (N1-N3), older sentences naming
   classes migration 0007 replaced.
3. Docs fixed in `dc83f97` (F1, N1-N3). Re-run with the workers stopped as README now says:
   messaging tests pass and `make smoke` passes (249), but the full suite fails F2 again
   (`1 failed, 278 passed`); alone the test passes 10/10.
4. The coordinator traced F2 to phase 01: `tests/support/scratch_db.py` runs Alembic in-process
   and `env.py`'s `fileConfig` disabled every existing logger, `praxis.harness` included, so a
   later test captured no refusal line. It fails after `test_migration_0007.py` or `test_refs.py`
   and after none of the other phase 01 files. Fixed in `56c0170` (`disable_existing_loggers=False`
   and a regression test in `test_migration_0007.py`, which `make smoke` runs; the test fails
   without the fix).
5. Acceptance re-run at `56c0170`: **pass**. A follow-up confirmed each corrected statement.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `make up`, `make status`, `make migrate`, `make workers-up` (pmverify3a) | healthy, migrations at head | `all services healthy`; `Running upgrade 0006 -> 0007` | pass |
| Repository checks | AGENTS.md "Checks" | exit 0 | all exit 0 at `56c0170` (ruff with `.verify/` scratch excluded) | pass |
| Unit | `uv run pytest` | pass | `372 passed, 280 deselected` | pass |
| Integration | `uv run --env-file infra/.env pytest -m integration -rs`, workers stopped | pass | at `bbfe1ce` `5 failed, 274 passed` (F1, F2); at `56c0170` `280 passed`, none skipped | pass (after fixes) |
| Smoke | `make smoke`, workers stopped | pass | `250 passed` at `56c0170` | pass |
| F2 order | `test_migration_0007.py`, `test_refs.py`, then `test_refusals_are_logged_with_ids[dsh]` in one session | pass | exit 0 at `56c0170` | pass |
| Task Verify lines | phase file tasks 1.1-4.1 | each passes | each passed, tests named in the raw acceptance reports | pass |
| Migration round trip (1.1) | scratch DB 0006 -> seed -> 0007 -> down -> up | backfilled classes and `blob_refs` rows | as notes.md#d3; round trip clean | pass |
| History guard (3.3) | 20 x 500-character questions; seeded 65 KiB payload | pass; fail | passed; failed | pass |
| Link check | lychee, CI args, offline | 0 errors | `0 Errors` at `bbfe1ce` (local lychee 0.24.2); at `56c0170` left to CI's `links` job | pass (bbfe1ce) |
| gitleaks, actionlint | - | - | not installed on the host; CI runs both | blocked locally (CI) |
| Revisions | `git cat-file -t`; `git ls-remote` | commits on the remote | `56c0170` on `origin/docs/92-phase-3a-01-verification` | pass |
| Docs describe the code | `git diff --stat <code_sha> <docs_sha>` | empty | same commit | pass |
| Secrets and transcripts | `git grep` for token patterns; `.jsonl`/transcript files | none | only the pattern itself in the verify-phase skill and a phase 1 evidence file; `.jsonl` files are spike results and test fixtures accepted in earlier verifications | pass |

## As-built claims

Every claim the phase owed (task 4.1: `schemas.md`'s new tables, column, classes and D7's outbox
pattern; the threat model's encryption-at-rest, clear-text backup, `audit_log` ownership and
72-hour history statements; the decision log) is confirmed against code and read-only probes, or
clearly labelled as a later phase's work. See the raw as-built and follow-up reports.

| Claim (quoted) | Location | Status | Evidence |
|---|---|---|---|
| "All three carry retention class `task`." | schemas.md, Phase 2 events | contradicted (N1), fixed in `dc83f97` | 0007 moved them to `transcript`/`ephemeral`; follow-up confirmed the new text |
| "All carry retention class `task` ..." | overview.md, Event tables row | contradicted (N2), fixed in `dc83f97` | same; confirmed |
| "finishes with outputs as `audit` artifacts" | overview.md, `run_harness_turn` row | contradicted (N3), fixed in `dc83f97` | `activity.py:693` puts `retention="artifact"`; confirmed |
| "Run `make smoke` ... with the worker containers stopped" | README, Local stack | confirmed | added in `dc83f97` (F1); LISTEN on `message_wakes` from the orchestrator container; CI order in `ci.yml` |

## Findings

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| F1 | Major | The integration suite fails four messaging tests while the documented workers run: the orchestrator's wake dispatcher consumes the tests' wake rows. No doc said to stop them. Predates phase 01 | fixed in `dc83f97` (README); re-run passed |
| F2 | Major | Phase 01's in-process migrations (`tests/support/scratch_db.py`) let `env.py`'s `fileConfig` disable existing loggers; `test_refusals_are_logged_with_ids[dsh]` then fails. CI misses it: `make smoke` does not run `tests/test_runner_conformance.py` | fixed in `56c0170` with a regression test `make smoke` runs; re-run passed |
| N1-N3 | Nit | Older sentences named classes migration 0007 replaced | fixed in `dc83f97`; follow-up confirmed |
| B1 | - | gitleaks and actionlint not installed on the host | accepted: CI runs both |

## Verdict

**pass**: at `56c0170` every acceptance test and Verify line passed with observed output; every
as-built claim is confirmed; code and docs are the same commit, which is on the remote; the
evidence checks are clean.

## Open items

- `56c0170` changes `common/persistence/migrations/env.py` after phase 01's impl review passed; a
  targeted impl-review follow-up of that diff is recommended before the phase is marked done.

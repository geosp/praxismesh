---
review: verification
phase: Phase 3A persistence (plan docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle, phase 03)
change: docs/plans/2026-11-19-phase-3a-persistence-and-lifecycle
rfc: n/a
adrs: []
commit_sha: 4d269bef0ec2e251515750eed0fe31a1befdc4ec
docs_sha: 1b91b617ab80247b6d9f2f3bdd34023ba47924b5
diff_base: n/a
session: coordinator with fresh verifier subagents run one at a time (docs/reviews/README.md rules 1 and 8)
date: 2026-11-21
verdict: pass
reviewers:
  - { lens: acceptance and demo (at 4d269be), status: completed (resumed once after an API authentication error), result: pass; 3 checks blocked locally (CI-only), 3 observations }
  - { lens: as-built claims (code and docs 4d269be), status: completed, result: 4 Nits and 1 unverifiable claim, all documentation }
  - { lens: as-built follow-up (docs 1b91b61), status: completed, result: pass; 2 low-severity wording notes }
---

# Verification: Phase 3A persistence, phase 03 (backup, restore, reconciliation and acceptance; issue #92)

## Inputs

A disposable worktree of the pinned commit, with `infra/.env` from `infra/.env.example` changed
only as README "Several checkouts" and "Model endpoint" direct (Compose project `pmverify3a`,
ports 55432, 57233, 58080 and 58333, `VLLM_BASE_URL=http://spark-01:8000`). The owner's
`praxismesh` stack and the `pm3adev` development stack were not touched, and no image was
built (`DRILL_BUILD=--no-build`, `DEMO_BUILD=--no-build`: the existing `praxismesh-worker:dev`).
The plan, the phase file and notes.md, README, AGENTS.md, the Makefile, the runbook ("Backup and
restore" and reconcile), the overview's Phase 3A persistence section, schemas.md, the decision
log and the demo record. Raw reports:
[raw/persistence-verification-phase-03-*.md](raw/). The observed demo is recorded in
[docs/demos/phase-3a-lifecycle.md](../../demos/phase-3a-lifecycle.md), "Gate verification run".

## History

1. Acceptance and demo at `4d269be`: every repository check, the unit suite (397 passed), the
   full integration suite with the model tests (367 passed, none skipped), `make drill`, the
   demo, and extra end-to-end R23 and killed-restore runs through `make restore`. The verifier
   stopped once on an API authentication error and was resumed from its checkpoint files.
2. As-built claims at `4d269be`: four Nits (N1-N4) and one unverifiable claim (U1), all
   documentation.
3. Docs corrected in `1b91b61` (documentation only); a follow-up confirmed all nine corrected
   statements.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `uv python install 3.11`, `uv sync --locked`, `make up`, `make status`, `make migrate` (pmverify3a) | healthy, migrations at head | all services healthy, the model endpoint answers; migrations at 0007; no undocumented step | pass |
| Repository checks | AGENTS.md "Checks" | exit 0 | all exit 0 | pass |
| Unit | `uv run pytest` | pass | `397 passed` | pass |
| Integration | `uv run --env-file infra/.env pytest -m integration -rs`, workers stopped | pass | `367 passed`, none skipped (15 min 15 s) | pass |
| Evidence table | every test the phase's verification table names, against `pytest --collect-only` | each exists and passes | all 57 references exist (R18's `history_guard.py` is a session guard); all passed | pass |
| Drill | `DRILL_BUILD=--no-build make drill` | passes | `drill: passed` in 112 s: refused restore, killed restore refused next, restore with reconcile's findings read as information, the comms role, the removed object dangling under both holders | pass |
| Demo | `DEMO_BUILD=--no-build bash infra/demo/phase-3a-lifecycle.sh` | every step as documented | exit 0 in 118 s; steps 0-5 pass | pass |
| R23 end to end | `make restore` into a stack with a task, and with a Workflow and no task row | refused, unchanged | refused with "refusing to restore into a stack that holds data", exit 2, state unchanged | pass |
| Killed restore | SIGKILL during "restore: loading praxismesh", then `make restore` | refuses; after reset and up, succeeds | "an earlier restore did not finish", exit 2; then "restore: done", `"clean": true` | pass |
| Link check | lychee, CI args, offline | 0 errors | lychee is not installed on the host | blocked locally (CI) |
| gitleaks, actionlint | - | - | not installed on the host; CI runs both | blocked locally (CI) |
| Drill in CI (task 2.3) | the CI `stack` job's `make drill` step | passes within 45 min | no CI run at 4d269be (a branch push runs no CI); the step and its budget are in `ci.yml`; the hand-started run 44931363435 at d4e32c4 passed it | blocked locally (CI on the PR) |
| Revisions | `git cat-file -t`; `git branch -r --contains` | commits on the remote | both on `origin/feat/92-phase-3a-backup-restore` | pass |
| Docs describe the code | `git diff --stat 4d269be 1b91b61 -- . ':!docs'` | empty | empty | pass |
| Secrets and transcripts | `git grep` for token patterns; `.jsonl`/transcript files | none | only the scan pattern itself in two docs; `.jsonl` files are spike results and test fixtures accepted in earlier verifications, none in this phase's diff | pass |
| CI on the tested code | `gh api .../commits/4d269be/check-runs` | informational | no check runs | informational |

## As-built claims

| Claim (location) | Status | Evidence |
|---|---|---|
| Reconcile, Backup, Restore and Drill rows (overview.md, Phase 3A) | confirmed | raw as-built report, code file:line and probes |
| "Integration, each on a scratch database with an in-memory bucket: ... `test_restore_refusals.py`" (overview.md, Tests) | contradicted (N1), corrected in 1b91b61, confirmed | it uses a SeaweedFS bucket and the real Temporal; now listed under "Against the stack" |
| "Backup holds the removal lock for its whole run" (runbook) | contradicted (N2), corrected, confirmed | the manifest is written after the lock is released |
| "Use the same images as the backup (`images` in `manifest.json`)" (runbook) | contradicted (N3), corrected, confirmed | `images` holds the default services' images only |
| notes.md#d8: the manifest fields, `--no-extensions`, the workers restarted, the mark (N4a-d) | contradicted (Nits), corrected, confirmed | restore.sh and backup.py as cited in the raw reports |
| "an Activity that was running is retried by Temporal" (runbook) | unverifiable (U1), reworded to cite `make recovery-check`, confirmed | recovery-check retries a killed worker's Activity on another running worker: the same Temporal retry |
| Every other claim of the listed documents | confirmed | raw as-built report |

## Findings

| ID | Severity | Location | Expected | Observed | Resolution |
|---|---|---|---|---|---|
| N1-N4, U1 | Nit | overview, runbook, notes.md#d8 | as built | wording (above) | fixed in 1b91b61; follow-up confirmed |
| FU1 | Nit | runbook, Activity retry | a worker that "runs again" | recovery-check retries on another running worker | accepted: the same Temporal retry; the sentence says the check shows it |
| FU2 | Nit | notes.md#d8, opening line | "for the whole run" | the manifest is written after the lock | accepted: plan context; the runbook, which operators read, states it exactly |
| O1 | observation | demo record, step 2a | the recorded figures | rows 34 and `idempotency_keys` here, rows 35 and tool results recorded | accepted: the documented expectation ("the plan, by reason") holds; counts vary with the model's run |
| O2 | observation | a stack after the integration suite | - | reconcile lists test residue (488 dangling, 116 never ended) | accepted: test data on a developer stack; restore treats it as information |
| O3 | observation | right after `make up` | - | one `start_workflow` "Namespace default is not found" | accepted: transient, outside phase 03; restore's check would fail closed |

## Verdict

**pass.** Every acceptance suite, the drill and every demo step passed with observed output;
every as-built claim is confirmed after the documentation fix in `1b91b61`; the evidence checks
are clean. The link check, gitleaks, actionlint and the drill as a CI step run only in CI; the
pull request's `ci-ok` at its head is the coordinator's check before merge.

## Cleanup

The verification stack was removed with `make reset` in the worktree, and the worktree was
removed. The verifier deleted its own backups; the drill and the demo deleted theirs.

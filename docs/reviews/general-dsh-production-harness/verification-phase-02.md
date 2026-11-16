---
review: verification
phase: general-dsh-production-harness (plan phase 02)
change: docs/plans/2026-11-15-dsh-production-harness
rfc: n/a
adrs: [ADR-0005, ADR-0006]
commit_sha: 86cfec87bfb1ed83c60150d2104a41b6720b7018
docs_sha: 7b06ce60046f59817c65b97db783fddd6d8f0d95
diff_base: n/a
session: coordinator with fresh verifier subagents run one at a time (docs/reviews/README.md rule 1; light tier, independence from impl-review waived per rule 7)
date: 2026-11-16
verdict: pass
reviewers:
  - { lens: acceptance and demo (at 62ffc76), status: completed, result: fail }
  - { lens: as-built claims (at 62ffc76), status: completed }
  - { lens: acceptance and as-built follow-up (at 86cfec8), status: completed }
  - { lens: as-built wording follow-up (docs 7b06ce6), status: completed }
---

# Verification: DSH migration phase 02 (DSH runner and worker pair)

## Inputs

Disposable worktrees of the pinned commits; plan, phase file and notes; setup docs (README, AGENTS.md
"Checks", Makefile, `infra/.env.example`); `docs/architecture/overview.md` sections "DSH migration
phase 01" and "phase 02" (added for this gate). A disposable Compose project (`pmverify02`, own
ports) set up from `infra/.env.example`; the owner's running stack was not stopped or changed.
Raw reports: [raw/](raw/) (`verification-phase-02-*.md`).

## History

1. First pass at 62ffc76: **fail**. Four integration tests (`test_dsh_usage.py` x3,
   `test_step_limit_stops_a_runtime_that_does_not_exit`) depended on the developer's
   `VLLM_BASE_URL`; with the example env they failed, and CI's stack job would too. The as-built
   check found the same, plus wording issues.
2. Fixed in d170701 (tests set their own endpoint or build their config after the fake model
   starts) and 86cfec8 / 7b06ce6 (as-built wording). Re-verified at 86cfec8 with `VLLM_BASE_URL`
   empty: all pass. The corrected wording was re-checked against 86cfec8: no contradiction.

## Checks (final, at code 86cfec8)

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `infra/.env` from `.env.example` (own project, ports); `make up`, `make status`, `make migrate` | healthy, 0004 | "all services healthy"; "0003 -> 0004" | pass |
| Lint, format, types | `ruff check .`, `ruff format --check .`, `mypy` | clean | clean; 118 files | pass |
| Plans, agents | `check_plans.py`, `sync_agents.py --check` | 0 errors | 0 errors; up to date | pass |
| Unit | `uv run pytest` | pass | 267 passed, 178 deselected | pass |
| DSH integration (overview command) | `uv run --env-file infra/.env pytest -m integration tests/integration/test_dsh_*.py` | pass, no model endpoint | 55 passed | pass |
| Conformance (dsh) | `pytest -m integration tests/test_runner_conformance.py` | pass | 19 passed | pass |
| Smoke | `make smoke` | pass | 150 passed, 4 skipped (`test_model_endpoints.py`: no endpoint, expected) | pass |
| R18 outcome cases | within the integration run | spike TaskResults up to D9/D11 | 12 parametrized cases + lost-after-finish + cancel passed | pass |
| Evidence | revisions, remote, docs diff, secrets, transcripts | clean | see [raw/verification-phase-02-evidence-checks.md](raw/verification-phase-02-evidence-checks.md); `git diff 86cfec8 7b06ce6 -- . ':!docs'` empty | pass |

## As-built claims

All claims in the phase 01 and phase 02 sections were confirmed against the code and the live
disposable stack (raw/verification-phase-02-as-built.md), after the wording fixes. Remaining Nits,
accepted:

| Claim | Status | Note |
|---|---|---|
| Usage accounting: unobserved usage set to NULL when the attempt finishes | confirmed with a Nit | a finished row whose earlier attempt was unobserved holds a number with `usage_known = false`, per the notes.md#d7 rule; the sentence reads as the attempt's own usage |
| Isolation probe runtime result; tests pass without an endpoint | confirmed by earlier runtime evidence | the narrow re-check could not run them; the follow-up run at 86cfec8 observed both (raw/verification-phase-02-follow-up.md) |

## Findings

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| V1 | Major | Four integration tests needed the developer's `VLLM_BASE_URL` | fixed in d170701; re-verified |
| V2 | Major | As-built Tests section described a command that failed as documented | fixed (V1) and reworded in 86cfec8 / 7b06ce6 |
| V3 | Minor | `:dev` image tags are shared by every checkout on a host; the documented start did not rebuild the worker image | documented as a known limit; start instructions build both images |
| V4 | Nit | Phase 01 probe sentence stale; launcher op list missed `members`; usage and test descriptions imprecise | reworded |
| V5 | Note | The verifier's build retagged the shared `:dev` images on the host; the owner's running stack kept running on its own image | reported to the owner |

## Verdict

**pass**: every acceptance test and demo item passed with observed output at 86cfec8, the as-built
claims at 7b06ce6 are confirmed, and the evidence checks are clean.

---
review: verification
phase: Phase 2 messaging (plan docs/plans/2026-11-18-phase-2-events-and-comms, phases 02 and 03)
change: docs/plans/2026-11-18-phase-2-events-and-comms
rfc: n/a
adrs: [ADR-0007, ADR-0009]
commit_sha: 417c441c0f3c65ec637f873113a41d72aeda1e0e
docs_sha: 8e9802ad67a36d28fbf8785cf4dd2ab58e65d051
diff_base: 7f0ed8538119ca7de512a73d3341ef24d0a31cf7
session: coordinator with fresh verifier subagents run one at a time (docs/reviews/README.md rules 1 and 8; light tier, independence from impl-review waived per rule 7)
date: 2026-11-19
verdict: pass
reviewers:
  - { lens: acceptance and demo (at 417c441), status: completed, result: pass }
  - { lens: as-built claims (code and docs 417c441), status: completed, result: 1 Major, 5 Nits (docs only) }
  - { lens: as-built follow-up (docs f19ea8f), status: completed, result: 6 confirmed, 1 imprecision }
  - { lens: as-built follow-up (docs 8e9802a), status: completed, result: pass }
---

# Verification: Phase 2 messaging, the inbox, the comms MCP server and waiting tasks (issue #79)

## Inputs

A disposable worktree of the pinned commit, with `infra/.env` from `infra/.env.example` changed
only in the Compose project name (`pmphase2`) and its ports, so the owner's `praxismesh` stack was
not touched; the fake model as the model endpoint (no local model was available to the
verifier). The roadmap's Phase 2 file, the plan and its phases 02 and 03, README, AGENTS.md, the
Makefile, the runbook ("Messaging between tasks"), the demo record and script, the as-built
overview and schemas. Raw reports: [raw/messaging-verification-*.md](raw/). Demo evidence:
[docs/demos/phase-2.md](../../demos/phase-2.md). The event-table half of Phase 2 was verified
separately: [verification-events.md](verification-events.md).

## History

1. Acceptance and demo at `417c441`: **pass**. Every check and test passed; the demo passed every
   messaging checklist item on the fake model. The recorded run on the owner's local model could
   not be reproduced (blocked, not passed). Three documentation points (V1-V3).
2. As-built claims at `417c441`: one Major (A1: the idle timeout ends a waiting task without a
   claim; the docs said it claims again) and five Nits, all in documentation. Corrected in
   `e851939` and `f19ea8f`; `f19ea8f` keeps the demo script as verified, so the docs revision
   changes nothing outside `docs/`.
3. Follow-up at `f19ea8f`: the six corrected statements confirmed; one imprecision (A7: an idle
   ending cancels unanswered questions to the task rather than marking them `undelivered`).
   Corrected in `8e9802a`.
4. Follow-up at `8e9802a`: both corrected statements confirmed; no findings.

## Checks

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| Setup | `make up`, `make db-roles`, `make migrate` (pmphase2) | healthy; migrations at head; the `praxis_comms` role | all as documented; `0006 (head)`; role present with its grants | pass |
| Repository checks | AGENTS.md "Checks" (`uv sync --locked`, ruff, ruff format, mypy, pytest, the three check scripts) | exit 0 | all exit 0 | pass |
| Unit | `uv run pytest` | pass | `340 passed`; `tests/test_task_workflow_waiting.py` 15 of 15 | pass |
| Integration | `uv run --env-file infra/.env pytest -q -m integration` (pmphase2 workers stopped, as their dispatcher would take the tests' wake rows) | pass | `247 passed, 4 skipped` (the model-endpoint tests: no real endpoint), including the messaging suites `test_messages.py`, `test_comms_mcp.py`, `test_comms_role.py`, `test_dispatcher.py`, `test_harness_activity.py`, `test_two_agents.py`, `test_messaging_failures.py`, `test_messaging_endings.py`, `test_messaging_history.py` | pass |
| History bound (R33) | `test_messaging_history.py` output | every run under 2,000 events; at most one Signal for 50 messages in one turn | 100 wakes: runs of 1,009, 1,013 and 443 events; 50 messages: one run of 43 events, 0 `inbox` Signals | pass |
| Demo (task 2.1) | `sh infra/demo/phase-2-messaging.sh` on the fake model | the roadmap's messaging checklist | idle B woken, correlated answer to A; observer reconnect showed every offset once; C's question expired and C was told; E's cross-request send `rejected`; histories one run of about 55 events each | pass |
| Demo on the local model | the recorded run in docs/demos/phase-2.md | - | the verifier has no local model | blocked (recorded by the implementer) |
| Docs describe this code | `git diff --stat 417c441 8e9802a -- . ':!docs'` | empty | empty | pass |
| Remote | `git branch -r --contains` both SHAs | on the remote | `origin/feat/79-agent-messaging` | pass |
| Nothing committed that must not be | secret pattern and transcript scan of both SHAs | no secret, no session transcript | the pattern matches only where it is quoted (the verify-phase skill, the Phase 1 evidence); the `.jsonl` files are spike fixtures and results, not session transcripts | pass |
| CI on the tested code | `gh api .../commits/417c441/check-runs` | informational | no runs (CI runs on pull requests) | not run |
| gitleaks, actionlint | - | - | not installed on the host; CI runs both | blocked locally (CI) |

## Findings

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| V1 | Minor | The demo script's header did not give the fake-model setup | fixed in `f19ea8f`: the demo record's Reproduce line gives it (the script stays as verified) |
| V2 | Trivial | README's status line still says Phase 2 has not started | open until close: plan task 2.2 updates the status lines after verification |
| V3 | Trivial | The messaging demo shows batching only on a 13-event task | accepted: batching under a busy response is recorded in the events demo |
| A1 | Major | The overview and runbook said an idle waiting task claims again; it ends `succeeded` without a claim | fixed in `e851939`; confirmed at `f19ea8f` and `8e9802a` |
| A2 | Nit | The comms role "nothing else": it also has `CONNECT`, `USAGE` on `public` and `PUBLIC` reads | fixed in `e851939` |
| A3 | Nit | The runbook said `make workers-up` starts the orchestrator first; it starts every worker at once | fixed in `e851939`: the runbook starts the orchestrator worker first |
| A4 | Nit | "Every ending runs `complete_task`" omits the endings before the task is recorded | fixed in `e851939` |
| A5 | Nit | schemas.md said 16 KB; the limit is 16,384 characters | fixed in `e851939` |
| A6 | Nit | The `ask_agent` "default 300 s" read as `max_ask_wait`'s default | fixed in `e851939` |
| A7 | Nit | An idle ending was said to make every unread row `undelivered`; questions to it are cancelled | fixed in `8e9802a`; confirmed |
| U1-U4 | Unverifiable | Runtime claims (rerun after a kill, NOT_FOUND for a closed Workflow, comms tools failing without the role, replay by old code) | accepted: each is consistent with the code, and U1 and U2 are exercised by `test_messaging_failures.py` and `test_dispatcher.py`, which passed |

## Verdict

**pass**: at `417c441` every acceptance test and demo step that could run passed with observed
output (the local-model run is blocked for the verifier, not passed, and is recorded by the
implementer); the docs at `8e9802a` are confirmed or marked unverifiable with reasons;
`git diff --stat 417c441 8e9802a -- . ':!docs'` is empty; both SHAs are on the remote.

# Phase 3A persistence, phase 02: acceptance walkthrough

Date: 2026-11-21. Tested implementation: `4dde76d70a3a7e378dddb1a7714f0a9ddc76362a`; docs
`0d9db273d179c27f8abb203e85524625c1ef040d`. Contract: [plan](../plans/2026-11-19-phase-3a-persistence-and-lifecycle/plan.md),
phase 02. Phase 02 has no demo checklist: the plan's demo is phase 03's (task 3.2). This record
collects what the gate verifier observed running the documented operator commands; it is not a
live audience demo. Verdict and full evidence: [verification-persistence-02.md](../reviews/phase-3a/verification-persistence-02.md)
and its [raw reports](../reviews/phase-3a/raw/).

## Environment

A disposable worktree of the tested commit; `infra/.env` from `infra/.env.example` with only the
README "Several checkouts" and "Model endpoint" changes (Compose project `pmverify3a`, its own
ports, `VLLM_BASE_URL=http://spark-01:8000`). Real Temporal, SeaweedFS and the model; Python 3.11
through `uv`; stack images as pinned in `infra/docker-compose.yml`.

## Steps

| # | Command or action | Expected (runbook) | Observed | Result |
| --- | --- | --- | --- | --- |
| 1 | `./agentctl task submit --wait --instructions "..." --input orders.csv --output order-summary.md` (twice, two requests, same input) | both succeed | `"status": "succeeded"`; `task output` printed the order summary | pass |
| 2 | `./agentctl gc --dry-run` | the plan, by reason; nothing changes | `"batches": 0, ... "unrecognised": [], "finished_from_earlier_runs": 0` (nothing has expired on a fresh stack) | pass |
| 3 | `./agentctl request delete REQ --dry-run` | the plan; nothing changes | `"batches": 8, "rows": 35, "references": 26, "blobs": 9`, by reason; database snapshot unchanged | pass |
| 4 | `./agentctl events prune --task TASK_B --below 5 --dry-run` | nothing changes | `"events": 4`; `tail` still starts at offset 1 | pass |
| 5 | `./agentctl request delete REQ` | removes, redacts, records | the same counts as the dry run; exit 0 | pass |
| 6 | `./agentctl task output TASK_A order-summary.md` | no outputs after a delete | `error: task ... has no output 'order-summary.md' (outputs: none)`, exit 2 | pass |
| 7 | `./agentctl task status TASK_A`; `./agentctl tail TASK_A --no-follow` | content redacted, IDs and usage kept; events expired | `"summary": "[deleted 2026-11-21]"`, `"artifacts": []`, usage kept, a `deleted` attempt row; `expired: events before 27 were pruned` | pass |
| 8 | Task B, which shares the input file | a shared blob stays | B's input still reads | pass |
| 9 | Refusals: delete a request with a running task, without and with `--force` | refused, nothing changes | refused, naming the task; `--force` refused for a running Workflow | pass |
| 10 | Terminate a Workflow, then `request delete REQ --force` | proceeds; reason shown | proceeds; plan, report and first tombstone list `"forced": {"task-...": "closed"}` | pass |
| 11 | Resubmit the deleted request's file, then `./agentctl gc` | the new task reads it; gc keeps it | the blob is live again, its references live; `gc` reported `batches 0` and the blob stayed | pass |
| 12 | A second removal while one holds the lock | fails at once | "another gc, request delete, events prune or backup is running; try again when it ends" | pass |
| 13 | Failure case: the as-built check of the runbook | (found by this verification) | the runbook overstated what the audit log refuses; corrected in `0d9db27` and confirmed | recovered |

## Cleanup

The verifiers wrote only under the worktree's `.verify/` and to the pmverify3a stack. The stack
is torn down with `make reset` in the worktree, which is then removed (`git worktree remove`).
The owner's `praxismesh` stack was not touched.

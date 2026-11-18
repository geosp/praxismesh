<!-- Verbatim subagent report (adr-review-0007-0008-round-2, targeted follow-up at 03dd1b6); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# ADR review round 2: ADR-0007 and ADR-0008 (branch docs/62-close-dsh-plan, HEAD 03dd1b6)

This is a targeted follow-up under docs/reviews/README.md rule 6. I read both ADRs at HEAD, the round-1 report, and `git diff 97578b7..HEAD -- docs/adr`. I checked the claims against harness_activity/activity.py, common/persistence/repositories.py, common/persistence/retention.py, harness_activity/dsh/ledger.py, harness_activity/dsh/runner.py, orchestrator/activities.py, migration 0004, notes.md (#d9, #d10, #rollout) and reviews.md (F106). Every test named in the two Confirmation sections exists at HEAD.

## Round-1 findings: status

| Round-1 finding | Status at HEAD | Evidence |
|---|---|---|
| 0007 M1 (stale writes on the failure path; `close_unfinished` exception) | Mostly fixed. The new list of unfenced writes is incomplete (see the new M1 below). | activity.py:309-343, repositories.py:273-311 |
| 0007 M2 (orphaned audit blobs) | Fixed. The ADR now says the blobs are kept indefinitely and adds a Phase 3A follow-up. | retention.py:1-3, :17; activity.py:554 |
| 0007 Nit (unserviceable refusal) | Fixed. | activity.py:235-237 |
| 0007 Nit (ledger dispatch returns False) | Fixed. | repositories.py:503-510, ledger.py:95-98, dsh/runner.py:580-581 |
| 0007 Nit (32-bit hash) | Fixed. | repositories.py:380 |
| 0007 Nit (unfenced repository writers) | Fixed. | repositories.py:183, :423 |
| 0008 M1 (scope limited to ledgered runners) | Fixed. The decision is scoped to DSH, and `openai_agents` is stated as an accepted limit. One wording detail remains (Nit below). | orchestrator/activities.py:48-49, repositories.py:350-351 |
| 0008 Nit (default window fallback) | Fixed, and it matches the code. | activity.py:359, orchestrator/activities.py:53-58 |
| 0008 Nit (downgrade writes 0) | Fixed. | 0004:64-65, notes.md:103-104 |
| 0008 Nit (effective budget) | Fixed. | orchestrator/activities.py:85 |
| 0008 Nit ("Phase 2 events carry `usage_known`") | Fixed (removed). | — |
| 0008 Nit (D11 bundled with the rest) | Fixed. The title is wider and the Context explains why D11 is bundled. | — |

## ADR-0007: Fence every harness attempt's writes in one locked transaction per task

### Major

**M1. The new list of writes that skip the fence presents itself as complete. It misses one write and gives the charge too narrow a scope.**
- Location: Decision outcome, the bullet "Two writes skip the newer-attempt check, and must stay bounded as they are".
- Statements: "Two writes skip the newer-attempt check" and "charging unsettled requests on a failure (`close_unknown`) is unfenced (a known deviation, migration plan F106)".
- Evidence:
  - The charge does not run only on a failure. `_open` calls `_charge`, which calls `close_unknown`, on every DSH attempt. It runs after the fenced `start` (activity.py:399-403, :376, :353), so a newer attempt can start between the two. F106 itself is not limited to failures: "A stale attempt's `_charge` rewrites usage columns without the fence (R6)" (reviews.md:293; notes.md:161-162 "a stale attempt's charge writes usage columns unfenced").
  - The ADR states no bound for `close_unknown`, although it says these writes "must stay bounded as they are". The bound is earlier attempts of the same turn only: `attempt < :a`, where `:a` is the writer's own attempt at open and the writer's attempt + 1 on a failure (repositories.py:550, activity.py:280, :309).
  - A third attempt write also skips the check. `UsageLedgerRepository.settle` takes neither the lock nor the newer-attempt check (repositories.py:512-536); the gateway calls it on every response (gateway.py:297, :308). It is safe only because it updates its own row `AND settled_at IS NULL`, and a newer attempt's `close_unknown` sets `settled_at` on earlier unsettled rows first (repositories.py:553-559). A future change to either statement could break that guarantee unnoticed.
- Why it matters: this bullet is the ADR's answer to round-1 M1. The Follow-up says a write path "must take the fence or justify why it need not", so the list of exceptions has to be complete and correct to be checkable.
- Fix:
  - Say "three writes".
  - Describe the charge as running "at attempt open and on a failure", bounded to earlier attempts of the same turn (below the writer's attempt, or through it on a failure).
  - Add `settle`, which updates only the writer's own still-unsettled ledger row, so a request a newer attempt has already closed stays closed.

### Nits
- Decision outcome, bullet 2: "On the success path the Activity then raises `Superseded`". A stale start (activity.py:400-401) is not on a "success path". "Otherwise (no runner failure)" would be more accurate.
- Links: F106 is cited as "migration plan F106", but Links gives only notes.md#d10. The deviation is recorded in notes.md#rollout (notes.md:161), which round 1 also cited; add it.

Verdict ADR-0007: changes-requested

## ADR-0008: Count ledgered model usage over every attempt, and record unobserved usage as unknown and charged, never as zero

No Blocker or Major. The new scoping is accurate:
- `task_totals` returns early when there are no ledger rows (orchestrator/activities.py:48-49).
- `_ledger_usage_sql` leaves rows that have no ledger rows unchanged (repositories.py:350-351).
- The fallback window matches orchestrator/activities.py:53-58 and activity.py:359.
- The bundling rationale meets the one-decision rule.
- The options, the downsides and the Confirmation tests are real and exist.

### Nits
- Consequences, the `openai_agents` "Bad" bullet: "a lost `openai_agents` attempt keeps what its last heartbeat reported (0 when it never reported)". This is true of the turn's running total, which the next attempt takes from heartbeat details (activity.py:214, :104-121, :148-156). The lost attempt's own `task_attempts` row always stays at 0, because nothing writes heartbeat usage to it and `_ledger_usage_sql` skips it (repositories.py:162-164, :350-351, :366). Say "the turn's total keeps what its last heartbeat reported; the lost attempt's own row stays at 0 tokens".
- docs/adr/README.md:19: the index title ("Count ledgered model usage over every attempt; record unobserved usage as unknown and charged, never as zero") differs from the ADR title ("..., and record ..."). Make them identical.

Verdict ADR-0008: pass

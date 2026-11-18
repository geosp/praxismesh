<!-- Verbatim subagent report (adr-review-0007-0008-round-1, branch docs/62-close-dsh-plan at 97578b7); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# ADR review: ADR-0007 and ADR-0008 (branch docs/62-close-dsh-plan, HEAD 97578b7)

Inputs read at HEAD: both ADRs, docs/adr/README.md, docs/templates/adr.md, ADR-0005, ADR-0006, plan.md (R6, R7, R11-R13, D7, D9, D10, D11), notes.md (#d7, #d9, #d10, #rollout), decision-log.md, and the code and tests the ADRs cite. All cited test names exist at HEAD. CI's `stack` job runs them through `make smoke`, which runs `pytest -m integration tests/integration` (Makefile:104-105, ci.yml:103-120). The phase 03 demo record shows `usage_known: false` for a lost-attempt task (docs/demos/general-dsh-production-harness-03.md:16, :31).

## ADR-0007: Fence every harness attempt's writes in one locked transaction per task

### Major

**M1. The ADR says a stale attempt writes nothing, but on the runner-failure path it does write. The ADR also drops the plan's recorded exception for `close_unfinished`.**
- Location: Decision outcome, bullet 2.
- Statement: "a stale write raises `FenceRejected` and the Activity raises `Superseded`, writing nothing."
- Evidence: when a runner reports a failure, `_runner_failed` behaves differently.
  - It first calls `_charge`. `_charge` runs `close_unknown`, which updates `usage_ledger.settled_at` and `task_attempts` usage under the lock but without the newer-attempt check (harness_activity/activity.py:308-310; common/persistence/repositories.py:551-574).
  - It then suppresses `FenceRejected` from the fenced finish (activity.py:313).
  - Finally it raises `CancelledError` or `ApplicationError`, not `Superseded`. On a non-retryable failure it also calls the unfenced `close_unfinished` (activity.py:330-343). The `NonRetryableError` path does the same (activity.py:271-277).
- Why it matters: notes.md#d10 records this exception: "`close_unfinished` is unfenced but touches only rows at or below the writer". The bound comes from `through_attempt` (repositories.py:280-311). The ADR leaves this rule out, and a future change must keep it. The ADR's Follow-up cites only notes.md#rollout/F106, which covers the unfenced charge but not `close_unfinished`.
- Fix: narrow the claim to "fenced writes refuse". Record that `close_unfinished` is unfenced and limited to rows at or below the writer (and that task completion closes the whole task), and that the charge is unfenced (F106).

**M2. The downside about orphaned artifact blobs claims a cleanup that does not exist.**
- Location: Consequences, the second "Bad" bullet.
- Statement: "a stale attempt can still upload artifact blobs that nothing references; they stay until retention removes them."
- Evidence: output blobs are stored as `retention="audit"` (activity.py:554).
  - `DEFAULT_LIFETIME["audit"]` is `None`, "kept until an operator policy says otherwise" (common/persistence/retention.py:17).
  - Retention "records them only; deletion and garbage collection arrive in Phase 3A" (retention.py:1-3).
- Today these blobs are kept indefinitely, so the downside is understated. State that, and add Phase 3A garbage collection of unreferenced audit blobs as a follow-up.

### Nits
- Decision outcome, bullet 3: "A template-version refusal inserts an uncounted `refused` row". The preflight `Unserviceable` refusal (`dsh_unserviceable`) also calls `record_refusal` (activity.py:235-237), so say "a refusal (template version or unserviceable worker)".
- Decision outcome, bullet 2: "a stale write raises `FenceRejected`". A stale ledger dispatch returns `False` instead (repositories.py:503-510). The gateway then denies the request as `superseded` (ledger.py:95-98), and the DSH runner raises `Superseded` (dsh/runner.py:580-581).
- Consequences "Bad" (serialization): `hashtext` is a 32-bit hash (repositories.py:380), so two different tasks can collide and share a lock. Worth one clause.
- Follow-up: the repository still exposes unfenced writers, `CheckpointRepository.insert` (repositories.py:423) and `finish(fenced=False)`, the default (repositories.py:183). Naming them would make "a new write path must take the fence" checkable.

Verdict ADR-0007: changes-requested

## ADR-0008: Record unobserved model usage as unknown and charge it conservatively, never as zero

### Major

**M1. The ADR states the rule for every runner, but the code and the plan apply it only to ledgered (DSH) runners, and one consequence bullet contradicts itself.**
- Location: title, Context, Decision outcome bullets 1-3, and the second "Bad" bullet in Consequences.
- Statements:
  - Title: "Record unobserved model usage as unknown ... never as zero".
  - Second "Bad" bullet: "every runner must route model calls through a ledgered gateway, or its usage is unknown; `openai_agents` reports usage from its SDK, and DSH through the gateway."
- Evidence: `openai_agents` has no ledger rows. Its usage comes from SDK responses (harness_activity/runner.py:173-174) and travels in heartbeats.
  - Task completion skips the ledger reconciliation: "no ledger rows: openai_agents counts in the Activity" (orchestrator/activities.py:47-48).
  - `_ledger_usage_sql` leaves "Rows of turns with no ledger rows (openai_agents)" alone (repositories.py:349-351).
  - The token columns keep `server_default="0"` (migrations/versions/0003_phase1_tables.py:68-69), and migration 0004 only makes them nullable (0004:34-35).
- Consequence: a lost `openai_agents` attempt's row stays at 0 tokens with `usage_known = true`, and any usage after its last heartbeat goes unrecorded. Its usage is not reported as unknown, which contradicts the bullet's "or its usage is unknown".
- The plan scopes these rules to the gateway ledger: R11 is "Usage comes from the gateway ledger", and the decision log entry for 2026-11-16 reads "DSH turn usage ... is cumulative" (decision-log.md:102).
- Fix: scope the decision to runners whose model calls go through the ledgered gateway (DSH today). State `openai_agents`'s actual behavior (SDK-reported, heartbeat-carried, lost usage after the last heartbeat not recorded) as an accepted limit rather than a rule it satisfies. Or record a new decision if all runners must comply.

### Nits
- Decision outcome, bullet 3: "charged the template's `context_window`". When the template has no window, the code falls back to `DEFAULT_CONTEXT_WINDOW` (activity.py:359). When the orchestrator no longer has the task's template version, it uses `max(current, DEFAULT_CONTEXT_WINDOW)` (orchestrator/activities.py:52-58). Mention the fallback.
- Decision outcome, bullet 2: "A NULL is never replaced with 0". The migration 0004 downgrade does replace NULL with 0 (0004:64-65). Add "(rollback below 0004 is unsupported, notes.md#d7)".
- Context: "Task budgets (`max_tokens` on the profile)". The effective budget is `min(profile.max_tokens, template.max_tokens_cap)` (orchestrator/activities.py:85).
- Follow-up: "Phase 2 events carry `usage_known` unchanged" is not decided in the plan or notes, and `AgentEvent` has no such field (docs/roadmap/schemas.md:15). Mark it as a proposal, or drop it.
- One decision per ADR: D11 (every attempt's usage counts, settled usage included) is broader than "unobserved usage", which is all the title covers. Either widen the title or note that D11 is bundled because it shares the same ledger derivation.

Verdict ADR-0008: changes-requested

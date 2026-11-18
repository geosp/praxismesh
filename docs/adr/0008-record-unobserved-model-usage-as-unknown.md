---
id: ADR-0008
title: Record unobserved model usage as unknown and charge it conservatively, never as zero
status: proposed
date: 2026-11-17
issue: "#62"
related:
  - docs/plans/2026-11-15-dsh-production-harness/plan.md
  - docs/adr/0005-adopt-dsh-as-primary-agent-harness.md
supersedes: null
superseded_by: null
---

# ADR-0008: Record unobserved model usage as unknown and charge it conservatively, never as zero

## Context and problem statement

Task budgets (`max_tokens` on the profile) and reported spend depend on token usage. Usage
is known only when a model response arrives. When a worker dies mid-request, a deadline
stops a runtime, or an attempt is lost, the request may have consumed tokens that nobody
observed. The DSH spike stored such usage as 0 (spike findings F1, F2), which understates
spend and lets a task exceed its budget across retries. Failing the turn instead would make
every worker loss fatal, against the recovery contract.

The migration plan requires usage from the gateway ledger (R11), unknown usage recorded and
never zero (R12), and unknown usage charged conservatively (R13).

## Considered options

- Record unknown usage explicitly, charge each unobserved request an upper bound, and count
  every attempt of a turn.
- Store 0 for unobserved usage.
- Fail the turn when usage cannot be observed (the spike's fail-closed denial).
- Count only the last attempt's usage.

## Decision outcome

Chosen option: "Record unknown usage explicitly and charge an upper bound", because it never
reports unobserved spend as zero (R12) and keeps worker loss recoverable while the budget
still bounds spend (R13).

- A ledger row is written before each model request is dispatched and settled with the
  response's usage (`usage_ledger`).
- Token columns are nullable, and `usage_known` on attempts and results says whether the
  numbers are complete. A NULL is never replaced with 0.
- Each request left unsettled is charged the template's `context_window` as input plus the
  per-request output cap (2048 tokens, which the gateway enforces on every request) as
  output, and the result reports `usage_known: false`. The charge is applied by the next
  attempt, by a turn that ends with no later attempt, or at task completion.
- Turn usage (tokens and inner turns) is cumulative over all of a turn's attempts.

Rejected: zero, because it hides spend; failing the turn, because worker loss would become
fatal; the last attempt only, because retried and lost attempts' spend would disappear.

### Consequences

- Good, because a reported total is never below what was spent, and `usage_known` tells
  readers when it is an estimate.
- Good, because a lost attempt is retried, not fatal.
- Bad, because the charge overstates spend: a lost request costs `context_window` + 2048
  tokens and can exhaust a budget sooner than the real use would.
- Bad, because every runner must route model calls through a ledgered gateway, or its usage
  is unknown; `openai_agents` reports usage from its SDK, and DSH through the gateway.
- Follow-up: a new runner or model path must write ledger rows or report usage as unknown;
  Phase 2 events carry `usage_known` unchanged.

### Confirmation

`tests/integration/test_persistence_phase1.py::test_unknown_usage_is_stored_as_null_never_zero`;
`tests/integration/test_dsh_usage.py` (charging on non-retryable failure, cancel, retry,
exhaustion and task completion; `test_retryable_failure_is_charged_once_across_attempts`);
`tests/integration/test_harness_activity.py::test_lost_attempt_usage_is_seeded_and_counted`;
`tests/test_dsh_runner_parts.py::test_output_is_capped_at_the_charge_assumption`; run by CI.
The demo record of the migration's phase 03 shows a lost attempt's task reporting
`usage_known: false`.

## Links

- [Migration plan](../plans/2026-11-15-dsh-production-harness/plan.md), D7, D9, D11, R11-R13; notes.md#d7, #d9.
- [Decision log](../roadmap/decision-log.md), 2026-11-15 and 2026-11-16 usage entries.

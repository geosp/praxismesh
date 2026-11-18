---
id: ADR-0008
title: Count ledgered model usage over every attempt, and record unobserved usage as unknown and charged, never as zero
status: accepted
date: 2026-11-17
issue: "#62"
related:
  - docs/plans/2026-11-15-dsh-production-harness/plan.md
  - docs/adr/0005-adopt-dsh-as-primary-agent-harness.md
supersedes: null
superseded_by: null
---

# ADR-0008: Count ledgered model usage over every attempt, and record unobserved usage as unknown and charged, never as zero

## Context and problem statement

Task budgets (the effective token budget is the smaller of the profile's `max_tokens` and the
template's cap) and reported spend depend on token usage. Usage is known only when a model
response arrives. When a worker dies mid-request, a deadline stops a runtime, or an attempt
is lost, the request may have consumed tokens that nobody observed. The DSH spike stored such
usage as 0 (spike findings F1, F2), which understates spend and lets a task exceed its budget
across retries. Failing the turn instead would make every worker loss fatal, against the
recovery contract.

The migration plan requires usage from the gateway ledger (R11), unknown usage recorded and
never zero (R12), unknown usage charged conservatively (R13), and turn usage cumulative over
attempts (D11). The rules apply where model calls go through PraxisMesh's ledgered gateway,
which is the DSH runner today. This ADR records them together because they are one
accounting model derived from the same ledger rows: counting every attempt (D11) is what
makes a charge for a lost attempt's requests reach the turn's total.

## Considered options

- A ledger per request: count every attempt's settled usage, record unobserved requests as
  unknown, and charge each an upper bound.
- Store 0 for unobserved usage.
- Fail the turn when usage cannot be observed (the spike's fail-closed denial).
- Count only the last attempt's usage.

## Decision outcome

Chosen option: "A ledger per request", because it never reports unobserved spend as zero
(R12), keeps worker loss recoverable while the budget still bounds spend (R13), and keeps
retried attempts' spend in the total (D11).

For runners whose model calls go through the ledgered gateway (DSH):

- A ledger row is written before each model request is dispatched and settled with the
  response's usage (`usage_ledger`, R11).
- Token columns are nullable, and `usage_known` on attempts and results says whether the
  numbers are complete. A NULL is never replaced with 0 (rolling back below migration 0004,
  which would, is unsupported).
- Each request left unsettled is charged an input of the template's `context_window` (or a
  default window when the template sets none, and at least that default when the orchestrator
  no longer has the task's template version) plus an output of the per-request cap (2048
  tokens, which the gateway enforces on every request). The result then reports
  `usage_known: false`. The charge is applied by the next attempt, by a turn that ends with
  no later attempt, or at task completion.
- Turn usage (tokens and inner turns) is cumulative over all of a turn's attempts.

Rejected: zero, because it hides spend; failing the turn, because worker loss would become
fatal; the last attempt only, because retried and lost attempts' spend would disappear.

### Consequences

- Good, because a reported DSH total is never below what was spent, and `usage_known` tells
  readers when it is an estimate.
- Good, because a lost attempt is retried, not fatal.
- Bad, because the charge overstates spend: a lost request costs `context_window` + 2048
  tokens and can exhaust a budget sooner than the real use would.
- Bad, because the guarantee covers ledgered runners only. `openai_agents` reports usage from
  its SDK's responses, carried in heartbeats, and has no ledger rows. When an
  `openai_agents` attempt is lost, the turn's total keeps what its last heartbeat reported
  (0 when it never reported) with `usage_known` still true, the lost attempt's own row stays
  at 0 tokens, and usage after its last heartbeat is not recorded. This is an
  accepted limit of the fallback runner, not a case of this rule.
- Follow-up: a new runner that should meet these rules must send its model calls through a
  ledgered gateway; bringing `openai_agents` under them would be a new decision.

### Confirmation

`tests/integration/test_persistence_phase1.py::test_unknown_usage_is_stored_as_null_never_zero`;
`tests/integration/test_dsh_usage.py` (charging on non-retryable failure, cancel, retry,
exhaustion and task completion; `test_retryable_failure_is_charged_once_across_attempts`);
`tests/integration/test_harness_activity.py::test_lost_attempt_usage_is_seeded_and_counted`;
`tests/test_dsh_runner_parts.py::test_output_is_capped_at_the_charge_assumption`; run by CI.
The demo record of the migration's phase 03 shows a lost DSH attempt's task reporting
`usage_known: false`.

## Links

- [Migration plan](../plans/2026-11-15-dsh-production-harness/plan.md), D7, D9, D11, R11-R13; notes.md#d7, #d9.
- [Decision log](../roadmap/decision-log.md), 2026-11-15 and 2026-11-16 usage entries.

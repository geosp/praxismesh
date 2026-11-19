<!-- Provenance: verbatim copy of .verify/report-follow-up-2.md, written by a fresh verifier subagent (verify-phase gate mode, brief "Follow-up after fixes") for Phase 2 messaging at code_sha 417c441c0f3c65ec637f873113a41d72aeda1e0e and docs_sha 8e9802a. Copied with cp; not edited. -->

# Phase 2 messaging: targeted follow-up 2 (rule 6)

Code: 417c441c0f3c65ec637f873113a41d72aeda1e0e. Docs: 8e9802a (fetched from origin/feat/79-agent-messaging). Read code only; no tests or services run.

## Non-docs diff
`git diff --stat 417c441 8e9802a -- . ':!docs'` printed nothing: **confirmed empty**.

## Code path
- Idle timeout: orchestrator/workflow.py:369-380. With `claim.next_deadline is None` the idle timeout is added to the limits (370-371). On `TimeoutError`, if `deadline is None` it returns `"succeeded", None` (380). There is no `claim_inbox` call on this path. A question's deadline falls through to the loop's next `claim_inbox` (381 comment, loop at 341).
- That ending goes to `_complete` (workflow.py:236-239, 294), which runs the `complete_task` Activity (workflow.py:~435). `complete_task` (orchestrator/activities.py:123) calls `MessageRepository.end_task` (activities.py:150).
- `end_task` (common/persistence/messages.py:291-332):
  - It cancels asks sent *to* the task that are still in an open status (OPEN_SQL, messages.py:31), and uses RETURNING to collect their senders (311-318).
  - It sets non-ask messages to the task that are still `pending` or `claimed` to `undelivered`, with reason "ended before reading it" (320-326).
  - It calls `_wake_if_sleeping` for each asker (327-328; messages.py:503-515).
- `context()` (messages.py:~337-358) returns the caller's `undelivered` messages, which backs the runbook's `get_task_context` remark.

## Statements
1. overview.md:254, "After a Signal or a question's deadline it claims again; at the idle timeout it ends `succeeded` without a claim; `end_task` then marks its unread messages `undelivered` and cancels unanswered questions to it, waking their askers."
   **Confirmed.** Evidence is above (workflow.py:341, 377-381; activities.py:150; messages.py:311-328).
2. runbook.md:202-205, "At the idle timeout the task ends `succeeded` without claiming; its unread messages then become `undelivered`, which their senders see in `get_task_context`, and unanswered questions to it are cancelled, which wakes their askers."
   **Confirmed.** The evidence is the same, plus `context()`, which returns the sender's undelivered rows.

Nuance (informational, no severity): `_wake_if_sleeping` inserts a wake only for an asker whose `task_inbox.sleeping` is true. An asker that is not sleeping sees the cancellation at its next claim. "Wakes their askers" is accurate for askers that are waiting.

Result: 2 of 2 statements confirmed; the non-docs diff is empty; no findings.

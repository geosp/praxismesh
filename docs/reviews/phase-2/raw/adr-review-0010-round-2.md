Review of ADR-0010 at c9bffccf2f006044cd64d6547d09557b94952b59 (read-only; I changed nothing).

ADR: /home/geo/develop/praxismesh/docs/adr/0010-wake-agents-through-a-durable-inbox.md

## Accuracy: checked and correct
- **Send path** (`/home/geo/develop/praxismesh/common/persistence/messages.py`):
  - The body limit is 16,384 characters (`MAX_BODY`, :29), and a longer body is refused (:380-381).
  - The fence comes first, then the request lock (`_enter`, :357-365).
  - A wake row is added only if the recipient is sleeping. The insert uses `ON CONFLICT DO NOTHING` and is followed by `pg_notify` (:503-515).
- **Claim** (:233-289):
  - It takes the request lock only.
  - It assigns pending rows to the given turn, and the Workflow passes `run.turn + 1` (`/home/geo/develop/praxismesh/orchestrator/workflow.py:344`).
  - It returns IDs and the next deadline, with no bodies.
  - It sets `sleeping = not ids` (:282-288). So the "sleeping flag stays set until the next claim" downside is real.
- **`end_task`** takes the request lock only (:291-329). `complete_task` calls it (`/home/geo/develop/praxismesh/orchestrator/activities.py:150`).
- **Dispatcher** (`/home/geo/develop/praxismesh/orchestrator/dispatcher.py`):
  - It `LISTEN`s and polls every 1 s (`POLL_S`, :33).
  - Each wake row gets its own transaction: delete, then Signal (:84-101).
  - A failed Signal rolls the delete back (:98-100). NOT_FOUND drops the row (:111-114).
  - It is started in the orchestrator worker (`/home/geo/develop/praxismesh/workers/main.py:199`).
  - It is the only production code that sends `inbox`. Nothing in `comms_mcp/` imports `temporalio`.
- **Workflow** (`/home/geo/develop/praxismesh/orchestrator/workflow.py`):
  - The Signal sets only a flag (:85-88), and the flag is cleared before each claim (:340).
  - The Workflow sleeps only when the claim count is zero (:363-374).
  - It continues as new past `HISTORY_LIMIT = 1000` or when Temporal suggests it, carrying `carried` (:52, :331-336).
  - Every v2 ending goes through `_complete` (:294, :405-448).
- **Measured numbers:** 1,009, 1,013 and 443 events, and 0 Signals for 50 messages. These match `/home/geo/develop/praxismesh/docs/reviews/phase-2/verification-messaging.md:55` and `/home/geo/develop/praxismesh/docs/reviews/phase-2/raw/messaging-verification-acceptance.md:61`.
- **Confirmation tests:** each one exists and checks what the ADR says it checks.
  - `test_two_agents.py:65` asserts `b_signals >= 1` and that A gets the answer.
  - `test_messages.py:237` asserts that the claim result holds no body.
  - `test_messaging_failures.py:170` asserts one stored row after a SIGKILL.
  - `test_dispatcher.py:84` and `:158` cover the stopped dispatcher and the race.
  - `test_messaging_history.py:118` and `:175` cover the history bounds.
  - `tests/test_task_workflow_waiting.py` covers the claim-before-sleep loop (:142, :173).
- **Links:** both anchors resolve (`docs/architecture/overview.md:241`, `notes.md:33`). `status` is `proposed`, and the front matter matches the template.

## ADR rules and consistency
- **ADR rules are met:**
  - It records one decision; the D11 and D17 bullets are explicitly labelled as context.
  - The context explains why the decision was needed.
  - It lists three options, and each rejected option has its own reason, which plan D6 supports ("a Temporal client in a worker subprocess, against design §4.4"; "a worker slot each").
  - It records real downsides and a follow-up, and the Confirmation can be checked.
- **Consistency:**
  - It does not contradict design §4.4: a wake row plus the dispatcher is a reading of "a trigger to wake/schedule the recipient" (`design-decisions.md:35`).
  - It does not contradict ADR-0007 or ADR-0009.
  - The dispatcher deletes the row and then sends the Signal. Plan D6 says it deletes "once the Signal is accepted". The code produces the same result, and its docstring explains why (`dispatcher.py:7-12`).

## Findings
No Blocker or Major findings.

- Nit (Consequences, second Good bullet): the numbers are attributed to `tests/integration/test_messaging_history.py`, but that file only asserts `< 2000` events (:171) and `<= 1` Signal (:206). The 1,009/1,013/443 and "no Signal" figures come from the verification run (`verification-messaging.md:55`), so cite that run instead.
- Nit (Decision outcome, the "Signals carrying the messages" rejection): the §4.4 reason does not cover the option's own "(or a service it calls)" variant, and §4.4 rules out "arbitrary Temporal admin APIs", not every client (`design-decisions.md:34`). The R28/R33 reason is enough to reject it on its own.
- Nit (Context, second bullet): "A woken turn sees every message that arrived before it started" overstates R15. The claim runs before the turn starts (`workflow.py:342-364`), so a message that lands between the claim and the turn waits for the next claim. R15 promises only "claimed before the recipient next sleeps".
- Nit (Consequences, ADR-0007 bullet): "as ADR-0009's event table does" reads as if event writes also take the request lock. They take the fence and the `event_logs` row lock (`docs/architecture/overview.md:206`).
- Nit (Considered options): the ADR does not consider sending a body-free Signal straight from the send path, which needs no wake rows or dispatcher. So it never says why the wake has to be durable: a wake row survives a failed Signal (R15). That would justify the dispatcher, which is the ADR's main cost.

Verdict: accept

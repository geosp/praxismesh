Review of ADR-0010 at commit 3f251690e7a163985e3e06dbffd0c4fac38e1d33. Nothing was modified.

ADR: /home/geo/develop/praxismesh/docs/adr/0010-wake-agents-through-a-durable-inbox.md

## Accuracy: what holds
I checked each "As built" statement against the code. All of these match:
- **Send path:** the body limit is 16,384 characters (`MAX_BODY = 16_384`, common/persistence/messages.py:29). An over-length body is refused at :380-381. The request lock is taken in `_enter` (:357-365). The wake row is added only when the recipient is sleeping, with `ON CONFLICT DO NOTHING`, followed by `pg_notify` (:503-515).
- **Dispatcher:**
  - Polls every 1 s (`POLL_S = 1.0`, orchestrator/dispatcher.py:33).
  - Handles one row per transaction, deleting it and then sending the Signal (:84-101).
  - A failed Signal rolls the delete back (:98-100), and NOT_FOUND drops the row (:111-114).
  - It is started in the orchestrator worker (workers/main.py:199).
  - It is the only production code that sends the `inbox` Signal.
- **Claim:** it returns IDs and the next deadline, with no bodies (common/persistence/messages.py:233-289). Count is a property (common/schemas/messages.py:58-60). It sets `sleeping = not ids` (:282-288).
- **Waiting loop:** `woken` is cleared before the claim (orchestrator/workflow.py:340). The loop sleeps only when the count is zero (:363-374).
- **Continue-as-new:** happens past `HISTORY_LIMIT = 1000` or when Temporal suggests it, with the state carried in `TaskStart.carried` (:52, :331-336).
- **Endings:** every v2 ending goes through `_complete`, which runs `complete_task` (:294, :405-448). `complete_task` calls `end_task` (orchestrator/activities.py:150).
- **Measured numbers:** "1,009, 1,013 and 443 events" and "no Signal" for 50 messages match docs/reviews/phase-2/raw/messaging-verification-acceptance.md:61 and docs/reviews/phase-2/verification-messaging.md:55.
- **Confirmation tests:** every test named exists and checks what the ADR says:
  - tests/integration/test_two_agents.py:65 (asserts `b_signals >= 1`)
  - tests/integration/test_messaging_failures.py:170
  - tests/integration/test_dispatcher.py:84 and :158
  - tests/integration/test_messaging_history.py:118 and :175
  - tests/test_task_workflow_waiting.py:142 and :173
- **Links:** both anchors resolve (docs/architecture/overview.md:241; the notes.md D6 heading at line 33).

## Findings

**Major: Decision outcome, first paragraph, and Considered options. The rejected long-polling option has no reason for losing, and the stated rationale is wrong for it.**
- The ADR says the chosen option is "the only option that keeps every message durable before anyone is woken, keeps bodies out of Temporal histories, and needs no Temporal client in the tool server."
- Option 3 ("One long-polling Activity per waiting task waits on the inbox until a row arrives") meets all three criteria. It reads the same durable inbox, can return IDs only, and runs in the orchestrator rather than in `comms_mcp`. So "the only option" is false.
- The ADR never says why option 3 lost. The real reason is in plan D6: "one long-polling Activity per waiting task (a worker slot each)". Plan Risks repeats it: "each holds a Workflow but no worker slot".
- Option 2 is also rejected only by that collective sentence. The concrete reasons are in plan D6 ("a Temporal client in a worker subprocess, against design §4.4") and R28/R33 (bodies and one Signal per message in history).
- The ADR rules require "the rejected ones and why they lost" (.agents/skills/docs-design/SKILL.md:38, :157). ADR-0007 shows the expected form with an explicit "Rejected: ..., because ..." line (docs/adr/0007-fence-harness-attempts-in-one-transaction.md:59-61).
- Fix: add a "Rejected:" line giving each losing option its own reason, and remove "only".

**Nits**
- Consequences, the terminated-workflow bullet: "its messages stay open until their deadlines" is true only for questions. Sends and replies have no deadline and stay `pending` (end_task never runs, messages.py:291-329). The task also stays `running`, so new sends to it are still accepted (plan Assumptions: "sends to it are accepted until their deadlines").
- Consequences, the two-hops bullet: in "a task is woken late when it is down", "it" is ambiguous. It should name the dispatcher.
- Consequences, the ADR-0007 bullet: "every inbox write can share a transaction with ADR-0007's fence" overstates. The claim and `end_task` take only the request lock, with no fence (plan D10; messages.py:238, :296). It should say "every attempt's inbox write".
- Confirmation: the core no-bodies-in-history property is backed only by a review item. tests/integration/test_messages.py:237 (`test_the_claim_inbox_activity`, which asserts the claim result holds no body, R28) could be named. Also, `test_messaging_failures.py`, `test_dispatcher.py` and `test_messaging_history.py` are given without their `tests/integration/` path.
- Decision outcome, "As built": the continue-as-new (D11) and complete_task (D17) bullets are separate decisions folded in as mechanics. That is acceptable if read as context, but the ADR's single decision is inbox plus wake-only Signal.

## Consistency
- No contradiction with design §4.4 (docs/roadmap/design-decisions.md:34-35). The wake row and dispatcher are a valid reading of "a trigger to wake/schedule the recipient".
- No contradiction with ADR-0007 or ADR-0009.
- The dispatcher's delete-then-Signal in one per-row transaction is worded differently from plan D6 ("deletes a row once the Signal is accepted"). The committed behaviour is equivalent, and the code comment explains why (orchestrator/dispatcher.py:7-12).
- No overstated measurement found.

Verdict: changes-requested

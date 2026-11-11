# PraxisMesh plan: Phase 2

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 2: Real-time events and the comms MCP

**Read first:** `PROJECT_PLAN.md`, then §4.3, §4.4; schemas.

- [ ] Verify and adopt Temporal Python Workflow Streams if suitable; otherwise add a minimal offset-based transport behind an interface. Implement event state rollover across Continue-As-New.
- [ ] Batch status/tool/token deltas; assign monotonic `seq` and `attempt_id`; document retention/truncation and retry/reset semantics.
- [ ] Implement `comms_mcp`: `post_status`, `send_to_agent`, `ask_agent`, `get_task_context`, worker-only and authorization-scoped.
- [ ] Add application-DB migrations for the message inbox/outbox and the event index on top of the Phase 0 baseline. *(Moved forward in rev 2.9: this phase's inbox depends on it.)*
- [ ] Build **durable PostgreSQL message inbox** with correlation/reply IDs, dedupe, deadline, wake-up/dispatch of idle recipients, and bounded blocking Update/Signal mechanics. Prevent circular waiting and propagate timeout/cancellation.
- [ ] Implement `agentctl tail <workflow_id>` with offset resume and gap detection; use the same internal event interface for Phase 4 gateway and Phase 8 UI.
- **Accept:** two running agents exchange an answer; idle recipient can be awakened; an unanswered request times out; worker crash and Continue-As-New do not drop accepted messages; disconnect/reconnect yields no duplicate display or gaps **within retention**; unauthorized messaging is rejected; high token volume does not explode history.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** Two agents communicate while an observer watches the conversation live.

- [ ] Open `agentctl tail` on a workflow; demonstrate Agent A asking Agent B a question and receiving a correlated answer, including waking an idle Agent B.
- [ ] Disconnect the observer and reconnect using its last offset; show retained events resume in order without duplicate display.
- [ ] Send a deliberately unanswered question to show a bounded timeout rather than a hung agent; demonstrate one unauthorized message is rejected.
- [ ] Show event batching under a busy response and a bounded Temporal history (report event count/size).
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-2.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

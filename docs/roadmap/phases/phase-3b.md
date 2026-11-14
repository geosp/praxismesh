# PraxisMesh plan: Phase 3B

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 3B: Verification, escalation, replanning and bounded execution

**Read first:** `PROJECT_PLAN.md`, then §4.3, §4.5; schemas.

*Split from the former Phase 3 in rev 2.9. Depends on Phase 3A.*

- [ ] Implement acceptance verification, separately classified infrastructure retries and quality retries, escalation, bounded replanning, plan revisioning and preservation of completed work.
- [ ] Add global/per-task ceilings: active children, graph size/depth, tokens, attempts, turns, time, cost, escalations and replans. Implement Continue-As-New with explicit child ownership tracking, state transfer and reconciliation.
- [ ] **Approval and input CLI (rev 2.10):** extend `agentctl` with `pending`, `answer`, `approve`, `reject` and `cancel`. Each command authenticates the caller, checks authorization, sends an audited Signal or Update, and is idempotent. Add an optional outbound notification hook (a generic webhook; no hosted dependency) that fires when a run enters `needs_input` or awaits approval. Phase 5 merge approvals and the Phase 8 approvals inbox use the same API.
- **Accept:** a deliberately under-tiered quality failure escalates successfully; a crashed worker does not count as quality escalation; bounded replan preserves verified results; every ceiling stops work with a clear terminal state when reached; Continue-As-New cannot orphan unfinished work; a `needs_input` question can be listed and answered through `agentctl` by an authorized identity only; the benchmark suite shows no regression beyond the owner's limit.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** Poor results are caught and escalated within hard limits, and long runs survive restarts.

- [ ] Force a quality failure at a low tier, show evidence-driven escalation to an eligible higher tier, and display the total budget and task attempt ledger.
- [ ] Inject a worker restart and Continue-As-New during active work; show verified results are reused, children are accounted for, and history size stays bounded.
- [ ] Let a run stop at `needs_input`; show it in `agentctl pending`, answer it, and show the run resume. Show an unauthorized caller being refused.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-3b.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

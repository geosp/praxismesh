# PraxisMesh plan: Phase 4A

Part of the PraxisMesh project plan, revision 2.11. Start from the core plan:
[PROJECT_PLAN.md](../../../PROJECT_PLAN.md). This planned phase follows Phase 4
and precedes Phase 5, under [ADR-0003](../../adr/0003-early-compose-task-ui.md).
Its sequencing is owner-accepted after independent planning review. Its detailed
implementation design and implementation have not started or been approved.

## Phase 4A: Live task interaction UI on Compose

**Read first:** `PROJECT_PLAN.md`, then §4.4, §4.9, §4.12; schemas when touched.

**Prerequisites:** Phase 2 event/reconnect contracts, Phase 3A task/plan records,
Phase 3B input/approval/cancellation controls, and the Phase 4 gateway with
conversation identity, background operations, authentication and authorization.
Full process tier applies: independently reviewed implementation-plan contract,
separate implementation review and verification sessions, as-built update and
saved acceptance/demo evidence. Kubernetes is not a prerequisite.

- [ ] Design and implement the task frontend in TypeScript/React/Vite, served
  locally through Docker Compose. Document setup, browser entry point, UI/API
  topology, authenticated access and cleanup. Keep the CLI and official client
  workflows supported.
- [ ] Provide task/conversation submission and continuation using only the
  Phase 4 compatibility matrix's supported request types and authorized
  profiles. Display stable response/task identifiers and a queryable task list;
  opening the browser later can retrieve the same background work.
- [ ] Display live assistant output separately from status/tool events. Show
  server-provided plan/dependency status, task attempts and budget summaries;
  do not fabricate progress, expose private reasoning, or imply future
  capabilities. Link to Temporal execution details where authorized.
- [ ] Reuse the Phase 2/4 event interface for offset resume, deduplication,
  ordering and explicit retention gaps. Closing/reloading the browser or losing
  its network connection leaves durable work running. Cancellation is explicit.
- [ ] Retrieve terminal results and existing access-controlled artifact refs
  through server APIs; preserve task/conversation identity on follow-up.
- [ ] Provide a questions and approvals inbox using Phase 3B's authenticated,
  idempotent, audited actions; answer a `needs_input` question, approve/reject
  a supported pending approval, and cancel a permitted task. Server-side
  authorization applies to every read and mutation, including direct requests.
- [ ] Extend the threat model for browser-rendered untrusted content and browser
  sessions. Render model/tool output safely, do not execute returned scripts or
  HTML, and keep secrets and privileged service credentials out of frontend
  assets and event payloads. The UI receives no direct DB, object-store admin,
  Temporal admin or Kubernetes access.
- [ ] Add browser/API acceptance tests for submission, retrieval, live events,
  reload/reconnect/gaps, continuation, approval decisions, cancellation and
  unauthorized access. Freeze browser authentication/session details and
  measurable UI acceptance thresholds in the phase RFC after Phase 4 contracts
  are established; no new mechanism is asserted verified by this plan.
- **Accept:** a user submits useful work in the browser, sees live progress,
  returns by a stable ID after disconnect, answers a question and retrieves a
  result. Reconnect preserves retained event ordering without duplicate display
  and reports gaps. Authorized approvals/cancellation work and unauthorized
  reads/actions fail through the API. Everything runs locally on Compose.

**Out of scope:** cluster/fleet management, template/profile/MCP editing,
rollout/scale controls, full operational dashboards and Phase 6B stage views
remain Phase 8. A workflow editor remains deferred. File uploads and other
unsupported Phase 4 request types are not introduced here. GitHub delivery
and merge-approval presentation may be extended once Phase 5 supplies them;
Phase 4A does not implement Phase 5 early.

**Demo checklist (required)**
**Audience-visible outcome:** A user can interact live with durable tasks in a
browser without shell access or Kubernetes.

- [ ] From documented Compose prerequisites, sign in and submit a task; show its
  stable ID, real progress/events, available dependency status and final result.
- [ ] Close/reopen the browser during background work; retrieve the same task.
  Disconnect/reconnect the observer and show ordered retained events without
  duplicates; exercise explicit retention-gap handling.
- [ ] Answer a pending question and show continuation of the same logical work;
  approve/reject supported pending decisions and cancel a separate task.
- [ ] Show unauthorized direct API reads/actions fail, and hostile task/tool
  text displays safely without script execution or secrets exposure.
- [ ] Save reproduction, exact commands/actions, IDs, environment/versions,
  expected versus observed behavior, cleanup and pass/fail in
  `docs/demos/phase-4a.md`.

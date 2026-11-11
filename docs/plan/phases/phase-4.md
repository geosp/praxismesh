# PraxisMesh plan: Phase 4

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 4: OpenAI-compatible gateway

**Read first:** `PROJECT_PLAN.md`, then §4.6, §4.9; schemas.

- [ ] `/v1/models` exposes authorized agent profiles.
- [ ] Publish and implement the **compatibility matrix** from §4.9 (`docs/api/compatibility.md`), with one contract test per listed parameter and error mapping.
- [ ] Implement `/v1/chat/completions` streaming and nonstreaming using correct `chat.completion.chunk` protocol; `/v1/responses` uses its distinct typed event protocol. Expose operational progress through separate endpoint/extension, not as fabricated assistant reasoning.
- [ ] Implement Responses background submit, `GET /v1/responses/{id}`, cancellation endpoint and reconnect behavior; client disconnect leaves durable work running by default.
- [ ] Persist `conversation_id`, `response_id`, request/idempotency keys and Temporal workflow/run references in application PostgreSQL; one conversation supports multiple turns and pending background work.
- [ ] Support `previous_response_id`, authorized `metadata.repo`/`metadata.delivery`, `needs_input` follow-ups on the correct job and resumable event streams where supported.
- [ ] Implement bearer auth **plus** per-client authorization, repo allowlists, policies, rate limits, budget checks, and audit.
- [ ] Test official `openai` Python SDK both sync/async: chat SSE, responses typed SSE, background submit/status/cancel, transient network retry, idempotency, follow-up and `needs_input` continuation.
- **Accept:** unmodified official clients work for the supported API subset; a long-running job survives disconnect; cancellation is explicit; retries don't create duplicate work; unauthorized repo or forced mode is rejected; every parameter in the compatibility matrix behaves as documented, and unsupported ones fail with a clear OpenAI-style error instead of being silently dropped.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** An unmodified OpenAI client talks to the platform, streams results, and follows up.

- [ ] Use a minimal example with the official OpenAI Python SDK to list models and receive both a Chat Completions stream and a Responses API stream using their distinct event formats.
- [ ] Submit a long-running background response, disconnect, reconnect/poll it by ID and show it finishes; cancel a separate run and show its final state.
- [ ] Provide a follow-up through `previous_response_id` or the supported conversation mechanism and resolve a `needs_input` turn without starting an unrelated task.
- [ ] Retry the same submission/idempotency key and show one underlying job; demonstrate a disallowed repository override is rejected.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-4.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

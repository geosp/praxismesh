# Fresh reader assessment: ADR-0003

Reviewed commit: `80c2dc2637840de4ebc5ab4bdd60059ab3f3db24`.
Input: `docs/adr/0003-early-compose-task-ui.md` only.
The response below is preserved verbatim.

## What this proposes

Split the UI work into an earlier Phase 4A for browser-based task interaction and a later Phase 8 for Kubernetes administration and other advanced views. Phase 4A would run locally in Docker Compose after the Phase 4 gateway, reuse existing server contracts, and support submitting, observing, resuming, controlling and retrieving tasks. This brings browser interaction into the MVP, while adding a gated phase before Phase 5 completes it.

## How the existing system works, per this document

The current plan places the UI in Phase 8, where task interaction is combined with administration that depends on Phase 7’s Kubernetes deployment work. Earlier phases already plan event observation, durable controls, questions, approvals, identity and API authorization. Docker Compose is the default deployment through Phase 6B; the document does not establish which of these capabilities are implemented today.

## Sections I could not paraphrase

None. No Blockers.

## Unexplained project-specific terms or decisions

- **Nit — Decision outcome / Consequences:** “Full process tier” and “full-tier gates” are not defined. A standalone reader cannot tell which reviews or evidence they require.
- **Nit — Decision outcome:** “Template/profile/MCP administration” and “verified-workflow views” are named without explaining their project-specific meaning. Their placement in Phase 8 is understandable, but their functional boundaries require the linked documents.

## Places where parts do not connect

No findings. The document connects the earlier UI to its prerequisite phases, separates retained administration work, and explicitly defers implementation details to later designs. The acceptance/demo covers the principal task-interaction goals.

Project instructions **were supplied automatically in the conversation**, including AGENTS.md. I opened only the named ADR and did not use other repository files.

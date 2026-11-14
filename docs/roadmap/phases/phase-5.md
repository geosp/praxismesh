# PraxisMesh plan: Phase 5

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 5: GitHub delivery

**Read first:** `PROJECT_PLAN.md`, then §4.6, §4.8, §4.13; schemas.

- [ ] **Threat model complete for GitHub delivery (rev 2.10):** before the Phase 5 design review, extend `docs/security/threat-model.md` with repository content, issue and review authors, the GitHub App credential path, the sandbox boundary and webhook ingress. The design review checks the RFC against it.
- [ ] **Security baseline before real credentials (moved forward from Phase 9 in rev 2.9):** the ADR-selected sandbox for untrusted repository code and tests is in place, holds no GitHub or App credentials and has restricted egress; tokens are redacted from logs, events and streams; an automated check confirms no credential appears in Temporal history, application PostgreSQL, `BlobStore` or logs; any endpoint reachable beyond localhost (gateway, webhook ingress) uses TLS; expired-token handling is tested. Worker-to-Temporal mTLS and payload-codec encryption remain in Phase 9.
- [ ] GitHub App auth with short-lived scoped installation tokens; keep App private keys out of agent pods and logs.
- [ ] Implement **explicitly authorized new-repository provisioning** for `new_repo_policy=ask|auto`, with `never` denying and `ask` pausing for human approval. Verify the actual GitHub identity/token permissions for repo creation independently from ordinary installation-token permissions; require owner/org allowlist, name/visibility/quotas, secret-safe bootstrap and branch protection. Use stable operation IDs, lookup-before-retry and reconciliation so failures do not create duplicate repositories.
- [ ] Durable workspace manager: fetch/clone, task worktrees/branches, integrated branch, conflict detection and recovery from git/checkpoints.
- [ ] Dedicated delivery coordinator merges task work into **one PR**, resolves overlaps through fix tasks and tracks branch/commit/PR identifiers idempotently in PostgreSQL.
- [ ] Open/update PR with plan, results, acceptance and workflow link. On retry, reconcile GitHub state before creating new resources.
- [ ] Webhook-driven CI wait with fallback reconciliation; only accept green checks on **latest head SHA**; feed CI failures to bounded fix tasks.
- [ ] Human merge approval Signal by default, optional explicit profile auto-merge; enforce branch protection and default-branch push prohibition. Approvals are issued through the Phase 3B `agentctl approve` path.
- [ ] Provide github-mcp-server inside authorized repo-capable worker templates. Sandbox untrusted tests/code without privileged credentials.
- [ ] **First tagged release (rev 2.10):** when this phase closes, tag the MVP release per `docs/release.md` with a changelog and the license-check result for anything distributed. From this tag onward, every phase demo includes an upgrade from the previous tag: migrations apply, in-flight Workflows continue or follow the documented migration path, and stored references still resolve.
- **Accept:** request creates one PR with green latest-SHA CI; failed CI is fixed; two agents' overlapping edits produce resolvable conflict rather than overwrite; crash immediately after push/PR create recovers with no duplicate PR; merge waits for required approval; no default-branch push; an authorized new-repo request creates at most one repository and delivers through the same PR/CI/approval path; unauthorized creation is denied; untrusted code runs only inside the selected sandbox; no credential appears in history, logs or stored evidence.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** A request turns into one reviewable GitHub pull request, not a direct push.

- [ ] Run a code task against an explicitly configured throwaway repository; show distinct agent worktrees integrated into a single delivery branch and PR.
- [ ] Cause overlapping edits and show an explicit conflict-resolution step; introduce a CI failure, let the agent fix it, and verify green checks on the latest head SHA.
- [ ] Crash delivery immediately after a push or PR creation and show recovery without a duplicate branch or pull request.
- [ ] Show that merge remains blocked pending the required human approval and repository branch protections.
- [ ] In a throwaway owner/org with suitable permissions, request a **new repository** and show that authorization and creation are idempotent and that delivery still goes through a PR. If the GitHub permission/test owner is unavailable, record this demo item as blocked, not passed.
- [ ] Show the sandbox holding: an untrusted test that tries to read a credential or reach a blocked host fails, and a scan of history and logs finds no token.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-5.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

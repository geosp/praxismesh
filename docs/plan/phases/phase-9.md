# PraxisMesh plan: Phase 9

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Phase 9: Hardening

**Read first:** `PROJECT_PLAN.md`, then §4.8, §4.11, §4.13.

- [ ] Payload codec encryption + `BlobStore` offload above configurable threshold; validate SeaweedFS and optional Ceph/GCS adapters; retention, checksum validation, GC and access controls. Evaluate SDK external storage only if stable/suitable.
- [ ] mTLS between workers and Temporal (self-hosted cluster), plus TLS/service identities for other sensitive links.
- [ ] Custom Prometheus metrics and Grafana dashboard for queues, quality, budgets, token usage, retries, TTFT, GPU and object-store health. Extends the Phase 1 baseline.
- [ ] Tool approval policies per tool/profile; `approval_request` event, Signal resolution and auditable decisions.
- [ ] Harden the Worker Versioning strategy adopted in Phase 7: exercise changed Workflow code, rollout compatibility and replay safety under failure injection.
- [ ] Chaos, reconciliation and recovery tests: DB unavailable, BlobStore unavailable, missing blob, replay, uncommitted workspace loss, webhook duplication, dropped event, CI/head-SHA race and pod disruption.
- [ ] Security/reliability tests for **stage-policy bypass**, self-review/self-approval, forged review evidence, commit changed after review, attempt-limit exhaustion, unauthorized GitHub repository creation, duplicate provisioning after crash, and malicious repository-supplied instructions or skill definitions. Each must fail closed with an auditable result. Trace every test to an entry in `docs/security/threat-model.md`; a threat with no test is recorded as an accepted risk with a named owner.
- [ ] `docs/operations/runbook.md`: start/stop, tier capacity, rotate secrets, replay/debug, stuck workflow, storage backup/restore, webhook reconciliation, version rollback. Builds on the Phase 3A backup/restore drill.
- **Accept:** large artifact round-trips under encryption; unsafe tool blocks for authorization; mTLS enforced; workflow code rolls without nondeterminism; failure injection recovers without duplicated side effects or data loss beyond documented retention.

**Demo checklist (required; run live or record a reproducible walkthrough)**  
**Audience-visible outcome:** Security controls and recovery procedures work during deliberately induced failures.

- [ ] Attempt a forbidden tool action and show the approval or authorization gate blocks it with an auditable record; verify encrypted large-object round-trip.
- [ ] Use the runbook to inject worker loss, a temporary PostgreSQL or blob-store outage, and a duplicate event; show bounded retries/reconciliation and no duplicate side effects.
- [ ] Roll a workflow/worker version and demonstrate replay compatibility or the documented safe migration path; confirm required secure connections are enforced.
- [ ] Present the resulting metrics, alerts, recovery record, history size, and any explicitly documented data-retention limitations.
- [ ] Save demo evidence and reproduction steps in `docs/demos/phase-9.md` (environment/versions, exact commands or UI actions, IDs/links, expected vs. observed result, screenshots or recording, cleanup, pass/fail).

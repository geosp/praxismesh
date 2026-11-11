# Proposal

## Why

Every later phase runs on a local platform stack: durable execution (Temporal), the application database, object storage and model endpoints. Phase 0 of the plan (`docs/plan/phases/phase-0.md`) builds that stack so it starts with one command, survives restarts and proves each part works, before any product logic exists. The Pre-0 spike decided "go" on the local model path (`docs/spikes/harness-vllm.md`), so the stack can now target it.

## What Changes

- A Docker Compose stack in `infra/`:
  - ParadeDB as the one PostgreSQL server (ADR-0002), hosting Temporal's databases and a separate application database;
  - Temporal Server with its UI;
  - SeaweedFS with an S3-compatible endpoint.
- `make up`, `make down` and `make migrate`; `.env.example` with no secrets committed; health checks; named volumes.
- vLLM is reached as an **external** endpoint configured in `.env` (the DGX Spark pair), with an optional Compose profile for a local vLLM on a GPU machine.
- An Alembic migration baseline for the application database, with `pg_search` available there.
- Smoke tests:
  - a hello-world Temporal Workflow;
  - both vLLM API styles (Anthropic Messages and OpenAI chat);
  - an S3 round trip against SeaweedFS;
  - migrations from a clean volume and after a restart.
- A reproducible demo, including a missing-dependency failure that gives a clear diagnostic.

Not in scope: product code (gateway, orchestrator, harness workers), Kubernetes, GCS or Ceph services (documented only), and security hardening beyond keeping secrets out of Git.

## Capabilities

### New Capabilities
- `dev-environment/local-stack`: starting, stopping, health checking and persisting the local platform stack, and diagnosing missing dependencies.
- `persistence/app-database`: the application database, separate from Temporal's, with a migration baseline.
- `storage/blob-store`: the default S3-compatible object store and its documented alternatives.
- `inference/model-endpoints`: reaching the configured model endpoints in both API styles.

### Modified Capabilities
- None (no existing specs).

## Impact

- New: `infra/` (Compose file, environment template), `Makefile`, `migrations/` (Alembic), `tests/smoke/`, a CI job that runs the stack on GitHub's runners.
- New runtime dependencies (Python, pinned in `uv.lock`): `temporalio`, `alembic`, a PostgreSQL driver, and an S3 client.
- Container images, pinned by tag and digest: ParadeDB `0.26.6-pg16` (AGPL-3.0, run unmodified; see `docs/release.md`), Temporal Server and admin tools 1.32.2, Temporal UI 2.58.1, SeaweedFS 4.53.
- Design: [docs/rfcs/phase-0-local-infrastructure.md](../../../docs/rfcs/phase-0-local-infrastructure.md).

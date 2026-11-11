# Proposal

## Why

Every later phase runs on a local platform stack: durable execution (Temporal), the application database, object storage and model endpoints. Phase 0 of the plan (`docs/plan/phases/phase-0.md`) builds that stack so it starts with one command, survives restarts and proves each part works, before any product logic exists. The Pre-0 spike decided "go" on the local model path (`docs/spikes/harness-vllm.md`), so the stack can now target it.

## What Changes

- A Docker Compose stack in `infra/`:
  - ParadeDB as the one PostgreSQL server (ADR-0002), hosting Temporal's databases and a separate application database;
  - Temporal Server with its UI;
  - SeaweedFS with an S3-compatible endpoint.
- `make up`, `make down` and `make migrate`; `.env.example` with no secrets committed; health checks; named volumes.
- vLLM is reached as an **external** endpoint configured in `.env` (the DGX Spark pair: two machines serving one model at one base URL). A local vLLM Compose profile is deferred until a GPU machine runs the stack.
- An Alembic migration baseline for the application database (`common/persistence/migrations/`, plan §6), with `pg_search` installed there by the database init.
- One-shot jobs that set up Temporal's schema and create its namespace with a retention period (§4.13), safe to repeat.
- Smoke tests:
  - a hello-world Temporal Workflow;
  - both vLLM API styles (Anthropic Messages and OpenAI chat);
  - an S3 round trip against SeaweedFS;
  - migrations from a clean volume and after a restart.
- A reproducible demo, including a missing-dependency failure that gives a clear diagnostic.

Not in scope: product code (gateway, orchestrator, harness workers), Kubernetes, GCS or Ceph services (documented only), a Compose vLLM service, and security hardening beyond keeping secrets out of Git.

## Capabilities

### New Capabilities
- `dev-environment/local-stack`: starting, stopping, health checking and persisting the local platform stack, and diagnosing missing dependencies.
- `persistence/app-database`: the application database, separate from Temporal's, with a migration baseline.
- `storage/blob-store`: the default S3-compatible object store and its documented alternatives.
- `inference/model-endpoints`: reaching the configured model endpoints in both API styles.

### Modified Capabilities
- None (no existing specs).

## Impact

- New: `infra/` (Compose file, database init script), `.env.example`, `Makefile`, `common/persistence/migrations/` (Alembic), `tests/integration/` (marked `integration`, excluded from the default unit run), a CI `stack` job, and a Dependabot `docker-compose` entry.
- New runtime dependencies (Python, pinned in `uv.lock`): `temporalio`, `alembic`, `psycopg[binary]` 3, `boto3`, `httpx`; dev: `boto3-stubs[s3]`.
- Container images, pinned by tag and digest: ParadeDB `0.26.6-pg16` (AGPL-3.0, run unmodified; see `docs/release.md`), Temporal Server and admin tools 1.32.2, Temporal UI 2.58.1, SeaweedFS `chrislusf/seaweedfs:4.53`.
- Tracking issue: #34.
- Design: [docs/rfcs/phase-0-local-infrastructure.md](../../../docs/rfcs/phase-0-local-infrastructure.md).

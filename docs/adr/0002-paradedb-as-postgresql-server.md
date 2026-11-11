---
id: ADR-0002
title: Use ParadeDB as the PostgreSQL server, shared by the application and Temporal in Compose
status: accepted
date: 2026-11-11
issue: null
related: ["PROJECT_PLAN.md §2, §3", "docs/plan/schemas.md §5", "docs/plan/design-decisions.md §4.16", "docs/plan/phases/phase-0.md"]
supersedes: null
superseded_by: null
---

# ADR-0002: Use ParadeDB as the PostgreSQL server, shared by the application and Temporal in Compose

## Context and problem statement

The plan uses PostgreSQL for two separate things: Temporal's persistence and visibility, and the application database (plan §3, §4.16, §5). The application will need more than relational queries: full-text search over transcripts, events and audit records (§5 event index, the Phase 8 UI), possibly vector retrieval for agent memory, and aggregations over task history. The owner wants one database for everything the project may need, without a separate search or vector system.

ParadeDB is PostgreSQL with extensions: `pg_search` (BM25 full-text search) and vector search through pgvector. Checked 2026-11-11: release v0.26.6 (2026-11-08), images published for PostgreSQL 15, 16, 17 and 18 (for example `paradedb/paradedb:0.26.6-pg16`), license AGPL-3.0.

Temporal constraint, from Temporal's documentation (checked 2026-11-11): persistence is tested on PostgreSQL 13 to 16 ("PostgreSQL 13.18, 14.15, 15.10 and 16.6"; 17 is not listed). Advanced visibility on PostgreSQL needs version 12 or later with Temporal Server 1.20 or later. Neither needs any extension. The current Temporal Server release is v1.32.2.

## Considered options

- **Plain PostgreSQL:** the plan's original choice. Search or vectors later would need extensions added by hand or another system.
- **ParadeDB for the application only, plain PostgreSQL for Temporal:** two database servers in Compose.
- **ParadeDB as the one server, hosting Temporal's databases and the application database in Compose.**

## Decision outcome

Chosen option: "ParadeDB as the one server", because it gives the application search, vectors and analytics inside PostgreSQL with no second system, and the owner prefers one server in local Compose.

- **Image:** `paradedb/paradedb:0.26.6-pg16`, pinned by tag (and digest in Compose). PostgreSQL 16 is the newest major version Temporal tests. Move to a newer PostgreSQL major only once Temporal's tested range includes it.
- **Separation stays logical:** Temporal's persistence and visibility databases and the application database are separate databases on the shared server, with separate roles. Temporal's databases stay private to Temporal (§4.16); the application never reads them.
- **Portability:** application tables, queries and Alembic migrations use plain PostgreSQL. ParadeDB features (`pg_search` indexes, vector columns) are used only where search or retrieval needs them, in their own migrations, so a plain PostgreSQL server can still run everything else. (Phase 0 note: migration `0002` requires `pg_search` on the main chain; a plain-PostgreSQL deployment would branch around it. Decision log, Phase 0 gate fixes.)
- **Production (Phase 7):** may split Temporal and the application onto separate servers. This ADR does not decide that.

### Consequences

- Good, because full-text search, vector retrieval and aggregations are available in the database the application already uses, with no Elasticsearch or separate vector store.
- Good, because one server keeps the local stack small.
- Bad, because the default deployment now includes an **AGPL-3.0** component. Running it unmodified as a separate service does not change PraxisMesh's Apache-2.0 license, but anyone distributing a modified ParadeDB takes on AGPL obligations. The README and the release license check must say so.
- Bad, because Temporal and the application share one server's resources and upgrade cycle locally; a PostgreSQL major upgrade must stay inside Temporal's tested range.
- Bad, because Temporal is not tested on ParadeDB as such; it is tested on the PostgreSQL version ParadeDB is built on.
- Follow-up: Phase 0 verifies Temporal's schema setup and smoke test on this image, and records the image digest.

### Confirmation

- Phase 0's Compose stack runs `paradedb/paradedb:0.26.6-pg16`. Temporal's `temporal-sql-tool` setup (plugin `postgres12`) and the hello-world Workflow smoke test pass on it; `CREATE EXTENSION pg_search` succeeds in the application database.
- The application's migrations apply on a clean volume and after a restart (Phase 0 migration baseline).
- The release license check (`docs/release.md`) lists ParadeDB as AGPL-3.0.

## Links

- ParadeDB: https://github.com/paradedb/paradedb (AGPL-3.0, v0.26.6)
- Temporal persistence and visibility: https://docs.temporal.io/temporal-service/persistence, https://docs.temporal.io/self-hosted-guide/visibility/postgresql
- Plan: `PROJECT_PLAN.md` §2, §3; `docs/plan/design-decisions.md` §4.16; `docs/plan/schemas.md` §5; `docs/plan/phases/phase-0.md`

# persistence/app-database Specification

## Purpose
The application database: separate from Temporal's own databases on the shared ParadeDB server, with versioned migrations that later phases extend (plan §4.16, §5, ADR-0002).

## Requirements

### Requirement: Separate application database
The application database SHALL be a separate database with its own role on the shared ParadeDB server. Connect privileges SHALL be revoked from `PUBLIC` and granted only to each database's own role. The application SHALL NOT read or write Temporal's databases. (Plan: Phase 0 task 1; §4.16; ADR-0002.)

#### Scenario: Role isolation
- **WHEN** the application role tries to connect to a Temporal database
- **THEN** the connection is refused

### Requirement: Migration baseline
The application database SHALL be managed by Alembic migrations in `common/persistence/migrations/`, starting from an empty baseline revision, applied with `make migrate` as the application role. (Plan: Phase 0 task 6; §6 layout.)

#### Scenario: Clean volume
- **WHEN** `make migrate` runs against a freshly created database volume
- **THEN** all revisions up to head are applied and head is recorded as current

#### Scenario: After restart
- **WHEN** the stack is restarted and `make migrate` runs again
- **THEN** it succeeds without changes and the current revision is unchanged

### Requirement: ParadeDB search extension available
The `pg_search` extension SHALL be installed in the application database by the database init (as the superuser), and a migration SHALL check that it is present, so later phases can add search indexes without changing the server. (Plan decision log 2026-11-11, ParadeDB; ADR-0002.)

#### Scenario: Extension present
- **WHEN** the baseline migrations have been applied
- **THEN** `pg_search` is listed among the application database's installed extensions

### Requirement: Phase 1 tables
Migration `0003` SHALL add the tables Phase 1 needs: `tasks`, `task_attempts`, `checkpoints`, `idempotency_keys`, `blob_objects`, `sample_orders`, and the `openai_agents` session-store tables. Session-store tables SHALL be created by the migration, never by an SDK at runtime. (Plan: Phase 1 task 2; §5 "checkpoint/attempt tables in Phase 1".)

#### Scenario: Migrate from the Phase 0 baseline
- **WHEN** `make migrate` runs on a database at revision `0002`
- **THEN** it applies `0003`, the tables exist, and a second run changes nothing

### Requirement: Retention class from the first write
Every row in a Phase 1 table and every stored blob SHALL carry a `retention_class` (`ephemeral`, `task` or `audit`) from its first write. Tables written by an SDK or the sample server SHALL default the column, so their inserts still record a class. Phase 1 SHALL NOT delete by retention. (Plan: Phase 1 task 3; §4.13 retention.)

#### Scenario: No record without a class
- **WHEN** the integration tests have run a task
- **THEN** every row in the Phase 1 tables and every `blob_objects` row has a non-null `retention_class`

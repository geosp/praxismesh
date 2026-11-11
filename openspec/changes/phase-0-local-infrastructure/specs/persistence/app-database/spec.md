# Spec Delta

## Purpose

The application database: separate from Temporal's own databases on the shared ParadeDB server, with versioned migrations that later phases extend (plan §4.16, §5, ADR-0002).

## ADDED Requirements

### Requirement: Separate application database
The application database SHALL be a separate database with its own role on the shared ParadeDB server. The application SHALL NOT read or write Temporal's databases. (Plan: Phase 0 task 1; §4.16; ADR-0002.)

#### Scenario: Role isolation
- **WHEN** the application role tries to connect to a Temporal database
- **THEN** the connection is refused

### Requirement: Migration baseline
The application database SHALL be managed by Alembic migrations, starting from an empty baseline revision, applied with `make migrate`. (Plan: Phase 0 task 6.)

#### Scenario: Clean volume
- **WHEN** `make migrate` runs against a freshly created database volume
- **THEN** the baseline revision is applied and recorded as current

#### Scenario: After restart
- **WHEN** the stack is restarted and `make migrate` runs again
- **THEN** it succeeds without changes and the current revision is unchanged

### Requirement: ParadeDB search extension available
The `pg_search` extension SHALL be available in the application database, created by a migration, so later phases can add search indexes without changing the server. (ADR-0002 confirmation.)

#### Scenario: Extension present
- **WHEN** the baseline migrations have been applied
- **THEN** `pg_search` is listed among the application database's installed extensions

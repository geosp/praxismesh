# Spec Delta

## Purpose

The application's own PostgreSQL database, separate from Temporal's private persistence, with an Alembic migration baseline (plan §4.13, §4.16, §5).

## ADDED Requirements

### Requirement: Phase 1 tables
Migration `0003` SHALL add the tables Phase 1 needs: `tasks`, `task_attempts`, `checkpoints`, `idempotency_keys`, `blob_objects`, and the session-store tables for both runners. Session-store tables SHALL be created by the migration, never by an SDK at runtime. (Plan: Phase 1 task 2; §5 "checkpoint/attempt tables in Phase 1".)

#### Scenario: Migrate from the Phase 0 baseline
- **WHEN** `make migrate` runs on a database at revision `0002`
- **THEN** it applies `0003`, the tables exist, and a second run changes nothing

### Requirement: Retention class from the first write
Every row in a Phase 1 table and every stored blob SHALL carry a `retention_class` (`ephemeral`, `task` or `audit`) from its first write. Phase 1 SHALL NOT delete by retention; it only records the class. (Plan: Phase 1 task 3; §4.13 retention.)

#### Scenario: No record without a class
- **WHEN** the integration tests have run a task
- **THEN** every row in the Phase 1 tables and every `blob_objects` row has a non-null `retention_class`

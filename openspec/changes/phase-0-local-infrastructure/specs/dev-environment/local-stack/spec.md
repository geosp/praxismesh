# Spec Delta

## Purpose

The local platform stack that every later phase runs on: one command starts Temporal, its UI, the database server and object storage, with health checks, persistent state and clear diagnostics (plan Phase 0).

## ADDED Requirements

### Requirement: One-command start and stop
The local stack SHALL start with `make up` and stop with `make down`, from a clean checkout plus a filled-in `.env`, with no other manual setup. It SHALL run Temporal Server (1.28 or later) with the Temporal UI, one ParadeDB PostgreSQL server (ADR-0002) and SeaweedFS with an S3-compatible endpoint. (Plan: Phase 0 tasks 1 and 3; §2 runtime.)

#### Scenario: Clean start
- **WHEN** a developer runs `make up` on a clean checkout with `.env` created from `.env.example`
- **THEN** every service reports healthy and the Temporal UI is reachable on its documented port

#### Scenario: Stop
- **WHEN** a developer runs `make down`
- **THEN** all stack containers stop and named volumes remain

### Requirement: Health checks
Every service in the stack SHALL define a health check, and `make up` SHALL wait until all services are healthy or exit non-zero naming the unhealthy service. (Plan: Phase 0 task 3.)

#### Scenario: Unhealthy service
- **WHEN** a service fails its health check within the start timeout
- **THEN** `make up` exits non-zero and names that service

### Requirement: Persistent state
Database contents, Temporal history and stored objects SHALL be kept in named volumes and survive `make down` followed by `make up`. (Plan: Phase 0 accept criteria.)

#### Scenario: Restart keeps state
- **WHEN** a Workflow has completed and an object has been stored, and the stack is restarted
- **THEN** the Workflow is still visible in Temporal and the object can still be read

### Requirement: Configuration without committed secrets
All endpoints, ports and credentials SHALL come from `.env`. The repository SHALL contain only `.env.example` with placeholder values. (Plan: Phase 0 task 3; §2 no committed secrets.)

#### Scenario: No secrets in Git
- **WHEN** the repository is scanned by CI's secret scan
- **THEN** no credential or real endpoint address is found, and `.env` is git-ignored

### Requirement: Clear diagnostics for missing dependencies
A missing prerequisite (Docker not running, `.env` missing, a required variable unset, the model endpoint unreachable) SHALL produce a clear message naming the problem, never a silent success. (Plan: Phase 0 demo checklist, failure item.)

#### Scenario: Missing environment file
- **WHEN** `make up` runs without `.env`
- **THEN** it exits non-zero with a message telling the developer to copy `.env.example`

### Requirement: Temporal smoke test
A hello-world Workflow and Activity SHALL run against the local Temporal and complete, and the run SHALL appear in the Temporal UI. (Plan: Phase 0 task 4 and accept criteria.)

#### Scenario: Hello Workflow
- **WHEN** the smoke test starts the hello-world Workflow
- **THEN** the Workflow completes with the expected result and is listed by the Temporal visibility API

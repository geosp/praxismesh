# Spec Delta

## Purpose

Default object storage for large artifacts (sessions, checkpoints, transcripts, tool output): SeaweedFS through its S3-compatible API, with GCS and Ceph documented as optional alternatives (plan §1, §5 BlobStore).

## ADDED Requirements

### Requirement: S3 round trip on the default store
The default object store SHALL be SeaweedFS through its S3-compatible endpoint, configured from `infra/.env`, and SHALL support put, get and delete of an object. (Plan: Phase 0 task 5; §1 deployment principles.)

#### Scenario: Round trip
- **WHEN** the smoke test puts an object, reads it back and deletes it
- **THEN** the bytes read equal the bytes written and the object no longer exists after deletion

### Requirement: Optional backends documented, not required
GCS and Ceph RGW settings SHALL be documented, and the default stack SHALL NOT require either service or any external credential. (Plan: Phase 0 task 5; §1 GCS is opt-in.)

#### Scenario: Default stack is local
- **WHEN** the stack runs with `infra/.env` created from `infra/.env.example`
- **THEN** no GCS or Ceph endpoint or credential is needed

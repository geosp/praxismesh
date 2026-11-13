# storage/blob-store Specification

## Purpose
Default object storage for large artifacts (sessions, checkpoints, transcripts, tool output): SeaweedFS through its S3-compatible API, with GCS and Ceph documented as optional alternatives (plan §1, §5 BlobStore).

## Requirements

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

### Requirement: BlobStore contract
Code SHALL store blobs only through the async `BlobStore` interface: `put`, `get`, `stream`, `stat` and `delete`. `put` SHALL return a `BlobRef` with a content-addressed key, a sha256 checksum, the content type, the byte count, the retention class and the creation time, and never any credential. Putting content that already exists SHALL return the same `BlobRef`. (Plan: Phase 1 task 2; §5 `BlobRef`, `BlobStore` contract; §4.13 immutable content keys and checksums.)

#### Scenario: Idempotent put
- **WHEN** the same bytes are put twice
- **THEN** both calls return a `BlobRef` with the same key and checksum, and one object is stored

### Requirement: Typed storage errors
Every adapter SHALL map its failures to `BlobNotFound`, `BlobCorrupt` (checksum mismatch on read), `BlobUnauthorized` or `BlobUnavailable` (retryable). (Plan: Phase 1 task 2; §4.13 distinguish missing, unauthorized and corrupt blobs.)

#### Scenario: Missing and corrupt blobs
- **WHEN** a caller reads a key that does not exist, or reads an object whose bytes no longer match its checksum
- **THEN** it gets `BlobNotFound` or `BlobCorrupt`, never a generic error or wrong bytes

### Requirement: One contract suite for every adapter
A shared contract test suite SHALL run against every adapter: the in-memory fake in the unit run and the S3 adapter against SeaweedFS in the `stack` job. (Plan: Phase 1 task 2; §8 BlobStore contract tests.)

#### Scenario: S3 adapter passes the contract
- **WHEN** the contract suite runs against SeaweedFS
- **THEN** every case passes, including idempotent put, stream, stat and the typed errors

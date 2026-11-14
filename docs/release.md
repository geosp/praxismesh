# Releases, versioning and compatibility

This document defines how PraxisMesh is versioned and released, and the compatibility rules every change must follow (plan §0.1). Nothing has been released yet. The first tagged release happens when Phase 5 closes (the MVP; `docs/roadmap/phases/phase-5.md`).

## Versioning

- PraxisMesh follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
- Before 1.0, breaking changes may appear in a minor release, but they are **always listed** in the changelog under a "Breaking" heading, with migration steps.
- From 1.0, breaking changes require a major release.
- Tags are `vMAJOR.MINOR.PATCH` on `main`, created from a commit whose required checks passed.

## Changelog

- `CHANGELOG.md` starts with the first release and follows [Keep a Changelog](https://keepachangelog.com/): Added, Changed, Deprecated, Removed, Fixed, Security, plus Breaking.
- The license check lists third-party services the default deployment runs. ParadeDB (the PostgreSQL server, ADR-0002) is AGPL-3.0: it runs unmodified as a separate service, and a modified ParadeDB would carry AGPL obligations.
- Each release entry links the phase evidence it closes (`docs/demos/phase-N.md`, `docs/reviews/phase-N/`) and records the dependency license-check result for anything distributed (phase-5.md).

## Release procedure (from the first release)

1. The phase gate has passed: reviews, verification, demo evidence, and the coordinator approval gate in `docs/reviews/README.md`.
2. Update `CHANGELOG.md` in a pull request.
3. Tag the merged commit and create the GitHub release with the changelog entry.
4. From the first tag onward, every later phase demo includes an upgrade from the previous tag (plan, Phase 5 onward).
5. Distributed artifacts follow the harness licensing constraint in plan §2: Dockerfiles are published, not prebuilt images containing third-party harnesses, until the licensing question is resolved.

## Compatibility rules

### Application database migrations

- Migrations are forward-only and versioned with the code that needs them. A release contains every migration since the previous release.
- Each migration applies from a clean volume and from the previous release's schema. Both paths are tested before release.
- Destructive changes (dropping or renaming columns or tables) take two releases: first stop using the old structure, then remove it.

### CRDs and schema versions

- Kubernetes CRDs and versioned configuration schemas use explicit API versions. A new version ships alongside the old one with a conversion path before the old one is removed.
- Removal of a schema or CRD version is a breaking change and is listed in the changelog.

### Gateway API

- The gateway's OpenAI-compatible surface follows the compatibility matrix in `docs/api/compatibility.md` (published with the Phase 4 RFC): every parameter is honored, ignored (documented) or rejected.
- Changing a parameter's classification, removing an endpoint or changing a response shape is a breaking change.

### Temporal Workflow code

- Any change that would alter the command sequence of in-flight Workflow histories (adding, removing or reordering Activities, timers, child Workflows, Signals or Updates) must use Temporal versioning or patching, or a new Workflow type.
- Workflow changes ship with replay tests against recorded histories from the previous release.
- Long-running entity Workflows follow the Worker Versioning strategy decided in Phase 7.

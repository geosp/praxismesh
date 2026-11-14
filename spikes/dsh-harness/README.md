# DSH primary-harness compatibility spike

Isolated experiment for [issue #62](https://github.com/geosp/praxismesh/issues/62)
and the [approved contract](../../docs/plans/2026-11-14-dsh-harness-evaluation/plan.md).
Production dependencies, templates and dispatch remain unchanged.

## Candidate selection

The inspected research snapshot is 39163dd30f703a79079e2d2446545cff3c453738.
The published matching Python SDK/runtime pair selected for Phase 01 is
0.2.2rc2, associated with the official dsh-v0.2.2-rc.2 source tag at
ddac96760b6edf8fa0fe17cbdcf0b512f4c12b2c. This is a separately identified
release candidate, not a claim that the published wheels were built from the
research snapshot. Source evidence is refreshed against the release before use.
Artifact identities and digests are recorded in artifacts.json and uv.lock.

Upstream code runs only in the disposable Docker environment. The isolated uv
project stages dependencies; it does not activate a user DSH installation. No
upstream binary or populated home is committed. Generated run state is ignored.

## Status

Phase 01 implementation in progress. No local-model or authority probe is yet
claimed as passing. Runtime startup and subsequent entry points will be recorded
with their observed outcomes before completion.

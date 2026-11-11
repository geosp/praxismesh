# Architecture decision records

One record per consequential architecture decision, written when the decision is made or superseded (plan §4.17). Trivial implementation details do not get ADRs.

- **Name:** `NNNN-<decision>.md`, numbered in order (`0001-...`).
- **Template:** [adr.md](../templates/adr.md) (MADR minimal plus Confirmation and Links).
- **Status:** `proposed`, `accepted` or `superseded`. A superseded ADR changes only its front matter (`status`, `superseded_by`); its body is never rewritten.
- **How:** the `docs-design` skill drafts ADRs on a draft pull request.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-keep-default-openspec-schema.md) | Keep OpenSpec's default `spec-driven` schema; review gates live in the review skills and CI | proposed |

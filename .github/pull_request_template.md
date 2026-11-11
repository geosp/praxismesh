## Summary

> [!TIP]
> 2-5 sentences: what changed and why. Write for a reviewer who has not seen the work.

## Issue

> [!TIP]
> `Closes #N` only if this PR fully resolves the issue; otherwise `Part of #N`. Never use closing keywords (closes/fixes/resolves) for any other issue.

Closes #

## Plan and spec trace

- **Phase:** <!-- e.g. Phase 1, 3A; or "bootstrap", "n/a" -->
- **Plan sections:** <!-- e.g. §4.3, §5 -->
- **OpenSpec change:** <!-- openspec/changes/<id>, or n/a -->
- **RFC / ADR:** <!-- docs/rfcs/..., docs/adr/..., or n/a -->

## Changes

-

## Testing

> [!TIP]
> List the suites actually run and their result. Do not list tests that were not run. Workflow code changes need replay tests (plan §8).

| Suite | Command | Result |
|---|---|---|
| Unit | | |

## Demo evidence

> [!TIP]
> Required when this PR completes a phase task: link `docs/demos/phase-N.md` and the run. Delete this section otherwise.

## Notes for reviewers

> [!TIP]
> Migrations, new dependencies, schema/API/CRD compatibility, security-relevant changes, known limitations. Delete if none.

## Checklist

- [ ] No secrets, credentials or session transcripts committed
- [ ] Decision log updated if constraints, APIs, architecture or acceptance criteria changed
- [ ] Plan task boxes checked only for work verified by tests, acceptance criteria and demo
- [ ] Generated agent files in sync (`uv run .agents/sync_agents.py --check`)

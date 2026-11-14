# Rename inventory and verification

## D1 · Directory roles

At base `baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda`, `docs/plan/` contains
19 tracked files: six topic files and thirteen phase files. PROJECT_PLAN.md is
the core roadmap and document map. The shared impl-plan skill discovers
`docs/plans/*/plan.md`; the roadmap files do not use that implementation-contract
format. Renaming their directory must not change that discovery root.

Reference inventory must include Markdown destinations, plain path strings,
frontmatter, local skills, CI configuration and scripts. Root AGENTS.md and
CLAUDE.md are the only repository instruction files found in the inventory.
Existing reviewer reports and ADRs cite the old directory, so a universal text
replacement would rewrite historical input manifests and evidence.

## D2 · Secret-scan compatibility

The existing Gitleaks configuration scopes one reviewed prose false positive by
rule, exact file path and exact line phrase, combined with AND. CI runs a canary
and scans history. Historical commits still contain docs/plan/schemas.md after
the rename. Removing its existing exception would change historical scanning.

Implementation must retain the old exact-path/phrase allowance for history and
cover the same prose at the new exact path. It must not suppress other paths,
other rules or unrelated lines. Update the canary to exercise both approved paths
and an ordinary file; also demonstrate that unallowlisted content in the renamed
schema file is still detected. Use generated dummy values and redacted reports;
never save credentials or raw scan material in repository evidence.

## Verification outline

- Compare old and moved file inventories through Git rename detection.
- Audit each moved-file diff: path maintenance only, preserving roadmap scope,
  phase order, acceptance criteria and task completion states.
- Check relative links from the new location, including links between topic and
  phase files, and anchors in externally referenced headings.
- Search for old-path references and classify every remaining match as a
  historical citation or explicit scan-history compatibility.
- Run the public plan validator, shared helper and generated-agent consistency
  check; the roadmap must not become a discovered implementation plan.
- Run offline link and workflow checks, the bounded Gitleaks canaries, and the
  repository's required checks before PR delivery.
- Demonstrate navigation from PROJECT_PLAN.md through the roadmap phase index,
  and from docs/README.md to both the roadmap and implementation plans.
- Save immutable design/implementation-review inputs and actual verification
  results without claiming runtime phase completion.

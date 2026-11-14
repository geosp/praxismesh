# Rename inventory and verification

## D1 · Directory roles

At the preservation baseline designated below, `docs/plan/` contains
19 tracked files: six topic files and thirteen phase files. PROJECT_PLAN.md is
the core roadmap and document map. The shared impl-plan skill discovers
`docs/plans/*/plan.md`; the roadmap files do not use that implementation-contract
format. Renaming their directory must not change that discovery root.

Reference inventory must include Markdown destinations, plain path strings,
frontmatter, local skills, CI configuration and scripts. Root AGENTS.md and
CLAUDE.md are the only repository instruction files found in the inventory.
Existing reviewer reports and ADRs cite the old directory, so a universal text
replacement would rewrite historical input manifests and evidence.

## Preservation baseline

The immutable preservation-comparison baseline is
`baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda`, the owner-merged Skill Central cutover
before this rename. This SHA governs comparisons of historical records and moved
roadmap text throughout R4/R5 verification. It is not the design-review SHA
(`c76f77e11dc2ab309a38ef63836e8003f18c82cc` for round 1), the later implementation
review SHA, or the final PR head. Record those separately in their reports.

Reproduce the 19-file roadmap inventory from the repository root:

```bash
git ls-tree -r --name-only baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda docs/plan
```

Expected: six topic files (bootstrap, decision-log, design-decisions, references,
revision-history, schemas) and thirteen phase files. Each relative suffix must
exist under docs/roadmap after the move, and docs/plan must be absent.

Historical-record comparison procedure:

1. Inventory baseline files under docs/adr, docs/reviews, docs/demos, docs/rfcs and
   openspec using `git ls-tree -r --name-only` at the baseline above. Include
   unchanged baseline files in the preservation comparison; new review evidence
   for this rename is recorded separately.
2. Save the changed-record inventory under a new `Historical navigation maintenance`
   section in these notes: one entry per file, its baseline blob hash, and each
   old/new Markdown destination. Preserve link labels and plain recorded paths.
3. For each changed record, load its baseline bytes with `git show <baseline>:<path>`.
   Identify the original byte ranges for the inventoried Markdown destinations;
   verify each range is a navigation target, not quoted code or a recorded input.
   Reconstruct expected bytes by replacing only those ranges, in reverse offset
   order, with the recorded new destinations. Compare expected and actual bytes
   exactly. Any other byte difference fails R4. Compare unchanged records exactly
   against their baseline bytes as well.
4. Record compared-file counts, the changed-record inventory, byte-comparison
   result and reviewed implementation SHA in the verification evidence. A manual
   diff alone does not substitute for the byte comparison. An implementation-time
   one-off checker may perform these operations without adding a runtime dependency.
5. For moved roadmap files, compare each baseline docs/plan suffix with its new
   docs/roadmap counterpart. Permit only path maintenance and the named entry in
   docs/roadmap/decision-log.md. Audit phase order, task states and acceptance text.

## Scanner contract

The scanner contract is the existing allowlist in the
[frozen configuration](https://github.com/geosp/praxismesh/blob/baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda/.gitleaks.toml#L10).
Read its exact expression without copying the known false-positive prose into
another scanned file:

```bash
git show baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda:.gitleaks.toml
```

Required invariants:

| Field | Preserved contract |
| --- | --- |
| Default rules | `extend.useDefault = true` |
| Target rule | `generic-api-key` only |
| Combination | `condition = "AND"` |
| Match source | `regexTarget = "line"` |
| Line expression | The exact `allowlists[0].regexes` value in the frozen TOML above; byte-for-byte unchanged |
| Historical path | Exactly `docs/plan/schemas.md` |
| New path | Exactly `docs/roadmap/schemas.md` |
| Other paths/rules/lines | No new exceptions |

CI scans history, so the historical path remains necessary. Only the path list
may gain the exact renamed path; descriptions and canary comments may explain
that maintenance. No directory-wide or rule-wide suppression is allowed.

Canary procedure: run the existing `secrets` job's canary from
.github/workflows/ci.yml with its pinned scanner version and checksum. Extend
its temporary fixture to cover this matrix:

| Fixture | Expected |
| --- | --- |
| Reviewed line expression at the historical schema path | Suppressed by that exact exception |
| Same reviewed expression at the new schema path | Suppressed by that exact exception |
| Same generated dummy-key line in an ordinary file | Detected |
| Unallowlisted dummy-key line at the historical schema path | Detected |
| Unallowlisted dummy-key line at the new schema path | Detected |

Extract the allowed expression from TOML, as the existing canary does. Generate
fresh dummy values, use redacted JSON reports, and assert the exact finding-file
set for each case. Verify the target rule for positive findings. Never save raw
values in evidence. The canary must fail if either expected finding disappears
or an approved fixture becomes a finding. Run the full history scan for the candidate's reachable lineage:

```bash
gitleaks git --config .gitleaks.toml --redact --log-opts=HEAD .
```

Expected: exit zero for the candidate lineage, including historical schema paths.
For baseline comparison, substitute its immutable SHA for HEAD. The default
command without --log-opts also visits other local refs: here it reports the
pre-existing local-only finding documented below with either configuration.
Record that separate outcome; do not claim the all-local-refs scan passed or
suppress unrelated history. The CI history-selection logic remains unchanged.

A pathless stdin diff scan cannot apply file-path exceptions; its warnings must
be checked against a file-aware scan rather than treated as a blanket PASS.
The committed HEAD-lineage scan includes the actual candidate changes.

## Verification procedure

Run commands from the repository root after implementation. Use installed tool
versions pinned in .github/workflows/ci.yml; do not introduce a private CI dependency.
The external helper location below is the existing owner's installation; another
contributor may use their approved Skill Central checkout.

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run .agents/sync_agents.py --check
uv run .github/scripts/check_plans.py
uv run /home/geo/.agents/skills/impl-plan/plan-tool.py check docs/plans/2026-11-14-roadmap-directory
uv run /home/geo/.agents/skills/impl-plan/plan-tool.py list docs/plans --all
git diff --check
actionlint
lychee --offline --no-progress --include-fragments --hidden --exclude-path '\.claude/skills' --exclude-path '\.git/' --exclude-path '\.venv' './**/*.md'
```

Expected: all commands exit zero; the helper has zero errors/warnings, discovery
contains implementation contracts but no roadmap file, generated agents are
current, and links/anchors resolve. The full test suite uses its normal integration
selection; report actual counts and skips rather than asserting integration ran.
Run the canary matrix and normal history scan described above as additional checks.

Review inventory and preservation with:

```bash
git diff --name-status --find-renames baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda
git diff --no-ext-diff baf8f32abe9c95fe8d0c0609f6997cdfb58e3fda -- docs/adr docs/reviews docs/demos docs/rfcs openspec
rg -n --hidden 'docs/plan(/|\b)|\.\./plan/' AGENTS.md PROJECT_PLAN.md README.md docs .agents .github .gitleaks.toml spikes openspec
```

Expected: all 19 roadmap files map to new paths; baseline historical changes are
only inventoried navigation destinations. Classify every residual old-path match
as preserved historical text, rename evidence, or the exact scan-history exception.
This textual audit supplements the required byte comparisons above.

Navigation walkthrough: start at PROJECT_PLAN.md, open the roadmap phase index,
follow a phase's Read first links and a schema anchor; then open docs/README.md
and follow its roadmap and implementation-plan entries. Expected: distinct roles,
valid destinations and no lost anchors. Save the observed outcomes and immutable
implementation SHA with the review/verification evidence. No runtime phase closure
is implied. Required CI must pass on the final PR head before owner merge.


## Historical navigation maintenance

Authorized 2026-11-14: update navigation destinations only. The
[byte-offset manifest](historical-navigation.json) records the exact baseline blob,
original ranges and old/new destinations. All other baseline historical records
remain byte-identical. Historical labels and recorded inputs retain their original
paths; current navigation follows the roadmap directory.

| Record | Baseline blob | Destination edits |
| --- | --- | --- |
| `docs/adr/0003-early-compose-task-ui.md` | `92315a26de091394bd5fcbfb781277a400513cff` | 8 |
| `docs/demos/bootstrap.md` | `43337636cd73c30ca8466911a5afc4a4279d1d6b` | 1 |
| `docs/demos/phase-0.md` | `a82d4cfd4faf4604e1d4d5998af96b6156d07013` | 1 |
| `docs/demos/phase-1.md` | `53a95a486b89a3a2113d858750d3b9e372f68e83` | 1 |
| `docs/reviews/phase-1/gate-followup.md` | `3a7a5a9504cde3bfd66b12384aa997929e2aa697` | 1 |
| `docs/rfcs/phase-1-single-agent.md` | `3b35cc8f58c9617a8e2dbb900f8df1695f77bbcd` | 3 |

Compared inventory: 147 baseline historical files; 6 changed records; 15 destination edits.


## Implementation check observations

The workflow canary matches the unique file/line/rule locations. The ordinary
fixture can produce two generic-api-key matches at the same location (the known
prose false positive and the generated dummy key); counting raw matches would
incorrectly fail the intended canary. Distinct expected locations remain exact.
The current contract passed; removing the new path or changing AND to OR was
correctly rejected by the same canary.

The local default all-refs history scan reported one pre-existing finding in an
unmerged commit, bc7fe4889d85cf3059f2a5a9676fb1ccb5738c3c, outside the preservation
baseline's ancestry. The unchanged baseline configuration reports the identical
finding. A full reachable-baseline scan passed, and the current HEAD lineage scan
passed with the new configuration. No suppression or CI history-selection change
was added for that local-only history. Report this distinction rather than
claiming the default all-local-refs scan passed.

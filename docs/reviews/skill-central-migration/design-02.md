---
review: design
phase: general-skill-central-migration
change: docs/plans/2026-11-13-skill-central-migration
rfc: n/a
adrs: [ADR-0003, ADR-0004]
commit_sha: 96aa6670531251509bb53a70c229c57e0eb922c8
docs_sha: n/a
diff_base: n/a
session: fresh
date: 2026-11-14
verdict: PASS
reviewers:
  - {lens: fresh-reader, status: completed}
  - {lens: codebase-fit, status: completed}
  - {lens: zoom-out, status: completed}
---

# Independent cutover design review, round 2

Frozen report below. Subsequent readability fixes are recorded in the plan review
log; no third design-review round or runtime phase closure is claimed.

**PASS — phase 03, second and final design-review round.** All three native reviewers completed. No Blocker or Major remains open after evidence-backed reconciliation. Six readability Nits remain open; none is waived.

**Revision and independence**

- Date: 2026-11-14.
- Session: fresh; no author or implementation transcript.
- Frozen repository: `/tmp/praxismesh-cutover-independent-review`.
- Full SHA: `96aa6670531251509bb53a70c229c57e0eb922c8`.
- Working tree: clean before and after review.
- Skill: `/home/geo/.agents/skills/design-review/SKILL.md`, with its sibling `impl-plan/SKILL.md` and `writing.md`.
- Three fresh native roles, started independently with `fork_turns: none`: one `design-reader`, two `design-reviewer` instances.
- Only the coordinator read the migration’s `reviews.md`. Reviewers confirmed they did not read prior review reports, author transcripts, or another reviewer’s output.

**Instruction-loading limitation:** despite the native reader role’s intended isolation, the harness supplied the user-provided AGENTS.md instructions, environment context and skill catalog. The reader confirmed it opened only `plan.md`. Both other reviewers also received automatic project instructions; therefore zoom-out was not completely free of project guidance. No author reasoning or prior findings were supplied to any reviewer.

**Exact assigned inputs**

Paths below are relative to the frozen repository root.

| Input | Fresh reader | Codebase-fit | Zoom-out |
|---|---|---|---|
| `docs/plans/2026-11-13-skill-central-migration/plan.md` | Yes, Summary first, then whole file | Yes | Yes |
| `docs/plans/2026-11-13-skill-central-migration/phases/03-cutover.md` | — | Yes | Yes |
| `docs/plans/2026-11-13-skill-central-migration/notes.md` | — | Yes | Yes |
| Every ADR-directory file listed below | — | Yes | Yes |
| `AGENTS.md`, `CLAUDE.md` | No file access | Yes | Not assigned |
| Repository code needed for the review | — | Permitted | Permitted |

The complete ADR list was:

```text
docs/adr/0001-keep-default-openspec-schema.md
docs/adr/0002-paradedb-as-postgresql-server.md
docs/adr/0003-early-compose-task-ui.md
docs/adr/0004-use-implementation-plans-for-development.md
docs/adr/README.md
```

No nested AGENTS.md or CLAUDE.md files were found in the Impact directories.

Beyond their assigned files, **both code reviewers individually inspected**:

```text
PROJECT_PLAN.md
docs/plans/2026-11-13-skill-central-migration/phases/01-prerequisites.md
docs/plans/2026-11-13-skill-central-migration/phases/02-suite.md
docs/development/planning.md
docs/development/skill-central-migration-checks.md
docs/requirements/baseline.md
docs/reviews/README.md
.agents/README.md
.agents/sync_agents.py
.github/scripts/check_plans.py
.github/workflows/ci.yml
```

Zoom-out inspected only the first 220 lines of `PROJECT_PLAN.md`, first 210 lines of CI, and first 200 lines of the agent generator. Its metadata commands were `git status --short` and `git diff --stat`.

**Codebase-fit additionally opened**:

```text
.github/scripts/ci_gate.py
tests/test_plans.py
.agents/skills/docs-design/SKILL.md
docs/plan/phases/phase-4a.md
```

Its content searches covered:

```text
.agents/skills/
docs/development/
.github/scripts/
tests/test_plans.py
tests/test_tool_pins.py
Makefile
pyproject.toml
.agents/agents/verifier.md
docs/templates/
.github/pull_request_template.md
docs/plan/design-decisions.md
docs/plan/decision-log.md
```

Its filename scans covered `.agents`, `.codex`, `.claude`, `.github`, the migration plan directory, `docs/requirements` and `openspec`. Git inspection covered status, four recent commit summaries, changed filenames, and preservation comparisons against `bfa79d1270ebba0f83fe3cf29d2abb7d448d37dd`. Filename enumeration exposed review-report paths; their contents were not opened.

Coordinator-only inputs additionally included `reviews.md`, the installed native role configurations, the installed skill instructions, and the documents cited in the reconciliation below.

**Fresh reader paraphrases — verbatim**

**From the Summary**

> The change moves implementation planning and independent reviews to the owner’s centrally managed skills and replaces OpenSpec CI with local contract checks. It retires active OpenSpec tooling while preserving completed phase records and guarantees. The main risk is losing skill discovery or weakening phase gates, so the replacement suite must be merged, installed and verified before cutover.

**From the whole plan**

> The migration first adds Codex and bundled-export support to Skill Central, then imports the planning and review suite, and finally switches PraxisMesh to that merged, verified installation. Future detailed requirements and designs live in implementation plans, while durable decisions live in ADRs and the master plan retains scope and gate authority. PraxisMesh removes superseded tooling and uses a public validator that requires no private credentials. The change also requires owner acceptance of an ADR reconciliation concerning Phase 4A’s required artifacts.

The reader reported no section it could not paraphrase and no direct contradiction between Summary and plan.

**Reviewer statuses**

| Reviewer | Native role | Status | Result |
|---|---|---|---|
| Fresh reader | `design-reader` | Completed | Clarity concerns, reconciled below |
| Codebase-fit | `design-reviewer` | Completed | No findings |
| Zoom-out | `design-reviewer` | Completed | No findings |
| Structure | Installed helper | Completed | Zero errors, zero warnings |

Codebase-fit confirmed that the CI replacement exists and participates in `ci-ok`, all eleven incorporated baseline specification paths exist, and historical specifications, archives, Phase 0/1 evidence and phase RFC contents remain unchanged. Task 3.1 covers D1–D3 and R1–R5.

Zoom-out found the cutover sequence, preservation strategy and ownership-aware rollback coherent. Both reviewers explicitly treated ADR-0004 as **proposed**, conditional on owner acceptance and merge.

Private Skill Central installer behavior and cross-platform execution were not independently reproduced. The repository records those as prerequisite evidence; this report makes no new execution claim.

**Consolidated findings and dispositions**

All findings originated with the fresh reader. “Contest” below is an evidence-backed disposition, not a waiver. Where a Major classification is contested but a useful clarity concern remains, that concern stays open as a Nit.

| ID | Severity and status | Place | Finding and proposed action or contest |
|---|---|---|---|
| N1 | **Nit — open**; original Major classification contested | Summary; D1–D2 | The Summary could explicitly name `docs/plans`, user-wide installation and conditional ADR acceptance. **Fix:** add a compact clarification. **Contest Major:** lines 15–21 already describe implementation planning, replacement validation, retained guarantees and gated cutover; the reader’s own paraphrases correctly describe the change. D2 lines 98–105 explicitly states the authority and acceptance boundary. No misleading interpretation was demonstrated. |
| N2 | **Nit — open**; original prerequisite Major classification contested | Terms; Summary; What changes | “Bundled-export prerequisites” and OpenSpec’s former role could be defined more directly. **Fix:** add short definitions. **Contest Major:** What changes line 31 identifies Codex and bundled-export intake; D1 explains Codex delivery, and the linked installation document provides operations. More detailed prerequisite implementation belongs outside the short overview. |
| N3 | **Nit — open** | D2 | Phase 4A’s purpose is not explained locally. **Fix:** identify it as the Compose task-interaction UI when first mentioning it. Its artifact reconciliation is understandable without this addition. |
| N4 | **Nit — open** | D1 | The Codex configuration sentence combines ownership, indirection, regular TOML files and the symlink restriction. **Fix:** separate the delivery mechanism from its reason. |
| N5 | **Nit — open; reopened from round-1 F6** | R4 | R4 still groups several independently checkable gates. Separate scenarios improved it, but the reader repeated the bundling concern. **Fix:** separate the policy into individually traceable requirements or labelled subrules. This does not block: the mandatory gates and refusal scenarios are explicit. |
| N6 | **Nit — open** | R2; Risks; Rollout & rollback | Discovery-before-merge is repeated in several places. **Fix:** retain one authoritative definition and use references elsewhere where that improves readability. |
| C1 | **Major — contested, closed** | D1; Rollout & rollback | Reader requested Skill Central’s location and manager interface inside `plan.md`. Installation commands and ownership rules are explicitly linked: `docs/development/planning.md:16–31` supplies preview, install and doctor commands. A private checkout’s machine-specific location is not needed to understand the design. |
| C2 | **Major — contested, closed** | Phases 01–03 | Reader reported missing task definitions and Verify steps in `plan.md`. The prescribed skill format deliberately places these in phase files. All three files exist; target task 3.1 and its Verify clause are at `phases/03-cutover.md:21`. Mechanical validation passes. |
| C3 | **Major — contested, closed** | D3; R5 | Reader requested validator format, commands and failure mechanics inside `plan.md`. D3 lines 109–113 states its scope, links its commands and boundary, and disclaims execution proof. Detailed mechanics belong in supporting documentation/code under the skill’s two-layer format. Codebase-fit confirmed the local implementation and CI wiring. |
| C4 | **Major — contested, closed** | R2; Rollout & rollback | Reader requested the full discovery matrix and evidence procedure locally. Rollout lines 128–130 states merge ordering, Linux/macOS checks and protected-SHA recording. The linked installation guide names the procedure; migration checks distinguish observed failures, later activation and owner confirmation. The gate is assessable across its documented inputs. |
| C5 | **Major — contested, closed** | R3; Links | Reader requested the historical inventory inside `plan.md`. R3 and the explicit baseline link intentionally incorporate it by reference. `docs/requirements/baseline.md` inventories eleven retained specification paths. Codebase-fit confirmed their existence and historical preservation. Duplicating the inventory is unnecessary. |
| C6 | **Major — contested, closed** | R4; Coordinator; Latest-head approval | Reader requested the complete evidence-inspection procedure locally. Terms lines 51–55 identifies the coordinator and links the operational authority. `docs/reviews/README.md` specifies matching evidence SHAs, latest-head checks, source comparison and refusal rules. The design states the policy and provides its mechanism. |
| C7 | **Nit — contested, closed** | D1 | Reader objected to the plain `notes.md#d1` reference. The installed `writing.md` itself uses `Details: notes.md#d1` as its example format. The file and D1 section exist; this is compliant navigation, not a missing dependency. |

**Closed-finding reconciliation**

The coordinator reconciled the prior log without exposing it to reviewers:

| Earlier finding | Final-round result |
|---|---|
| Design F1: ADR-0003 conflict | Fixed. Proposed ADR-0004 changes the artifact requirement and carries every other ADR-0003 decision and acceptance/demo obligation forward by reference. D2 and task 3.1 require that reconciliation. |
| Design F2: Summary omitted prerequisites/public validator | Fixed; both now appear. N1–N2 retain narrower clarity suggestions. |
| Design F3: Undefined operational terms | Fixed by Terms and authority links. Requests to duplicate full procedures are contested above. |
| Design F4: Ownership/harness variants unclear | Fixed by Terms and D1’s Codex exception. Summary-level clarity remains under N1. |
| Design F5: Validator scope broad | Fixed by D3’s explicit scope and boundary. Additional implementation-detail demands are contested under C3. |
| Design F6: Combined rules | **Reopened as N5** because the R4 bundling concern recurred. |
| Design F7: Revert’s installation consequences implicit | Fixed. Rollback explicitly retains shared installation state and requires a separate owner decision for user-wide recovery. |
| Implementation F1: Structural validation cannot prove human enforcement | Previously accepted; remains closed. This review claims no such proof. |
| Implementation F2: Completed parent with unfinished phases | No recurrence reported by codebase-fit. |

ADR-0004 is **not accepted by this review**. ADR-0003 remains the current accepted contract pending owner acceptance of the proposed reconciliation. When accepted, ADR-0004 correctly replaces the mandatory RFC/OpenSpec artifact follow-up while retaining the Compose UI scope, sequencing, full tier, security boundaries, Phase 8 split and acceptance/demo obligations.

**Mechanical checks and remaining work**

Executed read-only:

```text
python -B /home/geo/.agents/skills/impl-plan/plan-tool.py check docs/plans/2026-11-13-skill-central-migration
Result: 0 error(s), 0 warning(s)
```

No tests, edits, configuration changes or GitHub writes occurred. The report and round metadata were not persisted because this round was explicitly read-only.

Still open:

- Six Nits: N1–N6.
- Owner acceptance of proposed ADR-0004 with the cutover.
- Recording this report and updating review metadata in an authorized writing session.
- Latest-head checks, final evidence linkage and owner merge approval.

Unticked migration tasks and absence of an earlier design PASS were not treated as defects. This PASS covers the tooling cutover design; it does not close a runtime phase or authorize merge. The second and final round ends here.

The helper’s unchanged persisted state reports:

Next: /design-review docs/plans/2026-11-13-skill-central-migration

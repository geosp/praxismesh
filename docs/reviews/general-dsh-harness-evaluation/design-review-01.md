---
review: design
phase: general-dsh-harness-evaluation
change: docs/plans/2026-11-14-dsh-harness-evaluation
rfc: n/a
adrs: []
commit_sha: 3c994002986f9e2eb4df99d0161dbf2ec5327896
docs_sha: n/a
diff_base: n/a
session: fresh
date: 2026-11-14
verdict: FAIL
reviewers:
  - {lens: fresh-reader, status: completed}
  - {lens: codebase-fit, status: completed}
  - {lens: zoom-out, status: completed}
---

# Independent DSH spike design review, round 1

The fresh session report follows unchanged. This is review of the proposed
experiment; no runtime compatibility, adoption or phase closure is claimed.

**FAIL — changes requested.** All three reviewers completed. Mechanical checks passed. Two acceptance-definition gaps remain open; no DSH runtime behavior was tested.

Reviewed commit: `3c994002986f9e2eb4df99d0161dbf2ec5327896`  
Date: `2026-11-14`  
Scope: whole-plan, independent pre-implementation review of the isolated compatibility spike. This verdict concerns the evaluation contract, not adoption approval or runtime phase closure.

### Independence and reviewer status

All reviewers used fresh native roles with `fork_turns: none`. They received no author transcript, suspected findings, earlier verdicts or other reviewer output. Only the coordinator read `reviews.md`; it contains no earlier findings.

| Lens | Native role | Status | Result |
|---|---|---|---|
| Fresh reader | `design-reader` | Completed | Readability and acceptance-definition concerns |
| Codebase fit | `design-reviewer` | Completed | No findings |
| Zoom out | `design-reviewer` | Completed | No findings |

**Independence limitation:** all three reviewers report that PraxisMesh `AGENTS.md` was automatically supplied in their context. Consequently, the fresh reader did not achieve the skill’s intended “no project instructions” isolation. It opened only `plan.md`, reading the Summary first and then the whole file. The two design reviewers also read guidance on disk. This limitation is disclosed, not waived or represented as full isolation.

### Exact inputs

All repository paths below are relative to `/tmp/praxismesh-dsh-design-review` at the full commit above.

Fresh reader’s sole assigned and opened file:

```text
docs/plans/2026-11-14-dsh-harness-evaluation/plan.md
```

Both design reviewers received these explicit document inputs and permission to inspect relevant repository code:

```text
docs/plans/2026-11-14-dsh-harness-evaluation/plan.md
docs/plans/2026-11-14-dsh-harness-evaluation/phases/01-controlled-runtime.md
docs/plans/2026-11-14-dsh-harness-evaluation/phases/02-recovery-and-decision.md
docs/plans/2026-11-14-dsh-harness-evaluation/notes.md
docs/adr/0001-keep-default-openspec-schema.md
docs/adr/0002-paradedb-as-postgresql-server.md
docs/adr/0003-early-compose-task-ui.md
docs/adr/0004-use-implementation-plans-for-development.md
docs/adr/README.md
```

Codebase fit additionally received the prescribed guidance list:

```text
AGENTS.md
CLAUDE.md
```

Both design reviewers actually inspected these additional paths:

```text
AGENTS.md
PROJECT_PLAN.md
docs/roadmap/design-decisions.md
docs/benchmarks/2026-11-12-local-default.md
harness_activity/activity.py
harness_activity/runner.py
harness_activity/config.py
tests/benchmarks/run.py
tests/test_runner_conformance.py
```

Codebase fit additionally inspected:

```text
CLAUDE.md
docs/development/planning.md
docs/requirements/baseline.md
docs/roadmap/phases/phase-1.md
docs/benchmarks/baseline.json
harness_activity/tools.py
registry/loader.py
registry/templates/local-default.yaml
registry/mcp/sample-shop.yaml
common/schemas/task.py
common/schemas/capability.py
common/persistence/repositories.py
tests/benchmarks/agent_tasks/tasks.py
tests/integration/test_recovery.py
spikes/harness-vllm/pyproject.toml
```

Zoom out additionally inspected:

```text
docs/roadmap/phases/phase-2.md
harness_activity/workspace.py
```

The coordinator additionally read `reviews.md`, the installed design-review and impl-plan skills and writing rules, the repository review protocol/template, and the mechanical validator sources. No upstream reference was fetched. Upstream claims remain locally recorded source-inspection evidence, with runtime compatibility unverified.

### Fresh reader paraphrases — verbatim

**From the Summary**

> The change evaluates whether DeepSeek Harness can run PraxisMesh agents inside Temporal Activities using the existing local model and capabilities. It will produce experimental evidence and a go/no-go recommendation before any production replacement. The main risk is that an apparently functional runtime loses consistent recovery state or execution control after interruption.

**From the whole plan**

> The plan proposes an isolated DSH runtime and bridge, with pinned dependencies and explicitly granted capabilities. It tests local execution, authority enforcement, recovery, cancellation, accounting and structured completion, then compares results against an existing ten-task benchmark. Temporal retains durable orchestration, and production adoption requires a separate decision and migration plan.

The reader reported no Summary-versus-plan mismatch. Its existing-system paraphrase was:

> The existing Activity constructs OpenAI Agents SDK sessions directly, creating coupling between the runner and session/checkpoint handling. Temporal handles durable dispatch, retries and coordination; trusted templates select the local model and grant capabilities. The system already has checkpoint, attempt-ownership, side-effect and TaskResult contracts, although their details are largely outside this document. Its recorded benchmark baseline passes ten of ten tasks.

### Mechanical checks

| Check | Observed |
|---|---|
| `git rev-parse HEAD` | Exact requested full SHA |
| `git status --porcelain` | Empty before and after review |
| `python -B /home/geo/.agents/skills/impl-plan/plan-tool.py check docs/plans/2026-11-14-dsh-harness-evaluation` | 0 errors, 0 warnings |
| `python -B .github/scripts/check_plans.py` | 3 plans validated; 0 errors |
| Committed-input comparison | All five contract Markdown files tracked and byte-identical to HEAD |
| Local Markdown link targets | All targets checked in `plan.md` exist; anchor correctness was not separately checked |
| Nested guidance discovery | Only root `AGENTS.md` and `CLAUDE.md` found |
| Lifecycle helper `next` | Still requests design review because recorded status remains `none` |

These are structural checks, not tests or evidence that probes work. No dependencies were installed, upstream code executed/downloaded, models called, tests run, files/configuration edited, commits created or GitHub writes performed.

### Consolidated findings and dispositions

The table preserves every reader concern. Contested findings are explicitly closed with evidence; none is silently omitted. Detailed mechanics may remain in linked notes and phases.

Here, `plan`, `notes`, `P01` and `P02` mean the four files under the reviewed plan directory.

| ID | Severity | Source | Location and evidence | Proposed action / disposition |
|---|---|---|---|---|
| F1 | Blocker, contested | Reader | R7, `plan:99–103`: reader could not explain exact status/reference mapping. | **Contest:** exact mappings are implementation mechanics permitted outside the short plan. `harness_activity/runner.py:50–56`, `common/schemas/task.py:73–104`, `notes:71` and P02 task 2.2 identify the existing contract and required probe. The reader correctly paraphrased the requirement’s purpose. Closed as a Blocker; add a concise `TaskResult` definition as a readability improvement. |
| F2 | Major, contested | Reader | R4/D3: existing side-effect, ownership and acknowledgement guarantees allegedly undefined. | **Contest:** `plan:54–55,81–85,142–144` defines consistent pairing, nonduplication and superseded-attempt exclusion; `notes:66–68` specifies interruption probes. Acknowledgement-barrier discovery is an explicit experiment objective. Closed. |
| F3 | Major, contested | Reader | R8: ten benchmark checks absent from `plan.md`. | **Contest:** detailed checks belong in linked evidence/code. `plan:198`, `notes:54,72` and P02 task 2.3 identify reuse of the existing benchmark; `tests/benchmarks/agent_tasks/tasks.py` supplies the checks. Closed. |
| F4 | Nit | Reader | Terms/non-goals: `spark`, profiles and template locks receive little explanation. | **Fix:** add a short definition or source pointer identifying the existing model/template configuration. Open, nonblocking. |
| F5 | Nit | Reader | Non-goals, `plan:42`: runtime Phase 2 and Phase 1 evidence lack a one-line gist. | **Fix:** briefly identify Phase 1 as the existing harness baseline and Phase 2 as events/comms work. Open, nonblocking. |
| F6 | Major, contested | Reader | Phases table allegedly lacks tasks, requirement allocation and completion criteria. | **Contest:** these belong in phase files. P01 `delivers` and tasks 1.1–1.3, and P02 `delivers` and tasks 2.1–2.4 supply them. **Nit remains:** make the phase titles clickable so readers can reach that layer directly. |
| F7 | Major, contested | Reader | D2/Assumptions: artifact identities and inspected revision deferred to notes. | **Contest:** `plan:138,199` points to notes; `notes:12–17` records upstream revision `39163dd30f703a79079e2d2446545cff3c453738` and requires source/artifact provenance. Selecting reproducible matching artifacts is task 1.1, not an asserted completed prerequisite. Closed. |
| F8 | **Major — open** | Reader; coordinator upheld | R5, `plan:89–91`; `notes:69`; P02 task 2.2 require “configured bounds” and “configured grace,” but no probe values, configuration source or pre-run selection rule is specified anywhere in the contract. | **Fix:** in notes or P02, require recording turn/time limits, stop trigger, cleanup grace and observation deadline **before** each probe. Identify inherited limits versus spike-specific limits and the pass/fail rule for surviving work. This supplies an acceptance oracle without inventing a performance threshold. |
| F9 | **Major — open** | Reader; coordinator upheld | R6, `plan:95–97`; `notes:70` requires matching a model-boundary ledger, but does not identify how that ledger independently observes retries/auxiliary requests, its accounting units, or the exhaustion comparison. | **Fix:** specify in notes the authoritative observation point, counted units, request correlation/reconciliation rule and a deterministic exhaustion probe. Keep candidate-reported usage separate from boundary observations. The existing token accounting provides a reference, but not the candidate ledger design. |
| F10 | Major, contested | Reader | R9: hard gates allegedly unidentified. | **Contest:** `notes:88–91` explicitly identifies R1–R7 and R10 as hard gates and separately applies R8’s regression rule. This is permissible linked depth. Closed. |
| F11 | Major, contested | Reader | R3/D4: allowed fixture grants and forbidden operations not enumerated in `plan.md`. | **Contest:** trusted fixture composition is part of the experiment, not a production permission change. `notes:63–65,75–82` requires recorded composition, approved fixtures and denial probes; P01 tasks 1.1–1.2 implement them. Specific fixture identifiers may live in the spike README. Closed. |
| F12 | Nit | Reader | D3/R9: no explicit classification when the supported runtime lacks a consistency barrier. | **Fix:** state that demonstrated absence of a usable barrier fails R4, while inability to evaluate it because prerequisites are unavailable is blocked. Open, nonblocking. |
| F13 | Nit | Reader | R8 combines benchmark identity, regression threshold, comparison metadata and baseline preservation. | **Fix:** label the individual checks under R8 or reference a notes checklist. Open, nonblocking. |
| F14 | Nit | Reader | R10 combines orchestration ownership and auxiliary-work accounting. | **Fix:** distinguish the orchestration-inventory check from the R5/R6 checks for admitted auxiliary work. Open, nonblocking. |

Codebase fit confirmed the named local seams match their descriptions, found no conflicting accepted ADR and found no missing requirement delivery or concrete reuse problem. Zoom out judged the isolated spike proportionate to the uncertainty, with production migration appropriately deferred. Neither reviewer claimed upstream runtime capability had been verified.

### Verdict and outstanding work

**FAIL under the repository review protocol:** F8 and F9 remain open Majors. Their fixes belong in notes or phase tasks; expanding `plan.md` with detailed mechanics is unnecessary. F1’s original Blocker and the other contested Majors are closed through the explicit evidence above, not waived.

The fresh-reader instruction-isolation limitation also remains part of this report. No review log, frontmatter or saved report was written because your instructions prohibit edits. The contract therefore remains recorded as `design_review.status: none`.

Next: `/design-review docs/plans/2026-11-14-dsh-harness-evaluation` after the acceptance-definition fixes, in a fresh review session.

---
review: design
phase: general-dsh-harness-evaluation
change: docs/plans/2026-11-14-dsh-harness-evaluation
rfc: n/a
adrs: []
commit_sha: de6507f73ba9ec0a775299125e49f0fc366938d1
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

# Independent DSH spike design review, round 2

Frozen report below. Subsequent wording corrections are recorded in the plan log;
no third round, executable compatibility result or adoption approval is claimed.

**PASS — second and final design-review round**, with open Nits and the independence limitation below. No Blocker or Major remains open after evidence-backed reconciliation.

Reviewed SHA: `de6507f73ba9ec0a775299125e49f0fc366938d1`  
Scope: whole plan, `docs/plans/2026-11-14-dsh-harness-evaluation`. This verdict assesses the isolated spike contract; it grants neither DSH adoption approval nor runtime phase closure.

No files were changed. No downloads, installations, candidate model calls, tests, fixes, commits or GitHub writes occurred. The report and lifecycle metadata were not saved because edits were prohibited.

**Reviewer status and independence**

| Lens | Fresh native role | Status | Assessment |
|---|---|---|---|
| Reader | `design-reader` | Completed | Accurate paraphrases; concerns reconciled below |
| Codebase fit | `design-reviewer` | Completed | No findings |
| Zoom out | `design-reviewer` | Completed | No findings |
| Structure | Installed helper | Completed | Zero errors or warnings |

All three roles were spawned with `fork_turns: none`. No reviewer received author reasoning, earlier findings/verdicts or another reviewer’s output. Only the coordinator read `reviews.md` and the earlier report, after all fresh assessments completed.

The reader nevertheless reported automatically supplied `AGENTS.md` instructions and the skills catalog. It opened only `plan.md`, Summary first. Thus the intended absence of project instructions was **not achieved**; its assessment has reduced independence. Zoom out likewise reported automatic `AGENTS.md` visibility and review-status metadata in frontmatter. Codebase fit intentionally received guidance files. The shared read-only workspace also provides less isolation than separate checkouts.

Upstream claims were not independently reverified under the no-download restriction. No reviewer established executable DSH compatibility. Codebase fit disclosed truncated broad reads followed by focused reads of relevant sections.

**Exact inputs**

All repository paths below are relative to `/tmp/praxismesh-dsh-design-review`.

The reader’s sole assigned and opened file:

```text
docs/plans/2026-11-14-dsh-harness-evaluation/plan.md
```

Both design reviewers received this prescribed document list:

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

Codebase fit additionally received `AGENTS.md` and `CLAUDE.md`. No nested guidance files were found.

Both design reviewers reported inspecting these additional files, fully or in relevant excerpts:

```text
PROJECT_PLAN.md
docs/development/planning.md
docs/roadmap/design-decisions.md
docs/roadmap/phases/phase-1.md
harness_activity/activity.py
harness_activity/runner.py
harness_activity/config.py
registry/templates/local-default.yaml
registry/profiles/default.yaml
tests/test_runner_conformance.py
tests/benchmarks/run.py
```

Codebase fit additionally inspected:

```text
AGENTS.md
CLAUDE.md
docs/roadmap/phases/phase-2.md
docs/benchmarks/baseline.json
docs/benchmarks/2026-11-12-local-default.md
common/schemas/task.py
common/persistence/repositories.py
registry/loader.py
registry/registry.lock
registry/mcp/sample-shop.yaml
registry/skills/order-desk/SKILL.md
tests/benchmarks/agent_tasks/tasks.py
tests/support/worker_procs.py
tests/support/workers.py
sample_mcp/server.py
spikes/harness-vllm/README.md
spikes/harness-vllm/pyproject.toml
```

Zoom out additionally inspected:

```text
docs/requirements/baseline.md
harness_activity/tools.py
```

Coordinator-only inputs included the installed `design-review/SKILL.md`, `impl-plan/SKILL.md`, `impl-plan/writing.md`, helper output; native role configurations and their registration in `/home/geo/.codex/config.toml`; project guidance and planning/review protocol; `.github/scripts/check_plans.py`; the target contract; relevant runner, Activity, tool, workflow and benchmark excerpts; and finally:

```text
docs/plans/2026-11-14-dsh-harness-evaluation/reviews.md
docs/reviews/general-dsh-harness-evaluation/design-review-01.md
```

**Reader paraphrases — verbatim**

From the Summary:

> The change evaluates DeepSeek Harness as the runtime for agents executing inside Temporal Activities, using an isolated experiment with the existing local model and capabilities. It seeks evidence about recovery, execution limits and policy enforcement before considering adoption. The main risk is that normal execution succeeds while interruption breaks checkpoint consistency or control over running work.

From the whole plan:

> The plan adds an isolated DSH runtime and bridge, pins its dependencies and configuration, and tests compatibility with existing capabilities and task results. It checks authority restrictions, recovery, attempt fencing, cancellation, usage accounting and the existing ten-task benchmark. Temporal retains orchestration ownership throughout. The deliverable is evidence and a recommendation; production adoption requires a separate decision and implementation plan.

The reader found no material Summary-versus-plan discrepancy and no section whose intent it could not paraphrase.

**Mechanical evidence**

| Check | Observed result |
|---|---|
| HEAD | Exact requested SHA |
| Working tree | Clean before and after |
| Contract identity | `plan.md`, `notes.md`, both phases and `reviews.md` byte-identical to HEAD |
| `python -B …/impl-plan/plan-tool.py check …` | 0 errors, 0 warnings |
| `python -B .github/scripts/check_plans.py` | 3 plans validated; 0 errors |

These checks establish structure and snapshot identity, not compatibility, probe success or approval.

**Consolidated fresh findings and dispositions**

Here, `plan`, `notes`, `P01` and `P02` identify files inside the reviewed plan directory. Every reader concern is represented, including duplicates merged into one row. Readability is Major only when it causes materially wrong understanding; neither paraphrase demonstrates such a misunderstanding.

| ID | Reviewer severity | Finding and evidence | Explicit disposition |
|---|---|---|---|
| S1 | Reader: Major, twice | R7/Terms omit exact outcome mapping and completion mechanism. | **Contest; closed.** `plan:58–60,112–114` distinguishes task results from runner outcomes. `harness_activity/tools.py:8–10,33–37` defines explicit completion; `runner.py:215–228` handles continuation; `orchestrator/workflow.py:94–147` loops on continuation and maps terminal outcomes. P02 task 2.2 requires outcome/error validation. Detailed bridge mechanics belong in implementation, not the human overview. Earlier F1 remains contested. |
| S2 | Reader: Major | D2’s “trusted Cordis patches” is unexplained. | **Nit; open.** Cordis/composition are defined at `plan:50–52`; R3 restricts grants to trusted configuration; P01 tasks 1.1–1.2 require recorded composition and authority probes. This prevents a materially wrong authority model, but “patches” remains ambiguous. **Fix:** briefly define whether this means composition configuration, plugins or source modifications; record exact identities in the experiment inventory. |
| S3 | Reader: Nit | Assumptions does not identify the inspected upstream revision. | **Contest; closed.** `plan:152,175,213` directs readers to research; `notes:12–17` supplies revision and artifact-provenance constraints. P01 task 1.1 selects matching artifacts. This is permitted evidence depth; earlier F7 remains contested. |
| S4 | Reader: Blocker | R5’s numerical bounds and cleanup rules live in notes. | **Contest; closed; F8 fix verified.** `plan:98–100` states bounded stopping and links the policy. `notes:88–118` fixes the pre-run manifest, inherited/test limits, 5-second grace, 10-second observation deadline, independent observer and forced-cleanup failure rule. P02 task 2.2 explicitly requires these oracles. Missing-from-overview is not missing-from-contract. |
| S5 | Reader: Blocker | R6’s observation point, units and exhaustion oracle live in notes. | **Contest; closed; F9 fix verified.** `plan:104–108` states accounting and admission behavior. `notes:122–180` defines independent gateway/executor observations, dispatch/token/tool units, correlation, unknown-usage denial and exact exhaustion/retry/auxiliary sequences. P02 task 2.2 requires them. |
| S6 | Reader: Major | R8 omits the ten executable checks. | **Contest; closed.** `plan:118–122,212` identifies the existing benchmark and rule; `notes:184–191` supplies B1–B4. `tests/benchmarks/agent_tasks/tasks.py` contains the checks; `tests/benchmarks/run.py:147–156` implements regression comparison. P02 task 2.3 reuses them. Earlier F3 remains contested. |
| S7 | Reader: Major | R4/D3 omit detailed side-effect and checkpoint publication protocols. | **Contest; closed.** `plan:90–94,156–158` defines preservation, nonduplication, fencing and barrier discovery. `notes:66–68` specifies interruption probes; P02 task 2.1 implements them. Existing checkpoint/admission sequencing appears in `harness_activity/activity.py:284–338`; the idempotent fixture and pause-after-effect seam exists in `sample_mcp/server.py:97–156`. Discovering an equivalent DSH barrier is spike work. Earlier F2 remains contested. |
| S8 | Reader: Major | Tasks and deliverables require opening phase files. | **Contest; closed.** The writing rules explicitly put tasks in phase files. `plan:219–220` links both; their `delivers` and seven tasks supply allocation and verification. Earlier F6’s navigation Nit is fixed. |
| S9 | Reader: Nit | Separate-adoption language repeats across Summary, D5, rollout and decision log. | **Nit; open.** Evidence: `plan:20–22,168–170,196,224–225`. **Fix:** retain the Summary explanation and authoritative D5 rule; shorten redundant references where useful. |
| S10 | Reader: Nit | R5 and R7 scenarios bundle several trigger/outcome cases. | **Nit; open.** Evidence: `plan:100,114`. **Fix:** distinguish stalled provider, blocked tool and cancellation cases, and use a labelled outcome checklist in notes/P02. Preserve concise overview requirements. |
| S11 | Coordinator: Nit | Review-log preamble says no independent review has run despite the recorded first round. | **Nit; open.** `reviews.md:3` contradicts `reviews.md:6–15`. **Fix:** remove or qualify the stale preamble in a later authorized documentation update. Historical round-one FAIL remains valid for its original SHA. |

Codebase fit confirmed the SDK/session coupling, trusted configuration, production `openai_agents` restriction, result semantics and benchmark rule. It found no task-coverage, reuse or accepted-ADR conflict. Zoom out found the spike proportionate, with explicit recovery, accounting, cancellation and teardown outcomes.

**Reconciliation of every earlier finding**

| Prior ID | Current disposition | Evidence at reviewed SHA |
|---|---|---|
| F1 | Contested remains closed; optional definition verified | `plan:58–60`; S1’s code and P02 evidence |
| F2 | Contested remains closed | `plan:90–94,156–158`; `notes:66–68`; S7 |
| F3 | Contested remains closed | Existing benchmark checks and regression implementation; S6 |
| F4 | Fixed; no recurrence | `plan:53–57` explains model, policy/template and lock |
| F5 | Fixed; no recurrence | `plan:61–62` explains runtime Phases 1 and 2 |
| F6 | Major remains contested; navigation Nit fixed | Clickable phase titles at `plan:219–220`; phase task allocation |
| F7 | Contested remains closed | `notes:12–17`; P01 task 1.1; S3 |
| F8 | Fixed; not reopened | Complete pre-run stop/cleanup policy at `notes:88–118`; S4 |
| F9 | Fixed; not reopened | Independent ledger and exact accounting probes at `notes:122–180`; S5 |
| F10 | Contested remains closed | `notes:195–198` identifies R1–R7/R10 hard gates and separate R8 rule |
| F11 | Contested remains closed | `plan:84–86`; `notes:63–65,75–82`; P01 tasks 1.1–1.2 define recorded grants and denial probes |
| F12 | Fixed; no recurrence | `plan:130`; `notes:200–202` distinguish demonstrated barrier failure from unavailable prerequisites |
| F13 | Fixed; no recurrence | `plan:120` links labelled B1–B4 at `notes:184–191` |
| F14 | Fixed; no recurrence | Separate orchestration and auxiliary-work scenarios at `plan:136–137` |

No earlier finding was silently waived. The fresh reader’s objections to locating mechanics in notes/phases do not invalidate the substantive F8/F9 corrections: both acceptance oracles are now present and explicit.

**Remaining open items and stopping point**

Open Nits: **S2, S9, S10 and S11**. The reader’s automatic project-instruction visibility remains a disclosed independence limitation.

The repository still records `design_review.status: changes-requested`, round 1. This chat verdict did not update or save lifecycle evidence. DSH execution, compatibility, adoption approval and runtime phase gates remain outstanding work outside this review.

Second round complete; no third round or fixes initiated.

Next: `/design-review docs/plans/2026-11-14-dsh-harness-evaluation`

That is the helper’s literal output from unchanged metadata, **not a recommendation to run another round**.

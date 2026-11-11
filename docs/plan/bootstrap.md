# PraxisMesh plan: feasibility spike and bootstrap (Pre-0, §0)

Part of the PraxisMesh project plan, revision 2.10. Start from the core plan: [PROJECT_PLAN.md](../../PROJECT_PLAN.md). Section numbers match the core plan's document map.

## Pre-0. Feasibility spike and open inputs (before bootstrap)

**Gate:** This runs **before §0**. It is a throwaway experiment and a list of owner decisions, not implementation. **Status: planned; nothing here has been run or decided.** Added in revision 2.9 because the whole platform rests on one unproven assumption, and several inputs the plan depends on were never named.

### Pre-0.1 Harness-on-local-model spike

**Question to answer:** Can a Claude harness (Claude Agent SDK, or `claude -p --output-format stream-json`) complete multi-step, tool-using work against a local model served through vLLM's Anthropic Messages-compatible endpoint, reliably enough to build on?

- [ ] Pick one candidate local model and record model name, quantization, context length, GPU model/VRAM, vLLM version and the exact launch flags (served model name, tool-choice/parser settings).
- [ ] Run a small scripted set of tasks (proposed: about 20) that each need several tool calls, including at least one file edit, one shell command and one MCP tool call. Record per-task success, malformed tool calls, stalls, turns and tokens.
- [ ] Repeat the same set with the OpenAI-agents harness on vLLM's OpenAI-compatible endpoint, so the fallback is measured and not assumed.
- [ ] Record a decision: **go** (Claude harness on vLLM is the primary path), **go with adapter** (name the adapter and its limits), or **no-go** (name the primary path instead: OpenAI-agents harness locally, or the optional Anthropic API tier). The pass threshold is set by the project owner before the run, not after.
- *Preliminary probe, 2026-11-10 (not the spike):* against `qwen3.8-flash-next` on vLLM 0.32.0, OpenAI `/v1/chat/completions` answered, Anthropic `/v1/messages` answered with a `thinking` block then text, and `/v1/messages` with one tool returned a correct `tool_use` block (`stop_reason: tool_use`). Reasoning tokens count against `max_tokens` (a 30-token budget ended inside the thinking block). This shows the endpoint mechanics work; it says nothing yet about multi-step harness reliability, which the task set above must measure.
- [ ] Keep the spike code out of the product tree. Store the write-up at `docs/spikes/harness-vllm.md` once the repository exists; until then keep it beside this plan.

**Accept:** A dated write-up with the environment, raw results, the decision and its consequences for §4.1 and Phase 1. A no-go result is a valid outcome that changes the plan through the decision log; it is not a failed task.

### Pre-0.2 Open inputs that block later work

Each row needs a named human owner and a recorded answer. An unanswered row blocks the phase shown.

| Input | Blocks | Status |
|---|---|---|
| GitHub owner/organization and repository visibility | §0 | Answered: `geosp/praxismesh`, public |
| Open-source license | Public distribution | Answered: Apache-2.0 |
| Target coding tools and OpenSpec tool IDs | §0.2 | Proposed: Claude Code, GitHub Copilot, Codex CLI (shared `.agents/` layout in place). OpenSpec 1.17.0 initialized locally with tool ID `agents` (see decision log) |
| Source, version and license of the three specialist review skills, or the decision to use the §0.3 fallback | §0.3 | Open |
| Local model per tier, and what each tier means (count, intended workload, cost weight) | Phase 1 (one tier), Phase 3A (two tiers) | Partly answered: spike candidate `qwen3.8-flash-next` (NVFP4 MoE, 262K context) on the Spark pair; other registry candidates `qwen3.8-27b`, `gemma-4-26b-a4b`, `deepseek-v4-flash`, `gpt-oss-120b`. The Spark pair serves one model at a time, so a second tier means the RTX 3090 box or one model with two profiles (§7.1). Tier meanings, count and cost weights open |
| GPU hardware available for development and for the Phase 7 demo | Phase 0, Phase 7 | Answered: development and Compose on an x86_64 workstation with no NVIDIA GPU; model serving on 2x NVIDIA DGX Spark (arm64, 128 GB unified memory each) running vLLM 0.32.0 with tensor parallelism across both (one model at a time, registry in `geosp/mixvllm`); optional 2x RTX 3090 (24 GB each) box for smaller models. Phase 7 GPU node not yet chosen. Endpoints live in a git-ignored `.env`, never in this repository |
| Sandbox mechanism for untrusted repository code | Phase 5 | Open |
| Tenancy model (default proposed in §2: single-organization installation) | Phase 3A | Open |
| Harness licensing: confirm against Anthropic's terms (with counsel if needed) that the intended use and distribution of the Claude Agent SDK / Claude Code CLI is permitted, including use with non-Anthropic local models and inclusion in published images (see §2) | Publishing worker images; choice of default harness in Phase 1 | Open |
| Thresholds: spike pass rate, benchmark regression limit, routing accuracy, history-size bound | Pre-0.1, Phase 1, Phase 3A, Phase 3B | Open |
| Retention defaults (§4.13) and cost units (§4.5) | Phase 1, Phase 3A | Proposed; confirm |

## 0. Prerequisite: GitHub repository, OpenSpec, and specialist skills

**Gate:** This is a **project bootstrap stage before Phase 0**, not an additional application feature phase. **Status: in progress.** The repository `geosp/praxismesh` exists (public, Apache-2.0) and OpenSpec is initialized locally (see the decision log). CI, the remaining project files, branch protection and the specialist review skills remain pending.

### 0.1 Choose and create the shared repository

- [x] Confirm the GitHub owner/organization, check availability of the selected repository slug **`praxismesh`**, and create it only after authorization. **Done 2026-11-10: created by the owner as `geosp/praxismesh` (public); license Apache-2.0.** Confirm an open-source license before public distribution; initial private bootstrap is optional. Do not assume trademark, package registry, or domain availability.
- [ ] Create the repository with a `main` branch, README, `.gitignore`, `.editorconfig`, standard secret-exclusion rules, and a documented clone/bootstrap path. Record the canonical clone URL in this plan. *(Clone URL: `https://github.com/geosp/praxismesh.git`. Still missing: README, `.editorconfig`.)*
- [ ] Add `PROJECT_PLAN.md` and the `docs/plan/` files (together the versioned canonical plan; see the document map) and initialize `docs/rfcs/`, `docs/adr/`, `docs/architecture/`, and `docs/templates/` with concise README/index files. These folders are human-facing documentation, separate from `openspec/`. Do not mark plan tasks complete merely because files have been copied into Git.
- [ ] Set up repository permissions, PR-based changes, required review/check rules when available, and least-privilege access for each kind of session. Ensure automated sessions cannot silently override protected-branch policy. *(Partly done 2026-11-10: ruleset `protect-main` on the default branch requires PRs (0 approvals, single maintainer), resolved conversations, no force-push or deletion, with an empty bypass list. Squash-only merges and branch auto-delete are on. Still open: required status checks once CI exists, and per-session least-privilege access.)*
- [ ] **Project CI (rev 2.10):** create the pipeline that supplies the required status checks this plan relies on (GitHub Actions or the verified equivalent). Run on every PR: formatting and lint, type checking, unit tests, Workflow replay tests once Workflows exist, secret scanning, a dependency license scan, and a link check over the plan files. It must pass on an empty tree, expose no secrets to PRs from forks, and be registered as required checks on `main`. Model- and GPU-dependent suites run separately (§8).
- [ ] **Open-source project files (rev 2.10):** add `CONTRIBUTING.md`, `SECURITY.md` with a private vulnerability-reporting route, a code of conduct, issue and PR templates, `CODEOWNERS`, and `docs/release.md` describing versioning (SemVer; breaking changes allowed before 1.0 but always listed), the changelog, and the compatibility rules for database migrations, CRD/schema versions, the gateway API and Workflow code.

### 0.2 Install OpenSpec in the repository

- [ ] Confirm the development machine(s) and target coding tools (such as Claude Code, Codex, Cursor). Check the installed OpenSpec CLI first using `openspec --version`. If absent, choose an approved installation method from https://openspec.dev/docs/installation; don't silently run a remote shell installer or alter machine-global tools.
- [ ] From the **Git repository root**, initialize OpenSpec using `openspec init` (interactive) or `openspec init --tools <confirmed-tool-ids>`. Inspect existing tool/skill directories before init because generated integrations or legacy cleanup can affect those files. Record selected tool IDs, installed CLI version, and resulting generated paths.
- [ ] Commit the generated `openspec/` configuration, specifications/change directories, and explicitly selected coding-tool integration files. Distinguish maintained OpenSpec specifications from the master project plan and keep them consistent; apply the §4.16 build-time precedence rule: approved phase requirements are reflected in `openspec/specs/` and proposed work in `openspec/changes/`, each tracing to plan requirements.
- [ ] Verify CLI and initialization (`openspec --version`; check expected repo paths; `openspec list` and any applicable validation command after specs exist). Record the tool-specific invocation commands printed by init rather than assuming their spelling.

### 0.2.1 Evaluate a custom OpenSpec workflow schema (planning requirement)

**Purpose:** Determine whether OpenSpec's custom workflow schemas can express the project's isolated, skill-specialized engineering handoffs. This is an evaluation task, not authorization to modify or install tooling now.

**Known as of 2026-11-10 (web check; re-verify against the installed version):** OpenSpec supports project-level custom schemas under `openspec/schemas/<name>/schema.yaml`, managed with `openspec schema fork|init|validate|which`. A schema declares artifacts and the dependencies between them, and validation covers syntax, template existence, circular dependencies and artifact IDs. That is artifact ordering, not gate enforcement. The evaluation below is therefore **timeboxed to half a day** and should concentrate on the two open points: session isolation and how CI enforces what the schema cannot.

- [ ] Evaluate the custom workflow schema capabilities in the version of OpenSpec selected during bootstrap.
- [ ] Assess representation of specification, design, independent design review, implementation, independent implementation review, and independent verification, including artifact prerequisites.
- [ ] Define traceability from approved requirements to versioned artifacts, acceptance tests, review evidence and the exact Git commit or immutable artifact digest.
- [ ] Check that fresh, independent sessions can access only their required inputs without inheriting another session's private conversation history.
- [ ] Define how GitHub CI, protected branches, and required status checks enforce gates that OpenSpec artifact dependencies do not themselves enforce; a review verdict alone cannot authorize a merge.
- [ ] Record a reasoned decision: adopt a custom OpenSpec schema, use the default schema, or introduce minimal compatible extensions. Document any unsupported requirements or integration limitations.

**Accept:** A documented design decision demonstrates reproducible, isolated phase handoffs and independent verification using OpenSpec plus the existing specialist skills without adding a second orchestration or review framework. A schema is not considered adopted merely because the evaluation is written.

### 0.3 Integrate existing specialist skills from the other system

- [ ] Obtain the real source and setup instructions for the existing **design-review**, **implementation-review**, and **independent-verification** skills; record each source repository/package, version or pinned commit, license, and required runtime/tool permissions. **Do not invent or rewrite the user's existing skills.** *(2026-11-10, owner decision: design review and implementation review were adapted into project-owned skills `review-design` and `review-implementation` with agents `design-reader`, `design-reviewer` and `impl-reviewer`; see the decision log. Source and license not recorded. The verification skill did not exist; `verify-phase` with agent `verifier` was written for this project from the plan's requirements instead, by owner decision.)*
- [ ] **Fallback if the skills cannot be obtained (rev 2.9):** If any of the three skills cannot be exported, licensed or made to run by the date the project owner sets in Pre-0.2, record an ADR and use minimal project-level substitutes: three short review checklists (design review, implementation review, verification) derived from this plan's acceptance criteria and approved by the project owner. Label them as substitutes, keep them versioned in Git, and replace them when the real skills arrive. This is a recorded substitution, not a rewrite of the user's skills.
- [ ] Install or expose each skill to the appropriate coding tool/session using the format its original system supports. Where that system cannot be used directly, document an approved wrapper or compatibility adapter rather than changing the skill's semantics silently.
- [ ] Keep **design review**, **implementation**, **implementation review**, and **verification** in distinct sessions. Each first-pass reviewer receives only the approved requirements, relevant RFC/ADRs, allowed artifacts and immutable code/artifact reference required for its role; do **not** provide another reviewer's verdict, review report, rationale, implementation-session transcript or private reasoning before the reviewer records an independent assessment. The coordinator may send actionable findings to the implementer. For a remediation re-check, provide the correction list only after a fresh assessment (or explicitly label the separate targeted follow-up). Preserve versions and source identifiers for all reviews.
- [ ] Set the least privilege per role: reviewers can read code and execute bounded checks, whereas write/push/credential access is explicitly granted only to the sessions that need it. Keep skill permissions and credentials out of the application's runtime images.

### 0.4 Bootstrap acceptance and reproducible demonstration

**Accept:** A new developer or AI session can clone the chosen repo, locate the master plan and OpenSpec artifacts, run the configured OpenSpec integration, and invoke or discover each available specialist skill. The reviews can target an immutable commit. Any unprovided external skill is an **open blocker**, not a passing test.

**Demo checklist (required before Phase 0):**  
**Audience-visible outcome:** A fresh checkout is ready for independent phase planning, implementation, review, and verification.

- [ ] Show the actual GitHub repository, clone URL, default branch, protected change path, and clean clone.
- [ ] Show `openspec --version`, generated configuration/skill files in the clone, and a working OpenSpec command supported by the chosen coding tool.
- [ ] In separate fresh sessions, show that the installed design-review, implementation-review, and verification skills can be invoked or loaded against the same pinned commit (without exchanging conversation histories).
- [ ] Demonstrate a blocked unauthorized write or branch-protection check and verify that no secrets or session transcripts were committed.
- [ ] Open a PR with a deliberately failing check and show that merge is blocked; fix it and show the checks pass on the latest head.
- [ ] Save the commands, versions, commit SHA, expected versus observed behavior, and demo evidence in `docs/demos/bootstrap.md`; mark pass/fail explicitly.

**Boundary:** OpenSpec and the development-review skills are tools for **building this platform**, not necessarily runtime dependencies or worker skills of the platform being built. The worker-template skill security policy in Phase 1 remains a separate concern.

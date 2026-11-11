---
name: review-design
description: >-
  Reviews a PraxisMesh design - an OpenSpec change plus its linked phase RFC and
  ADRs - with reviewers that start from a fresh context, before implementation.
  Use after openspec-propose (or docs-design) and before openspec-apply-change,
  when the engineer asks to stress-test a design, or to run the independent
  design review that approves a phase RFC (gate mode).
---

# Design review

An agent that helped write a design fills its gaps from the conversation and doesn't notice them. This skill hands the design to reviewers that have no conversation history, so they judge only what is written, what the plan requires and what the code shows.

Order of work: `openspec-propose` (and `docs-design` for the RFC) -> **`review-design`** -> `openspec-apply-change` -> `review-implementation` -> tests -> `github-pr` -> at a phase gate, `verify-phase`.

## Step 0: Choose the mode

- **Informal:** a stress-test. The report goes in chat, and this session may apply approved fixes (Step 5).
- **Gate:** the review approves a phase RFC. Follow every rule in `docs/reviews/README.md`:
  - **Fresh session:** if this session wrote or discussed the design, stop and say a new session is needed.
  - **Pinned revision:** the reviewed files must be committed and unchanged (`git status --porcelain -- <paths>` empty). Record `git rev-parse HEAD`.
  - **Saved report:** with a verdict.
  - **No Step 5:** findings go back to the author.

If the user doesn't say, ask which mode. Use gate mode only when they confirm.

## Step 1: Select the change

If a change name was provided, use it. Otherwise infer it from the conversation, auto-select it if only one active change exists, or run `openspec list --json` and ask the engineer to pick one.

Announce: "Using change: <name>". Read its `proposal.md`, `design.md`, `tasks.md` and `specs/**`. If there is no `design.md`, review the proposal and specs instead and say so.

Find the **linked RFC and ADRs**: an RFC whose front matter has `openspec_change` set to this change, otherwise `grep -rl "<name>" docs/rfcs docs/adr`. In gate mode, a phase design review with no RFC is a Blocker (plan §4.17).

## Step 2: Build the reading lists

- **Change files:** absolute paths to the change artifacts above.
- **Design docs:** absolute paths to the linked RFC and ADRs.
- **Guidance files:**
  - the root `AGENTS.md`, plus any nested `AGENTS.md` in the top-level packages the design touches (for example `orchestrator/`, `gateway/`, `harness_activity/`, `common/`). Work out the packages from the paths named in the design and tasks.
  - `PROJECT_PLAN.md`, read for §2 (hard constraints) and §6 (layout);
  - the phase file in `docs/plan/phases/` and the design sections it lists under *Read first* (plan §9.7);
  - `docs/plan/schemas.md` when the design touches schemas.
- **Repository root:** the absolute path of the checkout being reviewed.

Do not add anything else. In particular, don't pass along your own reasoning, the conversation, or what you suspect is wrong. The reviewers are only useful if they don't share your context.

## Step 3: Run the reviewers

Start all three reviewers at once. Give each one its brief from [Reviewer briefs](#reviewer-briefs) with the placeholders filled in, and nothing more.

| Reviewer | Agent | Sees |
| --- | --- | --- |
| Fresh reader | `design-reader` | `proposal.md`, `design.md` and the RFC only, no project instructions |
| Codebase fit | `design-reviewer` | The change, design docs, guidance and plan files, the code |
| Zoom out | `design-reviewer` | The change, design docs, plan files and the code |

The agents are defined in `.agents/agents/` and generated for each harness.
- `design-reader` can only read files. In Claude Code it starts without `CLAUDE.md`/`AGENTS.md` (`omitClaudeMd`). Codex and Copilot cannot skip project instructions; when the reader ran there, say so in the report, because its paraphrase is less independent.
- `design-reviewer` searches the code read-only.
- If a harness cannot load these agents, spawn a fresh read-only subagent for each reviewer.

A reviewer that errors or returns nothing has not reviewed. Retry it once. If it fails again, report it as "not run", never as "no findings".

## Step 4: Report

Report in chat. In gate mode, also write the report from `docs/templates/review-report.md` to `docs/reviews/phase-N/design-review.md`, with the commit SHA, inputs, reviewer statuses and verdict (`docs/reviews/README.md`, rule 5). Offer to commit it on the RFC's branch.

1. **The fresh reader's paraphrase, word for word.** The engineer compares it with what they meant, so a wrong paraphrase is a finding in itself.
2. **The findings table.** Merge duplicates across reviewers. Give each finding an id, a severity (Blocker / Major / Nit), the reviewer that raised it, and one proposed action:
   - **Fix:** the concrete edit to the RFC, `design.md`, `tasks.md` or a spec.
   - **Contest:** why the finding is wrong, with evidence from the code, the plan, or a decision the engineer made.

   If a reviewer missed something because the reason exists only in the conversation, the design is missing it. Propose writing the reason into the RFC or `design.md` rather than contesting.
3. Each reviewer's status: completed or not run.
4. In gate mode, the verdict: PASS or FAIL, and the rule that decided it.

In informal mode, ask the engineer which fixes to apply. In gate mode, stop here: the author fixes, and any re-check runs in a new session.

## Step 5: Apply and re-check (informal mode only)

Apply the approved fixes, then run `openspec validate "<name>"`.

If a Blocker or Major was fixed, offer one more round with fresh reviewers for the lenses that raised them. In that round:

- A finding the engineer contested or accepted stays closed, even if a new reviewer raises it again.
- A fixed finding that comes back means the fix didn't work. Reopen it.

Stop after the second round and list anything still open. Suggest `openspec-apply-change` as the next step.

## Reviewer briefs

### Fresh reader

```text
You are reading a design for a codebase you have never seen. Read only these
files, and open nothing else:

<proposal.md path>
<design.md path>
<RFC path, if any>

1. Under the heading "What this proposes", explain in 2-5 sentences, in your
   own words, what the change does and why.
2. Under the heading "How the existing system works, per this document",
   explain in 2-5 sentences how the current system behaves, based only on
   what the document says.
3. List any section you couldn't paraphrase, and say why. Each one is a
   Blocker.
4. List project-specific terms, components, or decisions that are used but
   never explained. Skip general engineering terms.
5. List places where the parts don't connect: a step that relies on
   something never introduced, a goal with no mechanism, or a mechanism with
   no stated goal.

For items 3-5, give each finding a severity (Blocker / Major / Nit), where it
is (section heading), and what is missing. "No findings" is a valid answer.
```

### Codebase fit

```text
Review the proposed change in <change directory> against the code and the
project plan in the repository at <repository root>. Stay inside that
repository.

Read the change files: <change file paths>
Read the design docs: <RFC and ADR paths>
Read the guidance and plan files: <guidance and plan file paths>

1. Claims about the code. For every file path, module, function, class,
   Temporal Workflow or Activity, task queue, application PostgreSQL table or
   migration, BlobStore key or bucket, gateway endpoint, CRD, worker template,
   MCP server and config key that the design names: confirm it exists and
   behaves as the design says. If something doesn't exist and the design
   doesn't say it will be created, report it. If the repository has no code
   for this area yet, check the claims against PROJECT_PLAN.md and
   docs/plan/schemas.md instead, and say that you did.
2. Reuse. Search for existing code that already does what the design builds
   new, or a pattern it should follow and doesn't.
3. Project rules. Check the design against every rule in the guidance and
   plan files that applies to what it changes, for example:
   - Workflow code that does I/O, reads wall-clock time or randomness, or
     consults mutable database state instead of a versioned record returned by
     an Activity;
   - adding, removing or reordering Activity calls, Signals, Updates or child
     Workflows without Temporal versioning or patching, which breaks in-flight
     executions;
   - large payloads in Workflow or Activity parameters instead of references,
     and unbounded history without a Continue-As-New plan;
   - write Activities that are not idempotent or lack stable operation IDs;
   - secrets in config, privileges injected by requests or profiles, and
     anything that breaks the local, self-hosted default deployment.
   Skip rules that don't apply.
4. Requirements trace. Every requirement in specs/ must trace to a plan
   section, and every requirement the phase file assigns to this work must be
   covered by the specs and the design. Report gaps either way.
5. Tasks. Does tasks.md cover everything the design commits to, in an order
   that builds?

For each finding, give a severity (Blocker / Major / Nit), where it is,
what is wrong, and the evidence: a file:line from the code or a quote from
the design or the plan. "No findings" is a valid answer.
```

### Zoom out

```text
Review the proposed change in <change directory> for the repository at
<repository root>. Stay inside that repository. Read proposal.md, design.md,
tasks.md and the RFC (<RFC path>), read the plan files you are given
(<plan file paths>), and read whatever code you need to judge them.

1. Root cause. Does the design fix the cause of the problem described in
   proposal.md, or only a symptom?
2. Simplicity. Is there a smaller change that gets the same result? Is
   anything built for a future need that nobody stated?
3. Placement. Does new logic live where similar logic already lives, or where
   the plan's repository layout puts it?
4. Failure modes. What happens when a step fails halfway; when an Activity is
   retried; when a worker or pod dies mid-task; when a scaled-to-zero queue has
   no worker; when two runs overlap; when work takes longer than its timeout?
   Can each step safely run twice?
5. Rollout. Compatibility with in-flight Workflows, database migrations and
   the load they add, gateway API and CRD compatibility, and how the change is
   undone.
6. Gate fit. Do the acceptance tests and the demo actually prove the change
   works (plan §8)? Does the design name the plan's rethink trigger (§7.1)
   that applies, with a measurable signal?

For each finding, give a severity (Blocker / Major / Nit), where it is,
what is wrong, and the evidence: a file:line from the code or a quote from
the design or the plan. "No findings" is a valid answer.
```

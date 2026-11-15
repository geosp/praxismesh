---
review: implementation
phase: general-dsh-harness-evaluation/01
change: docs/plans/2026-11-14-dsh-harness-evaluation
rfc: n/a
adrs: []
commit_sha: 8d7897ed96698b87fc4d603783c24f273ee05251
code_sha: 8d7897ed96698b87fc4d603783c24f273ee05251
docs_sha: n/a
diff_base: 952d01e097332905ba56d6c26e1e342431f8f394
session: fresh
date: 2026-11-14
verdict: FAIL
reviewers:
  - { lens: Contract, status: completed }
  - { lens: Failure and retry, status: completed }
  - { lens: Scope and composition, status: completed }
---

# Implementation review: DSH harness evaluation, phase 01

## Inputs

Repository: `/tmp/praxismesh-dsh-implementation-review`.

All three reviewers received the exact shared header and their respective lens from the installed `/home/geo/.agents/skills/impl-review/SKILL.md`, with these committed inputs:

- Contract: `/tmp/praxismesh-dsh-implementation-review/docs/plans/2026-11-14-dsh-harness-evaluation/plan.md`
- Phase: `/tmp/praxismesh-dsh-implementation-review/docs/plans/2026-11-14-dsh-harness-evaluation/phases/01-controlled-runtime.md`
- Context: `/tmp/praxismesh-dsh-implementation-review/docs/plans/2026-11-14-dsh-harness-evaluation/notes.md`
- Guidance, under the repository root: `AGENTS.md`, `CLAUDE.md`, `PROJECT_PLAN.md`, `docs/reviews/README.md`, and `docs/development/planning.md`
- Delivered requirements: **R1, R2, R3, R10**
- Frozen diff:

```bash
git -C /tmp/praxismesh-dsh-implementation-review diff 952d01e097332905ba56d6c26e1e342431f8f394..8d7897ed96698b87fc4d603783c24f273ee05251
```

The coordinator also read committed `reviews.md` and `docs/templates/review-report.md`. No earlier implementation-review findings required suppression or reopening. Previous design-review verdicts were not passed to reviewers.

All three `impl-reviewer` agents were launched concurrently with `fork_turns: none`. No coordinator transcript, implementer transcript, suspicions, or other reviewer findings were supplied. Follow-up messages requested finalization and disclosure of execution and independence limitations.

### Independence and assessment limitations

This was a fresh assessment session. Automatically visible context included harness system/developer instructions, agent-role instructions, tool restrictions, and repository guidance. Fresh agents therefore lacked conversation history but were not free of harness instructions.

Reviewers shared the same read-only checkout; this was context separation rather than separate filesystem isolation. Each confirmed that it read no other reviewer report. Committed implementation evidence was available as an allowed artifact, but its execution claims were not independently reproduced.

No fixes, checkout edits, commits, GitHub writes, candidate binaries, Docker commands, or live model requests were performed. Runtime tests and demos were not run. Upstream SDK shutdown internals were unavailable in the checkout; no runtime guarantee is inferred from them.

## Mechanical checks

| Check | Observed |
|---|---|
| Frozen revision | HEAD equals the specified `code_sha`. |
| Clean committed inputs | `git status --porcelain` was empty before and after review. |
| Shared plan helper through `uv run` | Could not run: uv attempted a cache write on the read-only filesystem. |
| Same helper through `python -B` | **Passed: 0 errors, 0 warnings.** |
| Public plan validator through `python -B` | **Passed: 3 plans, 0 errors.** |
| `git diff --check <base>..<code_sha>` | Passed. |
| Static Python syntax | All six changed Python files parsed successfully without imports or execution. |
| Committed evidence JSON | Parsed successfully; all seven result references matched their serialized manifest digests. |

Unticked tasks:

- **1.1:** Separate environment, artifact/platform/composition identity and prerequisites.
- **1.2:** Authority probes and real local skill/MCP task through a bounded bridge.
- **1.3:** Service/auxiliary inventory, evidence and teardown.

All three appropriately remain unticked pending gate completion.

Delivered requirements without scenarios: **none**. Undefined requirement IDs in `delivers`: **none**.

Runtime acceptance checks, candidate tests, Docker isolation checks and live walkthroughs were skipped under the requested read-only assessment. The committed walkthrough identifies source commit `6eec0b0d19580113477286b6cfbe627235d07ac3`; it is implementation evidence, not independent verification of the frozen `code_sha`.

## Findings

Duplicate findings were merged. All resolutions remain open.

| ID | Severity | Reviewer | Location | Requirement / decision | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|---|
| F1 | **Major** | Contract; Scope and composition | `spikes/dsh-harness/preflight.py:27`; `spikes/dsh-harness/run_probe.py:139` | **R1**, task 1.1 | Preflight authenticates four installed files, but the entire mutable `site-packages` directory is mounted for execution. Alter another imported SDK module or transitive dependency after locked sync: verification still succeeds and records the original lock/artifact digests while different bytes execute. R1 requires mismatched prerequisites to block reproduction. | **Fix:** Add a test that changes an unlisted imported dependency and requires startup to block. Validate the complete executable dependency environment against recorded artifacts, or reconstruct an immutable verified environment before execution. | open |
| F2 | **Major** | Failure and retry | `spikes/dsh-harness/run_probe.py:274` | **R1**, tasks 1.2 and 1.3 | Every nonzero `docker inspect` return becomes `container_absent: true`; cleanup failure does not itself fail the record. If a probe returns successfully and subsequent removal/inspection fail because the Docker daemon is inaccessible, the controller can retain `exit: 0` and claim absence despite unknown container state. | **Fix:** Mock successful probe execution followed by daemon connection errors from removal and inspection; require failure or unknown cleanup status. Distinguish confirmed “no such container” from inspection failure. | open |
| F3 | Nit | Contract | `spikes/dsh-harness/container_driver.py:40`; `spikes/dsh-harness/run_probe.py:34` | **R3**, task 1.2 | Poison probes cover skill files and one native-command-shaped input. The oracle records tool names without enforcing an allowed catalog; hashing the read-only composition does not establish unchanged effective authority. A discovered additional plugin/tool/provider could escape these observations without exposing the poison skill name. No actual upstream bypass was demonstrated. | **Fix:** Add poisoned configuration/plugin/provider fixtures; assert effective grants and destinations remain unchanged, then attempt introduced operations. Include a regression test showing an unexpected catalog entry fails evidence validation. | open |
| F4 | Nit | Contract | `docs/spikes/dsh-harness.md:43`; `spikes/dsh-harness/run_probe.py:96` | **R10**, **D4**, task 1.3 | Title, timer/jobs and MCP resource facilities remain inventoried as present, while auxiliary reconciliation is deferred. If any admits auxiliary work, the delivered inventory does not map that path to identified R5 bounds and R6 checks. Admission was not established, so this is an unresolved coverage gap rather than a demonstrated competing coordinator. | **Fix:** Enumerate admitted and disabled auxiliary paths. Test each admitted path’s identified control/accounting hooks, or prove its admission is disabled. Full Phase 02 reconciliation need not be claimed prematurely. | open |
| F5 | Nit | Contract | `spikes/dsh-harness/run_probe.py:94`; `spikes/dsh-harness/run_probe.py:280` | Task 1.2; approved notes’ stop/cleanup procedure | The manifest declares ten seconds of observation but marks the oracle pending; cleanup performs one immediate inspection. The notes prescribe continued observation “before every probe.” An early-returning run can pass without that window. The implementation openly defers R5 proof, making this a disclosed procedural mismatch. | **Fix:** Add a controller test requiring observation through the declared window, including late work. Implement that procedure or obtain a reviewed contract clarification of its phase applicability. | open |
| F6 | Nit | Scope and composition | `spikes/dsh-harness/run_probe.py:98`; `spikes/dsh-harness/model_gateway.py:190`, `:200`, `:215` | **D4**, **R10**, task 1.2 | Owned work identifies only the container. Host gateway handlers are daemon threads, provider I/O can wait 100 seconds, and `Boundary.close()` joins only the listener. A short container deadline can leave an outstanding host provider request outside the recorded cleanup scope. Full R5 verification remains deferred. | **Fix:** Use a stalled local-provider fixture and short deadline; assert shutdown closes outstanding connections and joins handlers. Include host gateway work in the ownership inventory. | open |
| F7 | Nit | Failure and retry | `spikes/dsh-harness/run_probe.py:239`; `spikes/dsh-harness/README.md` cleanup instructions | **R1**, task 1.3 | The manifest is persisted before allocation of an unrelated random scratch-directory name, which is never recorded. After two overlapping controller crashes and container removal, manifests cannot identify each run’s “matching” scratch directory as the README instructs. | **Fix:** Test two interrupted runs and require each persisted record to identify its exact cleanup directory. Allocate a deterministic run-specific path or persist the mapping before candidate startup. | open |

The contract reviewer mapped all delivered scenarios and Decisions D1–D5. D3 checkpoint acknowledgement and full R4–R9 conformance remain Phase 02 work; their absence was not treated as a Phase 01 implementation failure. The scope reviewer found no per-run request-counter reset bypass.

## Verdict

**FAIL.** All three reviewers completed, but **F1 and F2 remain open Majors**. Under `docs/reviews/README.md` rule 5, each Major requires a fix or evidence-backed contest before PASS.

Mechanical validation passed through the disclosed Python substitution. It does not establish runtime acceptance or independent verification.

## Open items

- Resolve F1–F2 and disposition F3–F7.
- Review corrections in a fresh session against a newly frozen revision.
- Run independent verification and the required walkthrough before checking off tasks.
- The invoking coordinator must save this report and record review metadata. This checkout and its review logs were left unchanged.
- Phase 02 remains unstarted.
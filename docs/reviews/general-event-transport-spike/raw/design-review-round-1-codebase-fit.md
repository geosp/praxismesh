<!-- Verbatim subagent report (design-review round 1, codebase fit, plan at bace810); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Design review round 1: codebase fit, event-transport spike (bace810)

Scope: `docs/plans/2026-11-17-event-transport-spike/` (plan.md, phases 01 and 02, notes.md) at bace810, checked against the repository at the same revision, AGENTS.md and ADR-0001 to ADR-0008.

## Claims confirmed

- `AgentEvent` in `common/schemas/events.py` has the fields the plan lists (plus `blob_ref`), and the event types include `token`, `tool_call`, `tool_result` and `reset`.
- `AttemptEvents` (`harness_activity/events.py:33-55`) numbers events per attempt and stamps `attempt_id = f"{task_id}:{turn}:{attempt}"`.
- DSH emits one `token` event per model response, with counts only (`harness_activity/dsh/gateway.py:12`, `:320-323`).
- No Workflow uses Continue-As-New: `git grep continue_as_new` over `*.py` finds nothing.
- `t01-order-total` exists (`tests/benchmarks/agent_tasks/tasks.py:158`), and so does the `dsh` profile (`registry/profiles/dsh.yaml`).
- The root lock pins `temporalio` 1.36.0 (`uv.lock:2314-2315`).
- Temporal's dynamic config is empty (`infra/temporal/dynamicconfig.yaml`: `{}`), so the documented default history limits apply. This supports the Assumption behind R5.
- The DSH spike (`spikes/dsh-harness/pyproject.toml`) sets the "own uv project" precedent that D4 cites. Root ruff, mypy and pytest exclude `spikes/` (`pyproject.toml:30`, `:42`, `:47`), so the spike cannot break CI.
- Disposable Compose projects are an existing practice (`Makefile:5-23`, `docs/demos/general-dsh-production-harness-01.md:4`).

## Findings

### F1 · Major · Decisions › D1 (notes.md#d1); R1, R2, R4: readers are never given their offset, and the offset bounds disagree

- **What is wrong:** `read()` yields `AgentEvent | Expired`. The only position field on `AgentEvent` is `seq`, which counts per attempt and restarts at 0 for each new `AttemptEvents` (`harness_activity/events.py:41`, `self.seq = 0`). The transport's per-workflow offset is not on the event.
- **Why it cannot be added:** `AgentEvent` is `Strict`, which is frozen with `extra="forbid"` (`common/schemas/base.py`, `model_config = ConfigDict(extra="forbid", frozen=True)`). An implementation cannot attach the offset to the event.
- **Effect:** R1 says a tailer "reconnects from its last offset", but a reader has no offset to reconnect from. Its only option is to count from `from_offset` or `retained_base`. That works only if every implementation's offsets are dense, and it hides exactly the gap and repeat bugs that R1 and R4 are meant to catch.
- **The bounds disagree:**
  - R1 treats `from_offset` as exclusive: "reconnects from N, then it receives N+1 onwards".
  - R2 and the notes treat the retained base as inclusive: "events from B"; `Expired` is yielded "when from_offset < retained_base".
  - With an exclusive `from_offset`, a reader at B-1 has lost nothing but would still get an expiry report.
- **Fix:** have `read` yield `(offset, AgentEvent)` or an envelope type, and state once whether `from_offset` is inclusive or exclusive.

### F2 · Major · Phase 01 › task 1.4; Decisions › D3; R9: no way to plug in the recording sink without touching production code

- **No sink hook:** the plan says to "run `t01-order-total` once on the `dsh` profile with a JSON-lines recording sink". No recording sink exists, and the benchmark has no way to inject one. `make benchmark` (`Makefile:144-145`) runs the worker in-process (`tests/benchmarks/run.py:53-54`) through `workers.main.build_harness`. That function builds the runner without a sink: `DshRunner(control, UsageLedgerRepository(engine), blobs, pinned=pinned)` (`workers/main.py:97`), so it falls back to `NoOpSink` (`harness_activity/dsh/runner.py:238`). Adding a sink there would put a diff in `workers/`, which R9 forbids.
- **No access to the schema:** the spike is its own uv project and the root sets `package = false` (`pyproject.toml`, `[tool.uv]`), so the spike cannot import `common.schemas.events.AgentEvent`. The plan does not say how the spike gets the schema that task 1.4 verifies against ("the fixture parses as `AgentEvent`s") and that D1 uses.
- **Reuse:** `tests/support/dsh_container.py:112` already offers `runner(sink)`. `tests/integration/test_dsh_activity.py:143` already drives `DshRunner(..., sink)` through `HarnessActivities` with `MemorySink`, and `tests/support/fake_model` with `order_script.json` gives a deterministic DSH turn with no real model.
- **Fix:** say where the capture script runs (the root environment, outside production packages) and how it passes the sink. Either reuse this test support, which also removes the Assumption "One real-model DSH run ... is acceptable", or say why a real-model turn is needed. Also say whether the spike vendors or path-imports `AgentEvent`.

### F3 · Major · Requirements › R4, R5; Decisions › D1, D2: R4 cannot be tested through the interface, and R4 and R5 are undefined for the options without a Workflow

- **No way to trigger Continue-As-New:** D1 says "The shared suite tests only this interface", and the interface has no Continue-As-New operation. notes.md#d1 adds `expire_below` as a test hook for R2 but nothing comparable for R4. A parametrized suite therefore cannot make the Streams Workflow continue as new.
- **R4 for PostgreSQL and JetStream:** these two options have no Workflow in the spike (phase 01 task 2.2 adds one only for Streams). R4's scenario ("when the Workflow continues as new") is either not applicable to them or trivially true.
- **R5 for PostgreSQL and JetStream:** the same holds. There is no run whose history could grow.
- **Why it matters:** D2 makes R1-R7 must-pass. Without a defined "not applicable" outcome, the results file from phase 01 task 1.3 and the decision rule are ambiguous.
- **Fix:** add a test hook such as `roll_over(workflow_id)`, which on Streams calls `WorkflowStream.continue_as_new` and elsewhere is a no-op recorded as "not applicable". Then state how D2 treats a requirement that does not apply to an option.

### F4 · Major · Decisions › D1, D2; Phase 02 › task 2.1; ADR-0007: the attempt fence that ADR-0007 requires is left out of the comparison

- **The ADR's requirement:** ADR-0007 is accepted, and no later ADR supersedes it. Its follow-up says: "any new write path for attempts (Phase 2 events, a new runner) must take the fence or justify why it need not" (`docs/adr/0007-fence-harness-attempts-in-one-transaction.md:84`).
- **What the plan does instead:** D1 keeps attempt semantics "above" the interface, "the same for all three". Phase 02 task 2.1's assessment headings (components, backups, auth, upgrades, Kubernetes) do not include fencing, and Open questions says "None".
- **Why it matters:** the options are not equal here.
  - A PostgreSQL table can take `pg_advisory_xact_lock(hashtext(task_id))` in the same transaction as the insert.
  - Streams and JetStream cannot. A stale attempt's batches would land, and notes.md#verified itself says a retried Streams attempt "appears in the stream alongside the output from the previous attempt".
  - So the fence requirement could change D2's outcome, and the Phase 2 port would have to deal with it after the choice is made.
- **Fix:** add "fence or justification under ADR-0007" to the assessment in task 2.1, or record it under Open questions.

## Nits

- Phase 01 task 2.3 and Phase 02 task 3.1, R9 check: `git diff --stat main -- ...` is a two-dot diff against a moving `main`, so commits that land on `main` later make it non-empty. Use `main...HEAD` (merge-base).
- plan.md › Links, "Phase 2's event items (9, 10, 14)": `docs/roadmap/phases/phase-2.md` has no numbered items. 9, 10 and 14 are line numbers, so cite the items by text.
- Decisions › D6 and Phase 02 task 2.2: the plan adds no decision-log entry, and does not record the verified versions in §10. AGENTS.md requires architecture changes in `docs/roadmap/decision-log.md`, and `PROJECT_PLAN.md:75` requires verified versions in §10. The precedent is `decision-log.md:95` for ADR-0005. If the plan intends to defer this until the ADR is accepted, it should say so.
- Phase 01 task 1.1, "a PostgreSQL driver": the root already uses `asyncpg` 0.32.0 (`uv.lock:113-114`). Naming it keeps the measured driver the same as the one Phase 2 would port to.

<!-- Verbatim subagent report (design-review-round-3-targeted); saved by the coordinator per docs/reviews/README.md rule 1; local paths replaced by <repo>, <verify-checkout> and <scratch>. -->

Targeted follow-up design review, round 3: D10 and R7 wording at 38e379c compared with 10ef351

Verdict: changes requested. There is one Major and three Nits, and all four are wording fixes. Points (3) and (4) of the brief raised nothing. The new wording does not contradict ADR-0005 condition 2, R5, R6 (apart from F4) or R12. Nothing in notes.md or the phase 02 tasks contradicts it.

| ID | Severity | Place | Finding | Proposed fix |
| --- | --- | --- | --- | --- |
| F1 | Major | plan.md › Decisions › D10, last sentence | The rejected option used to read "a separate pre-check (races with a new attempt)". It now reads "an unlocked pre-check (races a new attempt)". The code uses exactly the kind of check the old wording rejected: `assert_current` (common/persistence/repositories.py:248-260) takes the lock, but in its own transaction. The lock is released at commit, and only then do the blob puts (harness_activity/activity.py:381-385) and the fenced finish (activity.py:387-397) run. So a locked separate pre-check still races a new attempt. That is F25 / reopened F6 in reviews.md. The narrower wording implies the locked pre-check is sound. D10 also never says what is not guaranteed: a stale attempt can still write audit-retention artifact blobs that nothing references. This residual appears only in the reviews.md F6/F25 resolutions, so the brief's "name what is and is not guaranteed for artifact blobs" is not met in the plan. | Restore "separate pre-check". Add one sentence: "A stale attempt may leave unreferenced artifact blobs; the check before upload (`assert_current`) is an early exit, not a guarantee." |
| F2 | Nit | plan.md › Decisions › D10, "Artifact blobs are referenced only through the fenced finish" | This is imprecise. The fenced finish writes no artifact references: `finish()` updates only outcome, failure category, token counts and tool calls (repositories.py:169-215). The references exist only in `TurnOutcome.outputs`, which `_finish` returns after the fenced `finish` succeeds (activity.py:387-415). The sentence suggests the attempt row holds the references. | Reword to "Artifact references leave the Activity only in the `TurnOutcome` returned after the fenced finish succeeds." |
| F3 | Nit | plan.md › Requirements › R7 | The statement says "never publishes an artifact", but the scenario checks that "no artifact reference or outcome is recorded". "Publish" is not defined. Read literally, the statement is false, because blobs can be written (F1). The scenario also does not say where the test should observe the result. | Make the statement match the scenario: "A stale attempt never returns an artifact reference or outcome." In the Then clause, name the place to observe: no `TurnOutcome` and no outputs in the task result. Optionally say that "stale" is judged at the fenced write, under the task lock. |
| F4 | Nit | plan.md › Decisions › D10 "refusals record a row", against R6 | D10 lists start, checkpoint insert and finish as fenced, then adds a separate rule that refusals record a row. That row is written without the fence: `record_refusal` (repositories.py:217-246) has no newer-attempt check. Its caller is activity.py:185. `close_unfinished` (repositories.py:262-295, called at activity.py:214) is also unfenced (accepted as F16). R6 says flatly that a stale attempt "never writes a checkpoint or attempt row", so R6 as written is not quite true for these two paths. | In D10, scope it: "`record_refusal` and `close_unfinished` are unfenced and touch only the writer's own or lower rows." Or narrow R6 to "never writes a checkpoint or attempt outcome through the run path". |

**Points with no findings**
- **ADR-0005 condition 2** (docs/adr/0005-adopt-dsh-as-primary-agent-harness.md:69-71) asks for a reviewed consistency contract built on a reimplemented barrier. D10 is still the commit step of that barrier (notes.md D6 step 4). R5's "committed checkpoint" glossary entry still matches `insert_fenced` (repositories.py:340-366).
- **R12** is unaffected. Refusal rows get tokens of 0 by column default (migration 0003_phase1_tables.py:68), which is correct for an attempt that used nothing.
- **Phase 02:** tasks 2.1, 2.5 and 1.1 and notes.md do not contradict the new wording. Task 2.5 already ports the R5-R15 integration cases, R7 included.

Files reviewed (at commit 38e379c):
- <repo>/docs/plans/2026-11-15-dsh-production-harness/plan.md
- <repo>/docs/plans/2026-11-15-dsh-production-harness/notes.md
- <repo>/docs/plans/2026-11-15-dsh-production-harness/phases/02-dsh-runner.md
- <repo>/docs/plans/2026-11-15-dsh-production-harness/reviews.md
- <repo>/common/persistence/repositories.py
- <repo>/harness_activity/activity.py
- <repo>/docs/adr/0005-adopt-dsh-as-primary-agent-harness.md

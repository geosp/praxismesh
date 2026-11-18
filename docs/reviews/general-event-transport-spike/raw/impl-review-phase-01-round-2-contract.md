<!-- Verbatim subagent report (impl-review phase 01 round 2, targeted contract, dfc16fd..a2c6e0c, frozen at a2c6e0c); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Impl review: event-transport spike, phase 01, round 2 (targeted, contract lens)

Diff `dfc16fd..a2c6e0c`, files read at `a2c6e0c`. Code has not changed since `bd6ea37`; the later commits change only results and reviews.

## Round 1 fixes

| ID | Status at a2c6e0c | Would a test fail without the fix? |
| --- | --- | --- |
| F31 | Enforced. All four `read()`s go through `transport.guarded()`. Streams maps `TruncatedOffset` to the retained base (streams.py:140-146). | Yes: `test_r2_mid_read`, plus the `SkipsExpiry` validation variant. The new check is weak, see M1. |
| F32 | Clarified in notes.md (no code change). This agrees with D5's wording. | n/a (documentation only) |
| F33 | Enforced in the code: Streams reads only through the poll Update (streams.py:135-151). The module docstring is stale (Nit). | No dedicated test |
| F34 | Enforced. `roll_over` waits for a new RUNNING run_id (streams.py:179-189). `check_r4_roll_over` asserts that the reader did not move. `check_r4_truncating_roll_over` expects `Expired(106)`. | Yes: `NeverRolls` fails both checks |
| F35 | Enforced in the Workflow (`batches=self.batches` is carried across continue-as-new). The check ignores what `roll_over` returns (Nit). | Only if the roll actually happens; there is no validation variant |
| F36 | Enforced: a fixed `QUEUE`, `close()` no longer terminates runs or deletes streams, and runs have a 2 h `RUN_TIMEOUT`. | No test |
| F37 | Partly. The commit and dirty fields are recorded, errors are recorded as `error`, and all four results files exist at `bd6ea37`. Partial-run detection only catches `-k`, `-m` and interrupts. | Reopened in part, see M2 |
| F38 | Enforced: table.py:145 clears the flag before the fetch. | Yes: `test_table_notify` waits about 1 s without the fix |
| F39 | Enforced (conftest.py:66-67). | n/a |
| F40 | Enforced (jetstream.py:110-113). | No test |
| F41 | Enforced (memory.py:73, table.py:173). | No test |
| F42 | Enforced: the `MIN_EVENTS` guard plus an atomic replace. | No test (spike script) |
| F43 | Enforced: removed. | n/a |

Accepted findings F44-F48 were not raised again.

## Findings

### M1 · Major · `check_r2_mid_read` doesn't check that the expiry report names the retained base, and `guarded()` turns any gap into an expiry (R2, R1; new mismatch introduced by the F31 fix)

- **Location:** spikes/event-transport/event_transport/checks.py:121-123; spikes/event-transport/event_transport/transport.py:49-50.
- **Contract:** R2: "it gets an expiry report naming B, then B onwards". R1: a reader "must receive every retained event".
- **Failure scenario:**
  1. A transport's follow reader loses events after a removal during a read. For example, after `expire_below(wf, 50)` it resumes at offset 60: a wrong base from a racing Query, a consumer that skips ahead, or an off-by-N in the `TruncatedOffset` path.
  2. `guarded()` cannot tell this apart from expiry. It yields `Expired(60)` and then 60..110 (transport.py:49-50 names the next delivered offset, not the retained base).
  3. The check only asserts `expiries[0].retained_base >= 6` and that the offsets after it are contiguous, so it passes. Events 50..59 are still retained but are never delivered.
- **Why the loose bound isn't needed:** in this check the base is deterministic at 50 for every implementation. The reader's generator is suspended after offset 5, so nothing beyond offset 5 is buffered when the removal happens. The "already buffered" allowance and the `>= 6` bound therefore hide a real R1/R2 violation.
- **Fairness:** the gap applies to all four options alike, so it doesn't favour one option, but it weakens R2 for every option. R1's and R4's tailers still assert that no `Expired` appears, so those checks are unaffected.
- **Test that would expose it:** a validation variant `ResumesPastBase(MemoryTransport)` that sets `position = log.base + 9` on removal. At a2c6e0c it passes `check_r2_mid_read`. The fix is to assert `expiries == [Expired(50)]` and `after_expiry == list(range(50, 111))`.

### M2 · Major · Reopens F37 in part: a node-ID, `-x` or `--deselect` run overwrites a results file with `"partial": false` and the full-suite command (F37; supports R8 and task 1.4's results files)

- **Location:** spikes/event-transport/tests/conftest.py:89-104.
- **How partial runs are detected:** a run counts as partial only when `config.option.keyword` or `config.option.markexpr` is set, or when `exitstatus not in (0, 1)`.
- **Failure scenario:**
  1. Run `SPIKE_TRANSPORTS=streams pytest tests/test_suite.py::test_r1_resume`. Node IDs are stored in `config.args`, not `keyword`. Or run `pytest -x`, which stops at the first failure with exit status 1.
  2. `results/suite-streams.json` is overwritten. It lists only the requirements that ran, and it says `"partial": false` and `"command": "SPIKE_TRANSPORTS=streams SUITE_HORIZON_S=60 pytest tests/test_suite.py"`.
  3. That command is synthesized at conftest.py:100-101 and claims a full-suite run that never happened.
- **Why it matters:** round 1's F37 is exactly this case ("partial runs overwrite"). Phase 02's R8 depends on these files.
- **Test that would expose it:** none exists for the results writer. Run the suite with a node ID, or with `-x` and a failing check, and assert that `partial` is true. The fix is to derive `partial` from the set of collected requirement tests against the full set (R1, R2, R3, R4, R7 for every option), or from `session.testscollected` against `session.testsfailed` and the deselected count, and to record `sys.argv` as well.

## Nits

- streams.py:6-8: the module docstring still says reads use "the stream's poll Query (catch-up) and poll Update (follow)". Since F33, reads use only the poll Update (streams.py:123-124).
- checks.py:94: `check_r3_resend` ignores what `roll_over` returns. If the Streams roll times out (returns False after about 30 s), R3 still passes without crossing a run, and no `NeverRolls` variant is checked against R3. The F35 check is only as strong as `roll_over`.
- conftest.py:74-75: teardown failures, such as a failing `close()` or worker shutdown, are dropped, so the requirement still reads `pass`.
- results/suite-*.json: all four files have the same `finished` (2026-11-18T04:42:21), which suggests one multi-transport session. Each file nevertheless records `SPIKE_TRANSPORTS=<name>`, so the recorded command is not the one that ran. It is still reproducible.
- transport.py:35-52 (all options alike): if a removal during a non-following read takes everything through the end, no `Expired` is ever yielded, because `guarded()` reports a gap only on the next delivered offset. Following readers report it only when a later event arrives. This is consistent across options, so it is not unfair, but R2's "first get an expiry report" is unmet in that edge case.
- jetstream.py:110-113, memory.py:73, table.py:173: the F40 and F41 fixes have no test that fails without them.
- capture.py:67: F42's guard checks the event count only. A failed turn with 10 or more events still replaces the fixture. This matches the recorded resolution text, but round 1 also raised the case "whatever `result.status` is".
- streams.py:42-44: `RUN_TIMEOUT` (2 h, which bounds the whole continue-as-new chain) and the shared fixed task queue are parameters only Streams has. They were added by the F36 fix but are not listed with the F45 parameters in notes.md#d5 for the report's extra-code and parameter count. They don't affect phase 01.

## R9

`git diff --stat f43c2ff..a2c6e0c -- . ':!spikes' ':!docs'` is empty.

## Fairness summary

Every fix applies to all four options alike: `guarded()` wraps every reader, `roll_over` returns `bool` everywhere, and R3's roll-over is a no-op for options without a Workflow. The extra checks only Streams runs (`check_r4_truncating_roll_over`, and the hosted assertions in `check_r4_roll_over`) cover R4, which D2 counts as N/A for the others. They make Streams harder to pass, not easier, which matches D2 and D5. The table's F38 fix removes a handicap without adding any tuning. I found no fix that favours one option. M1 weakens R2 for every option alike.

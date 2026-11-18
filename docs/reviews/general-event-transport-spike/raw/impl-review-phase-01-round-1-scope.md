<!-- Verbatim subagent report (impl-review phase 01 round 1, scope, f43c2ff..dfc16fd, frozen at dfc16fd); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Event-transport spike, phase 01, impl review round 1: scope lens

Diff: `f43c2ff..dfc16fd` (files read at `dfc16fd`). Contract: plan.md (R1-R4, R7, R9; D1, D2, D4, D5) and phases/01-interface-and-transports.md; notes.md#d1, #d5.

## Findings

### 1. Major: Streams follow readers crash with `TruncatedOffset` when a roll-over truncates past them, and D5's "map `TruncatedOffset` to `Expired`" is not implemented
- **Location:** `spikes/event-transport/event_transport/streams.py:105-132`, `streams.py:79-90` (`_RETRYABLE = {"StreamDraining"}` at :43); `streams_workflow.py:66-69`.
- **Requirement/decision:** D5 (Streams: "Readers ... map `TruncatedOffset` to `Expired` using a spike `retained_base` Query"), R2, R4.
- **Mechanism scope:** the code checks expiry once, at the start of `read()`, by comparing `after` with `retained_base`. D5's roll-over truncates the log to its last 500 events (`streams_workflow.py:66-69`) while follow readers are still running. The mid-read case is not handled. The module docstring (`streams.py:7-8`) says the reader "maps `TruncatedOffset` to `Expired` through the `retained_base` Query", but no code does this.
- **Failure scenario:** a tailer follows from offset 0 and lags more than 500 events, say at stream offset 1,000 while `end` is 1,600 (about 10 s behind at D3's 50 events/s). Roll-over starts: `truncate(1100)` runs, then `detach_pollers()`. The pinned SDK's `_on_poll` wait condition `payload.from_offset < self._base_offset` fires and raises `ApplicationError(type="TruncatedOffset")` (`.venv/.../workflow_streams/_stream.py:404-416`). `_retry` re-raises it because `"TruncatedOffset"` is not in `_RETRYABLE`, so `read()` raises `WorkflowUpdateFailedError`. What should happen is that the tailer gets `Expired(1101)` and then offsets 1101 onwards. R4 says a reader at N during a roll-over "gets N+1 onwards", and R2 says the expiry is reported. Neither holds. Phase 2's load can hit this case, with 3 tailers per agent and one killed and resumed every 60 s.
- **Test that would expose it:** a check that starts a follow reader at offset 3, publishes 600 more events without letting the reader consume them (or with the reader paused), calls `roll_over`, then resumes the reader. Assert that it yields `Expired(base)` and then contiguous offsets, not an exception.

### 2. Major: the suite never exercises Streams' roll-over truncation, or a retained base carried across Continue-As-New
- **Location:** `spikes/event-transport/event_transport/checks.py:99-118` (R4 check, 5+5 events) against `streams_workflow.py:24,66-69` (`KEEP_AT_ROLL = 500`).
- **Requirement/decision:** R4, R2, D5 ("after truncating the log to its last 500 events").
- **Scope gap:** the R4 check publishes 5 events before the roll-over. `keep_from = max(base-1, end-500)` is therefore `0`, and the truncate branch and the carried non-trivial `base` never run. Only `probes/streams_roll_over.py` covers 600 events, `Expired(101)` after CAN and offsets 101-605. That probe is a script, not a suite check. It writes no results file and only reports what it printed, in `probes/README.md`. A bug in the base carry, such as `StreamInput(base=...)` being dropped, would still pass the suite's R4 and R2.
- **Test that would expose it:** an R2 and R4 check that publishes more than 500 events, rolls over, then (a) reads after 0 and expects `Expired(end-499)` and (b) reads after `end-499-1` and expects no expiry.

### 3. Major: the suite's R4 check passes without showing that a roll-over happened while the reader was at N
- **Location:** `spikes/event-transport/event_transport/checks.py:112-118`; `streams.py:152-154` (`roll_over` is a fire-and-forget Signal).
- **Requirement/decision:** R4 ("Given a reader at offset N during a roll-over").
- **Failure scenario:** `roll_over` returns once the Signal is accepted. The publish of `b1` can be handled by the old run in the same activation, and its events are carried into the next run's state. The reader may also receive offsets 6-10 before the CAN, or the roll-over may not happen at all, for example if `wait_condition` never fires. In each case `got == [4..10]` still holds, so R4 is recorded as `pass` even though no reader crossed a run boundary. Nothing in the check compares run IDs. Only the probe does (`probes/streams_roll_over.py:13-17`). I could not verify the real ordering without running it, so this may pass for the right reason. The check simply does not prove it.
- **Test that would expose it:** in the Streams R4 check, record `describe().run_id` before the roll-over, wait until it changes, assert that the reader is still blocked at 5, then publish `b1` and assert `got == [4..10]`.

### 4. Major: R3 dedup across a roll-over is untested, although D5's roll-over interval is shorter than the re-send horizon
- **Location:** `spikes/event-transport/event_transport/checks.py:86-96`; `streams_workflow.py:31,49,75,84-86`.
- **Requirement/decision:** R3, D5 ("the set travels in the Continue-As-New arguments with the stream state").
- **Scope gap:** R3 promises dedup "within the re-send horizon" (600 s). D5 rolls over every 2,000 batches. At D5's 200 ms batching that is about 400 s per workflow, so in production a re-send will often land in a later run than the original. The suite's R3 check never rolls over. The code carries `self.batches` in `StreamInput` (`streams_workflow.py:75`), and that looks right, but no test checks it. This is the plan's open question "Streams does not deduplicate a retried attempt's events".
- **Test that would expose it:** publish `b0`, `roll_over`, wait for the new run, re-send `b0`, and assert `latest == 5`.

### 5. Major: the table reader's NOTIFY wake-up can be lost, so the 1 s poll fallback becomes the delivery path
- **Location:** `spikes/event-transport/event_transport/table.py:131-148`.
- **Requirement/decision:** D5 (table: "`LISTEN/NOTIFY` with a 1 s poll fallback"), with effects on phase 2's R6 and the plan's fairness risk.
- **Failure scenario:** the reader runs `await conn.fetch(...)` (:132). During that await, a publisher commits batch k and its NOTIFY reaches this connection, so `notified` sets `woken` (:118-120). The fetch snapshot was taken before the commit, so batch k is not in `rows`. The reader then runs `woken.clear()` (:146) and waits up to `POLL_S` = 1 s (:148). Batch k is delivered up to about 1 s late. The `notified` callback filters by `workflow_id` and only sets the event, so it cannot prevent this. Under D3's load (about 5 batches/s per agent) the race recurs. It pushes the table's p95 towards the R6 limit in phase 2, so the comparison would measure an implementation artifact rather than the mechanism. The memory reference does not have this problem, because it does not await between its loop and `clear()` (`memory.py:53-59`).
- **Test that would expose it:** a follow reader plus a publisher that sends batches at 200 ms intervals. Assert that every event arrives within, say, 200 ms of its commit. Moving `woken.clear()` before the `fetch` fixes it.

### 6. Major: the results files name commits that do not contain the code that produced them, and no Streams or NATS results file is committed
- **Location:** `spikes/event-transport/tests/conftest.py:71-91`; `results/suite-table.json`; `results/suite-memory.json`.
- **Requirement/decision:** tasks 2.1-2.3 ("Verify: the suite runs against it in a disposable project and its results file is written"), and the conftest docstring's own R8 claim ("with the commit and command that produced them").
- **Evidence:**
  - `suite-table.json` says `"commit": "632ccb22..."`, but `git ls-tree 632ccb2 spikes/event-transport/event_transport` lists no `table.py`. The table transport arrived in `dbf581e`.
  - `suite-memory.json` says `"commit": "7a2e47b..."`, which contains no `checks.py` or `tests/test_suite.py`.
  - The mechanism records `git rev-parse HEAD` at run time, with no dirty-tree check, so it names HEAD rather than the working tree that ran.
  - Neither `results/suite-streams.json` nor `results/suite-nats.json` exists at `dfc16fd`. The Streams and NATS passes are supported only by commit messages ("It passes R1-R4 and R7", "It passes R1-R3 and R7").
- **Failure scenario:** a phase 2 reader traces the table's R1-R7 passes to `632ccb2`, checks out that commit, and cannot reproduce the result, because the transport does not exist there.
- **Test that would expose it:** conftest refuses to write, or marks the result `dirty`, when `git status --porcelain -- spikes/event-transport` is non-empty. A check asserts that `results/suite-{streams,nats}.json` exist.

## Nits
- `streams.py:116-121` — non-follow reads use the poll **Query**, not the poll Update that D5 specifies ("Readers call the stream's poll Update"). The Query silently clamps to the base. A truncation between the `retained_base` pre-check (:108) and the Query gives a silent gap with no `Expired`. This is a narrow race in the suite, and acceptable only if recorded as a D5 deviation.
- `streams.py:107,113-123` — when `latest == 0` the pre-check is skipped and the first poll uses `from_offset=0`. The SDK never raises `TruncatedOffset` for offset 0 (`_stream.py:411`), so a truncation before that first poll gives a silent gap. This is an edge case for tailers that start before any event exists.
- `table.py:111-148`, `jetstream.py:74-111`, `memory.py:53-55` — expiry is checked only at the start of `read()`. If `expire_below` runs during a follow, the table and NATS readers skip to the base silently, and the memory reference raises `KeyError`. Neither option has automatic retention in this spike, so this matters only if phase 2 adds retention.
- `streams_workflow.py:62,90` — `batches_this_run` counts only stored (non-duplicate) `publish_batch` calls. Duplicate Updates, poll Updates and `expire_below` Updates also add history, so "every 2,000 batches" is not a history bound. This matches D5's literal wording, and the effect belongs to phase 2's R5.
- `streams_workflow.py:33` — `StreamInput.batches_this_run` is never set or read; `__init__` resets the counter to 0 (:51). It is dead state in the carried input, though harmless.
- `streams.py:79-90` — `_retry` swallows every `RPCError` (for example NOT_FOUND after `close()` terminates the Workflow) for 200 × 100 ms per call before it raises. Failures surface late. Spike-only.
- `table.py:60` — `max_size=20` per transport. Every follow reader holds a pooled connection for its lifetime, and an abandoned (`return`-ed) async generator releases it only when finalized. D3's 12 tailers plus kill and resume plus 4 publishers could exhaust the pool and block publishers. This is a phase 2 load concern.
- `jetstream.py:100-109` — in a non-follow read, if messages up to `last` are purged after `_state()`, `position` never reaches `last` and the loop fetches every 1 s forever. This is a narrow race, since R2's purge happens before the read.
- `checks.py:121-128` — the R7 fixture has 44 events and `BATCH` is 64, so the recorded turn goes out as one batch and R7 never crosses a batch boundary. R1 covers multi-batch ordering, so the risk is low.
- `conftest.py:84` — the recorded command is rewritten to `SPIKE_TRANSPORTS=<one name>` even when the session ran several transports, and it omits `SUITE_HORIZON_S`. A non-default horizon run is not reproducible from the file (R8, phase 2).
- `conftest.py:71-91` — a filtered run (`-k test_r1`) overwrites `suite-<name>.json` with only the requirements it ran. Nothing marks the file as partial.
- `streams.py:28` — imports the private `temporalio.contrib.workflow_streams._types._decode_payload` from a preview API. It should be counted as extra code or as a fragility in the D6 report.
- Phase task 1.1 asks for "a Compose overlay for a disposable project"; the delivery is an env file (`stack.env`) used with `make up ENV_FILE=...`. This is a wording mismatch only, with the same effect.

## Checked and consistent
- R9: `git diff --stat f43c2ff..dfc16fd -- . ':!spikes' ':!docs'` is empty.
- Dedup scope per option is per workflow: memory per-`_Log`, table `(workflow_id, batch_id)` checked under the counter row's `FOR UPDATE` lock, NATS per stream with `duplicate_window` in seconds (nats-py converts it to ns, `nats/js/api.py:501`), Streams per hosting Workflow and pruned with `workflow.now()`.
- Table offsets are gap-free per workflow: the counter row lock serializes publishers, and a re-send returns before any insert.
- The R3 near-horizon re-send happens at about horizon − 5 s (`checks.py:93`), inside the 60 s suite horizon that D5 allows for every option.
- R2's two scenarios (B−10 with the report, B−1 without) and the four broken-reference validations from task 1.4 are present.

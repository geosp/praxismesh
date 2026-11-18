<!-- Verbatim subagent report (impl-review phase 02 round 1, failure, 5371368..4d6c4ca, frozen at 4d6c4ca); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Event-transport spike, phase 02, impl review round 1: failure lens

Diff reviewed: `5371368..4d6c4ca`. Files were read at the commit named in each citation (`4d6c4ca` unless stated; deleted code at `1bfac67`, the measurement script at `c1fda62`).

## Units traced

- **`load.py` `Agents.publish` (the Activity).** It builds events, awaits `transport.publish` once per batch, heartbeats after each flush, publishes a final batch without a heartbeat, then returns `AgentResult`.
- **`LoadAgentWorkflow.run`.** One `execute_activity` call with no retry policy, a start-to-close timeout of seconds+120 and a 30 s heartbeat timeout.
- **`load.py` `main`.** Builds the transport, connects the client, starts the worker and sampler, starts tailers, runs `start_workflow` ×4, then `await h.result()`. Then: `latest()`, a catch-up of at most 60 s, stop, gather, `transport.close()`, and the results-file write.
- **`tail` / `consume`.** A cancel and restart every 60 s.
- **`measure.sh`.** For c1fda62 and 4d6c4ca.
- **`probes/streams_update_limit.py`** (1bfac67).
- **`check_r1_cancel`.**
- **Helpers read.** `TableTransport.publish/_read`, `guarded`, and Streams `_retry/close` (1bfac67). For asyncpg pool release: `.venv/.../asyncpg/pool.py:271-274` and `connection.py:1615,1783` (`UNLISTEN *`; the listener list is cleared).

## Findings

### F1 · Major · An agent run is never bounded, and orphans survive into the next run (R6, R8; task 1.2)

**Location:**
- `spikes/event-transport/load.py:77-83`: `execute_activity` has no `retry_policy`, so Temporal's default of unlimited attempts applies.
- `load.py:237-247`: `start_workflow` has no `execution_timeout`, and `await h.result()` has no deadline.
- `measure.sh`: no reset between runs.

**Scenario:** this happened at c1fda62 in the growth step, `uv run python load.py streams --no-roll --label growth`.
1. Every hosting run reached Temporal's cap of 2,000 Updates per run (notes.md F47).
2. Streams `_retry` (streams.py@1bfac67, `_retry`) retries only `WorkflowUpdateFailedError` with cause `StreamDraining` or `AcceptedUpdateCompletedWorkflow`, plus RPC timeouts. Any other error fails the Activity.
3. The Activity is then retried forever, so `h.result()` never returns and no `results/load-streams-growth.json` is written.

Evidence that this occurred: that file is not committed, and commit 36ebee0 says the growth was "read from the runs' histories by a new probe" after the run "stalled". I could not confirm which exception the cap raises. If the publish Update instead blocks, the outcome is the same, through the heartbeat timeout.

**What happens next:** after the operator kills `load.py`, the four `SpikeLoadAgent` runs stay Running on `spike76-load`. The next `load.py` on the same stack, for any option, registers a worker on that same queue. That worker picks up the orphaned Activity retries and publishes another ~200 events/s for up to 300 s through the new run's transport. That inflates the database and Temporal CPU samples and the contention behind R6 latency, and nothing in the results file shows it.

**Test:** run `load.py memory --seconds 10` with a transport whose `publish` raises. Assert that the process exits non-zero within a bound, and that no `SpikeLoadAgent` execution is still Running afterwards.

### F2 · Major · The growth results file includes runs left by earlier load runs, and has no provenance (R8; task 1.2 Verify)

**Location:**
- `probes/streams_update_limit.py@1bfac67`, query `WorkflowId STARTS_WITH 'spike76-stream-load-' AND ExecutionStatus = 'Running'`.
- `results/streams-growth-norollover.json`.

**Scenario:** Streams hosting Workflows end only at `RUN_TIMEOUT` (2 h); `close()` leaves them running (streams.py@1bfac67, `close`). The judged runs' last hosting runs (IDs `fb809c98`, `3c994f04` and `5e40dd37`, which are the run1-run3 IDs in `load-streams-run*.json`) were therefore still Running when the probe ran.
- The file holds 16 entries. Only 4 are from the growth run (`e47794c1`).
- The other 12 report 0.01-0.02 min and 18.9-25.8 MB/min.
- Anyone who takes a median or maximum of `mb_per_min` from the file gets about 20 MB/min instead of about 5.5. The report's figures are right only because they were taken from the 4 correct entries by hand.

**Provenance:** the file is a bare list with no `commit` or `command`. Task 1.2's Verify says "each results file names its commit and command". The command committed at c1fda62 (`measure.sh`) does not produce this file. The probe was added in 36ebee0, after the measurement commit, and deleted at 4d6c4ca. The report and notes.md therefore cite a source that is absent at the review head; only `probes/README.md` points to 1bfac67.

**Test:** a check that every file in `results/` has `commit` and `command` keys, and that the growth file's workflow IDs share one load run ID.

## Nits

- **`load.py:122,130`, batch IDs restart per attempt.** `f"{wf}-{out.batches}"` restarts at 0 on each Activity attempt. Within 600 s, the table's dedup (`table.py` `publish`, the `fresh` check) silently drops a retried attempt's new batches, while `out.published` still counts them and only the last attempt's `AgentResult` survives. The measured runs were unaffected: published equals the sum of tailers' `latest` (streams run1: 54,897 = 13,724+13,724+13,725+13,724). It is a Nit because no retry occurred, but the runner would not detect one.
- **`load.py:120-127`, heartbeat only after a flush.** A `publish` blocked for more than 30 s times out the attempt while its coroutine keeps running; the SDK learns of the cancel only at the next heartbeat. A second attempt then publishes concurrently to the same workflow. This combines with the batch-ID Nit above.
- **`load.py:97-128`, closed-loop producer.** The event rate depends on publish latency: Streams runs produced 54.9-55.0k events against the table's 57.8-58.1k, about 5% less load on Streams. D5 says "the same for every option". This is outside the failure lens.
- **`measure.sh`, mixed results after an abort.** `set -eu` aborts on a load failure, after the suite file for `runN` has been overwritten but before the load file has. `results/runN/` then mixes files from different invocations under one label. The per-file `commit` makes this detectable, but nothing checks it.
- **`load.py:334-336`, non-atomic overwrite.** The results file is overwritten in place, so a rerun with the same label silently replaces a committed result, and a kill during the write leaves a truncated file.
- **`load.py:213-261`, no `try/finally`.** On an exception, `transport.close()`, the tailer tasks and the sampler are not cleaned up. Process exit hides this.
- **`event_transport/checks.py` `check_r1_cancel`, can hang instead of failing.** `wait_for(anext(reader), 0.5)` waits for the inner cancel to finish, so a reader that swallows cancellation (the bug fixed in 5ae0731) hangs the test rather than failing it, and `pyproject.toml` configures no pytest-timeout. The later `aclose()` asserts little, because the generator has already finished after the cancel.
- **`docs/spikes/event-transport.md`, Measurements table.** The CPU rows are "run 1" only under a header that says "median of 3 runs", and other rows give no range. R8 says "measurements are reported as median and range".
- **Task 3.1, "reset the disposable projects".** Nothing in the diff shows that the reset happened; I could not verify it.
- **R10 table fencing (report, ADR-0009).** The proposed per-task advisory lock in every 200 ms publish transaction, which already holds the counter row `FOR UPDATE`, was not measured, and its lock order relative to ADR-0007's writers is not stated. It is a Nit because R10 asks only for a statement.
- **Streams hosting runs left during table runs.** Runs from the judged Streams loads stayed Running through later table loads on the same stack (`RUN_TIMEOUT` 2 h). They were idle, so their effect on the table's Temporal CPU figure is probably negligible.

## Checked and found sound

- **Table publish is atomic.** It is one transaction, the batch row is in the same transaction, and `NOTIFY` is delivered on commit. Under READ COMMITTED, the `FOR UPDATE` on the counter serialises concurrent re-sends of a batch.
- **Tailer cancel and resume are correct.** `tailer.last` is updated with no `await` between receiving an event and recording it, so a resume starts at `last` with no gap or repeat. The reader is awaited after the cancel, so its connection goes back to the pool before the restart.
- **A cancel during `add_listener` leaks nothing.** Pool release runs `UNLISTEN *` and clears listeners (asyncpg `pool.py:271-274`, `connection.py:1615,1783`).
- **No ID collisions across runs.** Agent workflow IDs carry a per-run UUID.

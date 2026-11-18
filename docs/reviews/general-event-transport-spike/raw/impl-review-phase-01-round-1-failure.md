<!-- Verbatim subagent report (impl-review phase 01 round 1, failure, f43c2ff..dfc16fd, frozen at dfc16fd); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Event-transport spike, phase 01, implementation review round 1: failure lens

Diff reviewed: `f43c2ff..dfc16fd`. All file:line references are at `dfc16fd`, under `spikes/event-transport/` unless stated otherwise. Library behaviour comes from the pinned sources in `spikes/event-transport/.venv` (temporalio 1.36.0, nats-py 2.17.0).

## Units traced

- **Streams publish** (`streams.py:74-90`): `_handle` → `start_workflow(USE_EXISTING)` once per instance (63-71) → `execute_update(publish_batch)` inside `_retry`. `_retry` makes up to 200 attempts, catches every `RPCError` and every `WorkflowUpdateRPCTimeoutOrCancelledError`, and retries a `WorkflowUpdateFailedError` only when its type is `StreamDraining`. The Workflow side (`streams_workflow.py:81-91`) prunes the batch set, checks it, appends and bumps `end`, all synchronously in one activation.
- **Streams read** (`streams.py:102-132`): `_handle` (which also starts the Workflow) → `latest` Query → `retained_base` Query, checked once → a loop over the poll Query (catch-up) or the poll Update (follow, `start_update` ACCEPTED → `result()`).
- **Streams hosting Workflow** (`streams_workflow.py:57-79`): wait for roll / 2,000 batches / CAN-suggested → truncate to the last 500 → `WorkflowStream.continue_as_new`. That last call is `detach_pollers` → wait `all_handlers_finished` → `continue_as_new(get_state())` (`temporalio/contrib/workflow_streams/_stream.py:332-336`).
- **Table publish** (`table.py:69-103`): one transaction: upsert the counter, take `FOR UPDATE` on it, check the batch's freshness, upsert the batch row, insert the events, update the counter, `pg_notify`. It is atomic; a retry after an ambiguous commit is deduplicated. I found no failure-ordering problem here.
- **Table read** (`table.py:111-151`): acquire a connection → LISTEN → read the bounds once → page loop → wait up to 1 s for a notification.
- **NATS publish** (`jetstream.py:58-65`): `_ensure` (add_stream) → one `js.publish` per event with `Nats-Msg-Id <batch>:<i>`. It is not atomic, but a retry is safe through the message IDs.
- **NATS read** (`jetstream.py:74-111`): `_ensure` (creates the stream) → `stream_info` once → an ephemeral pull consumer from `after+1` → a fetch loop.
- **Suite results** (`tests/conftest.py:54-91`): outcomes are gathered per report and written at `pytest_sessionfinish`.
- **capture.py** (`capture.py:42-69`): container → attempt → run → close → stop → write the fixture.

## Findings

### Major

**F1 · A Streams tailer crashes, instead of getting `Expired`, when the log is truncated under it (R2, D5)**
- Location: `event_transport/streams.py:43,84-86,123` and `streams.py:106-112`.
- What happens: expiry is checked only once, before the loop. In follow mode the poll Update fails with `ApplicationError(type="TruncatedOffset")` when `from_offset != 0 and from_offset < base` (`_stream.py:411-417`). `_retry` re-raises anything not in `_RETRYABLE = {"StreamDraining"}`, so the reader dies with `WorkflowUpdateFailedError`. The module docstring (`streams.py:7-8`) says the reader "maps `TruncatedOffset` to `Expired`", and D5 says readers "map `TruncatedOffset` to `Expired` using a spike `retained_base` Query". The code never does that.
- Scenario: under the D3 load (~50 events/s per agent), the hosting Workflow rolls over and keeps only the last 500 events (`streams_workflow.py:66-69`). A tailer that is more than 500 events (about 10 s) behind when the run continues as new gets `TruncatedOffset` on its next poll and its task raises. The same happens to any follower when `expire_below` runs.
- Two variants that skip silently instead of crashing:
  - A follower that started on an empty workflow (`latest == 0`, so no base check at line 107) still polls from offset 0. `_on_poll` never raises for offset 0, and `_collect_batch` clamps to the base (`_stream.py:411,422`).
  - The catch-up path uses the poll Query, which also clamps (`_stream.py:422`). A truncation between the base check and the first poll, or between pages when `more_ready` is set, drops events without an `Expired`.
- Test that exposes it: start `read(wf, 0, follow=True)` with a consumer that sleeps; publish 600 events; `roll_over`; publish more. Expect `Expired(base)`, then base onwards, and no exception.

**F2 · Streams and NATS `close()` destroys shared data, and a restarted Streams process cannot reach its existing streams (R1, D1)**
- Location: `streams.py:55-57,59-72,156-159`; `jetstream.py:43-56,77,124-127`; the interface docstring at `transport.py:52-53` ("Release connections.").
- What happens:
  - Each `StreamsTransport` runs its own worker on a random task queue (`spike76-streams-<uuid>`).
  - It starts the hosting Workflow on read as well as on publish, with `USE_EXISTING`.
  - On `close()` it terminates every Workflow it touched, including ones it only read.
  - `JetStreamTransport.read` creates the stream (`_ensure`, line 77), and `close()` deletes every stream in `_streams`.
  - The table's `close()` only closes the pool (`table.py:174-175`).
- Scenarios:
  - (a) Process restart. A publisher process dies and restarts with a new instance and a new queue. `USE_EXISTING` attaches to the old run, which sits on a queue no worker polls. Updates are never accepted. `_retry` swallows the RPC timeout or `RPCError` 200 times (`streams.py:81-90`): the call hangs, then raises `TimeoutError`.
  - (b) Two instances, one publishing and one tailing, which is how the phase 2 load (D3: tailers killed and resumed) would likely run. When the tailer's instance closes, it terminates the stream Workflow (Streams) or deletes the stream (NATS). The publisher's next call fails after the retry loop. A later instance that has not cached the ID starts a fresh run with an empty log, so offsets restart at 1. A reader resuming after N then gets nothing, or different events under reused offsets, which breaks R1.
  - (c) `probes/streams_roll_over.py:10` uses the fixed ID `probe-can`. If an earlier run was killed before `finally`, the next run attaches to the orphaned run and hangs.
- Test that exposes it: publish with instance A, read with instance B, close B, publish again with A, then read from 0 with a new instance C. Expect continuous offsets and all events.

**F3 · The R4 check can pass without any read crossing a roll-over (R4)**
- Location: `event_transport/checks.py:112-117`; `streams.py:152-154`.
- What happens: `roll_over` is a fire-and-forget Signal, and the publish of events 6-10 follows at once. If the Signal and the `publish_batch` Update land in the same Workflow task, the Update appends 6-10 to the old run. The parked poll Update's wait condition (`_stream.py:404-410`) then returns them, and the reader has all 7 items before Continue-As-New happens. Nothing asserts that the run changed or that a poll reached the successor run. The check also passes if the roll-over Signal is ignored entirely. The only evidence of a real Continue-As-New is the unasserted probe (`probes/README.md:11`).
- Test that exposes it: in the R4 check for hosted options, wait until `describe().run_id` differs from the first run before publishing; or assert that the reader's post-roll items came from the new run. Validate the check against a variant whose `roll_over` is a no-op.

**F4 · There is no publishing Activity for Streams (D5, task 2.2)**
- Location: `streams.py:74-77`.
- What happens: D5 says "a publishing Activity sends each batch as one Update to the hosting Workflow", and task 2.2 lists "a publishing Activity". The client calls `execute_update` directly; there is no `activity.defn` anywhere in the spike.
- Scenario: the Activity's retry, heartbeat and timeout path is where re-sends come from in production (the re-send horizon is defined as "Streams' default retry duration"). It is never exercised, so the R3 result and phase 2's extra-code count for Streams do not cover the mechanism D5 fixed.
- Test that exposes it: an Activity that publishes a batch and fails after the Update succeeds; its retry must store nothing new.

**F5 · No results files for Streams or NATS; the committed ones come from older commits (tasks 2.2 and 2.3 Verify)**
- Location: `results/` holds only `suite-memory.json` (commit `7a2e47b`) and `suite-table.json` (commit `632ccb2`). Task 2.2 says "Verify: as 2.1", that is, "its results file is written".
- What happens: the commit messages of `9fa1aac` and `dfc16fd` claim that R1-R4 and R7 pass, but no file records it.
- Test that exposes it: run `SPIKE_TRANSPORTS=streams,nats` on `dfc16fd` and commit the outputs.

**F6 · The results file records infrastructure failures as requirement failures, and an interrupted run overwrites a complete file (task 1.4, R8)**
- Location: `tests/conftest.py:63-64,71-91`.
- What happens:
  - A setup failure counts as `fail` for the requirement. If the disposable stack is down, or `option.build` raises (a connect error or a NATS port clash), every requirement of that option reads `"fail"`, which a reader would take as the transport failing.
  - `pytest_sessionfinish` also runs on Ctrl-C and on `-k` subsets, and rewrites `suite-<name>.json` with only the requirements that ran. For example, interrupting during R3's 55 s sleep leaves a file with R1 and R2 only, overwriting the complete one.
- Test that exposes it: run with the stack stopped and check that the file says error rather than fail; run with `-k r1` and check that existing entries are kept or the file is marked partial.

### Nits

- `table.py:124-141`, `jetstream.py:78-107`: the table and NATS readers also check expiry only once. An `expire_below` during a read skips events silently (the table query starts at whatever exists; JetStream jumps to `first_seq`, per `probes/README.md:10`). Nit because only Streams truncates during the planned load.
- `jetstream.py:100-109`: a non-follow read never ends if a purge removes every message through `last` during the read. `position` stays below `last` and each fetch times out.
- `jetstream.py:95,101-104`: with `inactive_threshold=60.0`, a tailer paused for more than 60 s loses its consumer. I could not verify whether the next `fetch` then raises or times out forever (`NatsTimeout` is swallowed), so the tailer may hang silently.
- `jetstream.py:60-65`: a batch is published one message at a time, so readers can see a half-stored batch, and overlapping publishers (attempts) interleave per event rather than per batch. Retries are safe through the message IDs; this matters for the R10 statement.
- `jetstream.py:81`: the base for an empty, purged stream is taken as `last+1`. If `purge(seq>last)` moves `first_seq` to `seq` (unverified), later offsets jump past `last+1`, which breaks gap-free offsets.
- `table.py:165-169`, `memory.py:69` against `streams_workflow.py:97`: `expire_below` past the end sets the base above `next_offset` in the table and memory transports. Events published later below that base are stored but never read. Streams caps the base at `end+1`, so the hook's meaning differs between options.
- `streams.py:87-88`: `_retry` swallows every `RPCError`, including not-found for a terminated Workflow, and hides real errors for 200 attempts.
- `streams.py:63-71`: the `_started` cache is never cleared, so an instance never restarts a terminated hosting Workflow.
- `streams.py:49,161`: if `worker.run()` fails, nothing reports it until `close()`; meanwhile every publish hangs in `_retry`.
- `streams_workflow.py:57-79`: hosting Workflows have no run timeout. A killed suite or probe leaves them running on a dead queue until `make reset`.
- `table.py:60,114`: each follow reader holds a pool connection for its whole life (pool max 20), and `pool.acquire()` in `publish` has no timeout. 12 tailers plus abandoned generators can block publishers in phase 2.
- `table.py:149-151`: `remove_listener` on a broken connection can raise in `finally` and hide the original error.
- `table.py:88-93`: batch rows are never pruned. Harmless for the spike.
- `tests/conftest.py:74-76`: the recorded commit does not say whether the working tree was dirty (R8).
- `tests/conftest.py:65`: R4 becomes `n/a` only when it passes. A non-hosted option that fails the R4 check is recorded as `fail`, although D2 says such an option counts as N/A.
- `tests/conftest.py:78-79`: overlapping suite runs both write the same results file, and the last one wins.
- `checks.py:55-62`: the R1 "kill" leaves the generator instead of cancelling it, so the follow readers' cancellation and `finally` paths are untested.
- `checks.py:86-96`, `streams_workflow.py:70-77`: no check re-sends a batch after a roll-over, so carrying the batch-ID set across Continue-As-New (D5) is untested.
- `capture.py:66-67`: the fixture is written in place, whatever `result.status` is. A failed re-run overwrites the committed fixture with a failed turn's events.
- `probes/jetstream_start_below_base.py:14`: the stream name `probe-expiry` is fixed. After a killed run, the stream persists in the NATS volume and the next run's printed counts differ.
- `streams_workflow.py:33,112`: `StreamInput.batches_this_run` and `ROLL_TIMEOUT` are unused.
- `temporalio/api/enums/v1/workflow_pb2.pyi:589`: Temporal counts completed and in-flight Updates per run (`TOO_MANY_UPDATES`), and poll Updates count too. Roll-over may be driven by update count rather than the 2,000-batch rule, and notes.md#verified does not record that limit. I did not verify the default.
- Task 1.1: the "Compose overlay" is an env file (`stack.env`) used through `make ENV_FILE=…`, not an overlay. It is functionally equivalent and acceptable.
- R9: the diff touches only `spikes/` and `docs/`. No finding.

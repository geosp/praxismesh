<!-- Verbatim subagent report (impl-review phase 01 round 1, contract, f43c2ff..dfc16fd, frozen at dfc16fd); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# Contract review: event-transport spike, phase 01 (f43c2ff..dfc16fd)

Lens: does the code keep every promise (R1, R2, R3, R4, R7, R9; D1-D5; tasks 1.1-2.3)? Files were read at dfc16fd. Paths are relative to `spikes/event-transport/` unless stated. Library behaviour was checked in the pinned `.venv` (temporalio 1.36.0 `contrib/workflow_streams/_stream.py`, nats-py 2.17.0).

## Promise map

| Promise | Enforcing code | Test that would fail without it |
| --- | --- | --- |
| R1 resume after N, in order, no repeat | memory.py:51-55; table.py:130-141; streams.py:113-126; jetstream.py:88-107 | checks.py:48-68 via test_suite.py:20; validated by test_suite_validation.py:66-68 |
| R2 scenario 1 (Expired(B) then B..) | transport.py:27-32 (`expiry_for`), called at memory.py:47, table.py:124-129, streams.py:106-112, jetstream.py:78-85 | checks.py:77-80; validated by SkipsExpiry (test_suite_validation.py:69) |
| R2 scenario 2 (after B-1: no report) | transport.py:30 (`after < base - 1`) | checks.py:81-83 (no negative validation variant) |
| R3 re-send stored once (immediate, near horizon) | memory.py:33-37; table.py:79-93 (same txn, counter row lock); streams_workflow.py:83-91; jetstream.py:52,64 (Msg-Id `<batch>:<i>`, window = horizon) | checks.py:86-96; validated by StoresResentTwice |
| R4 offsets continuous across roll-over | streams_workflow.py:57-79 (truncate to last 500, CAN with state, batches, base); streams.py:79-90 (retry on StreamDraining) | checks.py:99-118 -- but see F4: it passes with a no-op roll-over |
| R7 recorded turn replays exactly | all `publish`/`read` | checks.py:121-128; DropsEvent validation; fixture tests test_fixture.py |
| R9 diff inside spikes/ and docs/ | n/a (process) | none automated; `git diff --stat f43c2ff..dfc16fd` touches only `spikes/` and `docs/` (confirmed) |
| D1 interface, Expired, hooks, AgentEvent copy | transport.py:17-53; models.py | test_models.py:23 (field names only) |
| D2 R4 N/A for non-Workflow options | tests/conftest.py:65-66 | none |
| D4 isolated uv project, disposable stack, NATS by digest | pyproject.toml, stack.env, nats.compose.yml:7 | none (process) |
| D5 Streams: publishing Activity -> `publish_batch` Update | **missing** (F1) | none |
| D5 Streams: readers use poll Update; map TruncatedOffset to Expired | **partial** (F2, F3) | none |
| D5 Streams: roll-over on suggestion / 2,000 batches, keep 500 | streams_workflow.py:59-69 | probes/streams_roll_over.py (manual, not a test) |
| D5 Streams: batch-ID set travels in CAN args | streams_workflow.py:74-76 | none (F5) |
| D5 Table: table, counter row, batch row same txn, NOTIFY per batch, 1 s poll | table.py:32-103, 147-148 | none beyond suite |
| D5 NATS: stream per workflow, msg per event, Msg-Id, window, file, 1 replica, pull by start seq, first_seq for expiry | jetstream.py:43-111 | none beyond suite |
| Tasks 2.2 / 2.3 Verify: "the suite runs against it ... and its results file is written" | **missing** (F6) | n/a |

## Findings

### F1 · Major · D5, task 2.2 · No publishing Activity for Streams
- Location: event_transport/streams.py:74-77; whole diff (`git grep -i activit` finds only capture.py imports of `harness_activity`).
- Contract: D5 "a publishing Activity sends each batch as one Update to the hosting Workflow"; notes.md#d5 "the publishing Activity sends one `publish_batch(batch_id, events)` Update per batch"; task 2.2 lists "a publishing Activity". The task is checked off.
- Failure scenario: Phase 2 runs R6 (latency) and R5 (history) through `StreamsTransport.publish`, which calls `handle.execute_update` straight from the test process. The real path (agent Workflow -> Activity -> Update) adds an Activity schedule/start/complete round trip and history events per batch on the agent's Workflow. Streams is measured without that cost, favouring it on R6 and hiding a history cost the plan fixed as part of the mechanism.
- Test that would expose it: a test that publishes through the Activity (a worker registering it, a small caller Workflow) and asserts the events arrive; or simply a grep-level check that task 2.2's named component exists.

### F2 · Major · D5, R2, R1 · `TruncatedOffset` is never mapped to `Expired`; a lagging Streams tailer crashes after a roll-over
- Location: streams.py:79-90 (`_retry` re-raises any `WorkflowUpdateFailedError` whose cause type is not `StreamDraining`), streams.py:122-123 (follow path), streams_workflow.py:66-69 (roll-over truncates to the last 500).
- Contract: notes.md#d5 "Readers ... map `TruncatedOffset` to `Expired` using a spike `retained_base` Query". R2: "the reader must first get an expiry report naming the retained base".
- Library evidence: `_stream.py` `_on_poll` raises `ApplicationError(type="TruncatedOffset")` for a nonzero `from_offset` below the base.
- Failure scenario: tailer following workflow W at stream offset 1,000; publishers add 600 events, then the 2,000-batch or suggested roll-over truncates to the last 500 (base > 1,000). The tailer's next poll Update fails with cause type `TruncatedOffset`; `_retry` raises; `read()` ends with an exception instead of yielding `Expired(base)` then base onward. Under D5's roll-over policy this is routine for any slow tailer, not a test-hook edge case.
- The expiry check exists only at the start of `read` (streams.py:106-112). The same start-only pattern holds for the table (table.py:124-129), NATS (jetstream.py:78-85; the probe shows the consumer silently skips to `first_seq`) and memory; truncation during a read gives a silent gap in those three. That is out of the suite's reach today (only the test hook truncates them), but R2 is a universal claim ("when an event after the requested offset is no longer retained").
- Test that would expose it: start a follow reader at 0, stop consuming after offset 5, `expire_below(wf, 20)` (or roll over with >500 events), resume consuming; expect `Expired(20)` then 20 onward. All four options should run it.

### F3 · Major · D5, fairness · Streams catch-up reads use the poll Query, not the poll Update; truncation there is silent, and the suite never exercises the Update path for R1/R2/R7
- Location: streams.py:116-121 (non-follow uses `handle.query("__temporal_workflow_stream_poll", ...)`).
- Contract: D5 "Readers call the stream's poll Update directly"; notes.md#d5 "Readers call the stream's poll Update by Workflow ID".
- Library evidence: `_stream.py` `truncate` docstring: "poll updates requesting a nonzero offset before the new base receive an ApplicationError. Poll queries read from the retained base instead."
- Failure scenarios: (a) a catch-up read where a roll-over truncation lands between the `retained_base` Query (streams.py:108) and the poll Query gets a silent jump to the new base with no `Expired`, breaking R1/R2. (b) Queries write no history while accepted Updates do, so any catch-up read in Phase 2's R5 measurement is cheaper for Streams than the plan's fixed mechanism. (c) In the suite, R1's resumed read (checks.py:65), both R2 reads (checks.py:77, 81), R3's and R4's final reads and R7's read-back all call `read(..., follow=False)`, so for Streams only R1's first tail and R4's tail touch the Update path that D5 chose.
- Test that would expose it: run the R1/R2/R7 checks with `follow=True` readers (stopping at `latest`), or make the Streams non-follow path use the Update and compare.

### F4 · Major · R4 (observability) · The R4 check passes when `roll_over` does nothing
- Location: checks.py:99-118; memory.py:71-72 (no-op) passes it (results/suite-memory.json R4 "pass" before mapping to n/a).
- Failure scenario: if `StreamsTransport.roll_over` dropped the Signal, or the Workflow processed the Signal and the `publish_batch` Update in one activation so the new events were appended before CAN, the check still sees offsets 4..10 and passes. It never asserts that the run changed, that the reader was waiting when CAN happened, or that events published after the new run started were read. The run-ID check exists only in probes/streams_roll_over.py:12-17, which is manual and not part of the results file. With 5 events the roll-over truncation (keep 500) is never exercised in the suite either.
- Test that would expose it: in the Streams case, record `describe().run_id` before and after `roll_over`, wait until it differs before publishing batch b1, and publish more than 500 events first so the reader at N is inside the kept window across a truncating roll-over.

### F5 · Major · R3 + D5 (observability) · R3 never crosses a roll-over, so the batch-ID set "travels in the Continue-As-New arguments" is untested
- Location: checks.py:86-96 (no roll-over); streams_workflow.py:74-76 carries `batches=self.batches`.
- Contract: notes.md#d5 "the set travels in the Continue-As-New arguments with the stream state"; R3 "A batch re-sent with the same batch ID within the re-send horizon must not create a second copy".
- Failure scenario: delete `batches=self.batches` from the CAN input; batch b0 published, roll-over, b0 re-sent 10 s later: the new run has an empty set and stores b0 twice. The suite still reports R3 pass for Streams. This is the Streams-specific R3 risk the plan names ("Streams does not deduplicate a retried attempt's events").
- Test that would expose it: R3 variant: publish b0, `roll_over`, wait for the new run, re-send b0, assert `latest == 5`. N/A-safe for the other options (roll_over is a no-op).

### F6 · Major · tasks 2.2, 2.3 · No suite results for Streams or NATS, yet both tasks are checked off
- Location: `git ls-tree dfc16fd spikes/event-transport/results` lists only suite-memory.json and suite-table.json; docs/plans/.../phases/01-interface-and-transports.md tasks 2.2, 2.3 are `[x]`; plan.md phase table "7/7".
- Contract: task 2.2 "Verify: as 2.1" = "the suite runs against it in a disposable project and its results file is written"; task 2.3 same, plus the R9 diff check. Phase goal: "one shared suite reports R1-R4 and R7 for each".
- Failure scenario: a reader of the phase cannot tell whether Streams passes R1-R4/R7 (the whole spike's primary question, D2) or whether NATS ran at all; the probes README records observations, but not suite outcomes. F2-F5 behaviours (e.g. in-flight poll Update during CAN, streams.py:87-88) are unverified.
- Test that would expose it: `SPIKE_TRANSPORTS=streams,nats uv run pytest tests/test_suite.py` on the stack and commit the two results files.

### F7 · Major · results provenance (task 2.1 evidence; feeds R8) · Results files name commits that cannot have produced them
- Location: results/suite-memory.json:3 names `7a2e47b`, whose tree has no checks.py, test_suite.py or conftest.py (they arrive in 632ccb2); results/suite-table.json:3 names `632ccb2`, whose tree has no table.py (added in dbf581e). tests/conftest.py:74-76 records `git rev-parse HEAD` with no dirty-tree check.
- Failure scenario: Phase 2 re-runs "its commands ... on its commit" (R8) from these files and gets a different suite (or an `OPTIONS["table"]` ImportError). The recorded commit is not evidence for the recorded outcome. `command` (conftest.py:84) also embeds an absolute local venv path, and always prefixes `SPIKE_TRANSPORTS=<one name>` even when the run used a list.
- Test that would expose it: have conftest refuse to write (or flag `"dirty": true`) when `git status --porcelain -- spikes/event-transport` is non-empty; re-run on a clean checkout.

### F8 · Major · fairness (D5 table, Phase 2 R6) · The table reader can lose a NOTIFY and wait the full 1 s poll
- Location: table.py:131-148: `fetch` (await) -> yield rows -> `woken.clear()` -> wait.
- Failure scenario: tailer fetches rows up to offset 100; while the fetch is in flight or while the consumer handles the yielded rows, a publisher commits batch 101-140 and the NOTIFY sets `woken`; the reader then calls `woken.clear()` and waits up to `POLL_S` = 1 s before it sees 101-140. With 200 ms publishing under load this happens often, pushing table p95 toward 1 s and handicapping the table on R6 against Streams (long-poll Update) and NATS (long-poll fetch). Memory avoids it because it re-checks `next_offset` after its yields with no await before `clear()` (memory.py:53-58).
- Fix direction: clear before the fetch. Test that would expose it: a follow reader that sleeps in its consumer while a batch is published, asserting arrival well under 1 s.

## Nits

- tests/conftest.py:63-66 · R4 becomes "n/a" only when the non-hosted run *passes*; a failure is recorded as "fail" though D2 says an N/A requirement "counts as passed". The check is still meaningful as a follow test, so this may be intended, but Phase 2 could count it against table or NATS.
- tests/conftest.py:63 · A setup failure (stack down, connect error) is recorded as a requirement "fail" rather than an error, so infrastructure faults look like transport results.
- tests/conftest.py:71-91 · A partial run (`-k r1`) overwrites the results file with only the requirements it ran.
- transport.py:39, 52 · `read` gains a `follow` keyword and the protocol gains `close()`; neither is in D1's signature. The additions are additive and used uniformly.
- models.py:38 · `blob_ref` is `dict | None`, not `BlobRef | None`; the base class is pydantic `BaseModel` with its own config, not `Strict`. test_models.py:24 compares field names only, as notes.md#d1 asks, so type drift goes undetected.
- checks.py:55-62 · R1's "killed" tailer stops cleanly between items; no test cancels a tailer with a poll in flight (relevant to the Streams Update and the table connection).
- checks.py:71-83 · R2 does not cover "everything expired" (base > latest), where the four options compute the base differently (jetstream.py:81 `last + 1`, streams_workflow.py:97 `min(offset, end + 1)`, table/memory use the hook's offset unclamped).
- streams.py:28 · Imports the private `temporalio.contrib.workflow_streams._types._decode_payload` from a preview API; Phase 2's port should note it.
- streams_workflow.py:33, 112 · `StreamInput.batches_this_run` and `ROLL_TIMEOUT` are unused.
- table.py:60 · Pool `max_size=20` is an unfixed parameter; with 12 follow tailers each holding a connection, plus killed tailers that hold theirs until GC finalizes the generator, publishers could block under D3's load. Note it in the extra-code/operating-cost section.
- jetstream.py:95 · `inactive_threshold=60.0` is a parameter D5 does not list (harmless cleanup).
- nats.compose.yml:13 · The healthcheck (`nats-server --help`) does not probe readiness or JetStream; the digest was not verified in this review.
- tests/test_fixture.py:25-29 · The "no prompt text or credentials" check covers `payload` only, not the other string fields (these are fixed IDs in the committed fixture, so it is fine today).
- R9 · Holds for the frozen range (only `spikes/` and `docs/` changed), but the phase records no output of the task 2.3 R9 command.

## Fairness summary

The shared suite treats every option the same: same checks, a fresh workflow per check, the same 60 s R3 horizon (conftest.py:38-39) and batch size 64. The deviations that could tilt Phase 2 are: F1 and F3 (Streams measured without its fixed publishing Activity, and with Query catch-up reads that write no history: these favour Streams on R6/R5), F8 (the table loses wake-ups: this handicaps the table on R6), and the D2 N/A mapping nit (could handicap table or NATS). F2, F4 and F5 are cases where Streams' riskiest behaviours (truncation under roll-over, dedup across roll-over) are not observed by the suite, so a Streams "pass" would carry less weight than the table's.

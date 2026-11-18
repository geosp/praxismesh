<!-- Verbatim subagent report (events plan impl-review round 1, scope and composition, diff 41c0bcf..c7dcbcd; retry: the first scope subagent returned without reviewing and is not counted); reviewers: fresh-subagent (impl-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

## Scope review: phase 01 of the Phase 2 agent-events plan (diff 41c0bcf..c7dcbcd)

I found 3 Major issues and 9 Nits. The fence, the batch dedupe, the gap-free offsets, the reader rule and the 64/200 ms triggers all hold at the per-workflow and per-attempt scope the plan promises. The problems are where two mechanisms meet: the publisher's `closed` flag and the shielded close, where the attempt's event stream starts, and the 10 s close bound, which no test covers.

### Major

**M1. When the final flush times out, the second close replaces `EventsUnavailable` with `CancelledError`.** Concerns R8 and D2 ("on a database error raise a retryable error").
- **Location:** `harness_activity/events.py` (`close()` timeout branch and the `closed` property); `harness_activity/activity.py` (`_finish`, and the `except BaseException` block in `_attempt`).
- **How it happens:**
  - `close()` on timeout runs `self.task.cancel()` and returns the error. `closed` is `self.task.done()`, which stays False until the event loop runs the cancellation.
  - `_finish` then raises `EventsUnavailable`. It reaches the `except BaseException` in `_attempt` without any await in between, so `publisher.closed` is still False.
  - The handler emits a second `status` event and calls `close()` again. That call runs `await asyncio.shield(self.task)` on a task that is now cancelled. `shield` cancels its outer future when the inner task is cancelled, so `close()` raises `CancelledError`.
  - That `CancelledError` leaves the except block before `raise`. The original `EventsUnavailable` is lost, the "attempt events not stored" warning is never logged, and Temporal receives a `CancelledError` nobody requested.
- **Failure scenario:** the database hangs (for example, a network partition) during the final flush of a successful turn, and the publish blocks for more than 10 s.
- **Uncertainty:** I did not verify how Temporal classifies an unrequested `CancelledError`. It is probably still a retryable failure, but under the wrong type.
- **Test that would expose it:** a fake transport whose `publish` sleeps longer than the close bound, run through `run_harness_turn`. Assert that the error raised is `EventsUnavailable`, and that only one `status` event was emitted.

**M2. An attempt that fails before `_run` stores a `status` event with no `reset` before it.** Concerns R9 ("An attempt's first event is a `reset`") and D3.
- **Location:** `harness_activity/activity.py`. The publisher is created in `_attempt`, but `reset` is emitted only inside `_run`, after:
  - `self._open(...)`, which is the DSH `open_attempt` and also `_charge`;
  - `registry.templates[...]` and `build_config(...)`;
  - `self.checkpoints.latest(...)`.
- **Failure scenario:** the DSH launcher fails in `open_attempt`, or `build_config` or `checkpoints.latest` raises. The except path emits `status` (seq 0) and flushes it, so `tail` shows that attempt as `status failed` with no `reset`. A reader cannot see where the attempt starts or what it restored from.
- **Test that would expose it:** an integration test with `open_attempt` raising, which asserts `events[0].type == "reset"`.

**M3. The 10 s bound on `close()` and its timeout branch are untested at any scope.** Concerns task 2.1 ("a shielded `close()` bounded by 10 s"), R8 and D2.
- **Location:** `tests/test_event_publisher.py`. The only cancellation test, `test_close_completes_when_its_caller_is_cancelled`, uses a publish that takes 0.3 s.
- **What is missing:** no test lets a publish outlive the bound, or checks the timeout return value, the cancellation of the background task, or the follow-on `_attempt` except path. The case where the activity itself was cancelled first and then runs `close()` is also missing; the existing test cancels only the caller of `close()`.
- **Test that would expose it:** a `close(timeout_s=0.1)` over a hanging publish. Assert the return value, that `p.task` ends, and that no further publish happens. Then the M1 integration test.

### Nits
- **N1. Backoff budget is reset per drain** (`harness_activity/events.py`, `_drain`/`_run`): every trigger re-runs the full 0.25/0.5/1 s series. The plan says "backoff ... then at each later trigger", i.e. one try per trigger after the three backoffs. Re-sends happen more often than specified.
- **N2. Leftover events get a fresh 200 ms timer** (`harness_activity/events.py`, `_cut`): `self.oldest` is reset to `time.monotonic()` for events left after a 64-cut, not to the time of the oldest leftover event. Leftovers can wait up to 200 ms longer than R7's "200 ms after the oldest unpublished event".
- **N3. A close during a drain backoff gets no fresh re-send cycle** (`_run`: `if self.closing and (self.error is not None ...): return`): a brief database blip that ends just after the drain's last try fails the attempt retryably, even though up to 10 s of close budget was left.
- **N4. The re-send window is unbounded but dedupe is 600 s** (`events.py`, `TableTransport.publish`): while the attempt runs, a pending batch is re-sent indefinitely. A re-send more than 600 s after a lost-reply commit deletes its own `event_batches` row, then stores the events again. This is outside R1's stated "within 600 s", but nothing stops re-sending at the horizon.
- **N5. Tool-event correlation is keyed per tool name, not per call** (`harness_activity/runner.py`, `_Hooks.calls`): with parallel calls to the same tool, the `tool_result` events carry the wrong `call` number, then None. `test_tool_and_token_events` covers only sequential, distinct calls.
- **N6. Refused tools emit no events in `openai_agents`** (`harness_activity/runner.py`, `on_llm_end`): DSH emits `tool_call`/`tool_result status=refused` for them, so the two runners' D3 streams differ.
- **N7. `tail` stops on a transient Temporal error** (`orchestrator/cli.py`, `tail.closed`: `except Exception: return True`): any describe failure, including a transient one, counts as "closed", so a live follow ends early. D5 promises it stops only once the Workflow has closed.
- **N8. `tail` can print `Expired` twice** (`orchestrator/cli.py`, `print_events`): `last` is not advanced after an `Expired`. If the follower is cancelled between the `Expired` and the next event, the final read prints the `Expired` line again.
- **N9. Several properties are tested only at a smaller scope:**
  - R1's "two attempts each emitting, offsets 1..N" is only a memory-transport unit test (`test_batch_ids_name_the_attempt`). The integration test `test_a_retried_attempt_resets_from_its_checkpoint` has attempt 1 emit nothing.
  - Task 3.2 tests prune through `MemoryTransport.prune`, not the CLI `prune` command or the table.
  - The task 2.3 benchmark uses one task per agent with no concurrent same-task fenced writers, so it does not measure the per-task lock contention named in the Risks.
  - The second `status` event in the cancel-during-`_finish` path (same `closed`-flag cause as M1) is untested, and may be stored or silently dropped.

### Checked and found sound
- **Fence:** task lock, then the newer-attempt check, then the `event_logs` row lock; prune takes only the row lock. The 200-iteration deadlock test is present.
- **Dedupe and cleanup:** per-workflow batch rows with per-publish cleanup.
- **Gap-free offsets:** guaranteed by the row lock held until commit.
- **Reader rule:** `guarded` is applied by both transports, the NOTIFY clear-before-fetch is in place, and the cancelled-follower fix is tested.
- **Batch IDs:** they name the attempt.
- **Ordering:** one background task keeps batches in order, so offsets follow `seq` within an attempt.
- **R5:** a refused final flush makes no finish writes on both paths, and both are tested.
- **Failure path:** the flush runs before `_runner_failed` writes the outcome.
- **Timeouts:** `asyncio.timeout` on 3.11.17 handles the already-cancelled case correctly.

Files: /home/geo/develop/praxismesh/harness_activity/events.py, /home/geo/develop/praxismesh/harness_activity/activity.py, /home/geo/develop/praxismesh/harness_activity/runner.py, /home/geo/develop/praxismesh/common/events/table.py, /home/geo/develop/praxismesh/orchestrator/cli.py, /home/geo/develop/praxismesh/tests/test_event_publisher.py, /home/geo/develop/praxismesh/tests/integration/test_harness_activity.py, /home/geo/develop/praxismesh/tests/benchmarks/event_load.py

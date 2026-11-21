<!-- Verbatim reviewer report (Phase 3A persistence plan, phase 02 impl-review round 1, contract lens, diff 9a81933..8012f6b); reviewers: fresh-subagent (impl-reviewer). save-report refused (the report arrived as the agent's hand-back message, not as its transcript result), so the coordinator re-typed it from that message per the impl-review skill. -->

## Phase 02 review (contract lens): 9a81933..8012f6b

I found 5 Major findings and a set of Nits. Two of the Majors break R25, one can permanently stop every removal command, and two are drift or coverage gaps. The core engine order (D6), revive (D10), the run lock (D4), shared-blob safety (R3), the request lock with its fixed task list (R24), the kill/rerun behaviour (R13, R15) and the dry runs match the contract, and each has a test that would fail without the code.

### Promise to code to test (summary)

| Promise | Enforced at | Test that would fail without it |
|---|---|---|
| R3: shared blob kept | `removal.py:303-335` (`_mark_free_blobs`: no live ref) | `test_removal_engine.py:71`, `test_request_delete.py:270` |
| R6: expired removed | `lifecycle.py:398-473` | `test_gc.py:96` (checkpoints, late upload, refs); other tables: see M4 |
| R7: not expired kept | `lifecycle.py:257-269`, `refs.py:298-320`, `lifecycle.py:462` | `test_gc.py:96`, `:255`, `:181` |
| R8: orphan window | `lifecycle.py:476-489`, `removal.py:337-363` | `test_gc.py:240` |
| R9: expired read | `repositories.py:738-760`, `cli.py:135` | `test_blob_expired.py:41`, `:55` |
| R10, R11: delete and redact | `lifecycle.py:574-774` | `test_request_delete.py:150` |
| R12: refuse unended | `lifecycle.py:596-601` | `test_request_delete.py:236` |
| R13: tombstone per batch | `removal.py:255-262` | `test_request_delete.py:217-225`, `test_removal_kills.py` |
| R15: safe rerun | `removal.py:227-232`, `:383-402` | `test_removal_engine.py:130`, `:160`, `test_removal_kills.py` |
| R21: `--force` | `lifecycle.py:602-607` | `test_request_delete.py:251` (fake Temporal only) |
| R22: revive | `repositories.py:662-736` (phase 01 code) | `test_revive.py` |
| R24: fixed task list | `lifecycle.py:595`, `repositories.py:62` | `test_request_delete.py:337` |
| R25: no later writes | `lifecycle.py:620-639`, `refs.delete_mark` | `test_request_delete.py:291` (checkpoint, event and upload only; see M1, M2) |
| D4: run lock | `removal.py:65-85` | `test_event_prune.py:184` |
| D11: events only through prune | `table.py:238` is the only `DELETE FROM agent_events` | `test_event_prune.py` |

### Major

**M1. R25 and R11: some attempt writes are not fenced.**
- **Where:** `harness_activity/session_store.py:49-51` and `sample_mcp/server.py:95-121`.
- **What R25 promises:** "no attempt of its tasks may write a row". D12 adds that the fencing row makes "ADR-0007's fence refuse any later write by a running attempt".
- **What the fence covers:** only checkpoints, events, messages, usage and `start` (`NO_NEWER_ATTEMPT` users: `repositories.py:173,230,297,418,535`, `table.py:67`, `messages.py:376`).
- **What gets past it:** two writers never check it:
  - the openai_agents `SQLAlchemySession`, which writes `agent_messages`;
  - `sample_mcp.record_order`, which writes `idempotency_keys` and `sample_orders`.
- **Failure:** a `--force` delete runs while an openai-profile Activity is still running (the R25 scenario). The delete redacts `agent_messages`, then the SDK appends new conversation items with plain-text content to the same session. A `record_order` call likewise inserts new order and result rows after the delete. Those rows stay until gc, 30 or 90 days after the forced `ended_at`.
- **Docs:** the runbook narrows the promise to "checkpoint, event or message" (`runbook.md` "Removing data"), so the docs and R25 disagree.
- **Test that would expose it:** in `test_a_late_attempt_of_a_deleted_task_writes_nothing`, after the delete, append through `SQLAlchemySessionStore(task_id, engine).session.add_items(...)` and through `record_order`, then assert no new unredacted rows.

**M2. R25 and D12: the fencing row does not fence an attempt of the next turn.**
- **Where:** `lifecycle.py:621-627`. The fence row is `(max(turn)+1, attempt 1)`.
- **Why it leaks:**
  - `NO_NEWER_ATTEMPT` (`fence.py:30-33`) refuses only when a row has a higher turn, or the same turn with a higher attempt.
  - `AttemptRepository.start` (`repositories.py:167-198`) therefore accepts `(T+1, 1)`. It hits `ON CONFLICT ... DO UPDATE SET worker_identity`, which overwrites the fence row's worker. The same goes for `(T+1, 2+)`.
- **Failure:** an Activity task dispatched before the Workflow was terminated, whose `start()` runs after the `--force` delete, gets turn T+1 and passes every fenced write. That is the checkpoint, event publish and messages.
- **Fix direction:** use a turn that cannot be reached (for example `2**31-1`), or have `start` refuse a task that has a `deleted` row.
- **Test:** after a forced delete, call `AttemptRepository.start(task, T+1, 1, ...)` and then `insert_fenced` at `(T+1, 1)`. Both should be refused.

**M3. R8, R15 and D6: a bucket object whose key is not a content key stops every removal command for good.**
- **Where:** `removal.py:345-350` inserts a `blob_objects` row for any listed orphan key, with `checksum = 'sha256:' || substr(k, 8)`.
- **Why it fails:**
  - `blob_objects.checksum` has no check constraint (`0003_phase1_tables.py:101-108`), so the orphan batch commits.
  - `_bucket_step` then builds a `BlobRef` (`removal.py:410-419`), whose `checksum` must match `^sha256:[0-9a-f]{64}$` (`common/schemas/blob.py:17`). That raises a pydantic ValidationError.
  - The row keeps `removed_at` set and `bucket_deleted_at` null, so every later `gc`, `request delete` and `events prune` fails the same way in `finish_pending()` (`removal.py:227`).
- **Failure:** any object such as `tmp/x` or `notes.txt` in the bucket, older than 24 hours, ends removals until someone repairs the database by hand.
- **Existing code already handles this:** `refs.reindex` (`refs.py:369-372`, `_CONTENT_KEY`) skips non-content keys ("reported as an orphan, never recorded"). That is the drift between the two copies of the same logic.
- **Test:** put a stray object under a non-content key with an old `LastModified` into `MemoryBlobStore.objects`, then run `gc` twice.

**M4. R6: half of gc's row rules and its event expiry are never exercised by a gc test.**
- **What is untested:** `ROW_RULES` (`lifecycle.py:227-245`) for `agent_messages`, `agent_sessions`, `task_messages` (including the `extra` SQL for the recipient's end), `task_inbox`, `idempotency_keys` and `sample_orders`. Step 2 (`lifecycle.py:411-439`), the 30-day event prune, is also untested.
- **Why:** no test creates those rows for an expired task. `ancient` (`test_gc.py:106`) and `stored_task` (`test_removal_kills.py:50`) have no events or content rows. `test_gc.py:181` only checks that events are *kept* at 2 days.
- **Failure:** a wrong column in a rule, or a bad `:life`/`:now` binding in the `task_messages` extra, would leave rows forever without any test noticing.
- **Task 1.4's "after a GC, tail reports expired":** this is tested through `prune_events`, not `gc` (`test_event_prune.py:88`).
- **Test:** an ended-400-days task with rows in every rule's table and events; assert they are all gone and that `print_events` reports expired.

**M5. D3 (one source for each table's class): gc keeps its own copy of the class table.**
- **The copies:** `ROW_RULES` and `EVENT_RETENTION` (`lifecycle.py:227-248`), with `DELETE_ROWS` (`:520-525`) repeating four of the same rules, all restate `TABLE_CLASS` (`common/persistence/retention.py:32-50`).
- **The plan's Risks section:** it relies on "notes.md#d3 is the one source, and a test checks every `APP_TABLES` entry against it". No test references `ROW_RULES` or `DELETE_ROWS`.
- **Failure:** changing a table's class in `TABLE_CLASS` and the migration default leaves gc on the old lifetime. A table added to `TABLE_CLASS` by plans C or D gets no gc rule and never expires.
- **Fix direction:** derive `retention` from `TABLE_CLASS`, and add a test that every expiring table in `TABLE_CLASS` has a rule.

### Nits
- `lifecycle.py:644-654`, D4: the delete's first batch marks every upload reference of every task and inserts one fencing row per task in one transaction, with no 500 cap. The design needs all task locks in one batch, but "batches of at most 500 rows" does not hold for a large request.
- `refs.py:123-133` with `lifecycle.py:641-642`, D10 and R25: a deleted task is recognised only by a `delete:` mark on a reference. A task whose upload references were already gc-marked, or a pre-0007 task with no upload refs, gets no mark until step 5. If step 5 finds nothing live either, it never gets one, and a later late `put` makes a live reference. `delete_mark` could check the `deleted` attempt row instead.
- `removal.py:183-190`, `lifecycle.py:563`: a dry run holds every `FOR UPDATE` row lock, and for a delete the task locks, until the whole run rolls back. Concurrent `put`s and fenced writes block for the length of the dry run. It changes nothing, but it is not free for writers.
- `removal.py:229-232`: a dry run skips `finish_pending`, so its report leaves out the earlier runs' bucket deletes that the real run will do.
- `lifecycle.py:559-566`, R24: each TaskBusy retry re-reads the task list. A task that joined between tries is included, which is arguably still "when it began", since nothing had committed.
- `cli.py:281-290`, R7, R21 and D5: `workflow_status` is never run against real Temporal for gc or delete. All tests use fakes (`test_gc.py:40`, `test_request_delete.py:50`). The "queued = RUNNING" and "terminated = closed" mappings are unobserved, and a wrong namespace would read as "missing", which counts as closed for `--force`.
- Every removal test uses `MemoryBlobStore` as the bucket. `S3BlobStore.delete` of an already-deleted object, `list_objects` pagination and `LastModified` ageing on SeaweedFS are not observed. A stack test with `S3BlobStore` would cover them.
- `test_revive.py:67`, R22 scenario 1: "the next `gc` keeps it" is never checked. The test also removes the old task through a raw engine batch, not `delete_request`.
- `test_gc.py:121-129`, R7: for the running and 6-day tasks only the checkpoint row count is checked, not that their workspace blobs are still readable.
- `test_gc.py:113-118`, R6: references are not checked as marked; only rows and blobs are.
- `test_request_delete.py:158-170`, R10: checkpoint blobs (the workspace) are not checked as unreadable; only the checkpoint rows are.
- `test_blob_expired.py:26-38`: this test uses the stack database (`make_engine`) and leaves `blob_objects` rows marked with `bucket_deleted_at` null. The next stack `gc` will try to finish them.
- `lifecycle.py:734`, R11: a result whose real summary starts with `[deleted ` is never redacted. The marker format is encoded three times (`lifecycle.py:513`, `:516`, `:734`).
- `lifecycle.py:292`: the checkpoint holder key SQL repeats `refs.checkpoint_holder` (`refs.py:111-112`) and `REFERENCES` (`refs.py:60`). If the format drifts, gc deletes checkpoint rows but finds no refs, so their blobs are never freed.
- `lifecycle.py:116-121` and `table.py:226-235`: two copies of the "refs of events in [base, end)" query.
- `lifecycle.py:528-539` and `removal.py:65-85`: two near-identical session-lock context managers. `request_lock` writes the `hashtext` SQL inline instead of deriving it from `fence.REQUEST_LOCK`. `fence.py:26-27` declares `REQUEST_LOCK_KEY = 2` but hardcodes `2` in `REQUEST_LOCK`. `TRY_TASK_LOCK` (`removal.py:62`) repeats `TASK_LOCK`'s hashing (`fence.py:20`). If one copy changes, the delete's session lock stops conflicting with `end_task` and `record_task`.
- `removal.py:94-101`: `RefKey` duplicates `refs.Holder` plus `blob_key` (`refs.py:98-104`) and the key part of `refs.Reference` (`refs.py:215`).
- `removal.py:320-326` and `:345-350`: the placeholder `blob_objects` insert is written twice.
- `lifecycle.py:391-396` and `:610-615`: identical `drain` closures.
- Tests:
  - `tombstones` is defined three times: `test_request_delete.py:139`, `test_removal_engine.py:41`, `test_event_prune.py:72`.
  - `count`/`one` repeat `test_harness_activity.py:207`.
  - Event-publish builders are written three times: `test_gc.py:186`, `test_request_delete.py:108`, `test_event_prune.py:52`.
  - The fake Temporal is written three times: `test_gc.py:40`, `test_request_delete.py:50`, `test_removal_kills.py:46`.
  - All of these could live in `tests/support/lifecycle.py`.
- `plan.md:426`: the Phases table still shows phase 02 as "approved | 0/10" although all 10 tasks are checked in the phase file.
- `runbook.md` "Removing data" says a delete removes "every blob no other request holds". The code's rule is "no other live holder", which includes uploads with no request.

Files reviewed: `/home/geo/develop/praxismesh/common/persistence/removal.py`, `/home/geo/develop/praxismesh/orchestrator/lifecycle.py`, `/home/geo/develop/praxismesh/orchestrator/cli.py`, `/home/geo/develop/praxismesh/common/events/table.py`, `/home/geo/develop/praxismesh/common/persistence/repositories.py`, `/home/geo/develop/praxismesh/common/persistence/refs.py`, `/home/geo/develop/praxismesh/common/persistence/fence.py`, `/home/geo/develop/praxismesh/common/persistence/retention.py`, `/home/geo/develop/praxismesh/sample_mcp/server.py`, `/home/geo/develop/praxismesh/harness_activity/session_store.py`, and the tests under `/home/geo/develop/praxismesh/tests/integration/` (`test_gc.py`, `test_request_delete.py`, `test_removal_engine.py`, `test_removal_kills.py`, `test_event_prune.py`, `test_revive.py`, `test_blob_expired.py`) plus `/home/geo/develop/praxismesh/tests/support/lifecycle.py`.

# PR #53: T1 and T2 correction evidence

Implementation evidence, 2026-11-13. This is not an independent review or a
verification verdict. Phase 1 remains open (issue #44).

The preserved [targeted review](gate-followup-pr53.md) remains FAIL at
`60fe15d0fd755c391cbe79c0084f7def7b38c7db`. No review verdict or earlier demo
evidence was rewritten.

## Corrected implementation

New `code_sha`: `9472d20d3b5e5d7cee1542ffedf9c25335defadd`.

- T1: `test_activity_metrics_are_recorded` generates 20 input and 7 output
  tokens and checks both counter deltas. It compares checkpoint histogram sum
  deltas to independently packed expected workspaces (input only, then input
  plus an edit). The observed archive sizes were 110 and 139 bytes. Only the
  Activity module's clock is replaced; packing advances it by 0.25 and 0.5
  seconds, giving an exact expected duration sum delta of 0.75 seconds.
  Asyncio retains its real clock. Observation counts are also retained.
- T2: CLI submission log context includes `workflow_id=start.task_id`.
  The CLI test checks it along with request/task IDs, stderr JSON, and
  machine-readable stdout.
- Production metric code has no changes; all temporary mutations were restored.

## Mutation evidence

Each mutation was applied alone to `harness_activity/activity.py`, followed by:

```bash
UV_CACHE_DIR=/tmp/praxismesh-uv-cache uv run --env-file infra/.env pytest -m integration tests/integration/test_harness_activity.py::test_activity_metrics_are_recorded -q --tb=short
```

| Mutation | Observed failure | Result |
|---|---|---|
| Remove output-token `TOKENS` increment | Output sample `None` versus expected `0 + 7` | Exit 1; 1 failed |
| Replace `CHECKPOINT_BYTES.observe(len(data))` with `observe(0)` | Bytes sum `0.0` versus expected `0 + 110 + 139` | Exit 1; 1 failed |
| Replace `CHECKPOINT_SECONDS.observe(time.monotonic() - started)` with `observe(0)` | Duration sum `0.0` versus expected `0 + 0.75` | Exit 1; 1 failed |

After restoring every mutation, `git diff -- harness_activity/activity.py` was
empty. The full Activity integration file plus CLI test passed: 17 passed.

## Validation and handoff

Required dependency, Ruff lint/format, mypy, agent-sync, OpenSpec validation,
OpenSpec update dry-run, and whitespace checks passed. The OpenSpec validator
reported 5 passed; update reported no changes; 12 generated agent files were
up to date.

- `uv run pytest -q`: 157 passed, 91 deselected.
- `uv run --env-file infra/.env pytest -m 'integration or not integration' tests/integration/test_harness_activity.py tests/test_cli.py -q`: 17 passed.
- `make smoke`: 82 passed, 4 skipped (model endpoint not configured).

These runs used `UV_CACHE_DIR` under `/tmp`; tests needing sockets ran outside
the network-restricted sandbox against the existing local stack.

The next gate review must run in a fresh session at the new remote `code_sha`,
with the subsequent documentation-only commit proposed as `docs_sha`. Check that
`git diff <code_sha> <docs_sha> -- . ':!docs'` is empty. This evidence does not
close findings independently or authorize phase closure. After a review PASS,
Phase 1 light-tier verification must use those exact revisions.

## Handoff revalidation

A continuation on 2026-11-13 found the correction commits already present on
PR #53. The remote branch had advanced to
`c31d40aacdb74de7ca88479cecbf27552a06071f` through an existing merge of `main`,
adding the earlier `gate-followup.md` report. The local branch was fast-forwarded
to preserve that report and remote history. No merge was created in this
continuation. The diff from the `code_sha` above to that head contains only docs.

All three mutations were rerun separately with the command above, and each
failed at its intended assertion (exit 1, one failed test):

- Output-token recording removed: line 530, `None == (0 + 7)`.
- Checkpoint sizes zeroed: line 533, `0.0 == ((0 + 110) + 139)`.
- Checkpoint durations zeroed: line 537, `0.0 == (0 + 0.75)`.

Every mutation was restored, including on failure of the mutation driver;
`git diff --exit-code -- harness_activity/activity.py` passed afterwards.
The unit/replay suite again passed (157 passed, 91 deselected). Dependency sync,
Ruff lint/format, mypy, agent-sync and both OpenSpec checks again passed. The
agent-sync dependency download required network access; its successful rerun
reported all 12 generated files current.

After restoration, the full focused Activity/CLI run passed again (17 passed),
and `make smoke` passed (82 passed, 4 skips for an unconfigured model endpoint).
The preserved PR #53 review is byte-for-byte unchanged from `f160aea`.
The proposed `docs_sha` is the commit containing this appended revalidation;
its exact SHA is recorded externally in PR #53 to avoid self-reference. The
remote `code_sha` remains `9472d20d3b5e5d7cee1542ffedf9c25335defadd`.
Independent review and verification remain pending in a fresh session.

<!-- Verbatim subagent report (adr-review-0007-round-3, targeted follow-up at 19fc4e2); reviewers: fresh-subagent (design-reviewer); saved by the coordinator per docs/reviews/README.md rule 1 (copied unchanged). -->

# ADR review round 3: ADR-0007 (branch docs/62-close-dsh-plan, HEAD 19fc4e2)

Targeted follow-up under docs/reviews/README.md rule 6. Inputs read at HEAD: the ADR, `git diff HEAD~2..HEAD` for it, the round-2 report, harness_activity/activity.py, harness_activity/runner.py, harness_activity/dsh/{runner,gateway,ledger,session}.py, common/persistence/repositories.py, common/persistence/retention.py, orchestrator/activities.py, notes.md (#d10, #rollout), docs/adr/README.md and docs/templates/adr.md.

## Round-2 findings: status

| Round-2 finding | Status at HEAD | Evidence |
|---|---|---|
| M1: list of writes that skip the newer-attempt check incomplete; charge scope too narrow; no bound for `close_unknown` | Fixed | See below |
| Nit: "On the success path" | Fixed ("When the runner has not failed") | activity.py:399-401 (stale start raises `Superseded`, a plain `Exception`, runner.py:65, so it bypasses the `NonRetryableError` branch at activity.py:266); activity.py:487-490, :545-547, :570-571 |
| Nit: Links lacks notes.md#rollout for F106 | Fixed | notes.md:142 (`## Rollout`), :161-162 (F106) |

Check of the revised M1 bullet against the code:

- Completeness. The attempt-related DB writes reachable from harness_activity/ are `start` (fenced, repositories.py:140-147), `finish` with `fenced=True` at both call sites (activity.py:314-325, :558-569; repositories.py:188-220), `insert_fenced` (repositories.py:391-421; activity.py:465), `dispatch` (repositories.py:501-510; ledger.py:95), `record_refusal` (stated separately; repositories.py:234-257; activity.py:219, :235), `close_unfinished` (activity.py:271, :333; orchestrator/activities.py:130), `close_unknown` (via `_charge`, activity.py:353, called at :280, :309, :376) and `settle` (repositories.py:512-536; ledger.py:118; gateway.py:297, :308). `assert_current` and `newer_attempt_exists` only read. The three listed exceptions plus the separately stated refusal are therefore complete.
- `close_unfinished` bound: rows of the turn with `attempt <= :through_attempt` (repositories.py:296-312); both Activity callers pass `through_attempt=attempt` (activity.py:276, :338); task completion passes `turn=None` and no bound (orchestrator/activities.py:130). Matches.
- `close_unknown` bound: takes the lock (repositories.py:552) without the check; all statements limited to `turn = :turn AND attempt < :a` (repositories.py:550, :572); `:a` is the writer's attempt at open (activity.py:376) and `attempt + 1` on a failure (activity.py:280, :309), i.e. "through it". Runs only when `open_attempt` is set (activity.py:278, :308, :374), i.e. DSH. Matches, and "rewrite those usage columns" matches repositories.py:561-574 and notes.md:161-162.
- `settle` bound: `WHERE ... attempt = :a AND request_id = :r AND settled_at IS NULL`, no lock (repositories.py:521-527); a newer attempt's `close_unknown` sets `settled_at` on earlier unsettled rows (repositories.py:553-558), so a closed request stays closed. Matches.

## New findings

No Blocker or Major.

### Nits
- Consequences, "Bad, because a stale attempt can still upload artifact blobs that nothing references": a stale attempt also uploads the workspace and session blobs of a checkpoint whose fenced insert is then refused (activity.py:460-461 and session.py:84 run before `insert_fenced` at activity.py:465); these are `task`-class blobs (30-day lifetime, retention.py:17, not enforced until Phase 3A), so the statement understates the orphaned blobs; pre-existing text, not introduced by the revision.

The ADR still meets the ADR rules: front matter and sections follow docs/templates/adr.md, status `proposed`, the index row in docs/adr/README.md:18 matches the title, and every test named under Confirmation exists (test_persistence_phase1.py:190, :227, :252, :267, :290; test_harness_activity.py:580, :603; test_dsh_usage.py:274).

Verdict: pass

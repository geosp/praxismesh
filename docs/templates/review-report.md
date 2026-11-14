---
review: design            # design | implementation | verification
phase: <N, bootstrap, or general-<topic>>
change: <docs/plans/<plan>, or n/a>
rfc: <docs/rfcs/..., or n/a>
adrs: []
commit_sha: <full SHA reviewed; code_sha for implementation reviews and verification>
docs_sha: <as-built documentation revision; verification only, else n/a>
diff_base: <SHA, implementation reviews only; else n/a>
session: fresh            # verification in the light tier after impl-review: fresh (shared with implementation review, independence between them waived per §7.0)
date: <YYYY-MM-DD>
verdict: <PASS | FAIL>    # verification: pass | fail | blocked
reviewers:
  - { lens: <name>, status: <completed | not run> }
---

# <Design | Implementation> review / Verification: <change, RFC or phase title>

## Inputs

<Exact paths given to the reviewers, and the revision. Nothing else was provided.>

## Fresh reader paraphrase

<Design reviews only: the fresh reader's paraphrase, word for word. Delete for implementation reviews.>

## Checks (verification only)

| Check | Command or step | Expected | Observed | Result |
|---|---|---|---|---|
| | | | | pass / fail / blocked / not run |

## As-built claims (verification only)

| Claim (quoted) | Location | Status | Evidence |
|---|---|---|---|
| | | confirmed / contradicted / unverifiable | |

## Findings

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| F1 | Blocker / Major / Nit | | | | Fix / Contest | open / fixed in <sha> / contested: <reason> |

## Verdict

<PASS or FAIL (verification: pass, fail or blocked), with the rule that decided it (docs/reviews/README.md rule 5, or the verify-phase verdict rules).>

## Open items

<Anything still open after the final round.>

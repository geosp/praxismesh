---
review: design            # design | implementation
phase: <N, or general-<topic>>
change: <openspec/changes/<id>, or n/a>
rfc: <docs/rfcs/..., or n/a>
adrs: []
commit_sha: <full SHA reviewed; code_sha for implementation reviews>
diff_base: <SHA, implementation reviews only; else n/a>
session: fresh
date: <YYYY-MM-DD>
verdict: <PASS | FAIL>
reviewers:
  - { lens: <name>, status: <completed | not run> }
---

# <Design | Implementation> review: <change or RFC title>

## Inputs

<Exact paths given to the reviewers, and the revision. Nothing else was provided.>

## Fresh reader paraphrase

<Design reviews only: the fresh reader's paraphrase, word for word. Delete for implementation reviews.>

## Findings

| ID | Severity | Reviewer | Location | Scenario / evidence | Action | Resolution |
|---|---|---|---|---|---|---|
| F1 | Blocker / Major / Nit | | | | Fix / Contest | open / fixed in <sha> / contested: <reason> |

## Verdict

<PASS or FAIL, with the rule that decided it (see docs/reviews/README.md, rule 5).>

## Open items

<Anything still open after the final round.>
